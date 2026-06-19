"""Cleanup routes: resource discovery + deletion."""
from __future__ import annotations

import json
import subprocess
import sys

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from brickforge import PROJECT_ROOT, PACKAGE_ROOT
from brickforge.lib.sse import stream_subprocess
from brickforge.lib.env_utils import build_sub_env

router = APIRouter()


def _get_config():
    from brickforge.server import config
    return config


@router.get("/api/cleanup/resources")
async def cleanup_resources():
    env = build_sub_env(_get_config())
    script = """
from databricks.sdk import WorkspaceClient
import os, json

w = WorkspaceClient()
items = []

# Apps
app_name = os.environ.get('DBX_APP_NAME','').strip()
if app_name:
    try:
        app = w.apps.get(name=app_name)
        items.append({'id': f'app:{app_name}', 'category': 'apps', 'name': app_name})
    except: pass

# Genie spaces from PROJECT_GENIE_SPACES
raw_genie = os.environ.get('PROJECT_GENIE_SPACES', '').strip()
for sid in (raw_genie.split(',') if raw_genie else []):
    sid = sid.strip()
    if not sid: continue
    try:
        space = w.genie.get_space(space_id=sid)
        items.append({'id': f'genie:{sid}', 'category': 'genie', 'name': getattr(space, 'title', sid)})
    except: pass

# Tables, functions, procedures
schema = os.environ.get('PROJECT_UNITY_CATALOG_SCHEMA','').strip()
if '.' in schema:
    try:
        for t in w.tables.list(catalog_name=schema.split('.')[0], schema_name=schema.split('.')[1]):
            items.append({'id': f'table:{t.full_name}', 'category': 'tables', 'name': t.name})
    except: pass
    for kind in ['FUNCTION', 'PROCEDURE']:
        try:
            for fn in w.functions.list(catalog_name=schema.split('.')[0], schema_name=schema.split('.')[1]):
                items.append({'id': f'routine:{fn.full_name}', 'category': 'routines', 'name': fn.name})
        except: pass

# Env keys
for k in ['DATABRICKS_HOST','DATABRICKS_TOKEN','DATABRICKS_WAREHOUSE_ID','PROJECT_UNITY_CATALOG_SCHEMA',
          'AGENT_MODEL','AGENT_MODEL_TOKEN','DBX_APP_NAME','LAKEBASE_INSTANCE_NAME','MLFLOW_EXPERIMENT_ID']:
    if os.environ.get(k,'').strip():
        items.append({'id': f'env:{k}', 'category': 'env', 'name': k})

print(json.dumps({'items': items}))
""".strip()

    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=60,
            cwd=str(PACKAGE_ROOT), env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
        from brickforge.lib.env_utils import parse_subprocess_error; return {"items": [], "error": parse_subprocess_error(result.stderr, result.stdout) if result.stderr else "no output"}
    except Exception as e:
        return {"items": [], "error": str(e)}


@router.post("/api/cleanup/exec")
async def cleanup_exec(request: Request):
    body = await request.json()
    ids = body.get("ids", [])

    async def generate():
        env = build_sub_env(_get_config())
        script = f"""
from databricks.sdk import WorkspaceClient
from pathlib import Path
import os, re, json, sys

w = WorkspaceClient()
ids = {json.dumps(ids)}
config_path = os.environ.get('CONFIG_FILE', '')

for item_id in ids:
    cat, name = item_id.split(':', 1)
    try:
        if cat == 'app':
            w.apps.delete(name=name)
            print(f'[+] deleted app: {{name}}')
        elif cat == 'genie':
            w.genie.delete_space(space_id=name)
            print(f'[+] deleted genie space: {{name}}')
        elif cat == 'table':
            w.tables.delete(full_name=name)
            print(f'[+] deleted table: {{name}}')
        elif cat == 'routine':
            w.functions.delete(name=name)
            print(f'[+] deleted routine: {{name}}')
        elif cat == 'env':
            # Disable in config.json
            config_file = os.environ.get('CONFIG_FILE', '')
            if config_file:
                from lib.config_json import read_config, write_config
                cfg = read_config()
                # Try to disable via toggle pattern (multi-instance)
                disabled = False
                for section in ['ka', 'mcp', 'api', 'a2a']:
                    tools = cfg.get('tools', {{}}).get(section, {{}})
                    for slug, entry in tools.items():
                        if isinstance(entry, dict):
                            flat_key = name
                            if flat_key.startswith('PROJECT_'):
                                # Check if this slug matches
                                if slug in flat_key:
                                    entry['enabled'] = False
                                    disabled = True
                                    break
                    if disabled: break
                if not disabled:
                    # Scalar: set to None
                    pass
                write_config(cfg)
            print(f'[+] disabled env: {{name}}')
        else:
            print(f'[~] unknown category: {{cat}}')
    except Exception as e:
        print(f'[x] {{cat}}:{{name}}: {{str(e)[:100]}}')
    sys.stdout.flush()
print('[+] cleanup complete')
""".strip()

        async for event in stream_subprocess(
            [sys.executable, "-c", script], env=env, cwd=PROJECT_ROOT
        ):
            yield event

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
