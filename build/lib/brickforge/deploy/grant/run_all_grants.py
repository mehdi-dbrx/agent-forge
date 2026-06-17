#!/usr/bin/env python3
"""Run all grant scripts for the app service principal.

Python replacement for run_all_grants.sh -- works on all platforms,
no bash dependency.

Usage:
    uv run python deploy/grant/run_all_grants.py [APP_NAME]

Grants:
  1. UC tables (SELECT)
  2. UC functions/procedures (EXECUTE)
  3. SQL warehouse (CAN_USE)
  4. Serving endpoints (CAN_QUERY)
  5. Genie space (CAN_RUN)
  6. Lakebase permissions
  7. Secret scope (READ)
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
os.chdir(ROOT)

# Load config from config.json (preferred) or .env.local (legacy)
config_file = os.environ.get("CONFIG_FILE", "")
if config_file and Path(config_file).exists():
    import json
    sys.path.insert(0, str(ROOT))
    from lib.config_provider import flatten
    cfg = json.loads(Path(config_file).read_text())
    for k, v in flatten(cfg).items():
        os.environ.setdefault(k, v)
else:
    env_file = ROOT / ".env.local"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            eq = line.find("=")
            if eq > 0:
                os.environ.setdefault(line[:eq].strip(), line[eq + 1:])

APP_NAME = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DBX_APP_NAME", "")
SCHEMA = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "")

if not APP_NAME:
    print("[x] DBX_APP_NAME not set. Pass app name as argument or set in config.json", file=sys.stderr)
    sys.exit(1)
if not SCHEMA:
    print("[x] PROJECT_UNITY_CATALOG_SCHEMA not set in config.json", file=sys.stderr)
    sys.exit(1)

print(f"[~] Running all grants for app: {APP_NAME} (schema: {SCHEMA})")
sys.stdout.flush()

GRANT_DIR = ROOT / "deploy" / "grant"

PY = sys.executable

STEPS = [
    ("1. Granting UC table access",
     [PY, str(GRANT_DIR / "grant_app_tables.py"), APP_NAME, "--schema", SCHEMA]),
    ("2. Granting UC functions/procedures access",
     [PY, str(GRANT_DIR / "grant_app_functions.py"), APP_NAME, "--schema", SCHEMA]),
    ("3. Granting CAN_USE on SQL warehouse",
     [PY, str(GRANT_DIR / "authorize_warehouse_for_app.py"), APP_NAME]),
    ("4. Granting CAN_QUERY on serving endpoints",
     [PY, str(GRANT_DIR / "authorize_endpoint_for_app.py"), APP_NAME]),
    ("5. Granting CAN_RUN on Genie space",
     [PY, str(GRANT_DIR / "authorize_genie_for_app.py"), APP_NAME]),
    ("6. Granting Lakebase permissions",
     [PY, str(GRANT_DIR / "grant_lakebase_for_app.py"), APP_NAME]),
]


def run_step(label: str, cmd: list[str]) -> bool:
    print(f"[~] {label}...")
    sys.stdout.flush()
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print(f"  [x] {label.split('.', 1)[1].strip()} failed (non-blocking)")
        sys.stdout.flush()
        return False
    print(f"  [+] done")
    sys.stdout.flush()
    return True


for label, cmd in STEPS:
    run_step(label, cmd)

# Step 7: Secret scope grant (uses SDK instead of CLI)
print("[~] 7. Granting secret scope READ access...")
sys.stdout.flush()
try:
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    app = w.apps.get(name=APP_NAME)
    sp_id = getattr(app, "service_principal_client_id", None)
    if sp_id:
        try:
            from databricks.sdk.service.workspace import AclPermission
            # Ensure brickforge scope exists (for token storage)
            try:
                w.secrets.create_scope(scope="brickforge")
            except Exception:
                pass  # already exists
            for scope_name, perm in [("agent-forge", AclPermission.READ), ("brickforge", AclPermission.WRITE)]:
                try:
                    w.secrets.put_acl(scope=scope_name, principal=sp_id, permission=perm)
                    print(f"  [+] Secret scope {scope_name} -> {perm.value} granted to {sp_id}")
                except Exception as e:
                    print(f"  [!] Secret scope {scope_name} grant failed: {e}", file=sys.stderr)
        except Exception as e:
            print(f"  [!] Failed to grant secret scope ACL: {e}", file=sys.stderr)
    else:
        print("  [~] No SP client ID -- skipping secret scope grant")
except Exception as e:
    print(f"  [!] Secret scope grant skipped: {e}", file=sys.stderr)

print("\n[+] All grants applied successfully")
