#!/usr/bin/env python3
"""Grant CAN_USE on SQL warehouse to the app's service principal.

Usage:
  uv run python deploy/grant/authorize_warehouse_for_app.py [APP_NAME] [--warehouse-id ID]

  APP_NAME: Databricks app name (default: DBX_APP_NAME from .env.local)
  --warehouse-id: Warehouse ID (default: DATABRICKS_WAREHOUSE_ID from .env.local)
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local")

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import iam


def main() -> int:
    default_app = os.environ.get("DBX_APP_NAME", "").strip()
    default_wh = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()

    parser = argparse.ArgumentParser(description="Grant CAN_USE on SQL warehouse to app service principal")
    parser.add_argument("app_name", nargs="?", default=default_app, help="Databricks app name")
    parser.add_argument("--warehouse-id", default=default_wh, help="Warehouse ID")
    args = parser.parse_args()

    if not args.app_name:
        print("Error: app name required. Pass as argument or set DBX_APP_NAME in .env.local", file=sys.stderr)
        return 1

    wh_id = args.warehouse_id
    if not wh_id:
        w_tmp = WorkspaceClient()
        wh = next(iter(w_tmp.warehouses.list()), None)
        wh_id = str(getattr(wh, "id", None) or "") if wh else ""
    if not wh_id:
        print("Error: No warehouse ID. Set DATABRICKS_WAREHOUSE_ID or use --warehouse-id", file=sys.stderr)
        return 1

    w = WorkspaceClient()
    try:
        app = w.apps.get(name=args.app_name)
    except Exception as e:
        print(f"Error: Could not get app '{args.app_name}': {e}", file=sys.stderr)
        return 1

    sp_id = getattr(app, "service_principal_client_id", None) or getattr(app, "oauth2_app_client_id", None)
    sp_name = getattr(app, "service_principal_name", None)
    if not sp_id:
        print(f"Error: App '{args.app_name}' has no service_principal_client_id", file=sys.stderr)
        return 1

    print(f"Granting CAN_USE on warehouse {wh_id} to {sp_name or sp_id}")
    try:
        w.permissions.update(
            request_object_type="warehouses",
            request_object_id=wh_id,
            access_control_list=[
                iam.AccessControlRequest(
                    service_principal_name=sp_id,
                    permission_level=iam.PermissionLevel.CAN_USE,
                )
            ],
        )
        print("Done.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
