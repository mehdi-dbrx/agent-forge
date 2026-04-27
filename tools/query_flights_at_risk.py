"""Agent tool to query flights at risk of delay in a zone within a time window."""

from pathlib import Path

from langchain_core.tools import tool

from data.py.sql_utils import substitute_schema
from tools.sql_executor import execute_query, format_query_result, get_warehouse, _escape_sql_string

_FUNC_DIR = Path(__file__).resolve().parents[1] / "data" / "func"


@tool
def query_flights_at_risk(zone: str, time_start: str, time_end: str) -> str:
    """Flights at risk of delay: flights checking in through zone departing within time window. zone: e.g. 'B'. time_start/time_end: ISO or 'YYYY-MM-DD HH:MM:SS'."""
    w, wh_id = get_warehouse()
    sql = substitute_schema((_FUNC_DIR / "flights_at_risk.sql").read_text().strip())
    stmt = sql.replace("{zone}", _escape_sql_string(zone)).replace("{time_start}", _escape_sql_string(time_start)).replace("{time_end}", _escape_sql_string(time_end))
    try:
        columns, rows = execute_query(w, wh_id, stmt)
        return format_query_result(columns, rows)
    except RuntimeError as e:
        return f"Error: {e}"
