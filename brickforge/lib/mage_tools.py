"""
Mage tools - read and exec tools that call existing BrickForge HTTP endpoints.

All tools are async. Long-running exec tools stream progress via sse_queue.
"""

import os
import json
import asyncio
from typing import Any

import httpx


def _base_url() -> str:
    port = os.environ.get("VISUAL_PORT", os.environ.get("DATABRICKS_APP_PORT", "9000"))
    return f"http://localhost:{port}"


def _enable_gen_data():
    """Mark this project as using Mage-generated data.
    Sets use_gen_data=true (so gen endpoints see artifacts) and
    use_demo_data=false (Mage projects use their own data, not demos)."""
    from brickforge.server import config as _config
    _config.set("data.use_gen_data", True)
    _config.set("data.use_demo_data", False)


class MageToolkit:
    """Collection of tools Mage can call. Holds SSE queue for progress streaming."""

    def __init__(self, sse_queue: asyncio.Queue, mode: str = "magic"):
        self.sse_queue = sse_queue
        self.mode = mode
        self.spec_confirmed = False
        self.spec_json: dict | None = None  # Structured spec from present_spec

    # ── Read tools (no side effects) ─────────────────────────────────────

    async def read_status(self) -> str:
        """Get all setup block states (done/missing)."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.get("/api/setup/status")
            return resp.text

    async def read_config(self) -> str:
        """Get current config values (workspace, model, schema, features, etc.)."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.get("/api/setup/env")
            return resp.text

    async def read_tables(self) -> str:
        """Get table names and column schemas."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.get("/api/gen/tables")
            return resp.text

    async def read_functions(self) -> str:
        """Get UC functions and procedures list."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.get("/api/gen/routines")
            return resp.text

    async def read_prompt(self) -> str:
        """Get current system prompt text."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.get("/api/setup/prompts")
            return resp.text

    async def read_warehouses(self) -> str:
        """List available SQL warehouses (id, name, state)."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.get("/api/setup/resources", params={"type": "warehouses"})
            return resp.text

    async def read_catalogs(self) -> str:
        """List available Unity Catalog catalogs."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.get("/api/setup/resources", params={"type": "catalogs"})
            return resp.text

    async def read_models(self) -> str:
        """List available serving endpoints."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.get("/api/setup/models")
            return resp.text

    async def read_features(self) -> str:
        """Get feature and brick toggle states."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.get("/api/setup/status")
            data = resp.json()
            return json.dumps({
                "features": data.get("features", {}),
                "bricks": data.get("bricks", {}),
            })

    async def read_deploy_status(self) -> str:
        """Get app name, deploy state."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.get("/api/setup/status")
            data = resp.json()
            return json.dumps({
                "app_name": data.get("deploy", {}).get("app_name"),
                "deploy_status": data.get("deploy", {}).get("status"),
            })

    # ── Discovery action tools ────────────────────────────────────────────

    async def present_spec(self, spec: dict) -> str:
        """Present the agent spec for user approval. Validates JSON, shows summary, waits for confirmation.
        The spec must include 'entities' (list of table definitions) and 'actions' (list of function/procedure definitions)."""
        # Validate required fields
        if not isinstance(spec, dict):
            return "Invalid spec: must be a JSON object"
        if not spec.get("entities"):
            return "Invalid spec: must include 'entities' (list of tables with fields)"
        if not spec.get("actions"):
            return "Invalid spec: must include 'actions' (list of functions/procedures)"

        # Store the structured spec
        self.spec_json = spec

        # Generate user-facing summary based on mode
        if self.mode == "magic":
            bullets = []
            for a in spec["actions"]:
                desc = a.get("description", a.get("name", ""))
                bullets.append(f"- {desc}")
            summary = "Here's what your agent will do:\n\n" + "\n".join(bullets) + "\n\nSound right?"
        else:
            entities = ", ".join(e["name"] for e in spec["entities"])
            actions_lines = []
            for a in spec["actions"]:
                params = ", ".join(a.get("params", []))
                actions_lines.append(f"  {a['name']}({params}) - {a.get('description', '')}")
            lifecycle = spec.get("lifecycle", "")
            naming = spec.get("naming", {})
            summary = (
                f"**Tables:** {entities}\n"
                f"**Functions:**\n" + "\n".join(actions_lines) + "\n"
                f"**Lifecycle:** {lifecycle}\n"
                f"**Schema:** {naming.get('schema', 'TBD')}\n"
                f"**App:** {naming.get('app', 'TBD')}\n\n"
                f"Confirm?"
            )

        # Send summary directly to user
        await self.sse_queue.put({
            "event": "message",
            "data": {"role": "assistant", "text": summary},
        })

        return "Spec presented to user. Do NOT repeat or rephrase it. Wait for their confirmation."

    # ── Direct build tools (no subprocess, no gen endpoint) ───────────────

    async def generate_routine(self, query_spec: dict) -> str:
        """Generate a UC function or procedure from a structured JSON query spec.
        Uses the SQL template engine - deterministic, no LLM writes SQL.
        Returns the generated SQL string."""
        from brickforge.data.gen.sql_template_engine import generate_sql, validate_spec, build_schema_lookup

        # Load table schemas from config
        from brickforge.server import config as _config
        tables = _config.get("data.table_schemas") or []
        schema_lookup = build_schema_lookup(tables)

        # Refuse to generate without schema data - prevents hallucinated column names
        if not schema_lookup:
            return "No table schemas found in config. Call create_tables_sql first to define tables before generating routines."

        # Validate spec
        errors = validate_spec(query_spec, schema_lookup)
        if errors:
            return f"Spec validation failed:\n" + "\n".join(f"- {e}" for e in errors)

        # Generate SQL
        sql = generate_sql(query_spec, schema_lookup)

        # Save to project gen dir
        routine_name = query_spec["name"]
        routine_type = query_spec.get("type", "function")
        subdir = "func" if routine_type == "function" else "proc"
        out_dir = gen_dir() / subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{routine_name}.sql").write_text(sql)

        await self.sse_queue.put({"event": "progress", "data": {"line": f"[+] Generated {routine_name}.sql ({routine_type})\n"}})
        return f"Generated {routine_name}.sql:\n{sql}"

    async def create_tables_sql(self, entities: list) -> str:
        """Generate CREATE TABLE SQL from spec entities. Deterministic, no LLM.
        Each entity has name, fields (with types). Writes SQL files to gen/init/."""
        from brickforge.lib.project_paths import gen_dir

        out_dir = gen_dir() / "init"
        out_dir.mkdir(parents=True, exist_ok=True)
        created = []

        manifest_tables = []

        for entity in entities:
            name = entity["name"]
            fields = entity.get("fields", [])
            # Normalize fields to [{name, type}]
            norm_cols = []
            col_defs = []
            for f in fields:
                if isinstance(f, dict):
                    col_defs.append(f"{f['name']} {f.get('type', 'STRING')}")
                    norm_cols.append({"name": f["name"], "type": f.get("type", "STRING")})
                else:
                    col_defs.append(f"{f} STRING")
                    norm_cols.append({"name": f, "type": "STRING"})

            cols_str = ",\n  ".join(col_defs)
            sql = f"CREATE TABLE IF NOT EXISTS __SCHEMA_QUALIFIED__.{name} (\n  {cols_str}\n) USING DELTA;\n"

            (out_dir / f"create_{name}.sql").write_text(sql)
            created.append(name)
            manifest_tables.append({"name": name, "columns": norm_cols, "row_count": 0})
            await self.sse_queue.put({"event": "progress", "data": {"line": f"[+] Wrote create_{name}.sql\n"}})

        # Store table schemas in config (travels with project + bundles)
        from brickforge.server import config as _config
        _config.set("data.table_schemas", manifest_tables)

        _enable_gen_data()

        return f"Created SQL for {len(created)} table(s): {', '.join(created)}"

    async def generate_data(self, table_name: str, columns: list, row_count: int = 15, context_tables: list | None = None) -> str:
        """Generate synthetic CSV data for a table using LLM. Creative content - needs LLM.
        columns: list of {"name": "col", "type": "STRING"} or just ["col1", "col2"] (defaults to STRING).
        Returns the generated rows as JSON."""
        import csv
        import io
        from brickforge.lib.project_paths import gen_dir

        # Normalize columns to [{name, type}] format
        norm_cols = []
        for c in columns:
            if isinstance(c, dict):
                norm_cols.append({"name": c["name"], "type": c.get("type", "STRING")})
            else:
                norm_cols.append({"name": c, "type": "STRING"})

        row_count = min(row_count, 15)
        col_names = ", ".join(c["name"] for c in norm_cols)
        cols_desc = "\n".join(f"  - {c['name']}: {c['type']}" for c in norm_cols)

        system = (
            "You are a synthetic data generator for Databricks Delta tables.\n"
            "Generate realistic sample data matching the schema exactly.\n"
            "Return ONLY a JSON object: {\"rows\": [{\"col1\": \"val1\"}, ...]}\n"
            f"Generate exactly {row_count} rows. Columns: {col_names}\n"
            "Values must be realistic, varied, and domain-appropriate."
        )
        user = f"Table: {table_name}\n\nColumns:\n{cols_desc}\n\nGenerate {row_count} rows."

        if context_tables:
            user += "\n\nRelated tables (use matching IDs):\n"
            for ct in context_tables:
                ct_name = ct.get("name", "")
                ct_cols = ct.get("columns", ct.get("fields", []))
                ct_col_str = ", ".join(c["name"] if isinstance(c, dict) else c for c in ct_cols[:5])
                user += f"  {ct_name}: {ct_col_str}\n"

        # Call LLM directly - no subprocess
        os.environ.setdefault("DATABRICKS_HOST", "")  # ensure env set for SDK
        from brickforge.data.gen.llm_client import call_llm_json
        await self.sse_queue.put({"event": "progress", "data": {"line": f"[+] Generating {row_count} rows for {table_name}...\n"}})

        try:
            result = call_llm_json(system, user)
            rows = result.get("rows", [])
        except Exception as e:
            return f"Data generation failed: {e}"

        # Write CSV
        csv_dir = gen_dir() / "csv"
        csv_dir.mkdir(parents=True, exist_ok=True)
        if rows:
            headers = list(rows[0].keys())
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
            (csv_dir / f"{table_name}.csv").write_text(buf.getvalue())

        # Write CREATE TABLE SQL
        init_dir = gen_dir() / "init"
        init_dir.mkdir(parents=True, exist_ok=True)
        col_sql = ",\n  ".join(f"{c['name']} {c['type']}" for c in norm_cols)
        create_sql = f"CREATE TABLE IF NOT EXISTS __SCHEMA_QUALIFIED__.{table_name} (\n  {col_sql}\n) USING DELTA;\n"
        (init_dir / f"create_{table_name}.sql").write_text(create_sql)

        # Update table schemas in config
        from brickforge.server import config as _config
        existing = {t["name"]: t for t in (_config.get("data.table_schemas") or [])}
        existing[table_name] = {"name": table_name, "columns": norm_cols, "row_count": len(rows)}
        _config.set("data.table_schemas", list(existing.values()))

        _enable_gen_data()

        await self.sse_queue.put({"event": "progress", "data": {"line": f"[+] Wrote {table_name}.csv + create_{table_name}.sql ({len(rows)} rows)\n"}})
        return json.dumps({"table": table_name, "rows_generated": len(rows), "columns": [c["name"] for c in norm_cols]})

    async def generate_prompt(self, domain: str, entities: list | None = None, actions: list | None = None) -> str:
        """Generate agent system prompt using LLM. Creative content - needs LLM.
        Passes domain + spec context directly. No subprocess, no stale files."""
        from brickforge.lib.project_paths import prompt_dir
        from brickforge.data.gen.llm_client import call_llm_json

        entities_desc = ""
        if entities:
            entities_desc = "Tables: " + ", ".join(e.get("name", "") for e in entities)
        actions_desc = ""
        if actions:
            actions_desc = "Functions: " + ", ".join(a.get("name", "") + "(" + ",".join(a.get("params", [])) + ")" for a in actions)

        system = (
            "You generate system prompts for AI agents deployed on Databricks.\n"
            "Return a JSON object with:\n"
            "  main_prompt: the full system prompt (string)\n"
            "  knowledge_base: domain FAQ and operational knowledge (string)\n"
            "  user_prompt: an example first message from a user (string)\n"
            "Keep the tone warm, professional, and domain-appropriate.\n"
            "The agent should introduce itself and explain what it can do."
        )
        user = f"Domain: {domain}\n{entities_desc}\n{actions_desc}\nGenerate the prompt files."

        await self.sse_queue.put({"event": "progress", "data": {"line": "[+] Generating system prompt...\n"}})

        try:
            result = call_llm_json(system, user, max_tokens=8192)
        except Exception as e:
            return f"Prompt generation failed: {e}"

        # Write prompt files
        pdir = prompt_dir()
        pdir.mkdir(parents=True, exist_ok=True)

        main_prompt = result.get("main_prompt", "")
        knowledge_base = result.get("knowledge_base", "")
        user_prompt = result.get("user_prompt", "")

        if main_prompt:
            (pdir / "main.prompt").write_text(main_prompt)
            await self.sse_queue.put({"event": "progress", "data": {"line": f"[+] Wrote main.prompt ({len(main_prompt.splitlines())} lines)\n"}})
        if knowledge_base:
            (pdir / "knowledge.base").write_text(knowledge_base)
            await self.sse_queue.put({"event": "progress", "data": {"line": f"[+] Wrote knowledge.base ({len(knowledge_base.splitlines())} lines)\n"}})
        if user_prompt:
            (pdir / "user.prompt").write_text(user_prompt)
            await self.sse_queue.put({"event": "progress", "data": {"line": "[+] Wrote user.prompt\n"}})

        return f"Prompt generated: main.prompt ({len(main_prompt.splitlines())} lines), knowledge.base, user.prompt"

    async def save_files(self, filename: str, content: str, subdir: str = "") -> str:
        """Write content to a file in the project gen directory."""
        from brickforge.lib.project_paths import gen_dir

        target_dir = gen_dir() / subdir if subdir else gen_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / filename).write_text(content)
        return f"Saved {filename}"

    async def provision_tables(self) -> str:
        """Execute all CREATE TABLE SQL files and load CSV data into them."""
        result = await self._stream_exec("exec-tables")

        # Load CSV data into the created tables
        from brickforge.lib.project_paths import gen_dir
        csv_dir = gen_dir() / "csv"
        csv_files = sorted(csv_dir.glob("*.csv")) if csv_dir.exists() else []
        if csv_files:
            await self.sse_queue.put({"event": "progress", "data": {"line": "[~] Loading CSV data into tables...\n"}})
            import asyncio, sys
            from brickforge.lib.env_utils import build_sub_env
            from brickforge.server import config as _config
            from brickforge import PACKAGE_ROOT
            cmd = [sys.executable, str(PACKAGE_ROOT / "data" / "py" / "csv_to_delta.py")]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=build_sub_env(_config),
                cwd=str(PACKAGE_ROOT),
            )
            output = []
            async for line in proc.stdout:
                text = line.decode().rstrip()
                output.append(text)
                await self.sse_queue.put({"event": "progress", "data": {"line": text + "\n"}})
            await proc.wait()
            if proc.returncode != 0:
                return result + "\n[x] CSV data load failed"
            await self.sse_queue.put({"event": "progress", "data": {"line": "[+] CSV data loaded\n"}})
            result += "\nCSV data loaded into tables."

        return result

    async def provision_routines(self) -> str:
        """Execute all function and procedure SQL files against the warehouse."""
        # Functions first, then procedures
        result_parts = []
        func_result = await self._stream_exec("exec-functions")
        result_parts.append(func_result)
        # Procedures via the same pattern
        from brickforge.lib.project_paths import gen_dir
        proc_dir = gen_dir() / "proc"
        if proc_dir.exists() and list(proc_dir.glob("*.sql")):
            proc_result = await self._stream_exec("exec-functions")  # reuses same create_all pattern
            result_parts.append(proc_result)
        return "\n".join(result_parts)

    async def create_genie_space(self, name: str, description: str = "") -> str:
        """Create a Genie space via the setup API."""
        return await self._stream_exec("exec-genie", {"name": name, "description": description})

    async def create_mlflow_experiment(self) -> str:
        """Create an MLflow experiment."""
        return await self._stream_exec("exec-mlflow")

    # ── Exec tools (legacy - via HTTP endpoints) ────────────────────────

    async def create_project(self, name: str) -> str:
        """Create a new project."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.post("/api/projects", json={"name": name})
            return resp.text

    async def save_config(self, action: str, params: dict | None = None) -> str:
        """Execute a save action (save-warehouse, save-schema, save-model-endpoint, etc.).
        Action is the exact action name from the setup API.
        Params is a dict of action-specific parameters."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.post("/api/setup/exec", json={"action": action, "params": params or {}})
            return resp.text

    async def toggle_feature(self, key: str, enabled: bool) -> str:
        """Toggle a feature (MEMORY, CHART, VOICE, VISION, PERSONAS, DASHBOARD)."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.post("/api/setup/exec", json={
                "action": "save-feature-toggle",
                "params": {"key": key, "enabled": enabled},
            })
            return resp.text

    async def toggle_brick(self, key: str, enabled: bool) -> str:
        """Toggle a brick (KA, INFO_EXTRACTION, DOC_PARSING, TEXT_CLASSIFICATION)."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=10) as c:
            resp = await c.post("/api/setup/exec", json={
                "action": "save-brick-toggle",
                "params": {"key": key, "enabled": enabled},
            })
            return resp.text

    async def exec_provision(self, action: str, params: dict | None = None) -> str:
        """Execute a provisioning action with SSE streaming (exec-tables, exec-functions,
        exec-genie, exec-mlflow, exec-lakebase, exec-grants, exec-build).
        Progress lines are forwarded to the frontend via sse_queue."""
        return await self._stream_exec(action, params)

    async def exec_generate(self, endpoint: str, body: dict | None = None) -> str:
        """Call a gen endpoint with SSE streaming (/api/gen/schema, /api/gen/data,
        /api/gen/provision, /api/gen/routine-schema, /api/gen/routine-sql, etc.).
        Progress lines are forwarded to the frontend via sse_queue."""
        return await self._stream_gen(endpoint, body)

    async def exec_deploy(self) -> str:
        """Deploy the agent app to Databricks. Streams progress via sse_queue."""
        return await self._stream_exec("exec-deploy-agent")

    async def export_project(self, name: str) -> str:
        """Export project as .forge.zip bundle."""
        async with httpx.AsyncClient(base_url=_base_url(), timeout=30) as c:
            resp = await c.get(f"/api/projects/{name}/export")
            return f"Export ready: {resp.status_code}"

    async def push_github(self) -> str:
        """Push project to GitHub."""
        return await self._stream_exec("exec-git-push")

    # ── Streaming helpers ────────────────────────────────────────────────

    async def _parse_sse_stream(self, resp) -> tuple[list[str], list[dict]]:
        """Parse an SSE stream, forwarding progress and collecting results.
        Returns (text_lines, result_payloads)."""
        lines = []
        results = []
        current_event = "line"

        async for raw_line in resp.aiter_lines():
            raw_line = raw_line.strip()
            if not raw_line:
                current_event = "line"
                continue
            if raw_line.startswith("event:"):
                current_event = raw_line[6:].strip()
                continue
            if raw_line.startswith("data:"):
                data = raw_line[5:].strip()
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if current_event == "result":
                    results.append(parsed)
                elif current_event in ("line", "message"):
                    text = parsed.get("text", "")
                    if text:
                        await self.sse_queue.put({"event": "progress", "data": {"line": text}})
                        lines.append(text)
                # done event - ignore, we read until stream ends

        return lines, results

    async def _stream_exec(self, action: str, params: dict | None = None) -> str:
        """Stream a setup exec action, forwarding progress to sse_queue."""
        timeout = httpx.Timeout(connect=10, read=600, write=10, pool=10)
        async with httpx.AsyncClient(base_url=_base_url(), timeout=timeout) as c:
            async with c.stream("POST", "/api/setup/exec",
                                json={"action": action, "params": params or {}}) as resp:
                lines, results = await self._parse_sse_stream(resp)
        if results:
            return json.dumps(results[-1])
        return "\n".join(lines[-10:]) if lines else "Action completed"

    async def _stream_gen(self, endpoint: str, body: dict | None = None) -> str:
        """Stream a gen endpoint, forwarding progress to sse_queue.
        Returns the last __RESULT__ payload as JSON string (for chaining gen steps)."""
        timeout = httpx.Timeout(connect=10, read=300, write=10, pool=10)
        async with httpx.AsyncClient(base_url=_base_url(), timeout=timeout) as c:
            async with c.stream("POST", endpoint, json=body or {}) as resp:
                lines, results = await self._parse_sse_stream(resp)
        if results:
            return json.dumps(results[-1])
        return "\n".join(lines[-10:]) if lines else "Generation completed"

    # ── Tool registry for bind_tools ─────────────────────────────────────

    def get_tools(self, phase: str = "discovery") -> list:
        """Return LangChain StructuredTool list for ChatDatabricks.bind_tools().
        phase='discovery': read-only tools (LLM can't generate/deploy)
        phase='build': all tools (after spec confirmed)"""
        from langchain_core.tools import StructuredTool

        specs = self._read_tool_specs()
        if phase == "build":
            specs = specs + self._exec_tool_specs()

        tools = []
        for name, method, desc, schema in specs:
            tools.append(StructuredTool.from_function(
                coroutine=method,
                name=name,
                description=desc,
                args_schema=schema,
            ))
        return tools

    def _read_tool_specs(self):
        """Read-only tools - available in all phases."""
        from pydantic import BaseModel, Field

        class Empty(BaseModel):
            pass

        class NameParam(BaseModel):
            name: str = Field(description="Name of the project or resource")

        class SpecParam(BaseModel):
            spec: dict = Field(description="The agent spec JSON with entities, actions, lifecycle, and naming")

        return [
            ("read_status", self.read_status, "Get all setup block states (done/missing)", Empty),
            ("read_config", self.read_config, "Get current config values", Empty),
            ("read_tables", self.read_tables, "Get table names and column schemas", Empty),
            ("read_functions", self.read_functions, "Get UC functions and procedures list", Empty),
            ("read_prompt", self.read_prompt, "Get current system prompt text", Empty),
            ("read_warehouses", self.read_warehouses, "List available SQL warehouses (id, name, state)", Empty),
            ("read_catalogs", self.read_catalogs, "List available Unity Catalog catalogs", Empty),
            ("read_models", self.read_models, "List available serving endpoints", Empty),
            ("read_features", self.read_features, "Get feature and brick toggle states", Empty),
            ("read_deploy_status", self.read_deploy_status, "Get app deploy status", Empty),
            ("create_project", self.create_project, "Create a new project", NameParam),
            ("present_spec", self.present_spec, "Present the agent spec for user approval. Call this after discovery with a structured spec JSON containing entities, actions, lifecycle, and naming.", SpecParam),
        ]

    def _exec_tool_specs(self):
        """Build tools - available after spec is confirmed."""
        from pydantic import BaseModel, Field

        class SaveConfigParams(BaseModel):
            action: str = Field(description="Action name: save-warehouse, save-schema, save-model-endpoint, save-genie, save-deploy-name, save-manual, save-lakebase, save-mlflow")
            params: dict = Field(default_factory=dict, description="Action-specific parameters")

        class QuerySpec(BaseModel):
            query_spec: dict = Field(description="Structured JSON query spec with name, type, params, returns, from, joins, where")

        class EntitiesList(BaseModel):
            entities: list = Field(description="List of entity dicts from the spec, each with name and fields")

        class SaveFileParams(BaseModel):
            filename: str = Field(description="File name to save")
            content: str = Field(description="File content")
            subdir: str = Field(default="", description="Subdirectory in gen dir (e.g. 'csv', 'init', 'func', 'proc')")

        class GenDataParams(BaseModel):
            table_name: str = Field(description="Table name to generate data for")
            columns: list = Field(description="Column definitions: [{name, type}] or just [name]")
            row_count: int = Field(default=15, description="Number of rows (max 15)")
            context_tables: list = Field(default_factory=list, description="Related tables for referential integrity")

        class PromptParams(BaseModel):
            domain: str = Field(description="Domain description for the agent")
            entities: list = Field(default_factory=list, description="Entity list from spec")
            actions: list = Field(default_factory=list, description="Action list from spec")

        class GenieParams(BaseModel):
            name: str = Field(description="Genie space name")
            description: str = Field(default="", description="Genie space description")

        class ToggleParams(BaseModel):
            key: str = Field(description="Feature or brick key")
            enabled: bool = Field(description="Enable or disable")

        class Empty(BaseModel):
            pass

        class NameParam(BaseModel):
            name: str = Field(description="Name of the project or resource")

        return [
            # Config
            ("save_config", self.save_config, "Execute a config save action", SaveConfigParams),
            # Direct build tools (no subprocess, no gen endpoint)
            ("generate_routine", self.generate_routine, "Generate a UC function or procedure from a JSON query spec. Uses the SQL template engine - deterministic, no LLM writes SQL.", QuerySpec),
            ("create_tables_sql", self.create_tables_sql, "Generate CREATE TABLE SQL files from spec entities.", EntitiesList),
            ("save_files", self.save_files, "Write content to a file in the project gen directory.", SaveFileParams),
            ("provision_tables", self.provision_tables, "Execute all CREATE TABLE SQL against the warehouse.", Empty),
            ("provision_routines", self.provision_routines, "Execute all function and procedure SQL against the warehouse.", Empty),
            ("create_genie_space", self.create_genie_space, "Create a Genie space.", GenieParams),
            ("create_mlflow_experiment", self.create_mlflow_experiment, "Create an MLflow experiment.", Empty),
            # LLM-powered direct tools (creative content - calls LLM inline, no subprocess)
            ("generate_data", self.generate_data, "Generate synthetic data for a table. Columns can be [{name, type}] or just [name]. Max 15 rows.", GenDataParams),
            ("generate_prompt", self.generate_prompt, "Generate agent system prompt from domain description + spec.", PromptParams),
            # Deploy + extras
            ("exec_deploy", self.exec_deploy, "Deploy the agent app to Databricks. Includes grants.", Empty),
            ("toggle_feature", self.toggle_feature, "Toggle a feature on/off", ToggleParams),
            ("toggle_brick", self.toggle_brick, "Toggle a brick on/off", ToggleParams),
            ("export_project", self.export_project, "Export project as .forge.zip", NameParam),
            ("push_github", self.push_github, "Push project to GitHub", Empty),
        ]

    async def execute(self, tool_call: dict) -> str:
        """Execute a tool call from the LLM response. Routes by name."""
        name = tool_call["name"]
        args = tool_call.get("args", {})

        method_map = {
            "read_status": self.read_status,
            "read_config": self.read_config,
            "read_tables": self.read_tables,
            "read_functions": self.read_functions,
            "read_prompt": self.read_prompt,
            "read_warehouses": self.read_warehouses,
            "read_catalogs": self.read_catalogs,
            "read_models": self.read_models,
            "read_features": self.read_features,
            "read_deploy_status": self.read_deploy_status,
            "create_project": self.create_project,
            "present_spec": self.present_spec,
            "save_config": self.save_config,
            "generate_routine": self.generate_routine,
            "create_tables_sql": self.create_tables_sql,
            "save_files": self.save_files,
            "provision_tables": self.provision_tables,
            "provision_routines": self.provision_routines,
            "create_genie_space": self.create_genie_space,
            "create_mlflow_experiment": self.create_mlflow_experiment,
            "generate_data": self.generate_data,
            "generate_prompt": self.generate_prompt,
            "exec_deploy": self.exec_deploy,
            "toggle_feature": self.toggle_feature,
            "toggle_brick": self.toggle_brick,
            "export_project": self.export_project,
            "push_github": self.push_github,
        }

        method = method_map.get(name)
        if not method:
            return f"Unknown tool: {name}"

        try:
            return await method(**args)
        except Exception as e:
            return f"Tool error ({name}): {e}"
