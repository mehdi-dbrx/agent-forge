"""Environment utilities: buildSubEnv, checkTokenExpiry, detectCloud, error parsing, logging."""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime

from brickforge.lib.config_provider import ConfigProvider

# ── Server logger ─────────────────────────────────────────────────────────────

def _get_server_logger() -> logging.Logger:
    """Get or create the server file logger (writes to ~/.brickforge/brickforge_<date>.log)."""
    logger = logging.getLogger("brickforge.server")
    if not logger.handlers:
        from brickforge import LOG_FILE
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger


def log_error(endpoint: str, error: str, full_traceback: str = "") -> None:
    """Log an error to ~/.brickforge/brickforge_*.log and print to terminal."""
    logger = _get_server_logger()
    logger.error(f"{endpoint}: {error}")
    if full_traceback:
        logger.debug(f"{endpoint} traceback:\n{full_traceback}")
    # Also print to terminal for live monitoring
    print(f"[error] {endpoint}: {error[:150]}")


# ── Error parsing ────────────────────────────────────────────────────────────

def parse_subprocess_error(stderr: str, stdout: str = "") -> str:
    """Parse subprocess output and return a clean user-facing error message.
    Full error is logged to server.log."""
    raw = stderr or stdout or ""

    # Log the full error
    if raw.strip():
        log_error("subprocess", raw[:200], raw)

    LOG_HINT = " (check ~/.brickforge/ for full logs)"

    # IP ACL blocked
    m = re.search(r"Source IP address: ([\d.]+) is blocked by Databricks IP ACL", raw)
    if m:
        ip = m.group(1)
        return f"Your IP ({ip}) is blocked by the workspace IP Access List. Connect via VPN, run from an authorized network, or ask your workspace admin to whitelist {ip}." + LOG_HINT

    # Permission denied (generic)
    if "PermissionDenied" in raw and "IP ACL" not in raw:
        return "Permission denied. Check your token has the required permissions for this operation." + LOG_HINT

    # Auth failures
    if "401" in raw and ("Unauthorized" in raw or "unauthorized" in raw):
        return "Token invalid or expired. Re-authenticate via bridge-forge." + LOG_HINT

    # Token parse error
    if "unable to parse response" in raw:
        return "Authentication error. Your token may be expired. Re-authenticate via bridge-forge." + LOG_HINT

    # SSL
    if "CERTIFICATE_VERIFY_FAILED" in raw or "SSL" in raw:
        return "SSL certificate error. Check your VPN or proxy settings." + LOG_HINT

    # DNS
    if "nodename nor servname" in raw or "Name or service not known" in raw:
        host_match = re.search(r"https?://([^\s/]+)", raw)
        host = host_match.group(1) if host_match else "the workspace"
        return f"Cannot reach {host}. Check the URL and your network connection." + LOG_HINT

    # App limit reached
    if "maximum limit" in raw and "apps" in raw:
        m = re.search(r"reached the maximum limit of (\d+) apps", raw)
        limit = m.group(1) if m else "max"
        return f"Workspace has reached the {limit} app limit. Delete unused apps from the workspace or use a different workspace."

    # Catalog/schema not found
    if "does not exist" in raw:
        m = re.search(r"(Catalog|Schema|Table|Function)\s+'([^']+)'\s+does not exist", raw)
        if m:
            return f"{m.group(1)} '{m.group(2)}' does not exist."

    # Generic traceback -- hide it, point to logs
    if "Traceback (most recent call last)" in raw:
        lines = raw.strip().split("\n")
        last_line = lines[-1].strip() if lines else "Unknown error"
        return f"{last_line}" + LOG_HINT

    # Short enough to show as-is
    if len(raw) < 200 and "Traceback" not in raw:
        return raw.strip()

    return "An error occurred" + LOG_HINT


def detect_cloud(host: str) -> str | None:
    if not host:
        return None
    if ".azuredatabricks.net" in host:
        return "azure"
    if ".gcp.databricks.com" in host:
        return "gcp"
    if ".cloud.databricks.com" in host:
        return "aws"
    return None


def build_sub_env(config: ConfigProvider, extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build a clean subprocess environment: config values + os.environ, minus auth conflicts."""
    from brickforge import PACKAGE_ROOT, PROJECT_ROOT, USER_DIR

    env = dict(os.environ)
    # Flatten structured config to flat env vars
    env.update(config.flatten())
    if extra_env:
        env.update(extra_env)
    # Force unbuffered output in all subprocesses (critical for SSE streaming)
    env["PYTHONUNBUFFERED"] = "1"
    # PYTHONPATH: ensure subprocess can import from brickforge/ (tools, data, agent, etc.)
    env["PYTHONPATH"] = str(PACKAGE_ROOT)
    # BRICKFORGE_ROOT: absolute path to brickforge/ for file I/O in scripts
    env["BRICKFORGE_ROOT"] = str(PACKAGE_ROOT)
    # CONFIG_FILE: absolute path to config.json (for scripts that write back)
    if (PROJECT_ROOT / "pyproject.toml").exists():
        env["CONFIG_FILE"] = str(PROJECT_ROOT / "config.json")  # editable: repo root
    else:
        env["CONFIG_FILE"] = str(USER_DIR / "config.json")  # pip: ~/.brickforge/
    # PROJECT_DIR: artifact root for active project (prompts, SQL, CSVs scoped per project)
    if hasattr(config, 'project_dir') and config.project_dir:
        env["PROJECT_DIR"] = str(config.project_dir)
    # If PAT token is set, remove SP OAuth vars to avoid SDK auth conflict
    if env.get("DATABRICKS_TOKEN") and env.get("DATABRICKS_CLIENT_ID"):
        env.pop("DATABRICKS_CLIENT_ID", None)
        env.pop("DATABRICKS_CLIENT_SECRET", None)
    # Remove CLI profile and databrickscfg interference -- BrickForge uses PAT auth only
    env.pop("DATABRICKS_CONFIG_PROFILE", None)
    env.pop("DATABRICKS_CLI_UPSTREAM", None)
    env.pop("DATABRICKS_CLI_UPSTREAM_VERSION", None)
    env["DATABRICKS_CONFIG_FILE"] = ""  # prevent SDK from reading ~/.databrickscfg
    # Remove stale venv
    env.pop("VIRTUAL_ENV", None)
    return env


def check_token_expiry(config: ConfigProvider) -> str | None:
    """Check if OAuth JWT token is expired. Auto-refresh if possible. Returns error message or None."""
    token = config.get("DATABRICKS_TOKEN") or os.environ.get("DATABRICKS_TOKEN", "")
    if not token or not token.startswith("eyJ"):
        return None  # PATs (dapi...) don't expire via JWT

    try:
        payload_b64 = token.split(".")[1]
        # Add padding
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp")
        if not exp or time.time() <= exp:
            return None  # not expired

        # Token is expired -- try to refresh silently
        refresh_token = config.get("DATABRICKS_REFRESH_TOKEN") or ""
        token_endpoint = config.get("DATABRICKS_TOKEN_ENDPOINT") or ""
        if refresh_token and token_endpoint:
            try:
                import urllib.request
                import urllib.parse
                data = urllib.parse.urlencode({
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": "databricks-cli",
                }).encode()
                req = urllib.request.Request(token_endpoint, data=data, method="POST")
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
                with urllib.request.urlopen(req, timeout=10) as r:
                    resp = json.loads(r.read())
                if resp.get("access_token"):
                    config.set_many({"DATABRICKS_TOKEN": resp["access_token"]})
                    os.environ["DATABRICKS_TOKEN"] = resp["access_token"]
                    if resp.get("refresh_token"):
                        config.set_many({"DATABRICKS_REFRESH_TOKEN": resp["refresh_token"]})
                    print("[auth] Token auto-refreshed silently")
                    return None
            except Exception as e:
                print(f"[auth] Token refresh failed: {e}")

        ago = round((time.time() - exp) / 60)
        return f"Token expired {ago} minute{'s' if ago != 1 else ''} ago. Re-authenticate via \"connect via terminal\" or enter a new token."
    except Exception:
        return None  # not a valid JWT, skip
