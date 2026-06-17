"""Agent tool to redeploy check-in agents via update_checkin_agent procedure."""

import json
import logging
import os
import urllib.request

from langchain_core.tools import tool

from data.py.sql_utils import get_schema_qualified
from tools.sql_executor import execute_query, execute_statement, get_warehouse

# Manager ID -> display name for staffing duty notifications
MANAGER_NAMES: dict[str, str] = {"M01": "J. Torres"}


def _get_agent_name(agent_id: str) -> str:
    """Look up agent name from checkin_agents. Returns agent_id if not found."""
    w, wh_id = get_warehouse()
    schema = get_schema_qualified()
    a = agent_id.replace("'", "''")
    stmt = f"SELECT name FROM {schema}.checkin_agents WHERE agent_id = '{a}' LIMIT 1"
    try:
        columns, rows = execute_query(w, wh_id, stmt)
        if rows and len(rows[0]) > 0 and rows[0][0]:
            return str(rows[0][0])
    except Exception:
        pass
    return agent_id


@tool
def update_checkin_agent(
    agent_id: str,
    zone: str,
    at_counter: str,
    counter: str | None = None,
    assigned_by_id: str | None = None,
) -> str:
    """Redeploy an agent to a zone/counter. Call when operator confirms redeploying an available agent (e.g. from root cause analysis recommendations).
    agent_id: e.g. 'A14'. zone: e.g. 'B'. counter: e.g. 'B08'; omit or leave empty to use {zone}01. at_counter: ACTIVE, AWAY, BREAK, or AVAILABLE. assigned_by_id: Manager ID when creating staffing duty (e.g. 'M01'), omit for non-Manager redeploys."""
    w, wh_id = get_warehouse()
    resolved_counter = counter or f"{zone}01"
    a = agent_id.replace("'", "''")
    z = zone.replace("'", "''")
    c = resolved_counter.replace("'", "''")
    ac = at_counter.replace("'", "''")
    ab = f"'{assigned_by_id.replace(chr(39), chr(39) * 2)}'" if assigned_by_id else "NULL"
    schema = get_schema_qualified()
    stmt = f"CALL {schema}.update_checkin_agent('{a}', '{z}', '{c}', '{ac}', {ab})"
    try:
        execute_statement(w, wh_id, stmt)
        if assigned_by_id:
            agent_name = _get_agent_name(agent_id)
            manager_name = MANAGER_NAMES.get(assigned_by_id, assigned_by_id)
            base = os.environ.get("TASK_EVENTS_URL", "http://127.0.0.1:3001")
            url = f"{base.rstrip('/')}/api/events/task-created"
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps({
                        "assigned_to_id": agent_id,
                        "agent_name": agent_name,
                        "manager_name": manager_name,
                    }).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception as e:
                logging.getLogger(__name__).warning("task_created webhook failed: %s", e)
        return f"Redeployed {agent_id} to Zone {zone}, counter {resolved_counter}, {at_counter}."
    except RuntimeError as e:
        return f"Error: {e}"
