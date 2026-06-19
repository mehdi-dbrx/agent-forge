"""GitHub integration -- device flow auth, repo creation, code push.

Uses GitHub OAuth Device Flow for auth (no redirects needed).
client_id is from the BrickForge GitHub OAuth App.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request

_log = logging.getLogger(__name__)

CLIENT_ID = "Ov23liqaGLy9v7sWlVsM"


def start_device_flow() -> dict:
    """Start GitHub device flow. Returns {user_code, device_code, verification_uri, interval}."""
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "scope": "repo",
    }).encode()
    req = urllib.request.Request(
        "https://github.com/login/device/code",
        data=data,
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def poll_device_flow(device_code: str, interval: int = 5, timeout: int = 300) -> str | None:
    """Poll GitHub for device flow completion. Returns access_token or None on timeout."""
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }).encode()

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(interval)
        req = urllib.request.Request(
            "https://github.com/login/oauth/access_token",
            data=data,
            headers={"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = json.loads(r.read())
            if "access_token" in resp:
                return resp["access_token"]
            error = resp.get("error", "")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval = resp.get("interval", interval + 5)
                continue
            if error in ("expired_token", "access_denied"):
                return None
        except Exception:
            continue
    return None


def get_user(token: str) -> str:
    """Get the authenticated GitHub username."""
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()).get("login", "unknown")


def create_repo(token: str, name: str, private: bool = True) -> str:
    """Create a GitHub repo. Returns clone_url. If exists, returns existing URL."""
    username = get_user(token)

    # Check if repo exists
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{username}/{name}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            repo = json.loads(r.read())
        return repo["clone_url"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise

    # Create
    req = urllib.request.Request(
        "https://api.github.com/user/repos",
        data=json.dumps({"name": name, "private": private, "auto_init": False}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        repo = json.loads(r.read())
    return repo["clone_url"]


def push_bundle(token: str, repo_url: str, bundle_zip: bytes, message: str = "BrickForge: project update") -> bool:
    """Extract bundle to temp dir, post-process for standalone use, and push via git CLI."""
    import os
    import shutil
    import subprocess
    import tarfile
    import tempfile
    import zipfile
    import io

    # Check git is available
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("[x] git CLI not found -- install git to push code")
        return False

    tmpdir = tempfile.mkdtemp(prefix="brickforge-push-")
    try:
        # Extract bundle
        zf = zipfile.ZipFile(io.BytesIO(bundle_zip))
        zf.extractall(tmpdir)
        zf.close()

        # ── Post-process for standalone repo ──────────────────────────────

        _postprocess_for_standalone(tmpdir)

        # ── Git push ─────────────────────────────────────────────────────

        # Insert token into URL for auth
        auth_url = repo_url.replace("https://", f"https://{token}@")

        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"

        cmds = [
            ["git", "init"],
            ["git", "checkout", "-b", "main"],
            ["git", "add", "."],
            ["git", "commit", "-m", message],
            ["git", "remote", "add", "origin", auth_url],
            ["git", "push", "-u", "origin", "main", "--force"],
        ]
        for cmd in cmds:
            label = " ".join(cmd[:3]) if "token" not in " ".join(cmd) else f"{cmd[0]} {cmd[1]} ..."
            r = subprocess.run(cmd, cwd=tmpdir, capture_output=True, text=True, env=env)
            if r.returncode != 0:
                stderr = r.stderr.strip()
                stderr = stderr.replace(token, "***")
                if "nothing to commit" in r.stdout:
                    print("[+] Nothing to commit (already up to date)")
                    return True
                print(f"[x] {label}: {stderr}")
                return False
        print("[+] Pushed to GitHub")
        return True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Standalone repo post-processing ─────────────────────────────────────────

# Setup App-only files that crash in standalone repos (from brickforge.* imports)
_STRIP_FROM_PUSH = [
    "lib/bridge_oauth.py",
    "lib/env_utils.py",
    "lib/sse.py",
    "lib/graph_builder.py",
    "lib/token_store.py",
    "lib/github_client.py",
    "lib/config_json.py",
]


def _postprocess_for_standalone(tmpdir: str) -> None:
    """Transform the deploy bundle into a standalone, cloneable project."""
    import os
    import tarfile

    # 1. Extract tarballs (frontend assets)
    for tgz in ["app/client/dist.tar.gz", "app/server/dist.tar.gz"]:
        tgz_path = os.path.join(tmpdir, tgz)
        if os.path.exists(tgz_path):
            with tarfile.open(tgz_path) as tf:
                tf.extractall(os.path.dirname(tgz_path))
            os.remove(tgz_path)

    # 2. Strip Setup App-only lib/ files
    for rel in _STRIP_FROM_PUSH:
        path = os.path.join(tmpdir, rel)
        if os.path.exists(path):
            os.remove(path)

    # 3. Read config for generated files
    config_path = os.path.join(tmpdir, "config.json")
    config = {}
    if os.path.exists(config_path):
        config = json.loads(open(config_path).read())

    project_name = (config.get("app") or {}).get("name") or "agent-app"
    host = (config.get("workspace") or {}).get("host") or ""
    schema = (config.get("workspace") or {}).get("unity_catalog_schema") or ""
    model = (config.get("model") or {}).get("endpoint") or ""

    # 4. Generate start_local.sh
    _write(tmpdir, "start_local.sh", _generate_start_local())
    os.chmod(os.path.join(tmpdir, "start_local.sh"), 0o755)

    # 5. Generate start.sh (Databricks Apps boot script)
    _write(tmpdir, "start.sh", _generate_start_sh())
    os.chmod(os.path.join(tmpdir, "start.sh"), 0o755)

    # 6. Rewrite pyproject.toml
    _write(tmpdir, "pyproject.toml", _generate_pyproject(project_name))

    # 7. Generate README.md
    _write(tmpdir, "README.md", _generate_readme(project_name, host, schema, model))

    # 8. Generate .gitignore
    _write(tmpdir, ".gitignore", _generate_gitignore())


def _write(tmpdir: str, name: str, content: str) -> None:
    import os
    with open(os.path.join(tmpdir, name), "w") as f:
        f.write(content)


def _generate_start_local() -> str:
    return '''\
#!/bin/bash
set -e
cd "$(dirname "$0")"

# ── Pre-flight checks ──────────────────────────────────────────────────────

# 1. Python version check (>= 3.11 required)
PYTHON=""
for cmd in python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    echo "[x] Python 3.11+ is required but not found."
    echo "    Install it from https://www.python.org/downloads/"
    exit 1
fi
echo "[+] Using $PYTHON ($ver)"

# 2. Node.js check (required for chat UI)
if ! command -v node &>/dev/null; then
    echo "[x] Node.js is required for the chat UI but not found."
    echo "    Install it from https://nodejs.org/ (v20+ recommended)"
    exit 1
fi
NODE_VER=$(node -v 2>/dev/null)
echo "[+] Node.js $NODE_VER"

# 3. Port checks (8000 = agent server, 3000 = chat UI)
for PORT in 8000 3000; do
    PID=$(lsof -ti :$PORT 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "[!] Port $PORT is in use (PID $PID)"
        read -p "    Kill it? (Y/n): " KILL
        if [ "$KILL" != "n" ] && [ "$KILL" != "N" ]; then
            kill -9 $PID 2>/dev/null
            sleep 1
            echo "[+] Killed process on port $PORT"
        else
            if [ "$PORT" = "8000" ]; then
                echo "[~] Will try next available port for agent server"
                export AGENT_PORT=8001
            else
                echo "[~] Will try next available port for chat UI"
                export CHAT_APP_PORT=3001
            fi
        fi
    fi
done

# ── Auth ───────────────────────────────────────────────────────────────────

# 4. Read host from config.json
HOST=$($PYTHON -c "import json; print(json.load(open('config.json')).get('workspace',{}).get('host',''))" 2>/dev/null)
if [ -z "$HOST" ]; then
    echo "[x] No workspace host found in config.json"
    echo "    Set workspace.host in config.json and re-run."
    exit 1
fi
echo "[~] Workspace: $HOST"

# 5. Resolve token
if [ -z "$DATABRICKS_TOKEN" ]; then
    # Check if a CLI profile exists for this host
    PROFILE=$($PYTHON -c "
import configparser, os
cfg = configparser.ConfigParser()
cfg.read(os.path.expanduser('~/.databrickscfg'))
host = '$HOST'.rstrip('/')
for s in cfg.sections():
    if cfg.get(s, 'host', fallback='').rstrip('/') == host:
        print(s)
        break
" 2>/dev/null)

    if [ -n "$PROFILE" ]; then
        # Profile exists -- get a short-lived token from the OAuth session
        echo "[~] Found CLI profile: $PROFILE"
        TOKEN=$(databricks auth token --host "$HOST" -o json 2>/dev/null | $PYTHON -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
        if [ -n "$TOKEN" ]; then
            export DATABRICKS_TOKEN="$TOKEN"
            echo "[+] Token loaded from CLI profile"
        else
            echo "[!] CLI profile expired. Re-authenticating..."
            databricks auth login --host "$HOST"
            TOKEN=$(databricks auth token --host "$HOST" -o json 2>/dev/null | $PYTHON -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
            if [ -n "$TOKEN" ]; then
                export DATABRICKS_TOKEN="$TOKEN"
                echo "[+] Token refreshed"
            else
                echo "[x] Auth failed. Try: export DATABRICKS_TOKEN=<your-token>"
                exit 1
            fi
        fi
    else
        # No profile -- offer to create one
        echo ""
        echo "[!] No authentication configured for $HOST"
        echo ""
        echo "    Options:"
        echo "    1) Create a CLI profile (recommended -- opens browser for OAuth)"
        echo "    2) Paste a Personal Access Token manually"
        echo ""
        read -p "    Choose (1/2): " AUTH_CHOICE

        if [ "$AUTH_CHOICE" = "1" ]; then
            # Check if Databricks CLI is installed
            if ! command -v databricks &>/dev/null; then
                echo ""
                echo "[x] Databricks CLI not found."
                echo "    Install: brew install databricks/tap/databricks"
                echo "    Or:      curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh"
                echo ""
                read -p "    Try installing now? (Y/n): " INSTALL
                if [ "$INSTALL" != "n" ] && [ "$INSTALL" != "N" ]; then
                    curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh
                    if ! command -v databricks &>/dev/null; then
                        echo "[x] Installation failed. Install manually and re-run."
                        exit 1
                    fi
                else
                    echo "[x] Cannot continue without auth. Exiting."
                    exit 1
                fi
            fi
            echo "[~] Creating CLI profile for $HOST..."
            echo "    A browser window will open for authentication."
            echo ""
            databricks auth login --host "$HOST"
            # Get token from new profile
            TOKEN=$(databricks auth token --host "$HOST" -o json 2>/dev/null | $PYTHON -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
            if [ -n "$TOKEN" ]; then
                export DATABRICKS_TOKEN="$TOKEN"
                echo "[+] Profile created and token loaded"
            else
                echo "[x] Profile created but token retrieval failed."
                echo "    Try: export DATABRICKS_TOKEN=<your-token> && ./start_local.sh"
                exit 1
            fi
        elif [ "$AUTH_CHOICE" = "2" ]; then
            echo -n "    Token: "
            read -s TOKEN
            echo ""
            if [ -z "$TOKEN" ]; then
                echo "[x] Empty token. Exiting."
                exit 1
            fi
            export DATABRICKS_TOKEN="$TOKEN"
        else
            echo "[x] Invalid choice. Exiting."
            exit 1
        fi
    fi
fi

# 6. Validate token
echo -n "[~] Verifying connection..."
HTTP_CODE=$($PYTHON -c "
import urllib.request, os
req = urllib.request.Request('$HOST/api/2.0/preview/scim/v2/Me',
    headers={'Authorization': 'Bearer ' + os.environ['DATABRICKS_TOKEN']})
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        print(r.status)
except Exception as e:
    print(getattr(e, 'code', 0))
" 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    echo " ok"
else
    echo " failed (HTTP $HTTP_CODE)"
    echo "[x] Token is invalid or expired for $HOST"
    echo "    Re-run this script to re-authenticate."
    exit 1
fi

# ── Venv + deps ────────────────────────────────────────────────────────────

if [ ! -d .venv ]; then
    echo "[~] Creating virtual environment..."
    $PYTHON -m venv .venv
    . .venv/bin/activate
    echo "[~] Installing dependencies (this may take a few minutes)..."
    pip install -q -r requirements.txt
else
    echo "[~] Activating virtual environment..."
    . .venv/bin/activate
fi

# ── Start ──────────────────────────────────────────────────────────────────

# Core paths
export PYTHONPATH="$(pwd)"
export CONFIG_FILE="$(pwd)/config.json"

# Flatten config.json to env vars (needed for Node.js chat UI)
python lib/export_config_env.py
. /tmp/_env_exports.sh
rm -f /tmp/_env_exports.sh

# Chat UI env vars (normally injected by Databricks Apps runtime via app.yaml)
export API_PROXY="${API_PROXY:-http://localhost:8000/invocations}"
export CHAT_APP_PORT="${CHAT_APP_PORT:-3000}"
export TASK_EVENTS_URL="${TASK_EVENTS_URL:-http://127.0.0.1:${CHAT_APP_PORT}}"
export CHAT_PROXY_TIMEOUT_SECONDS="${CHAT_PROXY_TIMEOUT_SECONDS:-300}"

# MLflow (optional -- enables tracing to Databricks)
export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-databricks}"
export MLFLOW_REGISTRY_URI="${MLFLOW_REGISTRY_URI:-databricks-uc}"

echo ""
echo "[+] Starting agent server..."
echo "    Chat UI: http://localhost:${CHAT_APP_PORT}"
echo ""
exec python -c "from agent.start_server import main; main()"
'''


def _generate_start_sh() -> str:
    return '''\
#!/bin/bash
set -ex
echo "[start.sh] pwd=$(pwd) ls=$(ls -la)"
cd /app/python/source_code
echo "[start.sh] source_code contents: $(ls)"
if [ -f _bundle.dat ]; then
    echo "[1/4] Extracting bundle..."
    unzip -o _bundle.dat -d .
    rm _bundle.dat
    echo "[1/4] done -- contents: $(ls)"
fi
echo "[2/4] Unpacking dist archives..."
for tgz in app/client/dist.tar.gz app/server/dist.tar.gz; do
    if [ -f "$tgz" ]; then
        tar xzf "$tgz" -C "$(dirname "$tgz")"
        rm "$tgz"
    fi
done
echo "[2/4] done"
if [ ! -d .venv ]; then
    echo "[3/4] Installing Python deps (first deploy)..."
    python -m venv .venv
    . .venv/bin/activate
    if [ -f requirements.txt ]; then
        pip install -r requirements.txt 2>&1
    fi
else
    echo "[3/4] Reusing existing venv..."
    . .venv/bin/activate
    if [ -f requirements.txt ]; then
        pip install -q --upgrade -r requirements.txt 2>&1
    fi
fi
echo "[3/4] done"
echo "[4/4] starting agent..."
export PYTHONPATH="$(pwd)"
export CONFIG_FILE="$(pwd)/config.json"
python lib/export_config_env.py
. /tmp/_env_exports.sh
rm -f /tmp/_env_exports.sh
exec python -c "from agent.start_server import main; main()"
'''


def _generate_pyproject(project_name: str) -> str:
    safe_name = project_name.replace(" ", "-").lower()
    return f'''\
[project]
name = "{safe_name}"
version = "1.0.0"
requires-python = ">=3.11"
'''


def _generate_readme(project_name: str, host: str, schema: str, model: str) -> str:
    return f'''\
# {project_name}

Databricks AI agent application.

## Quick Start

```bash
./start_local.sh
```

The script checks prerequisites (Python 3.11+, Node.js), handles authentication,
installs dependencies, and starts the server.

Chat UI will be available at http://localhost:3000

## Configuration

All settings are in `config.json`:
- Workspace: {host}
- Schema: {schema}
- Model: {model}

## Notes

- Chat history is stored in memory and lost on restart (no database in local mode)
- Authentication uses a short-lived OAuth token resolved at startup -- re-run the script if it expires

## Deploy to Databricks Apps

```bash
pip install brickforge
brickforge
```
'''


def _generate_gitignore() -> str:
    return '''\
.venv/
__pycache__/
*.pyc
.env.local
.DS_Store
brickforge.egg-info/
'''
