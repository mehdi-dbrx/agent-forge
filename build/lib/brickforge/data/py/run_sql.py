#!/usr/bin/env python3
"""Run a SQL file. Substitutes __SCHEMA_QUALIFIED__ and __VOLUME_PATH__ from PROJECT_UNITY_CATALOG_SCHEMA.
Usage: python data/py/run_sql.py <path/to/file.sql>"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


if __name__ == "__main__":
    from databricks.sdk import WorkspaceClient
    from data.py.csv_to_delta import _wait_for_statement
    from data.py.sql_utils import substitute_schema
    if len(sys.argv) < 2:
        print("Usage: python data/run_sql.py <path/to/file.sql>", file=sys.stderr)
        sys.exit(1)
    sql_path = sys.argv[1]
    path = Path(sql_path) if Path(sql_path).is_absolute() else ROOT / sql_path
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    w = WorkspaceClient()
    wh = os.environ.get("DATABRICKS_WAREHOUSE_ID") or next(iter(w.warehouses.list())).id
    wh_id = str(getattr(wh, "id", wh) or wh)
    content = substitute_schema(path.read_text().strip())

    # Procedures with BEGIN...END must be sent as a single statement
    if "BEGIN" in content and "END;" in content:
        stmts = [content]
    elif "CALL " in content:
        create, call = content.split("CALL ", 1)
        stmts = [create.strip(), "CALL " + call.strip()]
    else:
        stmts = [s.strip() for s in content.split(";\n\n") if s.strip()]

    for stmt in stmts:
        sql = stmt if stmt.endswith(";") else stmt + ";"
        _wait_for_statement(w, wh_id, sql)
