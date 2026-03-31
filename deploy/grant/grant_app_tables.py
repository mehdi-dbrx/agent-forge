#!/usr/bin/env python3
"""Grant SELECT on all UC tables in schema to the app's service principal.

Usage:
  uv run python deploy/grant/grant_app_tables.py [APP_NAME] [--schema SCHEMA]

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
from tools.sql_executor import execute_statement, get_warehouse


def main() -> int:
    default_app = os.environ.get("DBX_APP_NAME", "").strip()
    default_schema = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()

    parser = argparse.ArgumentParser(description="Grant SELECT on UC tables to app service principal")
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

    print(f"Granting SELECT to app service principal: {app.service_principal_name} ({sp_id})")

    w_client, wh_id = get_warehouse()
    catalog, schema = args.schema.split(".", 1)

    tables = list(w.tables.list(catalog_name=catalog, schema_name=schema))
    if not tables:
        print(f"No tables in {catalog}.{schema}", file=sys.stderr)
        return 1

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

    for t in tables:
        full_name = f"`{catalog}`.`{schema}`.`{t.name}`"
        stmt = f"GRANT ALL PRIVILEGES ON TABLE {full_name} TO `{sp_id}`"
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
