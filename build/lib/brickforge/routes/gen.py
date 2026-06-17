"""Data generation routes: schema, data, save, provision, wizard-state, routines."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from brickforge import PROJECT_ROOT, PACKAGE_ROOT
from brickforge.lib.sse import stream_subprocess, sse_line, sse_done
from brickforge.lib.env_utils import build_sub_env

router = APIRouter()


def _get_config():
    from brickforge.server import config
    return config


def _sub_env():
    return build_sub_env(_get_config())


from brickforge.lib.project_paths import gen_dir as _gen_dir, prompt_dir as _prompt_dir


# ── Status & Discovery ───────────────────────────────────────────────────────

@router.get("/api/gen/status")
async def gen_status():
    config = _get_config()
    env = config.to_env_dict()
    model_ready = bool((env.get("AGENT_MODEL") or env.get("AGENT_MODEL_ENDPOINT")) and env.get("DATABRICKS_HOST"))
    manifest = None
    manifest_path = _gen_dir() / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    use_demo = (env.get("USE_DEMO_DATA") or env.get("USE_DEFAULT_DATA", "true")).strip().lower()
    use_gen = env.get("USE_GEN_DATA", "false").strip().lower()
    return {
        "modelReady": model_ready,
        "manifest": manifest,
        "useDefault": use_demo in ("true", "1", "yes"),
        "useGen": use_gen in ("true", "1", "yes"),
    }


@router.get("/api/gen/tables")
async def gen_tables():
    env = _get_config().to_env_dict()
    use_demo = (env.get("USE_DEMO_DATA") or env.get("USE_DEFAULT_DATA", "true")).strip().lower()
    use_gen = env.get("USE_GEN_DATA", "false").strip().lower()
    tables = []
    sources = []
    if use_demo in ("true", "1", "yes"):
        sources.append(("demo", PACKAGE_ROOT / "data" / "demo"))
    if use_gen in ("true", "1", "yes"):
        sources.append(("generated", _gen_dir()))

    for source, base in sources:
        csv_dir = base / "csv"
        init_dir = base / "init"
        if not csv_dir.exists():
            continue
        for csv_path in sorted(csv_dir.glob("*.csv")):
            table_name = csv_path.stem.replace("-", "_")
            sql_path = init_dir / f"create_{table_name}.sql"
            columns = []
            if sql_path.exists():
                content = sql_path.read_text()
                # Extract only the CREATE TABLE (...) block
                create_match = re.search(r'CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+\S+\s*\((.*?)\)', content, re.IGNORECASE | re.DOTALL)
                if create_match:
                    create_block = create_match.group(1)
                    for m in re.finditer(r"(\w+)\s+(STRING|INT|BIGINT|DOUBLE|FLOAT|BOOLEAN|DATE|TIMESTAMP\w*|DECIMAL[^,)]*)", create_block, re.IGNORECASE):
                        columns.append({"name": m.group(1), "type": m.group(2)})
            tables.append({"name": table_name, "columns": columns, "source": source})

    return {"tables": tables}


@router.get("/api/gen/routines")
async def gen_routines():
    env = _get_config().to_env_dict()
    use_demo = (env.get("USE_DEMO_DATA") or env.get("USE_DEFAULT_DATA", "true")).strip().lower()
    use_gen = env.get("USE_GEN_DATA", "false").strip().lower()
    routines = []
    sources = []
    if use_demo in ("true", "1", "yes"):
        sources.append(("demo", PACKAGE_ROOT / "data" / "demo"))
    if use_gen in ("true", "1", "yes"):
        sources.append(("generated", _gen_dir()))

    for source, base in sources:
        for sub, kind in [("func", "function"), ("proc", "procedure")]:
            d = base / sub
            if not d.exists():
                continue
            for f in sorted(d.glob("*.sql")):
                routines.append({"name": f.stem, "kind": kind, "source": source})

    return {"routines": routines}


# ── Wizard State ──────────────────────────────────────────────────────────────

@router.get("/api/gen/wizard-state")
async def get_wizard_state():
    config = _get_config()
    return config.get("data.wizard_state") or None


@router.put("/api/gen/wizard-state")
async def save_wizard_state(request: Request):
    body = await request.json()
    config = _get_config()
    config.set("data.wizard_state", body)
    return {"ok": True}


@router.delete("/api/gen/wizard-state")
async def delete_wizard_state():
    config = _get_config()
    config.set("data.wizard_state", None)
    return {"ok": True}


@router.get("/api/gen/routine-wizard-state")
async def get_routine_wizard_state():
    config = _get_config()
    return config.get("data.routine_wizard_state") or None


@router.put("/api/gen/routine-wizard-state")
async def save_routine_wizard_state(request: Request):
    body = await request.json()
    config = _get_config()
    config.set("data.routine_wizard_state", body)
    return {"ok": True}


@router.delete("/api/gen/routine-wizard-state")
async def delete_routine_wizard_state():
    config = _get_config()
    config.set("data.routine_wizard_state", None)
    return {"ok": True}


# ── Clear ─────────────────────────────────────────────────────────────────────

@router.delete("/api/gen/clear")
async def clear_gen():
    gen_dir = _gen_dir()
    deleted = 0
    for sub in ["csv", "init"]:
        d = gen_dir / sub
        if d.exists():
            for f in d.iterdir():
                if f.suffix in (".csv", ".sql"):
                    f.unlink()
                    deleted += 1
    for name in ["manifest.json", "wizard-state.json"]:
        try:
            (gen_dir / name).unlink()
            deleted += 1
        except FileNotFoundError:
            pass
    return {"ok": True, "deleted": deleted}


@router.delete("/api/gen/clear-routines")
async def clear_routines():
    gen_dir = _gen_dir()
    deleted = 0
    for sub in ["func", "proc"]:
        d = gen_dir / sub
        if d.exists():
            for f in d.iterdir():
                if f.suffix == ".sql":
                    f.unlink()
                    deleted += 1
    for name in ["routine-wizard-state.json"]:
        try:
            (gen_dir / name).unlink()
            deleted += 1
        except FileNotFoundError:
            pass
    return {"ok": True, "deleted": deleted}


# ── SSE Generation Endpoints ─────────────────────────────────────────────────

def _sse_gen(cmd: list[str], stdin_data: str | None = None):
    """Create an SSE streaming response for a generation subprocess."""
    async def generate():
        env = _sub_env()
        if stdin_data:
            import asyncio
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(PACKAGE_ROOT),
                env=env,
            )
            proc.stdin.write(stdin_data.encode())
            await proc.stdin.drain()
            proc.stdin.close()

            async for line_bytes in proc.stdout:
                text = line_bytes.decode("utf-8", errors="replace")
                if "VIRTUAL_ENV" in text and "does not match" in text:
                    continue
                if text.startswith("__RESULT__:"):
                    try:
                        from brickforge.lib.sse import sse_result
                        result_data = json.loads(text[len("__RESULT__:"):])
                        yield sse_result(result_data)
                    except json.JSONDecodeError:
                        yield sse_line(text)
                else:
                    yield sse_line(text)
            async for line_bytes in proc.stderr:
                text = line_bytes.decode("utf-8", errors="replace")
                if "VIRTUAL_ENV" in text:
                    continue
                yield sse_line(text, "err")
            await proc.wait()
            yield sse_done(proc.returncode == 0, proc.returncode or 0)
        else:
            async for event in stream_subprocess(cmd, env=env, cwd=PACKAGE_ROOT, detect_result=True):
                yield event

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ── Prompt Generation ─────────────────────────────────────────────────────────

@router.post("/api/gen/prompt-generate")
async def prompt_generate(request: Request):
    body = await request.json()
    domain = body.get("domain", "")
    table_schemas = body.get("tableSchemas")
    cmd = [sys.executable, "data/gen/generate_prompts.py", "--mode=generate", f"--domain={domain}"]
    if table_schemas:
        cmd.append(f"--tables-json={json.dumps(table_schemas)}")
    return _sse_gen(cmd)


@router.post("/api/gen/prompt-save")
async def prompt_save(request: Request):
    body = await request.json()
    stdin_data = json.dumps(body)
    cmd = [sys.executable, "data/gen/generate_prompts.py", "--mode=save"]
    return _sse_gen(cmd, stdin_data)


# ── Schema Generation ─────────────────────────────────────────────────────────

@router.post("/api/gen/schema")
async def gen_schema(request: Request):
    body = await request.json()
    domain = body.get("domain", "")
    table_schemas = body.get("tableSchemas")
    cmd = [sys.executable, "data/gen/generate_tables.py", "--mode=schema", f"--domain={domain}"]
    if table_schemas:
        cmd.append(f"--tables-json={json.dumps(table_schemas)}")
    return _sse_gen(cmd)


@router.post("/api/gen/data")
async def gen_data(request: Request):
    body = await request.json()
    stdin_data = json.dumps(body)
    cmd = [sys.executable, "data/gen/generate_tables.py", "--mode=data"]
    return _sse_gen(cmd, stdin_data)


@router.post("/api/gen/save")
async def gen_save(request: Request):
    body = await request.json()
    stdin_data = json.dumps(body)
    cmd = [sys.executable, "data/gen/generate_tables.py", "--mode=save"]
    return _sse_gen(cmd, stdin_data)


@router.post("/api/gen/provision")
async def gen_provision():
    cmd = [sys.executable, "data/gen/generate_tables.py", "--mode=provision-gen"]
    return _sse_gen(cmd)


# ── Routine Generation ────────────────────────────────────────────────────────

@router.get("/api/gen/routine-status")
async def routine_status():
    config = _get_config()
    env = config.to_env_dict()
    model_ready = bool((env.get("AGENT_MODEL") or env.get("AGENT_MODEL_ENDPOINT")) and env.get("DATABRICKS_HOST"))
    # Load table schemas for context: try gen manifest first, then existing UC tables
    table_schemas = None
    manifest_path = _gen_dir() / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
        table_schemas = manifest.get("tables")
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    # Fall back to existing UC tables if no generated tables
    if not table_schemas:
        try:
            from brickforge.routes.setup import _list_schema_tables
            uc_tables = _list_schema_tables(config)
            if uc_tables:
                table_schemas = [
                    {"name": t["name"], "columns": t.get("columns", [])}
                    for t in uc_tables
                ]
        except Exception:
            pass
    # Filter by PROJECT_TABLES selection if set
    if table_schemas:
        selected = env.get("PROJECT_TABLES", "").strip()
        if selected:
            selected_set = set(selected.split(","))
            table_schemas = [t for t in table_schemas if t["name"] in selected_set]
    return {"modelReady": model_ready, "tableSchemas": table_schemas}


@router.post("/api/gen/routine-schema")
async def routine_schema(request: Request):
    body = await request.json()
    domain = body.get("domain", "")
    table_schemas = body.get("tableSchemas")
    cmd = [sys.executable, "data/gen/generate_routines.py", "--mode=schema", f"--domain={domain}"]
    if table_schemas:
        cmd.append(f"--tables-json={json.dumps(table_schemas)}")
    return _sse_gen(cmd)


@router.post("/api/gen/routine-sql")
async def routine_sql(request: Request):
    body = await request.json()
    stdin_data = json.dumps(body)
    cmd = [sys.executable, "data/gen/generate_routines.py", "--mode=sql"]
    return _sse_gen(cmd, stdin_data)


@router.post("/api/gen/routine-save")
async def routine_save(request: Request):
    body = await request.json()
    stdin_data = json.dumps(body)
    cmd = [sys.executable, "data/gen/generate_routines.py", "--mode=save"]
    return _sse_gen(cmd, stdin_data)


@router.post("/api/gen/routine-provision")
async def routine_provision():
    cmd = [sys.executable, "data/gen/generate_routines.py", "--mode=provision-gen"]
    return _sse_gen(cmd)
