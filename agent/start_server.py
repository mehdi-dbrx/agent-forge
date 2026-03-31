from dotenv import load_dotenv
from mlflow.genai.agent_server import AgentServer, setup_mlflow_git_based_version_tracking

# Load env vars from .env then .env.local before importing the agent for proper auth
load_dotenv(dotenv_path=".env.local", override=True)

# Need to import the agent to register the functions with the server
import agent_server.agent  # noqa: E402

server = AgentServer("ResponsesAgent", enable_chat_proxy=True)

# Define the app as a module level variable to enable multiple workers
app = server.app  # noqa: F841

import os

from fastapi import HTTPException, Request

from tools.get_current_time import get_next_time  # noqa: E402
from tools.sql_executor import execute_query, get_warehouse  # noqa: E402

def _get_allowed_tables() -> frozenset[str]:
    csv_dir = Path(__file__).resolve().parents[1] / "data" / "csv"
    if not csv_dir.exists():
        return frozenset()
    return frozenset(p.stem.replace("-", "_") for p in csv_dir.glob("*.csv"))

ALLOWED_TABLES = _get_allowed_tables()


@app.get("/tables/{table_name}")
def get_table(table_name: str):
    """Return table data from UC. Used by Node /api/tables proxy (avoids DATABRICKS_* env in Node)."""
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=400,
            detail={"error": "Table not allowed", "allowed": list(ALLOWED_TABLES)},
        )
    schema_spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if not schema_spec or "." not in schema_spec:
        raise HTTPException(
            status_code=502,
            detail="PROJECT_UNITY_CATALOG_SCHEMA not set (catalog.schema)",
        )
    catalog, schema = schema_spec.split(".", 1)
    full_table = (
        f"{catalog}.`{schema}`.{table_name}"
        if "-" in schema or " " in schema
        else f"{catalog}.{schema}.{table_name}"
    )
    statement = (
        f"SELECT zone, avg_checkin_time_mins, baseline_mins, pct_change, window_mins, recorded_at "
        f"FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY zone ORDER BY recorded_at DESC) AS _rn "
        f"FROM {full_table}) sub WHERE _rn = 1"
        if table_name == "checkin_metrics"
        else f"SELECT * FROM {full_table}"
    )
    try:
        w_client, wh_id = get_warehouse()
        columns, rows = execute_query(w_client, wh_id, statement)
        return {"columns": columns, "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/current-time")
def current_time(request: Request):
    """Return simulated time. advance=true moves forward; backward=true moves back; else peeks."""
    advance = request.query_params.get("advance", "false").lower() == "true"
    backward = request.query_params.get("backward", "false").lower() == "true"
    if backward:
        t = get_next_time(advance=False, backward=True)
    else:
        t = get_next_time(advance)
    print(f"[current-time] advance={advance} backward={backward} -> {t}", flush=True)
    return {"currentTime": t}


@app.get("/current-time/backward")
def current_time_backward():
    """Step simulated time backward and return new time (avoids query-param forwarding issues)."""
    t = get_next_time(advance=False, backward=True)
    print(f"[current-time/backward] -> {t}", flush=True)
    return {"currentTime": t}


setup_mlflow_git_based_version_tracking()


def main():
    server.run(app_import_string="agent_server.start_server:app")
