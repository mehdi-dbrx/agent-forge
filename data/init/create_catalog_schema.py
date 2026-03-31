#!/usr/bin/env python3
"""Create Databricks Unity Catalog and schema if not exists. Reads PROJECT_UNITY_CATALOG_SCHEMA from .env.local."""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env.local", override=True)

TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELED", "CLOSED"})


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
                msg = err.message if err else s
                raise RuntimeError(f"Statement {s}: {msg}")


def main() -> None:
    from databricks.sdk import WorkspaceClient

    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA") or ""
    catalog, _, schema = spec.strip().partition(".")
    if not catalog or not schema:
        sys.exit("Set PROJECT_UNITY_CATALOG_SCHEMA to catalog.schema in .env.local")

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
