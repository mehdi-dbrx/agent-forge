"""Inline OAuth PKCE flow for local bridge auth.

Extracted from scripts/connect.sh embedded Python. Runs the full flow
in-process: discovery, PKCE, browser open, callback capture, token
exchange, PAT creation. No encryption needed (token stays in-process).
"""
from __future__ import annotations

import asyncio
import base64
import os
import datetime
import hashlib
import http.server
import json
import logging
import secrets
import socket
import ssl
import urllib.parse
import urllib.request
import webbrowser
from typing import Any

_log = logging.getLogger(__name__)
_ctx = ssl.create_default_context()

# Guard against concurrent flows
_flow_running = False


def verify_token(host: str, token: str) -> bool:
    """Quick check: is this token still valid for the given workspace?"""
    try:
        req = urllib.request.Request(
            f"{host}/api/2.0/preview/scim/v2/Me",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=5, context=_ctx) as r:
            data = json.loads(r.read())
        return bool(data.get("userName"))
    except Exception:
        return False


def discover_oauth(host: str) -> tuple[str, str]:
    """Discover OAuth authorization + token endpoints for a workspace."""
    url = f"{host}/oidc/.well-known/oauth-authorization-server"
    with urllib.request.urlopen(url, timeout=10, context=_ctx) as r:
        endpoints = json.loads(r.read())
    return endpoints["authorization_endpoint"], endpoints["token_endpoint"]


def setup_pkce() -> tuple[str, str, str, int]:
    """Generate PKCE verifier/challenge, state, and find a free port.
    Returns (verifier, challenge, state, port)."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("localhost", 0))
    port = sock.getsockname()[1]
    sock.close()

    return verifier, challenge, state, port


def build_auth_url(auth_endpoint: str, challenge: str, state: str, port: int) -> str:
    """Build the OAuth authorization URL."""
    redirect_uri = f"http://localhost:{port}"
    return (
        f"{auth_endpoint}"
        f"?client_id=databricks-cli"
        f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
        f"&response_type=code"
        f"&scope=all-apis+offline_access"
        f"&state={state}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
    )


def open_browser(auth_url: str) -> None:
    """Open the OAuth URL in the default browser."""
    webbrowser.open(auth_url)


async def wait_for_callback(port: int, state: str, timeout: int = 120) -> str:
    """Start a temporary HTTP server and wait for the OAuth callback.
    Returns the authorization code. Raises TimeoutError if no callback."""
    received: dict[str, str] = {}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if qs.get("state", [None])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch")
                return
            received["code"] = qs.get("code", [None])[0]
            # Redirect to the Setup App's branded success page
            app_url = os.environ.get("BRICKFORGE_APP_URL", "http://localhost:9000")
            self.send_response(302)
            self.send_header("Location", f"{app_url}/#bridge-success")
            self.end_headers()

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("localhost", port), CallbackHandler)
    server.timeout = timeout

    await asyncio.to_thread(server.handle_request)
    server.server_close()

    if "code" not in received or not received["code"]:
        raise TimeoutError("OAuth callback not received within timeout")
    return received["code"]


def exchange_token(
    token_endpoint: str, code: str, verifier: str, port: int
) -> tuple[str, str]:
    """Exchange authorization code for access token + refresh token."""
    redirect_uri = f"http://localhost:{port}"
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": "databricks-cli",
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }).encode()
    req = urllib.request.Request(token_endpoint, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15, context=_ctx) as r:
        resp = json.loads(r.read())
    return resp["access_token"], resp.get("refresh_token", "")


def get_user_name(host: str, access_token: str) -> str:
    """Fetch the authenticated user's display name."""
    try:
        req = urllib.request.Request(
            f"{host}/api/2.0/preview/scim/v2/Me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10, context=_ctx) as r:
            return json.loads(r.read()).get("userName", "unknown")
    except Exception:
        return "unknown"


def create_pat(host: str, access_token: str) -> str:
    """Create a 7-day PAT on the workspace. Revokes existing brickforge PATs first.
    Returns the PAT token value, or empty string on failure."""
    today = datetime.date.today().strftime("%Y%m%d")
    pat_name = f"brickforge-7days-{today}"

    # Revoke existing brickforge PATs
    try:
        list_req = urllib.request.Request(
            f"{host}/api/2.0/token/list",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(list_req, timeout=10, context=_ctx) as r:
            tokens = json.loads(r.read()).get("token_infos", [])
        now = int(datetime.datetime.now().timestamp() * 1000)
        for t in tokens:
            comment = t.get("comment", "")
            expiry = t.get("expiry_time", 0)
            if comment.startswith("brickforge-") and expiry > now:
                try:
                    del_req = urllib.request.Request(
                        f"{host}/api/2.0/token/delete",
                        data=json.dumps({"token_id": t["token_id"]}).encode(),
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(del_req, timeout=10, context=_ctx)
                except Exception:
                    pass
    except Exception:
        pass

    # Create new PAT
    try:
        req = urllib.request.Request(
            f"{host}/api/2.0/token/create",
            data=json.dumps({"lifetime_seconds": 604800, "comment": pat_name}).encode(),
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10, context=_ctx) as r:
            return json.loads(r.read()).get("token_value", "")
    except Exception as e:
        _log.warning("PAT creation failed: %s", e)
        return ""


def store_token(host: str, token: str, config: Any) -> None:
    """Store token in config (memory), keyring, and .workspaces."""
    import os
    import time

    # Config (memory only -- _save strips it from disk)
    config.set_many({"DATABRICKS_HOST": host, "DATABRICKS_TOKEN": token})

    # Keyring / secrets scope
    try:
        from brickforge.lib.token_store import get_token_store
        get_token_store().set(host, token)
    except Exception:
        pass

    # .workspaces file
    try:
        from brickforge import USER_DIR
        ws_file = USER_DIR / ".workspaces"
        ws_list = json.loads(ws_file.read_text()) if ws_file.exists() else []
        ws_list = [w for w in ws_list if w.get("host") != host]
        label = host.replace("https://", "").replace("http://", "").split(".")[0]
        ws_list.append({"host": host, "label": label, "last_used": time.strftime("%Y-%m-%d")})
        ws_file.parent.mkdir(parents=True, exist_ok=True)
        ws_file.write_text(json.dumps(ws_list, indent=2) + "\n")
    except Exception:
        pass
