#!/usr/bin/env python3
"""Deploy an Agent App to Databricks from a .forge project config.

Called by the Setup App backend. Generates app.yaml + databricks.yml from
the project config, bundles agent code into a zip, uploads to workspace,
and deploys via the Databricks Apps API.

Usage:
    python deploy/deploy_agent_app.py --config /path/to/config.json

The config.json is a flat key-value dict (same format as .env.local / ConfigProvider.toEnvDict()).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import tarfile
import zipfile
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.apps import App, AppDeployment
from databricks.sdk.service.workspace import ImportFormat

ROOT = Path(__file__).resolve().parents[1]

# ── Agent App file manifest ──────────────────────────────────────────────────

AGENT_APP_DIRS = [
    "agent",
    "tools",
    "lib",
    "data/demo",
    "data/init",
    "data/gen",
    "data/py",
    "conf",
    "eval",
]

# Dirs to pre-compress as tar.gz (faster snapshot, unzipped at startup)
AGENT_APP_TARBALL_DIRS = [
    "app/client/dist",
    "app/server/dist",
]

EXCLUDE_PATTERNS = {
    "__pycache__", ".mypy_cache", ".DS_Store", "node_modules",
    ".git", ".claude", "stash", "edu", "doc", "visual",
}


def _should_exclude(rel_path: Path) -> bool:
    parts = set(rel_path.parts)
    if parts & EXCLUDE_PATTERNS:
        return True
    if rel_path.suffix == ".pyc":
        return True
    return False


# ── app.yaml generation ──────────────────────────────────────────────────────

AGENT_APP_YAML_TEMPLATE = """\
command: ["bash", "start.sh"]

env:
  - name: MLFLOW_TRACKING_URI
    value: "databricks"
  - name: MLFLOW_REGISTRY_URI
    value: "databricks-uc"
  - name: API_PROXY
    value: "http://localhost:8000/invocations"
  - name: CHAT_APP_PORT
    value: "3000"
  - name: TASK_EVENTS_URL
    value: "http://127.0.0.1:3000"
  - name: CHAT_PROXY_TIMEOUT_SECONDS
    value: "300"
"""


def generate_app_yaml(config: dict) -> str:
    """Generate Agent App app.yaml -- runtime constants only.

    User config lives in config.json (shipped as file in bundle).
    Agent reads config.json at boot via start_server.py.
    """
    return AGENT_APP_YAML_TEMPLATE


# ── databricks.yml generation ────────────────────────────────────────────────

DATABRICKS_YML_TEMPLATE = """\
bundle:
  name: {app_name}

resources:
  apps:
    agent_app:
      name: "{app_name}"
      description: "BrickForge Agent Application"
      source_code_path: ./

      resources:
        - name: 'sql_warehouse'
          sql_warehouse:
            id: '{warehouse_id}'
            permission: 'CAN_USE'
{genie_resources}{endpoint_resources}
targets:
  default:
    mode: production
    default: true
"""


def generate_databricks_yml(config: dict) -> str:
    """Generate databricks.yml from structured config dict."""
    # Support both structured (config.json) and flat (legacy) formats
    if "workspace" in config:
        # Structured config.json
        app_name = (config.get("app") or {}).get("name", "brickforge-agent")
        warehouse_id = (config.get("workspace") or {}).get("warehouse_id", "PLACEHOLDER")
        genie_ids = (config.get("tools") or {}).get("genie_spaces", [])
        endpoint = (config.get("model") or {}).get("endpoint", "")
    else:
        # Legacy flat dict
        app_name = config.get("DBX_APP_NAME", "brickforge-agent")
        warehouse_id = config.get("DATABRICKS_WAREHOUSE_ID", "PLACEHOLDER")
        raw_genie = config.get("PROJECT_GENIE_SPACES", "")
        genie_ids = [s.strip() for s in raw_genie.split(",") if s.strip()] if raw_genie else []
        endpoint = config.get("AGENT_MODEL", "")

    genie_lines = ""
    for i, space_id in enumerate(genie_ids, 1):
        genie_lines += f"""\
        - name: 'genie_space_{i}'
          genie_space:
            space_id: '{space_id}'
            permission: 'CAN_RUN'
"""

    endpoint_lines = ""
    if endpoint and not endpoint.startswith("http"):
        endpoint_lines += f"""\
        - name: 'serving_endpoint'
          serving_endpoint:
            name: '{endpoint}'
            permission: 'CAN_QUERY'
"""

    return DATABRICKS_YML_TEMPLATE.format(
        app_name=app_name,
        warehouse_id=warehouse_id,
        genie_resources=genie_lines,
        endpoint_resources=endpoint_lines,
    )


# ── Bundle zip ───────────────────────────────────────────────────────────────

def _make_tarball(dir_path: Path, arcname: str) -> bytes:
    """Create a tar.gz of a directory, returning the bytes."""
    def _filter_xattr(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        # Strip macOS extended attributes that cause warnings on Linux
        info.pax_headers = {k: v for k, v in (info.pax_headers or {}).items() if not k.startswith("LIBARCHIVE.")}
        return info
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.add(str(dir_path), arcname=arcname, filter=_filter_xattr)
    return buf.getvalue()


def build_agent_bundle(config: dict) -> bytes:
    """Build a zip of the Agent App source + generated configs."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add agent app directories
        for dir_name in AGENT_APP_DIRS:
            dir_path = ROOT / dir_name
            if not dir_path.exists():
                continue
            for file_path in dir_path.rglob("*"):
                if file_path.is_dir():
                    continue
                rel = file_path.relative_to(ROOT)
                if _should_exclude(rel):
                    continue
                zf.write(file_path, str(rel))

        # Add pre-compressed dist dirs as tar.gz (faster snapshot)
        for dir_name in AGENT_APP_TARBALL_DIRS:
            parent = str(Path(dir_name).parent)  # "app/client"
            leaf = Path(dir_name).name            # "dist"
            tar_name = f"{parent}/{leaf}.tar.gz"   # "app/client/dist.tar.gz"
            pre_built = ROOT / tar_name
            if pre_built.exists():
                # Use pre-built tar.gz
                tar_bytes = pre_built.read_bytes()
            else:
                # Compress on-the-fly
                dir_path = ROOT / dir_name
                if not dir_path.exists():
                    continue
                tar_bytes = _make_tarball(dir_path, leaf)
            zf.writestr(tar_name, tar_bytes)
            print(f"  [+] {dir_name}/ -> {tar_name} ({len(tar_bytes)//1024}KB)")

        # Add pyproject.toml (copied into brickforge/ at build time)
        pyproject = ROOT / "pyproject.toml"
        if pyproject.exists():
            zf.write(str(pyproject), "pyproject.toml")
        else:
            # Editable install: pyproject.toml is at repo root
            pyproject_alt = ROOT.parent / "pyproject.toml"
            if pyproject_alt.exists():
                zf.write(str(pyproject_alt), "pyproject.toml")

        # Bundle pinned requirements.txt (pre-generated at build time)
        req_file = ROOT / "requirements.txt"
        if not req_file.exists():
            req_file = ROOT.parent / "requirements.txt"
        if req_file.exists():
            zf.write(str(req_file), "requirements.txt")
            print(f"  [+] requirements.txt (pinned)")
        else:
            # Fallback: generate from pyproject.toml (unpinned, slower resolve)
            _pyproject_path = ROOT / "pyproject.toml" if (ROOT / "pyproject.toml").exists() else ROOT.parent / "pyproject.toml"
            if _pyproject_path.exists():
                try:
                    import tomllib
                except ModuleNotFoundError:
                    import tomli as tomllib  # Python < 3.11
                with open(_pyproject_path, "rb") as pf:
                    deps = tomllib.load(pf).get("project", {}).get("dependencies", [])
                zf.writestr("requirements.txt", "\n".join(deps) + "\n")
                print(f"  [!] requirements.txt (unpinned -- slow install)")

        # Overlay project-scoped artifacts (prompts, gen data, conf)
        project_dir = os.environ.get("PROJECT_DIR", "").strip()
        if project_dir:
            pd = Path(project_dir)
            overlay_map = [
                (pd / "prompt", "conf/prompt"),
                (pd / "gen", "data/gen"),
                (pd / "conf", "conf"),
            ]
            for src_dir, bundle_prefix in overlay_map:
                if not src_dir.exists():
                    continue
                for file_path in src_dir.rglob("*"):
                    if file_path.is_dir() or file_path.name.startswith("."):
                        continue
                    rel = file_path.relative_to(src_dir)
                    arc_name = f"{bundle_prefix}/{rel}"
                    zf.writestr(arc_name, file_path.read_bytes())
            print(f"  [+] Project artifacts overlaid from {pd.name}/")

        # Ship config.json as a file (agent reads it at boot)
        zf.writestr("config.json", json.dumps(config, indent=2) + "\n")

        # Generate and add app.yaml (minimal -- no user env vars)
        app_yaml = generate_app_yaml(config)
        zf.writestr("app.yaml", app_yaml)

        # Generate and add databricks.yml (resource permissions only)
        dbx_yml = generate_databricks_yml(config)
        zf.writestr("databricks.yml", dbx_yml)

    return buf.getvalue()


# ── Deploy ───────────────────────────────────────────────────────────────────

def deploy(config: dict) -> dict:
    """Deploy the Agent App to Databricks.

    Returns dict with deployment info (app_name, url, deployment_id).
    """
    w = WorkspaceClient()
    me = w.current_user.me()
    # Support structured (config.json) or flat (legacy) config
    if "app" in config:
        app_name = (config.get("app") or {}).get("name", "brickforge-agent")
    else:
        app_name = config.get("DBX_APP_NAME", "brickforge-agent")

    print(f"[~] Building agent bundle...")
    bundle_zip = build_agent_bundle(config)
    print(f"[+] Bundle: {len(bundle_zip) / 1024 / 1024:.1f} MB")

    # Upload zip to workspace
    workspace_dir = f"/Workspace/Users/{me.user_name}/{app_name}"
    zip_path = f"{workspace_dir}/_bundle.dat"

    print(f"[~] Uploading bundle to {zip_path}...")
    # Clean workspace dir and recreate
    try:
        w.workspace.delete(workspace_dir, recursive=True)
    except Exception:
        pass
    w.workspace.mkdirs(workspace_dir)
    b64 = base64.b64encode(bundle_zip).decode()
    w.workspace.import_(path=zip_path, content=b64, format=ImportFormat.RAW, overwrite=True)
    print(f"[+] Bundle uploaded ({len(bundle_zip) // 1024}KB)")

    # Upload a startup script that unzips + starts
    startup_script = """\
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
# Flatten config.json to shell exports so ALL processes (Python, Node workers) inherit them
python lib/export_config_env.py
. /tmp/_env_exports.sh
rm -f /tmp/_env_exports.sh
exec python -c "from agent.start_server import main; main()"
"""
    def _upload_text(path: str, content: str):
        b64_content = base64.b64encode(content.encode()).decode()
        w.workspace.import_(path=path, content=b64_content, format=ImportFormat.RAW, overwrite=True)

    _upload_text(f"{workspace_dir}/start.sh", startup_script)
    _upload_text(f"{workspace_dir}/app.yaml", generate_app_yaml(config))
    print(f"[+] app.yaml + start.sh + config.json uploaded")

    # Create or get the app
    print(f"[~] Creating/checking app '{app_name}'...")
    try:
        app_info = w.apps.get(app_name)
        print(f"[+] App exists: {app_info.url}")
    except Exception:
        waiter = w.apps.create(app=App(name=app_name, description="BrickForge Agent Application"))
        print(f"[~] App creating, waiting for compute...")
        app_info = waiter.result()
        print(f"[+] App created: {app_name}")

    # Deploy
    print(f"[~] Deploying from {workspace_dir}...")
    dep_waiter = w.apps.deploy(app_name, app_deployment=AppDeployment(source_code_path=workspace_dir))
    dep_id = dep_waiter.deployment_id
    print(f"[+] Deployment started: {dep_id}")

    # Wait for deployment
    print(f"[~] Waiting for deployment...")
    try:
        dep_result = dep_waiter.result()
        state = dep_result.status.state.value if dep_result.status else "UNKNOWN"
        if state == "SUCCEEDED":
            print(f"[+] Deployment SUCCEEDED")
        else:
            print(f"[~] Deployment state: {state}")
    except Exception as e:
        print(f"[x] Deployment failed: {e}")

    app_info = w.apps.get(app_name)
    url = getattr(app_info, "url", "")
    print(f"[+] Agent App: {url}")

    return {
        "app_name": app_name,
        "url": url,
        "deployment_id": dep_id,
        "workspace_dir": workspace_dir,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy Agent App from config")
    parser.add_argument("--config", required=True, help="Path to config JSON (key-value dict)")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    result = deploy(config)
    print(json.dumps(result, indent=2))
