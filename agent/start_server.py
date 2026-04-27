from dotenv import load_dotenv
from mlflow.genai.agent_server import AgentServer, setup_mlflow_git_based_version_tracking

# Load env vars from .env then .env.local before importing the agent for proper auth
load_dotenv(dotenv_path=".env.local", override=True)

# Need to import the agent to register the functions with the server
import agent.agent  # noqa: E402

server = AgentServer("ResponsesAgent", enable_chat_proxy=True)

# Define the app as a module level variable to enable multiple workers
app = server.app  # noqa: F841

import os
import subprocess
from pathlib import Path

from fastapi import HTTPException

_NODE_SERVER = Path(__file__).resolve().parents[1] / "app" / "server" / "dist" / "index.mjs"

_CLIENT_DIST = Path(__file__).resolve().parents[1] / "app" / "client" / "dist" / "index.html"

@app.on_event("startup")
async def start_frontend():
    if not _CLIENT_DIST.exists() and _NODE_SERVER.exists():
        _frontend_root = str(_NODE_SERVER.parents[2])
        subprocess.run(["npm", "install"], cwd=_frontend_root, check=True)
        subprocess.run(["npm", "run", "build:client"], cwd=_frontend_root, check=True)
    if _NODE_SERVER.exists():
        node_env = os.environ.copy()
        node_env["NODE_ENV"] = "production"
        subprocess.Popen(
            ["node", str(_NODE_SERVER)],
            cwd=str(_NODE_SERVER.parents[2]),
            env=node_env,
        )

from tools.sql_executor import execute_query, get_warehouse  # noqa: E402

_ALLOWED_TABLES = {"flights", "checkin_metrics", "checkin_agents", "border_officers", "border_terminals"}

@app.get("/tables/{table_name}")
def get_table(table_name: str):
    """Return table data from UC."""
    if table_name not in _ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table not allowed: {table_name}")
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
    try:
        w_client, wh_id = get_warehouse()
        columns, rows = execute_query(w_client, wh_id, f"SELECT * FROM {full_table}")
        return {"columns": columns, "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))



try:
    setup_mlflow_git_based_version_tracking()
except Exception:
    pass  # mlflow 3.9.0 bug in search_logged_models — non-critical


def main():
    server.run(app_import_string="agent.start_server:app")
