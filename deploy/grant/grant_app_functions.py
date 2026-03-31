#!/usr/bin/env python3
"""Grant EXECUTE on all UC functions and procedures in schema to the app's service principal.

Usage:
  uv run python deploy/grant/grant_app_functions.py [APP_NAME] [--schema SCHEMA]

  APP_NAME: Databricks app name (default: DBX_APP_NAME from .env.local)
  --schema: Catalog.schema (default: PROJECT_UNITY_CATALOG_SCHEMA from .env.local)
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local")

from databricks.sdk import WorkspaceClient
from tools.sql_executor import execute_statement, execute_query, get_warehouse


def main() -> int:
    default_app = os.environ.get("DBX_APP_NAME", "").strip()
    default_schema = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()

    parser = argparse.ArgumentParser(description="Grant EXECUTE on UC functions/procedures to app service principal")
    parser.add_argument("app_name", nargs="?", default=default_app, help="Databricks app name")
    parser.add_argument("--schema", default=default_schema, help="Catalog.schema")
    args = parser.parse_args()

    if not args.app_name:
        print("Error: app name required. Pass as argument or set DBX_APP_NAME in .env.local", file=sys.stderr)
        return 1
    if not args.schema or "." not in args.schema:
        print("Error: --schema required (catalog.schema). Set PROJECT_UNITY_CATALOG_SCHEMA in .env.local", file=sys.stderr)
        return 1

    w = WorkspaceClient()
    try:
        app = w.apps.get(name=args.app_name)
    except Exception as e:
        print(f"Error: Could not get app '{args.app_name}': {e}", file=sys.stderr)
        return 1

    sp_id = getattr(app, "service_principal_client_id", None) or getattr(app, "oauth2_app_client_id", None)
    if not sp_id:
        print(f"Error: App '{args.app_name}' has no service_principal_client_id", file=sys.stderr)
        return 1

    print(f"Granting EXECUTE to app service principal: {app.service_principal_name} ({sp_id})")

    w_client, wh_id = get_warehouse()
    catalog, schema = args.schema.split(".", 1)

    routines_sql = f"""
    SELECT routine_name, routine_type
    FROM `{catalog}`.information_schema.routines
    WHERE routine_schema = '{schema}'
    ORDER BY routine_type, routine_name
    """
    try:
        columns, rows = execute_query(w_client, wh_id, routines_sql)
    except Exception as e:
        print(f"Error: Could not list routines in {catalog}.{schema}: {e}", file=sys.stderr)
        return 1

    name_idx = columns.index("routine_name") if "routine_name" in columns else 0
    type_idx = columns.index("routine_type") if "routine_type" in columns else 1
    routines = [(row[name_idx], row[type_idx]) for row in rows]

    if not routines:
        print(f"No functions or procedures in {catalog}.{schema}")
        return 0

    for stmt in [
        f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{sp_id}`",
        f"GRANT USE SCHEMA ON SCHEMA `{catalog}`.`{schema}` TO `{sp_id}`",
    ]:
        try:
            execute_statement(w_client, wh_id, stmt)
            print(f"  [+] {stmt}")
        except Exception as e:
            print(f"  [-] {stmt} - {e}", file=sys.stderr)
            return 1

    for routine_name, routine_type in routines:
        obj_type = "FUNCTION" if routine_type == "FUNCTION" else "PROCEDURE"
        full_name = f"`{catalog}`.`{schema}`.`{routine_name}`"
        stmt = f"GRANT EXECUTE ON {obj_type} {full_name} TO `{sp_id}`"
        try:
            execute_statement(w_client, wh_id, stmt)
            print(f"  [+] {stmt}")
        except Exception as e:
            print(f"  [-] {stmt} - {e}", file=sys.stderr)
            return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
