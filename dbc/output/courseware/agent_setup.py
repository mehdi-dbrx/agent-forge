# Databricks notebook source
# MAGIC %md
# MAGIC # Agent - Workspace Setup (SDK)
# MAGIC
# MAGIC This notebook provisions the complete Agent environment.
# MAGIC Uses the Databricks SDK wherever possible (REST only for Genie).
# MAGIC
# MAGIC 1. Schema & grants
# MAGIC 2. Tables & seed data
# MAGIC 3. Stored procedures & functions
# MAGIC 4. Upload agent code to workspace
# MAGIC 5. MLflow experiment
# MAGIC 6. Genie space
# MAGIC 7. Knowledge Assistant
# MAGIC 8. Deploy Databricks App
# MAGIC 9. Permissions & summary
# MAGIC
# MAGIC All source files are in the same folder as this notebook.

# COMMAND ----------

# MAGIC %pip install anyio==4.12.1 databricks-ai-bridge==0.14.1 databricks-langchain==0.15.0 databricks-mcp==0.8.0 databricks-openai==0.11.1 databricks-sdk==0.102.0 databricks-vectorsearch==0.65 fastapi==0.129.0 flask==3.1.2 flask-cors==6.0.2 langchain==1.2.10 langchain-community==0.4.1 langchain-core==1.2.13 langchain-openai==1.1.10 langchain-text-splitters==1.1.0 langgraph==1.0.8 langgraph-checkpoint==4.0.0 langgraph-prebuilt==1.0.7 langgraph-sdk==0.3.6 langsmith==0.7.3 mcp==1.26.0 mlflow==3.9.0 mlflow-skinny==3.9.0 mlflow-tracing==3.9.0 openai==2.21.0 pandas==2.3.3 pyarrow==22.0.0 pydantic==2.12.5 pydantic-core==2.41.5 pydantic-settings==2.13.0 pypdf==6.10.2 python-dotenv==1.2.2 pyyaml==6.0.3 requests==2.32.5 rich==14.3.2 sse-starlette==3.2.0 starlette==0.52.1 tabulate==0.9.0 tenacity==9.1.4 typing-extensions==4.15.0 typing-inspection==0.4.2 unitycatalog-ai==0.3.2 unitycatalog-client==0.4.0 unitycatalog-langchain==0.3.0 unitycatalog-openai==0.2.0 uvicorn==0.41.0
# MAGIC %restart_python

# COMMAND ----------

CATALOG = "amadeus"
SCHEMA = "airops"
SCHEMA_QUALIFIED = f"`{CATALOG}`.`{SCHEMA}`"
APP_NAME = "agent-app"
WORKSPACE_PATH = "/Workspace/Shared/agent-app"

import os, time
from pathlib import Path
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import (
    Disposition, ExecuteStatementRequestOnWaitTimeout, Format,
)

w = WorkspaceClient()
host = w.config.host.rstrip("/")
token = w.config.authenticate().get("Authorization", "").replace("Bearer ", "")

# Where this notebook lives — source files are alongside it
NOTEBOOK_DIR = os.path.dirname(
    dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
)
LOCAL_DIR = f"/Workspace{NOTEBOOK_DIR}"

def sql(stmt):
    """Execute SQL via SDK statement_execution (async + poll)."""
    resp = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=stmt,
        wait_timeout="0s",
        on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CONTINUE,
    )
    state = (resp.status and resp.status.state) and resp.status.state.value or ""
    if state in ("SUCCEEDED", "CLOSED"):
        return resp
    if state in ("FAILED", "CANCELED"):
        err = resp.status.error if resp.status else None
        raise RuntimeError(err.message if err else state)
    # Poll
    while True:
        time.sleep(3)
        poll = w.statement_execution.get_statement(resp.statement_id)
        s = (poll.status and poll.status.state) and poll.status.state.value or ""
        if s in ("SUCCEEDED", "CLOSED"):
            return poll
        if s in ("FAILED", "CANCELED"):
            err = poll.status.error if poll.status else None
            raise RuntimeError(err.message if err else s)

# Colored log helpers
_G, _C, _Y, _R, _B, _W = "\033[32m", "\033[36m", "\033[33m", "\033[31m", "\033[1m", "\033[0m"
_DIM = "\033[2m"
def ok(msg, indent=0):  print(f"{'  ' * indent}{_G}✓{_W} {msg}")
def info(msg, indent=0): print(f"{'  ' * indent}{_C}ℹ{_W} {msg}")
def warn(msg, indent=0): print(f"{'  ' * indent}{_Y}⚠{_W} {msg}")
def err(msg, indent=0):  print(f"{'  ' * indent}{_R}✗{_W} {msg}")
def progress(mins, msg, remaining=None):
    tail = f" {_DIM}(~{remaining} min to go){_W}" if remaining is not None else ""
    print(f"  {_C}[{mins}min]{_W} {msg}{tail}")

ok("Constants and helpers loaded")
print(f"    Notebook dir: {NOTEBOOK_DIR}")
print(f"    Local dir:    {LOCAL_DIR}")

# Discover warehouse via SDK
WAREHOUSE_ID = None
for wh in w.warehouses.list():
    state = wh.state.value if wh.state else ""
    if state in ("RUNNING", "STARTING", "STOPPED"):
        WAREHOUSE_ID = wh.id
        break
if not WAREHOUSE_ID:
    # Fallback: take first warehouse
    for wh in w.warehouses.list():
        WAREHOUSE_ID = wh.id
        break
if not WAREHOUSE_ID:
    raise RuntimeError("No SQL warehouse found in workspace")
ok(f"Using warehouse: {WAREHOUSE_ID}")

# COMMAND ----------

# Cell 1: Create Catalog + Schema + Grants
sql("CREATE CATALOG IF NOT EXISTS `amadeus`")
sql("GRANT USE CATALOG ON CATALOG `amadeus` TO `account users`")
ok("Catalog created + USE CATALOG granted")

sql("CREATE SCHEMA IF NOT EXISTS `amadeus`.`airops`")
ok("Schema created")

sql("GRANT ALL PRIVILEGES ON SCHEMA `amadeus`.`airops` TO `account users`")
ok("Grants applied")

# COMMAND ----------

# Cell 2: Create Tables + Seed Data
_init_dir = Path(LOCAL_DIR) / "data" / "init"
_tables = [
    ("create_flights.sql", "flights"),
    ("create_checkin_agents.sql", "checkin_agents"),
    ("create_checkin_metrics.sql", "checkin_metrics"),
    ("create_border_officers.sql", "border_officers"),
    ("create_border_terminals.sql", "border_terminals"),
]
for sql_file, table_name in _tables:
    sql_path = _init_dir / sql_file
    sql_text = sql_path.read_text()
    sql_text = sql_text.replace("__SCHEMA_QUALIFIED__", SCHEMA_QUALIFIED)
    for stmt in sql_text.split(";"):
        stmt = stmt.strip()
        if stmt:
            sql(stmt)
    ok(f"{table_name} table created and seeded")
    sql(f"GRANT SELECT ON TABLE `amadeus`.`airops`.{table_name} TO `account users`")

ok("All tables created and grants applied")

# COMMAND ----------

# Cell 3: Stored Procedures
_proc_dir = Path(LOCAL_DIR) / "data" / "proc"
_procedures = [
    ("update_flight_risk.sql", "update_flight_risk"),
    ("update_checkin_agents_procedure.sql", "update_checkin_agent"),
    ("update_border_officer_procedure.sql", "update_border_officer"),
    ("confirm_arrival_procedure.sql", "confirm_arrival"),
]
for sql_file, proc_name in _procedures:
    proc_path = _proc_dir / sql_file
    proc_sql = proc_path.read_text().strip()
    proc_sql = proc_sql.replace("__SCHEMA_QUALIFIED__", SCHEMA_QUALIFIED)
    sql(proc_sql)
    ok(f"{proc_name} procedure created")
    try:
        sql(f"GRANT EXECUTE ON PROCEDURE `amadeus`.`airops`.{proc_name} TO `account users`")
    except Exception:
        pass

ok("All procedures and grants applied")

# COMMAND ----------

# Cell 4: Upload Agent Code to Workspace
import base64

def upload_file(ws_path, content_bytes):
    """Upload a file to workspace via SDK."""
    w.workspace.import_(
        path=ws_path,
        content=base64.b64encode(content_bytes).decode("ascii"),
        overwrite=True,
        format=import_format,
    )

from databricks.sdk.service.workspace import ImportFormat
import_format = ImportFormat.AUTO

def upload_tree(local_root, ws_root, label=None):
    """Recursively upload a directory tree to workspace."""
    local_root = Path(local_root)
    files = sorted(f for f in local_root.rglob("*") if f.is_file())
    total_files = len(files)
    count = 0
    for local_path in files:
        rel = local_path.relative_to(local_root)
        ws_path = f"{ws_root}/{rel}"
        parent = "/".join(ws_path.split("/")[:-1])
        try:
            w.workspace.mkdirs(parent)
        except Exception:
            pass
        upload_file(ws_path, local_path.read_bytes())
        count += 1
        if label and total_files > 50 and count % 50 == 0:
            print(f"    {_DIM}... {label}: {count}/{total_files} files uploaded{_W}")
    return count

# Create target directory
try:
    w.workspace.mkdirs(WORKSPACE_PATH)
except Exception:
    pass

# Upload source directories
dirs_to_upload = ["agent", "tools", "data", "prompt", "config"]
total = 0
for d in dirs_to_upload:
    local = Path(LOCAL_DIR) / d
    if local.exists():
        n = upload_tree(local, f"{WORKSPACE_PATH}/{d}")
        ok(f"{d}/ — {n} files", indent=1)
        total += n

# Upload pyproject.toml
pyproject = Path(LOCAL_DIR) / "pyproject.toml"
if pyproject.exists():
    upload_file(f"{WORKSPACE_PATH}/pyproject.toml", pyproject.read_bytes())
    total += 1
    ok("pyproject.toml", indent=1)

# Upload frontend dist if present
dist_dir = Path(LOCAL_DIR) / "app" / "client" / "dist"
if dist_dir.exists():
    n = upload_tree(dist_dir, f"{WORKSPACE_PATH}/app/client/dist", label="app/client/dist")
    ok(f"app/client/dist/ — {n} files", indent=1)
    total += n
else:
    warn("No frontend dist found — skipped", indent=1)

# Upload server dist if present (Node Express server)
server_dist_dir = Path(LOCAL_DIR) / "app" / "server" / "dist"
if server_dist_dir.exists():
    n = upload_tree(server_dist_dir, f"{WORKSPACE_PATH}/app/server/dist", label="app/server/dist")
    ok(f"app/server/dist/ — {n} files", indent=1)
    total += n
else:
    warn("No server dist found — skipped", indent=1)

ok(f"Uploaded {total} files to {WORKSPACE_PATH}")

# COMMAND ----------

# Cell 5: Create MLflow Experiment
import mlflow

EXPERIMENT_NAME = "/Shared/agent-experiment"

try:
    exp_id = mlflow.create_experiment(EXPERIMENT_NAME)
    ok(f"Experiment created: {EXPERIMENT_NAME} (id={exp_id})")
except mlflow.exceptions.MlflowException as e:
    if "RESOURCE_ALREADY_EXISTS" in str(e):
        exp = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
        exp_id = exp.experiment_id
        ok(f"Experiment already exists: {EXPERIMENT_NAME} (id={exp_id})")
    else:
        raise

# Grant permissions via SDK
from databricks.sdk.service.iam import AccessControlRequest, Permission, PermissionLevel
try:
    w.permissions.set(
        request_object_type="experiments",
        request_object_id=exp_id,
        access_control_list=[
            AccessControlRequest(
                group_name="account users",
                permission_level=PermissionLevel.CAN_MANAGE,
            )
        ],
    )
    ok("Experiment permissions granted")
except Exception as e:
    warn(f"Could not set experiment permissions: {e}")

# COMMAND ----------

# Cell 6: Create Genie Space (SDK)
import json, uuid

def _gen_id():
    return uuid.uuid4().hex[:24] + "0" * 8

GENIE_SPACE_ID = None

serialized = {
    "version": 2,
    "config": {
        "sample_questions": [
            {"id": _gen_id(), "question": ["What are total check-ins by airline?"]},
            {"id": _gen_id(), "question": ["Show flights at risk of delay"]},
        ]
    },
    "data_sources": {
        "tables": [
            {"identifier": f"amadeus.airops.flights"},
            {"identifier": f"amadeus.airops.checkin_metrics"},
            {"identifier": f"amadeus.airops.checkin_agents"},
            {"identifier": f"amadeus.airops.border_officers"},
            {"identifier": f"amadeus.airops.border_terminals"},
        ],
        "metric_views": [],
    },
    "instructions": {
        "text_instructions": [],
        "example_question_sqls": [],
        "sql_functions": [],
        "join_specs": [],
        "sql_snippets": {"filters": [], "expressions": [], "measures": []},
    },
    "benchmarks": {"questions": []},
}

try:
    space = w.genie.create_space(
        warehouse_id=WAREHOUSE_ID,
        serialized_space=json.dumps(serialized),
        title="GENIE-AMADEUS-AIROPS",
        description="Flight operations data for the Agent AI assistant",
    )
    GENIE_SPACE_ID = space.space_id
    ok(f"Genie space created: {GENIE_SPACE_ID}")
except Exception as e:
    if "ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
        spaces = list(w.genie.list_spaces().spaces or [])
        for sp in spaces:
            if "GENIE-AMADEUS-AIROPS" in (getattr(sp, "title", "") or ""):
                GENIE_SPACE_ID = sp.space_id
                break
        ok(f"Genie space already exists: {GENIE_SPACE_ID}")
    else:
        warn(f"Could not create Genie space: {e}")
        print("    (Non-critical — agent works without Genie)")

# Grant CAN_RUN on Genie space to all users (so app SP can query it)
if GENIE_SPACE_ID:
    import requests as _req
    try:
        _resp = _req.patch(
            f"{host}/api/2.0/preview/permissions/genie/{GENIE_SPACE_ID}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "access_control_list": [
                    {"group_name": "account users", "permission_level": "CAN_RUN"}
                ]
            },
        )
        _resp.raise_for_status()
        ok("Genie space: granted CAN_RUN to all users")
    except Exception as e:
        warn(f"Could not set Genie permissions: {e}")

# COMMAND ----------

# Cell 7: Knowledge Assistant (Passenger Rights)
import random, yaml
from databricks.sdk.service.knowledgeassistants import (
    FilesSpec, KnowledgeAssistant, KnowledgeSource,
)

KA_DISPLAY_NAME = "ka-agent-passengers-rights"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/doc"

# --- Create UC Volume for PDFs ---
try:
    sql(f"CREATE VOLUME IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`.doc")
    ok("UC Volume created/verified")
except Exception as e:
    warn(f"Could not create volume: {e}")

# --- Upload PDFs from bundle to Volume ---
pdf_dir = Path(LOCAL_DIR) / "data" / "pdf"
uploaded = 0
if pdf_dir.exists():
    for pdf_file in sorted(pdf_dir.glob("*.pdf")):
        dest = f"{VOLUME_PATH}/{pdf_file.name}"
        with open(pdf_file, "rb") as fh:
            w.files.upload(dest, fh, overwrite=True)
        ok(f"Uploaded {pdf_file.name} to {dest}", indent=1)
        uploaded += 1
if uploaded == 0:
    warn("No PDFs found in data/pdf/ — KA will have no knowledge sources")

# --- Load KA config from bundle ---
ka_yml = Path(LOCAL_DIR) / "config" / "ka" / "ka_passengers.yml"
output_yml = Path(LOCAL_DIR) / "config" / "ka" / "output_format.yml"

raw = ka_yml.read_text(encoding="utf-8").replace("{volume_path}", VOLUME_PATH)
cfg = yaml.safe_load(raw)
ka_block = cfg["knowledge_assistant"]

# Merge output format instructions
instructions = ka_block.get("instructions", "")
if output_yml.exists():
    of = yaml.safe_load(output_yml.read_text(encoding="utf-8"))
    fmt = (of.get("output", {}) or {}).get("format", "")
    if fmt:
        instructions = fmt.strip() + "\n\n" + instructions.strip()

# --- Check if KA already exists ---
KA_ENDPOINT = ""
ka_name = ""
existing_ka = None
try:
    for ka in w.knowledge_assistants.list_knowledge_assistants():
        if (ka.display_name or "").lower() == KA_DISPLAY_NAME.lower():
            existing_ka = ka
            break
except Exception:
    pass

if existing_ka:
    ka_name = existing_ka.name or f"knowledge-assistants/{existing_ka.id}"
    ok(f"KA already exists: {ka_name}")
    # Check if already ACTIVE — skip wait loop entirely
    _state = existing_ka.state
    _s = _state.value if _state and hasattr(_state, "value") else str(_state or "")
    if _s == "ACTIVE" and existing_ka.endpoint_name:
        KA_ENDPOINT = existing_ka.endpoint_name
        ok(f"KA already ACTIVE — endpoint: {KA_ENDPOINT}")
else:
    info(f"Creating KA '{KA_DISPLAY_NAME}'...")
    try:
        ka_resp = w.knowledge_assistants.create_knowledge_assistant(
            knowledge_assistant=KnowledgeAssistant(
                display_name=ka_block["display_name"],
                description=ka_block["description"],
                instructions=instructions or None,
            )
        )
        ka_name = ka_resp.name or f"knowledge-assistants/{ka_resp.id}"
        ok(f"KA created: {ka_name}")

        # Add knowledge source
        src = cfg["knowledge_sources"][0]
        w.knowledge_assistants.create_knowledge_source(
            parent=ka_name,
            knowledge_source=KnowledgeSource(
                display_name=src["display_name"],
                description=src.get("description", ""),
                source_type="files",
                files=FilesSpec(path=VOLUME_PATH),
            ),
        )
        ok("Knowledge source added")
    except Exception as _ka_err:
        if "ALREADY_EXISTS" in str(_ka_err) or "already exists" in str(_ka_err).lower():
            ok("KA already exists (race condition)")
            # Re-fetch to get ka_name
            for ka in w.knowledge_assistants.list_knowledge_assistants():
                if (ka.display_name or "").lower() == KA_DISPLAY_NAME.lower():
                    ka_name = ka.name or f"knowledge-assistants/{ka.id}"
                    break
        else:
            raise

# --- Wait for KA to become ACTIVE ---
wait_msgs = [
    "KA is indexing your documents...",
    "Still provisioning -- good things take time...",
    "The bits are being arranged very carefully...",
    "Patience, young padawan...",
    "Almost there... probably...",
    "Somewhere, a model is reading your PDFs...",
    "This is the cloud equivalent of reading a book...",
    "Fun fact: you could make a sandwich while waiting...",
    "Provisioning... because instant gratification is overrated...",
    "Loading awesomeness... please stand by...",
]

if not KA_ENDPOINT:
    print()
    info("Waiting for KA to become ACTIVE...")
    print(f"    {_DIM}This typically takes 10-20 minutes.{_W}")
    print()

elapsed = 0
ka_ready = bool(KA_ENDPOINT)
if not KA_ENDPOINT:
    KA_ENDPOINT = ""
for attempt in range(60 if (not ka_ready and ka_name) else 0):
    try:
        ka_detail = w.knowledge_assistants.get_knowledge_assistant(ka_name)
        state = ka_detail.state
        if state:
            s = state.value if hasattr(state, "value") else str(state)
            if s == "ACTIVE":
                KA_ENDPOINT = ka_detail.endpoint_name or ""
                print()
                ok(f"KA is ACTIVE!")
                ok(f"Endpoint: {KA_ENDPOINT}")
                ka_ready = True
                break
            if s == "FAILED":
                print()
                err(f"KA reached FAILED state")
                err_info = getattr(ka_detail, "error_info", None)
                if err_info:
                    print(f"    {err_info}")
                break
    except Exception:
        pass

    mins_elapsed = elapsed // 60
    mins_remaining = max(0, 20 - mins_elapsed)
    msg = random.choice(wait_msgs)
    progress(mins_elapsed, msg, remaining=mins_remaining)

    time.sleep(30)
    elapsed += 30

if not ka_ready:
    warn("KA not ACTIVE after 30 min -- continuing anyway")
    warn("You may need to check KA status in the UI and redeploy the app with the endpoint name")

# --- Grant CAN_QUERY on KA serving endpoint to all users ---
# Permissions API requires the endpoint ID (UUID), not the name
if KA_ENDPOINT:
    from databricks.sdk.service.iam import AccessControlRequest, PermissionLevel
    try:
        _ep = w.serving_endpoints.get(KA_ENDPOINT)
        _ep_id = _ep.id
        w.permissions.update(
            request_object_type="serving-endpoints",
            request_object_id=_ep_id,
            access_control_list=[
                AccessControlRequest(
                    group_name="account users",
                    permission_level=PermissionLevel.CAN_QUERY,
                ),
            ],
        )
        ok(f"Granted CAN_QUERY on {KA_ENDPOINT} to account users")
    except Exception as e:
        warn(f"Could not set KA endpoint permissions: {e}")

ok(f"KA_ENDPOINT = {KA_ENDPOINT}")

# COMMAND ----------

# Cell 8: Deploy Databricks App (SDK)

# Generate app.yaml
app_yaml_content = f"""command: ["uv", "run", "python", "-c", "from agent.start_server import main; main()"]
env:
  - name: MLFLOW_TRACKING_URI
    value: "databricks"
  - name: MLFLOW_REGISTRY_URI
    value: "databricks-uc"
  - name: MLFLOW_EXPERIMENT_NAME
    value: "{EXPERIMENT_NAME}"
  - name: API_PROXY
    value: "http://localhost:8000/invocations"
  - name: CHAT_APP_PORT
    value: "3000"
  - name: TASK_EVENTS_URL
    value: "http://127.0.0.1:3000"
  - name: CHAT_PROXY_TIMEOUT_SECONDS
    value: "300"
  - name: AGENT_MODEL_ENDPOINT
    value: "databricks-claude-sonnet-4-6"
  - name: PROJECT_UNITY_CATALOG_SCHEMA
    value: "amadeus.airops"
  - name: DATABRICKS_WAREHOUSE_ID
    value: "{WAREHOUSE_ID}"
  - name: PROJECT_GENIE_CHECKIN
    value: "{GENIE_SPACE_ID or ''}"
  - name: PROJECT_KA_PASSENGERS
    value: "{KA_ENDPOINT}"
"""

upload_file(f"{WORKSPACE_PATH}/app.yaml", app_yaml_content.encode("utf-8"))
ok("app.yaml uploaded to workspace")

# --- Create app ---
import random
from databricks.sdk.service.apps import (
    App, AppDeployment, AppResource,
    AppResourceServingEndpoint,
    AppResourceServingEndpointServingEndpointPermission,
    AppResourceSqlWarehouse,
    AppResourceSqlWarehouseSqlWarehousePermission,
)

# Build resource list so the app SP gets granted access
app_resources = [
    AppResource(
        name="sql-warehouse",
        description="SQL warehouse for table queries",
        sql_warehouse=AppResourceSqlWarehouse(
            id=WAREHOUSE_ID,
            permission=AppResourceSqlWarehouseSqlWarehousePermission.CAN_USE,
        ),
    ),
]
if KA_ENDPOINT:
    app_resources.append(AppResource(
        name="ka-endpoint",
        description="Knowledge Assistant serving endpoint",
        serving_endpoint=AppResourceServingEndpoint(
            name=KA_ENDPOINT,
            permission=AppResourceServingEndpointServingEndpointPermission.CAN_QUERY,
        ),
    ))

wait_msgs = [
    "Brewing coffee while the app spins up...",
    "The app is warming up its neurons...",
    "Still provisioning -- good things take time...",
    "The bits are being arranged very carefully...",
    "App is getting its ducks in a row...",
    "Patience, young padawan...",
    "Almost there... probably...",
    "The app is doing push-ups before going live...",
    "Somewhere, a container is working very hard for you...",
    "This is the cloud equivalent of watching paint dry...",
    "Fun fact: you could make a sandwich while waiting...",
    "The hamsters powering the app are running fast...",
    "Provisioning... because instant gratification is overrated...",
    "Your app is putting on its cape...",
    "Loading awesomeness... please stand by...",
]

app_url = f"{host}/apps/{APP_NAME}"

print()
info(f"Creating app '{APP_NAME}'...")

app_exists = False
try:
    existing = w.apps.get(APP_NAME)
    compute = getattr(existing, "compute_status", None)
    c_state = getattr(compute, "state", "") if compute else ""
    if hasattr(c_state, "value"):
        c_state = c_state.value
    ok(f"App already exists: {APP_NAME}")
    print(f"    Compute: {c_state}")
    print(f"    URL: {getattr(existing, 'url', 'unknown')}")
    app_exists = True
except Exception:
    info("App not found -- creating it now...")
    try:
        w.apps.create(
            app=App(
                name=APP_NAME,
                description="Agent - AI Ops Advisor for flight operations",
                resources=app_resources,
            ),
        )
        ok("App creation initiated")
    except Exception as e:
        if "ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
            ok("App already exists (race condition)")
            app_exists = True
        else:
            raise

# --- Wait for app compute to be ACTIVE ---
print()
info("Waiting for app compute to be ACTIVE...")
print(f"    {_DIM}This typically takes 2-5 minutes.{_W}")
print()

elapsed = 0
app_ready = False
for attempt in range(30):
    try:
        app_info = w.apps.get(APP_NAME)
        compute = getattr(app_info, "compute_status", None)
        compute_state = ""
        compute_msg = ""
        if compute:
            compute_state = getattr(compute, "state", "")
            if hasattr(compute_state, "value"):
                compute_state = compute_state.value
            compute_msg = getattr(compute, "message", "")

        if compute_state == "ACTIVE":
            print()
            ok("App compute is ACTIVE!")
            app_ready = True
            break
        elif compute_state in ("ERROR", "FAILED"):
            print()
            err(f"App compute failed: {compute_state} - {compute_msg}")
            break

        mins_elapsed = elapsed // 60
        mins_remaining = max(0, 5 - mins_elapsed)
        msg = random.choice(wait_msgs)
        progress(mins_elapsed, f"compute={compute_state} | {msg}", remaining=mins_remaining)
    except Exception as ex:
        mins_elapsed = elapsed // 60
        progress(mins_elapsed, f"checking... ({ex})")

    time.sleep(60)
    elapsed += 60

if not app_ready and not app_exists:
    warn("App compute not active after 5 min -- attempting deployment anyway")

# --- Wait for any pending deployment to clear ---
print()
info("Checking for pending deployments...")
for wait_attempt in range(20):
    app_info = w.apps.get(APP_NAME)
    pending_dep = getattr(app_info, "pending_deployment", None)
    if not pending_dep:
        ok("No pending deployment -- ready to deploy")
        break
    pend_st = getattr(pending_dep, "status", None)
    pend_state = ""
    if pend_st:
        pend_state = getattr(pend_st, "state", "")
        if hasattr(pend_state, "value"):
            pend_state = pend_state.value
    mins = wait_attempt
    msg = random.choice(wait_msgs)
    progress(mins, f"Pending deployment ({pend_state}) | {msg}")
    time.sleep(60)
else:
    warn("Pending deployment still active after 20 min -- attempting deploy anyway")

# --- Deploy (with retry) ---
print()
info(f"Deploying app from {WORKSPACE_PATH}...")
print(f"    {_DIM}This typically takes 5-10 minutes.{_W}")
print()

deployment_id = None
for deploy_try in range(3):
    try:
        deploy_resp = w.apps.deploy(
            app_name=APP_NAME,
            app_deployment=AppDeployment(source_code_path=WORKSPACE_PATH),
        )
        deployment_id = getattr(deploy_resp, "deployment_id", None)
        ok(f"Deployment initiated (id: {deployment_id})")
        break
    except Exception as e:
        _err = str(e)
        if "pending deployment" in _err.lower():
            warn(f"[retry {deploy_try+1}/3] Pending deployment still active, waiting 2 min...")
            time.sleep(120)
        else:
            err(f"Deploy call failed: {e}")
            print("    You can deploy manually from the Apps UI")
            break

# --- Poll deployment status ---
# Wait for OUR deployment to become active before checking app state
elapsed = 0
deploy_done = False
for attempt in range(30):
    try:
        app_info = w.apps.get(APP_NAME)

        app_st = getattr(app_info, "app_status", None)
        app_state = ""
        app_msg = ""
        if app_st:
            app_state = getattr(app_st, "state", "")
            if hasattr(app_state, "value"):
                app_state = app_state.value
            app_msg = getattr(app_st, "message", "")

        active_dep = getattr(app_info, "active_deployment", None)
        active_dep_id = ""
        dep_status = ""
        if active_dep:
            active_dep_id = getattr(active_dep, "deployment_id", "")
            dep_st = getattr(active_dep, "status", None)
            if dep_st:
                dep_status = getattr(dep_st, "state", "")
                if hasattr(dep_status, "value"):
                    dep_status = dep_status.value

        pending_dep = getattr(app_info, "pending_deployment", None)
        pend_status = ""
        pend_dep_id = ""
        if pending_dep:
            pend_dep_id = getattr(pending_dep, "deployment_id", "")
            pend_st = getattr(pending_dep, "status", None)
            if pend_st:
                pend_status = getattr(pend_st, "state", "")
                if hasattr(pend_status, "value"):
                    pend_status = pend_status.value

        our_deploy_is_pending = deployment_id and pend_dep_id and str(pend_dep_id) == str(deployment_id)
        our_deploy_is_active = deployment_id and active_dep_id and str(active_dep_id) == str(deployment_id)

        if our_deploy_is_pending:
            mins_elapsed = elapsed // 60
            mins_remaining = max(0, 10 - mins_elapsed)
            msg = random.choice(wait_msgs)
            progress(mins_elapsed, f"deploying ({pend_status}) | {msg}", remaining=mins_remaining)
            time.sleep(60)
            elapsed += 60
            continue

        if app_state == "RUNNING":
            app_url = getattr(app_info, "url", "") or f"{host}/apps/{APP_NAME}"
            print()
            ok(f"{_B}App deployed and RUNNING!{_W}")
            print(f"    Deployment: {dep_status}")
            print(f"    URL: {_C}{app_url}{_W}")
            deploy_done = True
            break

        if app_state == "CRASHED" and (our_deploy_is_active or not deployment_id):
            print()
            err("App CRASHED after deployment!")
            print(f"    Message: {app_msg}")
            print(f"    Deployment status: {dep_status}")
            print("    Check app logs in the Apps UI for details")
            deploy_done = True
            break

        if "FAILED" in str(dep_status).upper() or "FAILED" in str(pend_status).upper():
            print()
            err("Deployment FAILED!")
            print(f"    App status: {app_state} - {app_msg}")
            print(f"    Deployment: {dep_status or pend_status}")
            print("    Check the Apps UI for details")
            deploy_done = True
            break

        mins_elapsed = elapsed // 60
        mins_remaining = max(0, 10 - mins_elapsed)
        msg = random.choice(wait_msgs)
        detail = f"app={app_state}"
        if pend_status:
            detail += f", deploy={pend_status}"
        elif dep_status:
            detail += f", deploy={dep_status}"
        progress(mins_elapsed, f"{detail} | {msg}", remaining=mins_remaining)
    except Exception as ex:
        mins_elapsed = elapsed // 60
        progress(mins_elapsed, f"checking... ({ex})")

    time.sleep(60)
    elapsed += 60

if not deploy_done:
    app_url = f"{host}/apps/{APP_NAME}"
    warn("Deployment not confirmed after 10 min")
    print(f"    Check manually: {app_url}")

# --- Grant CAN_USE on the app to all users ---
from databricks.sdk.service.apps import AppAccessControlRequest, AppPermissionLevel
try:
    w.apps.update_permissions(
        app_name=APP_NAME,
        access_control_list=[
            AppAccessControlRequest(
                group_name="account users",
                permission_level=AppPermissionLevel.CAN_USE,
            ),
        ],
    )
    ok("Granted CAN_USE on app to account users")
except Exception as e:
    warn(f"Could not set app permissions: {e}")

ok(f"APP_NAME = {APP_NAME}")

# COMMAND ----------

# Cell 9: Grant Permissions + Summary
from databricks.sdk.service.iam import AccessControlRequest, PermissionLevel

# Warehouse access via SDK
try:
    w.permissions.set(
        request_object_type="sql/warehouses",
        request_object_id=WAREHOUSE_ID,
        access_control_list=[
            AccessControlRequest(
                group_name="account users",
                permission_level=PermissionLevel.CAN_USE,
            )
        ],
    )
    ok("Warehouse permissions granted")
except Exception as e:
    warn(f"Could not set warehouse permissions: {e}")

# Summary
print()
print(f"{_G}============================================================{_W}")
print(f"  {_B}AGENT SETUP COMPLETE{_W}")
print(f"{_G}============================================================{_W}")
print(f"  Catalog/Schema:  {_C}amadeus.airops{_W}")
print(f"  Warehouse:       {_C}{WAREHOUSE_ID}{_W}")
print(f"  Genie Space:     {_C}{GENIE_SPACE_ID or 'N/A'}{_W}")
print(f"  KA Endpoint:     {_C}{KA_ENDPOINT or 'N/A'}{_W}")
print(f"  MLflow Exp:      {_C}{exp_id}{_W}")
print(f"  Agent Code:      {_C}{WORKSPACE_PATH}{_W}")
print(f"  App:             {_C}{app_url}{_W}")
print(f"{_G}============================================================{_W}")
