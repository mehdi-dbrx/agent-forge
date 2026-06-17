"""Shared Databricks SQL execution for agent tools."""

import os
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import (
    Disposition,
    ExecuteStatementRequestOnWaitTimeout,
    Format,
)


def _escape_sql_string(s: str) -> str:
    """Escape single quotes for SQL string literal."""
    return s.replace("'", "''")


def get_warehouse() -> tuple[WorkspaceClient, str]:
    """Return (WorkspaceClient, warehouse_id) for SQL execution."""
    w = WorkspaceClient()
    wh = os.environ.get("DATABRICKS_WAREHOUSE_ID") or next(iter(w.warehouses.list()))
    wh_id = str(getattr(wh, "id", wh) or wh)
    return w, wh_id


def execute_statement(w: WorkspaceClient, wh_id: str, stmt: str) -> None:
    """Run SQL via statement_execution, poll until done, raise on failure."""
    resp = w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=stmt,
        wait_timeout="30s",
        on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CONTINUE,
    )
    state = (resp.status and resp.status.state) and resp.status.state.value or ""
    if state in ("SUCCEEDED", "CLOSED"):
        return
    if state in ("FAILED", "CANCELED"):
        err = resp.status.error if resp.status else None
        raise RuntimeError(err.message if err else state)
    if state in ("PENDING", "RUNNING") and resp.statement_id:
        while True:
            time.sleep(2)
            poll = w.statement_execution.get_statement(resp.statement_id)
            s = (poll.status and poll.status.state) and poll.status.state.value or ""
            if s in ("SUCCEEDED", "CLOSED"):
                return
            if s in ("FAILED", "CANCELED"):
                err = poll.status.error if poll.status else None
                raise RuntimeError(err.message if err else s)
    raise RuntimeError(f"Statement did not complete: {state}")


def execute_query(w: WorkspaceClient, wh_id: str, stmt: str) -> tuple[list[str], list[list]]:
    """Execute SELECT, return (column_names, rows). Uses JSON_ARRAY format."""
    resp = w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=stmt,
        wait_timeout="30s",
        on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CONTINUE,
        format=Format.JSON_ARRAY,
        disposition=Disposition.INLINE,
    )
    state = (resp.status and resp.status.state) and resp.status.state.value or ""
    if state in ("FAILED", "CANCELED"):
        err = resp.status.error if resp.status else None
        raise RuntimeError(err.message if err else state)
    if state in ("PENDING", "RUNNING") and resp.statement_id:
        while True:
            time.sleep(2)
            poll = w.statement_execution.get_statement(resp.statement_id)
            s = (poll.status and poll.status.state) and poll.status.state.value or ""
            if s in ("SUCCEEDED", "CLOSED"):
                resp = poll
                state = s
                break
            if s in ("FAILED", "CANCELED"):
                err = poll.status.error if poll.status else None
                raise RuntimeError(err.message if err else s)
    if state not in ("SUCCEEDED", "CLOSED"):
        raise RuntimeError(f"Statement did not complete: {state}")

    columns = []
    if resp.manifest and resp.manifest.schema and resp.manifest.schema.columns:
        columns = [c.name or "" for c in resp.manifest.schema.columns]
    rows: list[list] = []
    if resp.result and resp.result.data_array:
        rows = list(resp.result.data_array)
    chunk_index = resp.result.next_chunk_index if resp.result else None
    while chunk_index is not None and resp.statement_id:
        chunk = w.statement_execution.get_statement_result_chunk_n(
            statement_id=resp.statement_id,
            chunk_index=chunk_index,
        )
        if chunk.data_array:
            rows.extend(chunk.data_array)
        chunk_index = chunk.next_chunk_index
    return columns, rows


def format_query_result(columns: list[str], rows: list[list]) -> str:
    """Format (columns, rows) as a readable string for the agent."""
    if not columns and not rows:
        return "(no rows)"
    lines = [" | ".join(columns)]
    for row in rows:
        lines.append(" | ".join(str(v) if v is not None else "" for v in row))
    return "\n".join(lines)
