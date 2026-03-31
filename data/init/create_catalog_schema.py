#!/usr/bin/env python3
"""Create Databricks Unity Catalog and schema if not exists. Reads AMADEUS_UNITY_CATALOG_SCHEMA from .env.local."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env.local", override=True)


def main() -> None:
    from databricks.sdk import WorkspaceClient

    from data.csv_to_delta import _wait_for_statement

    spec = os.environ.get("AMADEUS_UNITY_CATALOG_SCHEMA") or ""
    catalog, _, schema = spec.strip().partition(".")
    if not catalog or not schema:
        sys.exit("Set AMADEUS_UNITY_CATALOG_SCHEMA to catalog.schema in .env.local")

    w = WorkspaceClient()
    wh = os.environ.get("DATABRICKS_WAREHOUSE_ID") or next(iter(w.warehouses.list())).id
    wh_id = str(getattr(wh, "id", wh) or wh)

    _wait_for_statement(w, wh_id, f"CREATE CATALOG IF NOT EXISTS `{catalog}`")
    print(f"Catalog {catalog} ready (created or already existed)")

    _wait_for_statement(w, wh_id, f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")
    print(f"Schema {spec} ready (created or already existed)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback

        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
