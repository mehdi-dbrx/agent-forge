#!/usr/bin/env python3
"""Grant CAN_RUN on Genie space(s) to the app's service principal.

Two mechanisms (both applied):
  1. Direct API grant: permissions API call so the SP can access Genie immediately
  2. databricks.yml resource declaration: for DAB-based deploys (if ever used)

Usage:
  python deploy/grant/authorize_genie_for_app.py [APP_NAME]

  APP_NAME: Databricks app name (default: DBX_APP_NAME env var)
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
YML = ROOT / "databricks.yml"


from databricks.sdk import WorkspaceClient
from databricks.sdk.service import iam


def _get_genie_space_ids() -> list[str]:
    """Collect Genie space IDs from env and databricks.yml."""
    ids = set()

    # From env (comma-separated)
    raw = os.environ.get("PROJECT_GENIE_SPACES", "").strip()
    if raw:
        for sid in raw.split(","):
            sid = sid.strip()
            if sid:
                ids.add(sid)

    # From databricks.yml (already declared resources)
    if YML.exists():
        content = YML.read_text()
        for m in re.finditer(r"genie_space:\s*\n\s*space_id:\s*'([^']*)'", content):
            sid = m.group(1)
            if sid and sid != "PLACEHOLDER_GENIE_ID":
                ids.add(sid)

    return sorted(ids)


def _grant_via_api(w: WorkspaceClient, app_name: str, space_ids: list[str]) -> int:
    """Grant CAN_RUN on each Genie space to the app SP via permissions API."""
    try:
        app = w.apps.get(name=app_name)
    except Exception as e:
        print(f"Error: Could not get app '{app_name}': {e}", file=sys.stderr)
        return 1

    sp_id = getattr(app, "service_principal_client_id", None) or getattr(app, "oauth2_app_client_id", None)
    sp_name = getattr(app, "service_principal_name", None)
    if not sp_id:
        print(f"Error: App '{app_name}' has no service_principal_client_id", file=sys.stderr)
        return 1

    ok = True
    for space_id in space_ids:
        print(f"Granting CAN_RUN on Genie space {space_id} to {sp_name or sp_id}")
        try:
            w.permissions.update(
                request_object_type="genie",
                request_object_id=space_id,
                access_control_list=[
                    iam.AccessControlRequest(
                        service_principal_name=sp_id,
                        permission_level=iam.PermissionLevel.CAN_RUN,
                    )
                ],
            )
            print(f"  [+] Granted via API")
        except Exception as e:
            print(f"  [!] API grant failed: {e}", file=sys.stderr)
            ok = False

    return 0 if ok else 1


def _update_databricks_yml(space_ids: list[str]) -> None:
    """Ensure Genie space resources are declared in databricks.yml."""
    if not YML.exists():
        print(f"  [~] {YML} not found — skipping YAML update")
        return

    content = YML.read_text()

    for i, space_id in enumerate(space_ids, 1):
        if space_id in content:
            print(f"  [~] genie_space ({space_id}) already in databricks.yml")
            continue

        block = f"""        - name: 'genie_space_{i}'
          genie_space:
            space_id: '{space_id}'
            permission: 'CAN_RUN'
"""
        m2 = re.search(
            r"(        - name: 'sql_warehouse'\n          sql_warehouse:\n            id: '[^']*'\n            permission: 'CAN_USE'\n)",
            content,
        )
        if m2:
            content = content.replace(m2.group(1), m2.group(1).rstrip() + "\n" + block)
            print(f"  [+] Added genie_space ({space_id}) to databricks.yml")
        else:
            print(f"  [~] Could not find insertion point in databricks.yml — skipping YAML for {space_id}")

    YML.write_text(content)


def main() -> int:
    default_app = os.environ.get("DBX_APP_NAME", "").strip()

    parser = argparse.ArgumentParser(description="Grant CAN_RUN on Genie space to app SP")
    parser.add_argument("app_name", nargs="?", default=default_app, help="Databricks app name")
    args = parser.parse_args()

    space_ids = _get_genie_space_ids()
    if not space_ids:
        print("No Genie space configured — skipping (optional)", file=sys.stderr)
        return 0

    if not args.app_name:
        print("Error: app name required. Pass as argument or set DBX_APP_NAME", file=sys.stderr)
        return 1

    w = WorkspaceClient()

    # 1. Direct API grant (the one that actually matters for SDK-based deploys)
    result = _grant_via_api(w, args.app_name, space_ids)

    # 2. Also update databricks.yml (for completeness / DAB compat)
    _update_databricks_yml(space_ids)

    return result


if __name__ == "__main__":
    sys.exit(main())
