"""Agent tool to query check-in metrics for a given flight."""

from pathlib import Path

from langchain_core.tools import tool

from data.py.sql_utils import substitute_schema
from tools.sql_executor import _escape_sql_string, execute_query, format_query_result, get_warehouse

_FUNC_DIR = Path(__file__).resolve().parents[1] / "data" / "func"


@tool
def query_checkin_metrics(flight_number: str) -> str:
    """Check-in metrics for a flight: zone, departure time, delay risk, and status. Use when asked about check-in status or metrics for a specific flight."""
    w, wh_id = get_warehouse()
    sql = substitute_schema((_FUNC_DIR / "checkin_metrics.sql").read_text().strip())
    stmt = sql.replace("{flight_number}", _escape_sql_string(flight_number))
    try:
        columns, rows = execute_query(w, wh_id, stmt)
        return format_query_result(columns, rows)
    except RuntimeError as e:
        return f"Error: {e}"
