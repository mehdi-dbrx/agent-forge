"""Agent tool to restore baseline check-in metrics when zone is back to normal."""

from langchain_core.tools import tool

from data.py.sql_utils import get_schema_qualified
from tools.sql_executor import execute_statement, get_warehouse


@tool
def back_to_normal(zone: str) -> str:
    """Restore baseline check-in metrics for a zone when it is back to normal. Call when pct_change < 5 and previously flagged, or when operator confirms the zone has recovered."""
    w, wh_id = get_warehouse()
    schema = get_schema_qualified()
    escaped = zone.replace("'", "''")
    stmt = f"""INSERT INTO {schema}.checkin_metrics VALUES ('{escaped}', 5.10, 5.0, 2.0, 30, CAST('2026-02-25 10:30:00' AS TIMESTAMP_NTZ))"""
    try:
        execute_statement(w, wh_id, stmt)
        return f"Restored baseline metrics for Zone {zone}."
    except RuntimeError as e:
        return f"Error: {e}"
