"""Bridge auth routes: nonce, receive, status, script."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from brickforge import PROJECT_ROOT, PACKAGE_ROOT
from brickforge.lib.env_utils import detect_cloud

router = APIRouter()

# ── State ─────────────────────────────────────────────────────────────────────

_bridge_nonces: dict[str, dict] = {}  # nonce_id -> {value, expires}
_bridge_state: dict = {"status": "waiting"}

NONCE_TTL = 5 * 60  # 5 minutes


def _clean_expired_nonces():
    now = time.time()
    expired = [k for k, v in _bridge_nonces.items() if v["expires"] < now * 1000]
    for k in expired:
        del _bridge_nonces[k]


def _get_config():
    from brickforge.server import config
    return config


def _get_forge_mode():
    from brickforge.server import FORGE_MODE
    return FORGE_MODE


def _get_app_cloud():
    return detect_cloud(os.environ.get("DATABRICKS_HOST", ""))


# ── Nonce ─────────────────────────────────────────────────────────────────────

@router.get("/api/auth/bridge-nonce")
async def bridge_nonce():
    global _bridge_state
    _clean_expired_nonces()
    nonce_id = secrets.token_hex(16)
    nonce_value = secrets.token_hex(32)
    _bridge_nonces[nonce_id] = {"value": nonce_value, "expires": (time.time() + NONCE_TTL) * 1000}
    _bridge_state = {"status": "waiting"}
    config = _get_config()
    ws_default = config.get("workspace.host") or ""
    print(f"[bridge] nonce generated: id={nonce_id[:8]}... TTL=5min, active nonces={len(_bridge_nonces)}")
    return {"nonce_id": nonce_id, "nonce": nonce_value, "ws_default": ws_default}


# ── Receive ───────────────────────────────────────────────────────────────────

@router.post("/api/auth/bridge-receive")
async def bridge_receive(request: Request):
    global _bridge_state
    _clean_expired_nonces()
    body = await request.json()
    ciphertext = body.get("ciphertext", "")
    nonce_id = body.get("nonce_id", "")
    host = body.get("host", "")
    user = body.get("user", "")

    print(f"[bridge] receive: nonce_id={nonce_id[:8]}... host={host or '?'} user={user or '?'} ciphertext_len={len(ciphertext)}")

    if not ciphertext or not nonce_id:
        print("[bridge] receive REJECTED: missing ciphertext or nonce_id")
        return JSONResponse({"error": "ciphertext and nonce_id required"}, status_code=400)

    nonce = _bridge_nonces.get(nonce_id)
    if not nonce:
        print(f"[bridge] receive REJECTED: nonce not found. active={len(_bridge_nonces)}")
        return JSONResponse({"error": "invalid or expired nonce"}, status_code=403)

    try:
        # Decrypt using openssl subprocess (same as bridge script)
        result = subprocess.run(
            ["openssl", "enc", "-aes-256-cbc", "-d", "-a", "-A", "-pass", f"pass:{nonce['value']}", "-pbkdf2"],
            input=ciphertext.encode(), capture_output=True, timeout=5,
        )
        if result.returncode != 0:
            print(f"[bridge] openssl decrypt failed: {result.stderr.decode()[:100]}")
            return JSONResponse({"error": "decryption failed"}, status_code=400)

        token = result.stdout.decode("utf-8")
        print(f"[bridge] decrypted OK: payload_len={len(token)}, starts_with={token[:6]}...")

        # Parse: PAT bundle, JWT bundle, or plain token
        final_token = ""
        refresh_token = ""
        token_endpoint = ""
        is_pat = False

        try:
            bundle = json.loads(token)
            if bundle.get("pat"):
                final_token = bundle["pat"]
                is_pat = True
                print(f"[bridge] PAT received: {final_token[:12]}...")
            else:
                final_token = bundle.get("access_token", "")
                refresh_token = bundle.get("refresh_token", "")
                token_endpoint = bundle.get("token_endpoint", "")
                print(f"[bridge] JWT bundle: access_len={len(final_token)}, refresh_len={len(refresh_token)}")
        except (json.JSONDecodeError, TypeError):
            final_token = token
            print(f"[bridge] plain token: len={len(final_token)}")

        if not final_token or len(final_token) < 5:
            print(f"[bridge] REJECTED: token too short (len={len(final_token)})")
            return JSONResponse({"error": "received empty or invalid token"}, status_code=400)

        del _bridge_nonces[nonce_id]  # single use

        # Cross-cloud detection (before overwriting host)
        app_cloud = _get_app_cloud()
        target_cloud = detect_cloud(host)
        cross_cloud_warning = ""
        if app_cloud and target_cloud and app_cloud != target_cloud:
            cross_cloud_warning = f"The target workspace ({target_cloud}) is on a different cloud than this Setup App ({app_cloud}). The Setup App's IP may not be in the workspace's IP Access List. If API calls fail, ask your workspace admin to whitelist the Setup App's IP."
            print(f"[bridge] CROSS-CLOUD WARNING: app={app_cloud}, target={target_cloud}")

        # Store in config
        config = _get_config()
        updates: dict[str, str] = {}
        if host:
            updates["DATABRICKS_HOST"] = host
        updates["DATABRICKS_TOKEN"] = final_token

        if is_pat:
            config.disable_many(["DATABRICKS_REFRESH_TOKEN", "DATABRICKS_TOKEN_ENDPOINT"])
            print("[bridge] PAT mode -- cleared refresh token + token endpoint")
        else:
            if refresh_token:
                updates["DATABRICKS_REFRESH_TOKEN"] = refresh_token
            if token_endpoint:
                updates["DATABRICKS_TOKEN_ENDPOINT"] = token_endpoint

        # Clear conflicting auth
        for k in ["DATABRICKS_CONFIG_PROFILE", "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET"]:
            config.disable(k)

        config.set_many(updates)  # triggers _sync_env() -- updates os.environ

        # Persist token + auto-save workspace
        if host and final_token:
            try:
                from brickforge.lib.token_store import get_token_store
                get_token_store().set(host, final_token)
                # Auto-save to .workspaces
                import json as _json
                from brickforge import USER_DIR
                _ws_file = USER_DIR / ".workspaces"
                _ws_list = _json.loads(_ws_file.read_text()) if _ws_file.exists() else []
                _ws_list = [w for w in _ws_list if w.get("host") != host]
                _label = host.replace("https://", "").replace("http://", "").split(".")[0]
                _ws_list.append({"host": host, "label": _label, "last_used": time.strftime("%Y-%m-%d")})
                _ws_file.parent.mkdir(parents=True, exist_ok=True)
                _ws_file.write_text(_json.dumps(_ws_list, indent=2) + "\n")
                print(f"[bridge] token + workspace saved for {host}")
            except Exception as e:
                print(f"[bridge] token store save failed: {e}")

        _bridge_state = {"status": "connected", "host": host, "user": user, "time": int(time.time() * 1000), "warning": cross_cloud_warning}
        print(f"[bridge] state -> connected (host={host}, user={user})")
        return {"ok": True, "warning": cross_cloud_warning or None}

    except Exception as e:
        print(f"[bridge] error: {e}")
        return JSONResponse({"error": f"decryption failed: {e}"}, status_code=400)


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/api/auth/bridge-status")
async def bridge_status():
    return _bridge_state


# ── Script ────────────────────────────────────────────────────────────────────

@router.get("/api/auth/bridge-script")
async def bridge_script(request: Request, nonce: str = ""):
    if not nonce:
        return Response('#!/bin/bash\necho ""\necho "  [x] Invalid link. Go back to the Setup App and click Connect again."\necho ""\n', media_type="text/plain")

    nonce_data = _bridge_nonces.get(nonce)
    if not nonce_data:
        return Response('#!/bin/bash\necho ""\necho "  [x] Session expired. Go back to the Setup App and click Connect again."\necho ""\n', media_type="text/plain")

    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host_header = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    app_url = f"{proto}://{host_header}"
    print(f"[bridge] script download: nonce={nonce[:8]}... appUrl={app_url}")

    config = _get_config()
    current_host = config.get("workspace.host") or ""

    # Look for connect.sh: first in repo (editable), then in package (pip installed)
    script_path = PACKAGE_ROOT / "scripts" / "connect.sh"
    if not script_path.exists():
        script_path = Path(__file__).resolve().parent.parent / "static" / "connect.sh"
    try:
        template = script_path.read_text()
    except FileNotFoundError:
        return Response("connect.sh not found", status_code=500)

    import re
    script = template
    script = re.sub(r'^APP_URL=.*$', f'APP_URL="{app_url}"', script, flags=re.MULTILINE)
    script = re.sub(r'^NONCE=.*$', f'NONCE="{nonce_data["value"]}"', script, flags=re.MULTILINE)
    script = re.sub(r'^NONCE_ID=.*$', f'NONCE_ID="{nonce}"', script, flags=re.MULTILINE)
    script = re.sub(r'^WS_DEFAULT=.*$', f'WS_DEFAULT="{current_host}"', script, flags=re.MULTILINE)

    return Response(
        content=script,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=brickforge-connect.command"},
    )


# ── Cloud ─────────────────────────────────────────────────────────────────────

@router.get("/api/setup/cloud")
async def setup_cloud():
    return {"cloud": _get_app_cloud()}


# ── Bridge Mode + Inline Auth ─────────────────────────────────────────────────

@router.get("/api/auth/bridge-mode")
async def bridge_mode():
    is_local = not os.environ.get("DATABRICKS_APP_PORT")
    return {"mode": "local" if is_local else "deployed"}


@router.post("/api/auth/bridge-inline")
async def bridge_inline(request: Request):
    """Inline OAuth flow for local mode. SSE streaming."""
    from brickforge.lib.bridge_oauth import (
        verify_token, discover_oauth, setup_pkce, build_auth_url,
        open_browser, wait_for_callback, exchange_token, get_user_name,
        create_pat, store_token, _flow_running,
    )
    from brickforge.lib.sse import sse_line, sse_done
    import brickforge.lib.bridge_oauth as _oauth_mod

    body = await request.json()
    ws_host = body.get("host", "").strip().rstrip("/")
    if not ws_host:
        return JSONResponse({"error": "host required"}, status_code=400)
    if not ws_host.startswith("http"):
        ws_host = "https://" + ws_host

    if _oauth_mod._flow_running:
        return JSONResponse({"error": "OAuth flow already in progress"}, status_code=409)

    config = _get_config()

    async def generate():
        _oauth_mod._flow_running = True
        try:
            # Step 0: Check keyring
            from brickforge.lib.token_store import get_token_store
            store = get_token_store()
            existing = store.get(ws_host)
            if existing:
                yield sse_line("[~] Found saved token, verifying...\n")
                if verify_token(ws_host, existing):
                    store_token(ws_host, existing, config)
                    user = get_user_name(ws_host, existing)
                    yield sse_line(f"[+] Reconnected to {ws_host} as {user}\n")
                    yield sse_done(True)
                    return
                else:
                    yield sse_line("[~] Saved token expired, starting OAuth...\n")

            # Step 1: Discovery
            yield sse_line(f"[~] Discovering OAuth endpoints for {ws_host}...\n")
            try:
                auth_endpoint, token_endpoint = discover_oauth(ws_host)
                yield sse_line("[+] OAuth endpoints found\n")
            except Exception as e:
                yield sse_line(f"[x] OAuth discovery failed: {e}\n")
                yield sse_done(False, 1)
                return

            # Step 2: PKCE + local server
            yield sse_line("[~] Preparing authentication...\n")
            verifier, challenge, state, port = setup_pkce()
            auth_url = build_auth_url(auth_endpoint, challenge, state, port)

            # Step 3: Open browser
            yield sse_line("[~] Opening browser for SSO authentication...\n")
            open_browser(auth_url)

            # Step 4: Wait for callback
            yield sse_line("[~] Waiting for SSO authentication...\n")
            try:
                code = await wait_for_callback(port, state, timeout=120)
                yield sse_line("[+] Authentication successful\n")
            except TimeoutError:
                yield sse_line("[x] Timed out waiting for authentication (120s)\n")
                yield sse_done(False, 1)
                return
            except Exception as e:
                yield sse_line(f"[x] Callback error: {e}\n")
                yield sse_done(False, 1)
                return

            # Step 5: Exchange token
            yield sse_line("[~] Exchanging auth code for token...\n")
            try:
                access_token, refresh_token = exchange_token(token_endpoint, code, verifier, port)
                yield sse_line(f"[+] Token acquired ({len(access_token)} chars)\n")
            except Exception as e:
                yield sse_line(f"[x] Token exchange failed: {e}\n")
                yield sse_done(False, 1)
                return

            # Step 6: User info
            user = get_user_name(ws_host, access_token)
            yield sse_line(f"[+] Authenticated as {user}\n")

            # Step 7: Create PAT
            yield sse_line("[~] Creating 7-day PAT...\n")
            pat = create_pat(ws_host, access_token)
            final_token = pat or access_token
            if pat:
                yield sse_line(f"[+] PAT created ({pat[:12]}...)\n")
            else:
                yield sse_line("[~] PAT creation failed, using access token\n")

            # Step 8: Store
            yield sse_line("[~] Saving credentials...\n")
            store_token(ws_host, final_token, config)
            yield sse_line(f"[+] Connected to {ws_host}\n")
            yield sse_done(True)

        except Exception as e:
            yield sse_line(f"[x] {e}\n")
            yield sse_done(False, 1)
        finally:
            _oauth_mod._flow_running = False

    from fastapi.responses import StreamingResponse
    return StreamingResponse(generate(), media_type="text/event-stream")
