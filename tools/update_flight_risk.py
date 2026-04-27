"""Agent tool to update flight delay_risk via update_flight_risk procedure."""

from langchain_core.tools import tool

from data.py.sql_utils import get_schema_qualified
from tools.sql_executor import execute_statement, get_warehouse


@tool
def update_flight_risk(flight_number: str, at_risk: bool) -> str:
    """Update a flight's delay_risk status. Call when you identify flights at risk and the operator confirms.
    flight_number: e.g. 'BA312'. at_risk: True for AT_RISK, False for NORMAL."""
    w, wh_id = get_warehouse()
    schema = get_schema_qualified()
    escaped = flight_number.replace("'", "''")
    stmt = f"CALL {schema}.update_flight_risk('{escaped}', {'TRUE' if at_risk else 'FALSE'})"
    try:
        execute_statement(w, wh_id, stmt)
        return f"Updated {flight_number} to {'AT_RISK' if at_risk else 'NORMAL'}."
    except RuntimeError as e:
        return f"Error: {e}"
