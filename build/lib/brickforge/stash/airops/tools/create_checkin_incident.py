"""Agent tool to create a check-in incident anomaly in Zone B for demo scenarios."""

from langchain_core.tools import tool

from data.py.sql_utils import get_schema_qualified
from tools.sql_executor import execute_statement, get_warehouse


@tool
def create_checkin_incident() -> str:
    """Create a check-in incident anomaly for Zone B. Call when operator asks about Check-in Performance to inject a demo anomaly (pct_change 25%) before running the check-in performance flow."""
    w, wh_id = get_warehouse()
    schema = get_schema_qualified()
    try:
        execute_statement(
            w,
            wh_id,
            f"DELETE FROM {schema}.checkin_metrics WHERE zone = 'B'",
        )
        execute_statement(
            w,
            wh_id,
            f"INSERT INTO {schema}.checkin_metrics VALUES ('B', 6.25, 5.0, 25.0, 30, CAST('2026-02-25 10:00:00' AS TIMESTAMP_NTZ))",
        )
        return "Created check-in incident anomaly for Zone B."
    except RuntimeError as e:
        return f"Error: {e}"
