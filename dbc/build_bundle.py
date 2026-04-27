#!/usr/bin/env python3
"""
Vocareum Bundle Creator for Agent Forge.

Reads the Agent Forge repo, optionally builds the React frontend,
and generates a Vocareum courseware folder:

    dbc/output/courseware/
    ├── config.json
    └── agent-forge-setup.zip
        ├── agent_forge_setup.py       (notebook — one cell per step)
        ├── agent/                     (Python source, plain files)
        ├── tools/
        ├── data/
        ├── prompt/
        ├── config/
        ├── pyproject.toml
        └── app/client/dist/           (pre-built frontend, if available)

All files sit alongside the notebook in the Databricks file browser.
No base64, no binary blobs in the notebook.

Usage:
    python dbc/build_bundle.py
    python dbc/build_bundle.py --skip-frontend
    python dbc/build_bundle.py --output /tmp/out
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DEFAULT = ROOT / "dbc" / "output" / "courseware"

# ---------------------------------------------------------------------------
# Constants used inside the generated notebook
# ---------------------------------------------------------------------------
CATALOG = "dbacademy"
SCHEMA = "airops"
VS_ENDPOINT = "agent-forge-vs"
VS_EMBEDDING_MODEL = "databricks-bge-large-en"
APP_NAME = "agent-forge"

# ANSI helpers (build script output only)
G, Y, R, C, W = "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[0m"
BOLD = "\033[1m"

# ---------------------------------------------------------------------------
# Source files to include in the zip (alongside the notebook)
# ---------------------------------------------------------------------------
BUNDLE_FILES: list[str] = [
    # Agent code
    "agent/__init__.py",
    "agent/agent.py",
    "agent/utils.py",
    "agent/genie_capture.py",
    "agent/start_server.py",
    # Tools
    "tools/__init__.py",
    "tools/sql_executor.py",
    "tools/query_flights_at_risk.py",
    "tools/update_flight_risk.py",
    "tools/query_checkin_metrics.py",
    "tools/query_passengers_ka.py",
    # Data utilities
    "data/__init__.py",
    "data/py/__init__.py",
    "data/py/sql_utils.py",
    # SQL
    "data/init/create_flights.sql",
    "data/proc/update_flight_risk.sql",
    "data/func/checkin_metrics.sql",
    "data/func/flights_at_risk.sql",
    # Prompts
    "prompt/main.prompt",
    "prompt/knowledge.base",
    # Config
    "config/ka/ka_passengers.yml",
    "config/ka/output_format.yml",
    "config/vector-search/vs_passengers.yml",
    # Project
    "pyproject.toml",
]

PDF_DIR = ROOT / "data" / "pdf"
FRONTEND_DIR = ROOT / "app" / "client" / "dist"
SERVER_DIR = ROOT / "app" / "server" / "dist"


# ---------------------------------------------------------------------------
# Frontend build
# ---------------------------------------------------------------------------

def build_frontend(skip: bool = False) -> bool:
    """Build React frontend. Returns True if dist/ exists after."""
    if skip:
        print(f"  {Y}[!]{W} --skip-frontend: skipping npm build")
        return FRONTEND_DIR.exists()

    app_dir = ROOT / "app"
    if not (app_dir / "package.json").exists():
        print(f"  {Y}[!]{W} app/package.json not found, skipping frontend build")
        return FRONTEND_DIR.exists()

    if not shutil.which("npm"):
        print(f"  {Y}[!]{W} npm not found, skipping frontend build")
        return FRONTEND_DIR.exists()

    print(f"  {C}[*]{W} Running npm install + build in app/client ...")
    try:
        subprocess.run(["npm", "install"], cwd=str(app_dir), check=True,
                        capture_output=True, timeout=120)
        subprocess.run(["npm", "run", "build:client"], cwd=str(app_dir), check=True,
                        capture_output=True, timeout=120)
        print(f"  {G}[+]{W} Frontend built")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"  {Y}[!]{W} Frontend build failed: {e}")
        return FRONTEND_DIR.exists()


# ---------------------------------------------------------------------------
# Notebook cell generators
# ---------------------------------------------------------------------------
CELL_SEP = "\n# COMMAND ----------\n\n"


def _cell_header() -> str:
    return textwrap.dedent('''\
        # Databricks notebook source
        # MAGIC %md
        # MAGIC # Agent Forge - Workspace Setup
        # MAGIC
        # MAGIC This notebook provisions the complete Agent Forge environment:
        # MAGIC 1. Schema & grants
        # MAGIC 2. Tables & seed data
        # MAGIC 3. Stored procedures & functions
        # MAGIC 4. Upload agent code to workspace
        # MAGIC 5. MLflow experiment
        # MAGIC 6. Genie space
        # MAGIC 7. Vector Search index
        # MAGIC 8. Deploy Databricks App
        # MAGIC 9. Permissions & summary
        # MAGIC
        # MAGIC All source files are in the same folder as this notebook.
    ''')


def _cell_pip_and_constants() -> str:
    return textwrap.dedent(f'''\
        # MAGIC %pip install databricks-sdk databricks-langchain mlflow langchain langgraph \\
        # MAGIC   langchain-community langchain-openai python-dotenv pyyaml fastapi uvicorn \\
        # MAGIC   openai pydantic pydantic-settings requests httpx pandas pyarrow tenacity \\
        # MAGIC   rich tabulate flask flask-cors pypdf databricks-vectorsearch
        # MAGIC %restart_python

        # COMMAND ----------

        CATALOG = "{CATALOG}"
        SCHEMA = "{SCHEMA}"
        SCHEMA_QUALIFIED = f"`{{CATALOG}}`.`{{SCHEMA}}`"
        VS_ENDPOINT = "{VS_ENDPOINT}"
        VS_EMBEDDING_MODEL = "{VS_EMBEDDING_MODEL}"
        APP_NAME = "{APP_NAME}"
        WORKSPACE_PATH = "/Workspace/Shared/agent-forge"

        import json, os, time
        import requests as _requests
        from databricks.sdk import WorkspaceClient
        from pathlib import Path

        w = WorkspaceClient()
        host = w.config.host.rstrip("/")
        token = w.config.authenticate().get("Authorization", "").replace("Bearer ", "")
        headers = {{"Authorization": f"Bearer {{token}}", "Content-Type": "application/json"}}

        # Where this notebook lives — source files are alongside it
        NOTEBOOK_DIR = os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get())
        # On serverless, files are FUSE-mounted under /Workspace/
        LOCAL_DIR = f"/Workspace{{NOTEBOOK_DIR}}"

        def api(method, path, **kw):
            url = f"{{host}}{{path}}" if path.startswith("/") else path
            r = _requests.request(method, url, headers=headers, **kw)
            r.raise_for_status()
            return r.json() if r.content else {{}}

        # Colored log helpers
        _G, _C, _Y, _R, _B, _W = "\\033[32m", "\\033[36m", "\\033[33m", "\\033[31m", "\\033[1m", "\\033[0m"
        _DIM = "\\033[2m"
        def ok(msg, indent=0):  print(f"{{'  ' * indent}}{{_G}}✓{{_W}} {{msg}}")
        def info(msg, indent=0): print(f"{{'  ' * indent}}{{_C}}ℹ{{_W}} {{msg}}")
        def warn(msg, indent=0): print(f"{{'  ' * indent}}{{_Y}}⚠{{_W}} {{msg}}")
        def err(msg, indent=0):  print(f"{{'  ' * indent}}{{_R}}✗{{_W}} {{msg}}")
        def progress(mins, msg, remaining=None):
            tail = f" {{_DIM}}(~{{remaining}} min to go){{_W}}" if remaining is not None else ""
            print(f"  {{_C}}[{{mins}}min]{{_W}} {{msg}}{{tail}}")

        def sql(stmt):
            """Execute SQL via Statement Execution API (async + poll)."""
            body = {{
                "warehouse_id": WAREHOUSE_ID,
                "statement": stmt,
                "wait_timeout": "0s",
            }}
            resp = api("POST", "/api/2.0/sql/statements", json=body)
            stmt_id = resp.get("statement_id", "")
            status = resp.get("status", {{}}).get("state", "")
            while status in ("PENDING", "RUNNING"):
                time.sleep(3)
                resp = api("GET", f"/api/2.0/sql/statements/{{stmt_id}}")
                status = resp.get("status", {{}}).get("state", "")
            if status not in ("SUCCEEDED", "CLOSED"):
                _err = resp.get("status", {{}}).get("error", {{}}).get("message", status)
                raise RuntimeError(f"SQL failed: {{_err}}")
            return resp

        ok("Constants and helpers loaded")
        print(f"    Notebook dir: {{NOTEBOOK_DIR}}")
        print(f"    Local dir:    {{LOCAL_DIR}}")

        # Discover warehouse
        wh_list = api("GET", "/api/2.0/sql/warehouses")
        warehouses = wh_list.get("warehouses", [])
        WAREHOUSE_ID = None
        for wh in warehouses:
            if wh.get("state") in ("RUNNING", "STARTING", "STOPPED"):
                WAREHOUSE_ID = wh["id"]
                break
        if not WAREHOUSE_ID and warehouses:
            WAREHOUSE_ID = warehouses[0]["id"]
        if not WAREHOUSE_ID:
            raise RuntimeError("No SQL warehouse found in workspace")
        ok(f"Using warehouse: {{WAREHOUSE_ID}}")
    ''')


def _cell_schema_grants() -> str:
    return textwrap.dedent(f'''\
        # Cell 1: Create Catalog + Schema + Grants
        sql("CREATE CATALOG IF NOT EXISTS `{CATALOG}`")
        sql("GRANT USE CATALOG ON CATALOG `{CATALOG}` TO `account users`")
        ok("Catalog created + USE CATALOG granted")

        sql("CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`")
        ok("Schema created")

        sql("GRANT ALL PRIVILEGES ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO `account users`")
        ok("Grants applied")
    ''')


def _cell_tables_seed() -> str:
    return textwrap.dedent(f'''\
        # Cell 2: Create Tables + Seed Data
        # Read SQL from file alongside this notebook
        sql_path = Path(LOCAL_DIR) / "data" / "init" / "create_flights.sql"
        sql_text = sql_path.read_text()
        sql_text = sql_text.replace("__SCHEMA_QUALIFIED__", SCHEMA_QUALIFIED)

        # Split into statements and execute each
        for stmt in sql_text.split(";"):
            stmt = stmt.strip()
            if stmt:
                sql(stmt)
        ok("flights table created and seeded")

        sql("GRANT SELECT ON TABLE `{CATALOG}`.`{SCHEMA}`.flights TO `account users`")
        ok("Table grants applied")
    ''')


def _cell_procedures() -> str:
    return textwrap.dedent(f'''\
        # Cell 3: Stored Procedures + Functions
        proc_path = Path(LOCAL_DIR) / "data" / "proc" / "update_flight_risk.sql"
        proc_sql = proc_path.read_text().strip()
        proc_sql = proc_sql.replace("__SCHEMA_QUALIFIED__", SCHEMA_QUALIFIED)
        sql(proc_sql)
        ok("update_flight_risk procedure created")

        sql("GRANT EXECUTE ON PROCEDURE `{CATALOG}`.`{SCHEMA}`.update_flight_risk TO `account users`")
        ok("Procedures and grants applied")
    ''')


def _cell_upload_code() -> str:
    return textwrap.dedent('''\
        # Cell 4: Upload Agent Code to Workspace
        import base64

        def upload_file(ws_path, content_bytes):
            """Upload a file to workspace via REST API."""
            b64 = base64.b64encode(content_bytes).decode("ascii")
            api("POST", "/api/2.0/workspace/import", json={
                "path": ws_path,
                "content": b64,
                "overwrite": True,
                "format": "AUTO",
            })

        def upload_tree(local_root, ws_root, extensions=None, label=None):
            """Recursively upload a directory tree to workspace."""
            local_root = Path(local_root)
            files = sorted(f for f in local_root.rglob("*") if f.is_file() and (not extensions or f.suffix in extensions))
            total_files = len(files)
            count = 0
            for local_path in files:
                rel = local_path.relative_to(local_root)
                ws_path = f"{ws_root}/{rel}"
                parent = "/".join(ws_path.split("/")[:-1])
                try:
                    api("POST", "/api/2.0/workspace/mkdirs", json={"path": parent})
                except Exception:
                    pass
                upload_file(ws_path, local_path.read_bytes())
                count += 1
                if label and total_files > 50 and count % 50 == 0:
                    print(f"    {_DIM}... {label}: {count}/{total_files} files uploaded{_W}")
            return count

        # Create target directory
        try:
            api("POST", "/api/2.0/workspace/mkdirs", json={"path": WORKSPACE_PATH})
        except Exception:
            pass

        # Upload all source directories
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
    ''')


def _cell_mlflow_experiment() -> str:
    return textwrap.dedent('''\
        # Cell 5: Create MLflow Experiment
        EXPERIMENT_NAME = "/Shared/agent-forge-experiment"
        try:
            resp = api("POST", "/api/2.0/mlflow/experiments/create", json={
                "name": EXPERIMENT_NAME,
            })
            exp_id = resp.get("experiment_id", "")
            ok(f"Experiment created: {EXPERIMENT_NAME} (id={exp_id})")
        except Exception as e:
            if "RESOURCE_ALREADY_EXISTS" in str(e):
                resp = api("POST", "/api/2.0/mlflow/experiments/get-by-name", json={
                    "experiment_name": EXPERIMENT_NAME,
                })
                exp_id = resp.get("experiment", {}).get("experiment_id", "")
                ok(f"Experiment already exists: {EXPERIMENT_NAME} (id={exp_id})")
            else:
                raise

        # Grant permissions
        try:
            api("PUT", f"/api/2.0/permissions/experiments/{exp_id}", json={
                "access_control_list": [
                    {"group_name": "users", "all_permissions": [{"permission_level": "CAN_MANAGE"}]}
                ]
            })
            ok("Experiment permissions granted")
        except Exception as e:
            warn(f"Could not set experiment permissions: {e}")
    ''')


def _cell_genie_space() -> str:
    return textwrap.dedent(f'''\
        # Cell 6: Create Genie Space
        GENIE_SPACE_ID = None
        try:
            genie_resp = api("POST", "/api/2.0/genie/spaces", json={{
                "title": "Agent Forge - Flight Check-in",
                "description": "Flight operations data for the Agent Forge AI assistant",
                "warehouse_id": WAREHOUSE_ID,
                "table_identifiers": [
                    f"{CATALOG}.{SCHEMA}.flights"
                ],
            }})
            GENIE_SPACE_ID = genie_resp.get("space_id") or genie_resp.get("id", "")
            ok(f"Genie space created: {{GENIE_SPACE_ID}}")
        except Exception as e:
            if "ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
                try:
                    spaces = api("GET", "/api/2.0/genie/spaces")
                    for sp in spaces.get("spaces", []):
                        if "Agent Forge" in sp.get("title", ""):
                            GENIE_SPACE_ID = sp.get("space_id") or sp.get("id", "")
                            break
                except Exception:
                    pass
                ok(f"Genie space already exists: {{GENIE_SPACE_ID}}")
            else:
                warn(f"Could not create Genie space: {{e}}")
                print(f"    {{_DIM}}(Non-critical — agent works without Genie){{_W}}")

        # Note: Genie permissions are not exposed through API — must be set via UI if needed
    ''')


def _cell_vector_search() -> str:
    return textwrap.dedent(f'''\
        # Cell 7: Vector Search Index
        VS_INDEX_NAME = f"{CATALOG}.{SCHEMA}.pdf_chunks_index"
        VS_TABLE_NAME = f"{CATALOG}.{SCHEMA}.pdf_chunks"

        # --- Read PDFs from the bundle (alongside this notebook) ---
        from pypdf import PdfReader

        pdf_dir = Path(LOCAL_DIR) / "data" / "pdf"
        all_chunks = []

        if pdf_dir.exists():
            for pdf_file in sorted(pdf_dir.glob("*.pdf")):
                reader = PdfReader(str(pdf_file))
                full_text = ""
                for page in reader.pages:
                    full_text += page.extract_text() or ""

                chunk_size, overlap = 1000, 200
                source_name = pdf_file.name
                for i in range(0, len(full_text), chunk_size - overlap):
                    chunk = full_text[i:i + chunk_size]
                    if chunk.strip():
                        all_chunks.append({{
                            "content": chunk,
                            "source": source_name,
                            "chunk_id": f"{{source_name}}_{{i}}",
                        }})
                ok(f"{{source_name}}: {{len([c for c in all_chunks if c['source'] == source_name])}} chunks", indent=1)
        else:
            warn("No data/pdf/ directory found alongside notebook")

        ok(f"Total chunks: {{len(all_chunks)}}")

        # --- Create Delta table ---
        sql(f"DROP TABLE IF EXISTS {{VS_TABLE_NAME}}")
        sql(f\"\"\"
            CREATE TABLE {{VS_TABLE_NAME}} (
                chunk_id STRING,
                content STRING,
                source STRING
            ) USING DELTA
            TBLPROPERTIES (delta.enableChangeDataFeed = true)
        \"\"\")
        ok("pdf_chunks table created")

        # Insert chunks in batches
        batch_size = 10
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i+batch_size]
            values = []
            for c in batch:
                esc_content = c["content"].replace("'", "''").replace("\\\\", "\\\\\\\\")
                esc_source = c["source"].replace("'", "''")
                esc_id = c["chunk_id"].replace("'", "''")
                values.append(f"('{{esc_id}}', '{{esc_content}}', '{{esc_source}}')")
            sql(f"INSERT INTO {{VS_TABLE_NAME}} VALUES {{', '.join(values)}}")
        ok(f"Inserted {{len(all_chunks)}} chunks")

        sql(f"GRANT SELECT ON TABLE {{VS_TABLE_NAME}} TO `account users`")

        # --- Ensure VS endpoint exists ---
        import random

        print()
        info(f"Checking VS endpoint '{{VS_ENDPOINT}}'...")

        endpoint_exists = False
        try:
            resp = api("GET", f"/api/2.0/vector-search/endpoints/{{VS_ENDPOINT}}")
            state = resp.get("endpoint_status", {{}}).get("state", "")
            ok(f"VS endpoint exists (state: {{state}})")
            endpoint_exists = True
        except Exception:
            info("VS endpoint not found -- creating it now...")
            try:
                api("POST", "/api/2.0/vector-search/endpoints", json={{
                    "name": VS_ENDPOINT,
                    "endpoint_type": "STANDARD",
                }})
                ok("VS endpoint creation started")
            except Exception as e:
                if "ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
                    ok("VS endpoint already exists (race condition)")
                    endpoint_exists = True
                else:
                    raise

        # --- Wait for endpoint to be ONLINE ---
        wait_msgs = [
            "Brewing coffee while the endpoint spins up...",
            "Vector Search is warming up its neurons...",
            "Still provisioning -- good things take time...",
            "The bits are being arranged very carefully...",
            "Endpoint is getting its ducks in a row...",
            "Patience, young padawan...",
            "Almost there... probably...",
            "VS endpoint is doing push-ups before going live...",
            "Somewhere, a GPU is working very hard for you...",
            "This is the cloud equivalent of watching paint dry...",
            "Fun fact: you could make a sandwich while waiting...",
            "The hamsters powering the endpoint are running fast...",
            "Provisioning... because instant gratification is overrated...",
            "Vector Search endpoint is putting on its cape...",
            "Loading awesomeness... please stand by...",
        ]

        print()
        info("Waiting for VS endpoint to come ONLINE.")
        print(f"    {{_DIM}}This typically takes 15-20 minutes. Grab a coffee!{{_W}}")
        print()

        elapsed = 0
        vs_endpoint_online = False
        for attempt in range(120):
            try:
                resp = api("GET", f"/api/2.0/vector-search/endpoints/{{VS_ENDPOINT}}")
                state = resp.get("endpoint_status", {{}}).get("state", "")
                if state == "ONLINE":
                    print()
                    ok(f"{{_B}}VS endpoint ONLINE!{{_W}}")
                    vs_endpoint_online = True
                    break
            except Exception:
                state = "provisioning"

            # Poll: every 5 min for first 15 min, then every 1 min
            if elapsed < 900:
                interval = 300
            else:
                interval = 60

            mins_elapsed = elapsed // 60
            mins_remaining = max(0, 20 - mins_elapsed)
            msg = random.choice(wait_msgs)
            progress(mins_elapsed, msg, remaining=mins_remaining)

            time.sleep(interval)
            elapsed += interval

        if not vs_endpoint_online:
            warn("VS endpoint not ONLINE after 20 min -- attempting index creation anyway")

        # --- Create index via VectorSearchClient ---
        from databricks.vector_search.client import VectorSearchClient

        vs_client = VectorSearchClient(
            workspace_url=host,
            personal_access_token=token,
            disable_notice=True,
        )

        try:
            vs_client.create_delta_sync_index(
                endpoint_name=VS_ENDPOINT,
                index_name=VS_INDEX_NAME,
                source_table_name=VS_TABLE_NAME,
                primary_key="chunk_id",
                pipeline_type="TRIGGERED",
                embedding_source_column="content",
                embedding_model_endpoint_name=VS_EMBEDDING_MODEL,
            )
            ok("VS index creation started")
        except Exception as e:
            if "ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
                ok("VS index already exists")
            else:
                raise

        # --- Wait for index to sync ---
        print()
        info("Waiting for VS index to sync and become ready...")
        print(f"    {{_DIM}}This may take another 5-10 minutes.{{_W}}")
        print()

        idx = vs_client.get_index(index_name=VS_INDEX_NAME, endpoint_name=VS_ENDPOINT)
        elapsed = 0
        for attempt in range(120):
            desc = idx.describe()
            status_info = desc.get("status", {{}})
            ready = status_info.get("ready", False)
            row_count = status_info.get("indexed_row_count", "?")
            if ready:
                print()
                ok(f"{{_B}}VS index ONLINE{{_W}} ({{row_count}} rows indexed)")
                break

            mins_elapsed = elapsed // 60
            mins_remaining = max(0, 10 - mins_elapsed)
            msg = random.choice(wait_msgs)
            progress(mins_elapsed, f"{{msg}} (rows={{row_count}})", remaining=mins_remaining)

            time.sleep(60)
            elapsed += 60
        else:
            warn("VS index not ready in 20 min -- continuing anyway")

        ok(f"VS_INDEX_NAME = {{VS_INDEX_NAME}}")
    ''')


def _cell_deploy_app() -> str:
    return textwrap.dedent(f'''\
        # Cell 8: Deploy Databricks App

        # Generate app.yaml in the workspace target
        app_yaml_content = """command: ["uv", "run", "python", "-c", "from agent.start_server import main; main()"]
        env:
          - name: MLFLOW_TRACKING_URI
            value: "databricks"
          - name: MLFLOW_REGISTRY_URI
            value: "databricks-uc"
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
            value: "{CATALOG}.{SCHEMA}"
          - name: DATABRICKS_WAREHOUSE_ID
            value: "__WAREHOUSE_ID__"
          - name: PROJECT_GENIE_CHECKIN
            value: "__GENIE_SPACE_ID__"
          - name: PROJECT_VS_INDEX
            value: "__VS_INDEX__"
          - name: PROJECT_VS_ENDPOINT
            value: "{VS_ENDPOINT}"
        """
        app_yaml_content = app_yaml_content.replace("__WAREHOUSE_ID__", WAREHOUSE_ID)
        app_yaml_content = app_yaml_content.replace("__GENIE_SPACE_ID__", GENIE_SPACE_ID or "")
        app_yaml_content = app_yaml_content.replace("__VS_INDEX__", VS_INDEX_NAME)

        upload_file(f"{{WORKSPACE_PATH}}/app.yaml", app_yaml_content.encode("utf-8"))
        ok("app.yaml uploaded to workspace")

        # --- Create app ---
        import random

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

        print()
        info(f"Creating app '{{APP_NAME}}'...")

        app_exists = False
        try:
            existing = api("GET", f"/api/2.0/apps/{{APP_NAME}}")
            c_state = existing.get("compute_status", {{}}).get("state", "unknown")
            app_url = existing.get("url", "unknown")
            ok(f"App already exists: {{APP_NAME}}")
            print(f"    Compute: {{c_state}}")
            print(f"    URL: {{_C}}{{app_url}}{{_W}}")
            app_exists = True
        except Exception:
            info("App not found -- creating it now...")
            try:
                api("POST", "/api/2.0/apps", json={{
                    "name": APP_NAME,
                    "description": "Agent Forge - AI Ops Advisor for flight operations",
                }})
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
        print(f"    {{_DIM}}This typically takes 2-5 minutes.{{_W}}")
        print()

        elapsed = 0
        app_ready = False
        for attempt in range(30):
            try:
                app_info = api("GET", f"/api/2.0/apps/{{APP_NAME}}")
                compute_state = app_info.get("compute_status", {{}}).get("state", "unknown")
                compute_msg = app_info.get("compute_status", {{}}).get("message", "")

                if compute_state == "ACTIVE":
                    print()
                    ok(f"{{_B}}App compute is ACTIVE!{{_W}}")
                    app_ready = True
                    break
                elif compute_state in ("ERROR", "FAILED"):
                    print()
                    err(f"App compute failed: {{compute_state}} - {{compute_msg}}")
                    break

                mins_elapsed = elapsed // 60
                mins_remaining = max(0, 5 - mins_elapsed)
                msg = random.choice(wait_msgs)
                progress(mins_elapsed, f"compute={{compute_state}} | {{msg}}", remaining=mins_remaining)
            except Exception as ex:
                mins_elapsed = elapsed // 60
                progress(mins_elapsed, f"checking... ({{ex}})")

            time.sleep(60)
            elapsed += 60

        if not app_ready and not app_exists:
            warn("App compute not active after 5 min -- attempting deployment anyway")

        # --- Wait for any pending deployment to clear ---
        print()
        info("Checking for pending deployments...")
        for wait_attempt in range(20):
            try:
                app_info = api("GET", f"/api/2.0/apps/{{APP_NAME}}")
                pending_dep = app_info.get("pending_deployment")
                if not pending_dep:
                    ok("No pending deployment -- ready to deploy")
                    break
                pend_state = pending_dep.get("status", {{}}).get("state", "") if pending_dep else ""
                mins = wait_attempt
                msg = random.choice(wait_msgs)
                progress(mins, f"Pending deployment ({{pend_state}}) | {{msg}}")
            except Exception:
                pass
            time.sleep(60)
        else:
            warn("Pending deployment still active after 20 min -- attempting deploy anyway")

        # --- Deploy (with retry) ---
        print()
        info(f"Deploying app from {{WORKSPACE_PATH}}...")
        print(f"    {{_DIM}}This typically takes 5-10 minutes.{{_W}}")
        print()

        deployment_id = ""
        for deploy_try in range(3):
            try:
                deploy_resp = api("POST", f"/api/2.0/apps/{{APP_NAME}}/deployments", json={{
                    "source_code_path": WORKSPACE_PATH,
                }})
                deployment_id = deploy_resp.get("deployment_id", "")
                ok(f"Deployment initiated (id: {{deployment_id}})")
                break
            except Exception as e:
                _err = str(e)
                if "pending deployment" in _err.lower():
                    warn(f"[retry {{deploy_try+1}}/3] Pending deployment still active, waiting 2 min...")
                    time.sleep(120)
                else:
                    err(f"Deploy call failed: {{e}}")
                    print("    You can deploy manually from the Apps UI")
                    break

        # --- Poll deployment status ---
        # Wait for OUR deployment to become active before checking app state
        elapsed = 0
        deploy_done = False
        for attempt in range(30):
            try:
                app_info = api("GET", f"/api/2.0/apps/{{APP_NAME}}")
                app_state = app_info.get("app_status", {{}}).get("state", "unknown")
                app_msg = app_info.get("app_status", {{}}).get("message", "")

                active_dep = app_info.get("active_deployment", {{}})
                active_dep_id = active_dep.get("deployment_id", "") if active_dep else ""
                dep_state = active_dep.get("status", {{}}).get("state", "") if active_dep else ""

                pending_dep = app_info.get("pending_deployment", {{}})
                pend_dep_id = pending_dep.get("deployment_id", "") if pending_dep else ""
                pend_state = pending_dep.get("status", {{}}).get("state", "") if pending_dep else ""

                our_deploy_is_pending = deployment_id and pend_dep_id and str(pend_dep_id) == str(deployment_id)
                our_deploy_is_active = deployment_id and active_dep_id and str(active_dep_id) == str(deployment_id)

                if our_deploy_is_pending:
                    mins_elapsed = elapsed // 60
                    mins_remaining = max(0, 10 - mins_elapsed)
                    msg = random.choice(wait_msgs)
                    progress(mins_elapsed, f"deploying ({{pend_state}}) | {{msg}}", remaining=mins_remaining)
                    time.sleep(60)
                    elapsed += 60
                    continue

                if app_state == "RUNNING":
                    app_url = app_info.get("url", "") or f"{{host}}/apps/{{APP_NAME}}"
                    print()
                    ok(f"{{_B}}App deployed and RUNNING!{{_W}}")
                    print(f"    Deployment: {{dep_state}}")
                    print(f"    URL: {{_C}}{{app_url}}{{_W}}")
                    deploy_done = True
                    break

                if app_state == "CRASHED" and (our_deploy_is_active or not deployment_id):
                    print()
                    err("App CRASHED after deployment!")
                    print(f"    Message: {{app_msg}}")
                    print(f"    Deployment status: {{dep_state}}")
                    print("    Check app logs in the Apps UI for details")
                    deploy_done = True
                    break

                if "FAILED" in str(dep_state).upper() or "FAILED" in str(pend_state).upper():
                    print()
                    err("Deployment FAILED!")
                    print(f"    App status: {{app_state}} - {{app_msg}}")
                    print(f"    Deployment: {{dep_state or pend_state}}")
                    print("    Check the Apps UI for details")
                    deploy_done = True
                    break

                mins_elapsed = elapsed // 60
                mins_remaining = max(0, 10 - mins_elapsed)
                msg = random.choice(wait_msgs)
                detail = f"app={{app_state}}"
                if pend_state:
                    detail += f", deploy={{pend_state}}"
                elif dep_state:
                    detail += f", deploy={{dep_state}}"
                progress(mins_elapsed, f"{{detail}} | {{msg}}", remaining=mins_remaining)
            except Exception as ex:
                mins_elapsed = elapsed // 60
                progress(mins_elapsed, f"checking... ({{ex}})")

            time.sleep(60)
            elapsed += 60

        if not deploy_done:
            app_url = f"{{host}}/apps/{{APP_NAME}}"
            print()
            warn("Deployment not confirmed after 10 min")
            print(f"    Check manually: {{_C}}{{app_url}}{{_W}}")

        print()
        ok(f"APP_NAME = {{APP_NAME}}")
    ''')


def _cell_permissions_summary() -> str:
    return textwrap.dedent(f'''\
        # Cell 9: Grant Permissions + Summary

        # Warehouse access
        try:
            api("PUT", f"/api/2.0/permissions/sql/warehouses/{{WAREHOUSE_ID}}", json={{
                "access_control_list": [
                    {{"group_name": "users", "all_permissions": [{{"permission_level": "CAN_USE"}}]}}
                ]
            }})
            ok("Warehouse permissions granted")
        except Exception as e:
            warn(f"Could not set warehouse permissions: {{e}}")

        # VS endpoint access
        try:
            api("PUT", f"/api/2.0/permissions/vector-search-endpoints/{VS_ENDPOINT}", json={{
                "access_control_list": [
                    {{"group_name": "users", "all_permissions": [{{"permission_level": "CAN_USE"}}]}}
                ]
            }})
            ok("VS endpoint permissions granted")
        except Exception as e:
            warn(f"Could not set VS endpoint permissions: {{e}}")

        # Summary
        print()
        print(f"{{_G}}{'=' * 60}{{_W}}")
        print(f"  {{_B}}AGENT FORGE SETUP COMPLETE{{_W}}")
        print(f"{{_G}}{'=' * 60}{{_W}}")
        print(f"  Catalog/Schema:  {{_C}}{CATALOG}.{SCHEMA}{{_W}}")
        print(f"  Warehouse:       {{_C}}{{WAREHOUSE_ID}}{{_W}}")
        print(f"  Genie Space:     {{_C}}{{GENIE_SPACE_ID or 'N/A'}}{{_W}}")
        print(f"  VS Index:        {{_C}}{{VS_INDEX_NAME}}{{_W}}")
        print(f"  VS Endpoint:     {{_C}}{VS_ENDPOINT}{{_W}}")
        print(f"  MLflow Exp:      {{_C}}{{exp_id}}{{_W}}")
        print(f"  Agent Code:      {{_C}}{{WORKSPACE_PATH}}{{_W}}")
        print(f"  App:             {{_C}}{{app_url}}{{_W}}")
        print(f"{{_G}}{'=' * 60}{{_W}}")
    ''')


# ---------------------------------------------------------------------------
# config.json
# ---------------------------------------------------------------------------

def generate_config_json() -> dict:
    return {
        "workspace_setup": {
            "src": "agent-forge-setup.zip",
            "entry": "agent_forge_setup",
            "serverless_job_cluster": True,
            "timeout_minutes": 30,
        },
        "user_config": {
            "warehouse": {
                "name": "shared_wh",
            },
        },
        "shared_vector_search_endpoints": [
            {
                "name": VS_ENDPOINT,
                "endpoint_type": "STANDARD",
            },
        ],
        "enable_tokens": True,
    }


# ---------------------------------------------------------------------------
# Packaging
# ---------------------------------------------------------------------------

def create_setup_zip(output_path: Path, notebook_content: str, has_frontend: bool) -> None:
    """Create the setup zip with notebook + all source files alongside it."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # The notebook itself
        zf.writestr("agent_forge_setup.py", notebook_content)

        # All source files
        for rel_path in BUNDLE_FILES:
            full_path = ROOT / rel_path
            if full_path.exists():
                zf.write(str(full_path), rel_path)

        # PDFs
        if PDF_DIR.exists():
            for pdf_file in PDF_DIR.glob("*.pdf"):
                arc_path = f"data/pdf/{pdf_file.name}"
                zf.write(str(pdf_file), arc_path)

        # Frontend dist (if available)
        if has_frontend and FRONTEND_DIR.exists():
            for f in FRONTEND_DIR.rglob("*"):
                if f.is_file():
                    arc_path = f"app/client/dist/{f.relative_to(FRONTEND_DIR)}"
                    zf.write(str(f), arc_path)

        # Server dist (Node Express server)
        if SERVER_DIR.exists():
            for f in SERVER_DIR.rglob("*"):
                if f.is_file():
                    arc_path = f"app/server/dist/{f.relative_to(SERVER_DIR)}"
                    zf.write(str(f), arc_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build Vocareum courseware bundle for Agent Forge")
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT, help="Output directory")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip npm build of React frontend")
    args = parser.parse_args()

    output_dir: Path = args.output
    print(f"\n{BOLD}Agent Forge — Vocareum Bundle Creator{W}")
    print(f"  Output: {C}{output_dir}{W}\n")

    # Clean output
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Frontend
    print(f"{BOLD}1. Frontend{W}")
    has_frontend = build_frontend(skip=args.skip_frontend)
    if has_frontend:
        count = sum(1 for _ in FRONTEND_DIR.rglob("*") if _.is_file())
        print(f"  {G}[+]{W} Frontend client dist: {count} files")
    else:
        print(f"  {Y}[!]{W} No frontend client dist")
    if SERVER_DIR.exists():
        count = sum(1 for _ in SERVER_DIR.rglob("*") if _.is_file())
        print(f"  {G}[+]{W} Frontend server dist: {count} files")
    else:
        print(f"  {Y}[!]{W} No frontend server dist")

    # 2. Verify source files
    print(f"\n{BOLD}2. Source files{W}")
    missing = []
    for rel_path in BUNDLE_FILES:
        full_path = ROOT / rel_path
        if full_path.exists():
            print(f"  {G}[+]{W} {rel_path}")
        elif rel_path.endswith("__init__.py"):
            # Create missing __init__.py
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text("")
            print(f"  {Y}[!]{W} {rel_path} (created empty)")
        else:
            missing.append(rel_path)
            print(f"  {R}[-]{W} {rel_path} NOT FOUND")

    # PDFs
    pdf_count = 0
    if PDF_DIR.exists():
        for pdf_file in PDF_DIR.glob("*.pdf"):
            print(f"  {G}[+]{W} data/pdf/{pdf_file.name}")
            pdf_count += 1
    if not pdf_count:
        print(f"  {Y}[!]{W} No PDFs in data/pdf/")

    # 3. Generate notebook
    print(f"\n{BOLD}3. Generating notebook{W}")
    cells = [
        _cell_header(),
        _cell_pip_and_constants(),
        _cell_schema_grants(),
        _cell_tables_seed(),
        _cell_procedures(),
        _cell_upload_code(),
        _cell_mlflow_experiment(),
        _cell_genie_space(),
        _cell_vector_search(),
        _cell_deploy_app(),
        _cell_permissions_summary(),
    ]
    notebook_content = CELL_SEP.join(cells)
    print(f"  {G}[+]{W} {len(cells)} cells, {len(notebook_content):,} chars")

    # 4. Package
    print(f"\n{BOLD}4. Packaging{W}")

    setup_zip = output_dir / "agent-forge-setup.zip"
    create_setup_zip(setup_zip, notebook_content, has_frontend)
    print(f"  {G}[+]{W} {setup_zip.name} ({setup_zip.stat().st_size:,} bytes)")

    # config.json
    config_path = output_dir / "config.json"
    config = generate_config_json()
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"  {G}[+]{W} config.json")

    # Summary
    print(f"\n{BOLD}Bundle complete!{W}")
    print(f"  Output: {C}{output_dir}{W}")
    for f in sorted(output_dir.iterdir()):
        print(f"    {f.name} ({f.stat().st_size:,} bytes)")

    # Show zip contents summary
    with zipfile.ZipFile(setup_zip) as zf:
        print(f"\n  Zip contents: {len(zf.namelist())} files")
        dirs = sorted(set(n.split("/")[0] for n in zf.namelist()))
        print(f"  Top-level: {', '.join(dirs)}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
