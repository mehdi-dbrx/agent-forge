#!/usr/bin/env python3
"""Upload data/csv/*.csv to Delta tables in PROJECT_UNITY_CATALOG_SCHEMA. Creates volume 'data' if missing."""
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
load_dotenv(ROOT / ".env.local", override=True)

TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELED", "CLOSED"})

CSV_DIR = Path(__file__).resolve().parent / "csv"


def _wait_for_statement(w, wh_id: str, statement: str) -> None:
    from databricks.sdk.service.sql import ExecuteStatementRequestOnWaitTimeout

    resp = w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=statement,
        wait_timeout="50s",
        on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CONTINUE,
    )
    state = (resp.status and resp.status.state) and resp.status.state.value or ""
    if state in ("SUCCEEDED", "CLOSED"):
        return
    if state in ("FAILED", "CANCELED"):
        err = resp.status.error if resp.status else None
        msg = err.message if err else state
        raise RuntimeError(f"Statement {state}: {msg}")
    if state in ("PENDING", "RUNNING") and resp.statement_id:
        while True:
            time.sleep(2)
            poll = w.statement_execution.get_statement(resp.statement_id)
            s = (poll.status and poll.status.state) and poll.status.state.value or ""
            if s in ("SUCCEEDED", "CLOSED"):
                return
            if s in ("FAILED", "CANCELED"):
                err = poll.status.error if poll.status else None
                raise RuntimeError(f"Statement {s}: {err.message if err else s}")
            if s in TERMINAL_STATES:
                return
    raise RuntimeError(f"Statement did not complete: {state}")


def _delta_safe_name(name: str) -> str:
    """Delta-safe column name: no spaces or ,;{}()\\n\\t="""
    s = re.sub(r"[ ,;{}()\n\t=]+", "_", name).strip("_")
    return s or "col"


def _select_with_safe_columns(header_line: str) -> str:
    """Build SELECT `col1` AS safe1, `col2` AS safe2, ... from CSV header."""
    import csv
    from io import StringIO
    row = next(csv.reader(StringIO(header_line)))
    seen: dict[str, int] = {}
    parts = []
    for col in row:
        safe = _delta_safe_name(col) or "col"
        if safe in seen:
            seen[safe] += 1
            safe = f"{safe}_{seen[safe]}"
        else:
            seen[safe] = 0
        parts.append(f"`{col.replace(chr(96), chr(96)+chr(96))}` AS `{safe}`")
    return ", ".join(parts)


def main():
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.catalog import VolumeType

    w = WorkspaceClient()
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA") or ""
    if "." not in spec:
        print("Set PROJECT_UNITY_CATALOG_SCHEMA to catalog.schema", file=sys.stderr)
        sys.exit(1)
    catalog, schema = spec.strip().split(".", 1)

    vol_name = "data"
    try:
        w.volumes.create(catalog_name=catalog, schema_name=schema, name=vol_name, volume_type=VolumeType.MANAGED)
    except Exception as e:
        if "already exists" not in str(e).lower() and "RESOURCE_ALREADY_EXISTS" not in str(e):
            raise

    wh_id = os.environ.get("DATABRICKS_WAREHOUSE_ID") or next(iter(w.warehouses.list()), None)
    if not wh_id:
        print("No warehouse. Set DATABRICKS_WAREHOUSE_ID or create one.", file=sys.stderr)
        sys.exit(1)
    wh_id = getattr(wh_id, "id", wh_id)
    vol = f"/Volumes/{catalog}/{schema}/{vol_name}"

    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
        if not csv_path.is_absolute():
            csv_path = (CSV_DIR / csv_path).resolve()
        if not csv_path.exists():
            print(f"File not found: {csv_path}", file=sys.stderr)
            sys.exit(1)
        if csv_path.suffix.lower() != ".csv":
            print("Expected a .csv file.", file=sys.stderr)
            sys.exit(1)
        csv_files = [csv_path]
    else:
        csv_files = sorted(CSV_DIR.glob("*.csv"))

    for csv in csv_files:
        rpath = f"{vol}/{csv.name}"
        w.files.upload_from(file_path=rpath, source_path=str(csv), overwrite=True)
        t = f"`{catalog}`.`{schema}`.`{csv.stem.replace('-', '_')}`"
        header = csv.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        if header:
            select_list = _select_with_safe_columns(header[0])
            stmt = f"CREATE OR REPLACE TABLE {t} AS SELECT {select_list} FROM read_files('{rpath}', header => true)"
        else:
            stmt = f"CREATE OR REPLACE TABLE {t} AS SELECT * FROM read_files('{rpath}', header => true)"
        _wait_for_statement(w, wh_id, stmt)
    print("Done.")


if __name__ == "__main__":
    main()
