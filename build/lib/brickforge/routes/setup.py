"""Setup routes: status, profiles, resources, clear, toggle, instance, exec-log, exec, test."""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse

from brickforge import PROJECT_ROOT, PACKAGE_ROOT
from brickforge.lib.sse import sse_line, sse_done, ExecLogger, stream_subprocess

# Python executable -- use the same interpreter running the server
PYTHON = sys.executable

router = APIRouter()

STEP_ENV_KEYS: dict[str, list[str]] = {
    "host":      ["DATABRICKS_HOST", "DATABRICKS_TOKEN"],
    "warehouse": ["DATABRICKS_WAREHOUSE_ID"],
    "schema":    ["PROJECT_UNITY_CATALOG_SCHEMA"],
    "tables":    [],
    "functions": [],
    "model":     ["AGENT_MODEL"],
    "prompt":    [],
    "genie":     [],
    "bricks":    [],
    "vs":        ["PROJECT_VS_INDEX"],
    "mcp":       [],
    "api":       [],
    "a2a":       [],
    "features":  [],
    "mlflow":    ["MLFLOW_EXPERIMENT_ID"],
    "deploy":    ["DBX_APP_NAME"],
    "git":       [],
}

# ── Feature registry ──────────────────────────────────────────────────────────
# Each entry: env-key suffix -> {label, desc, default}
# The full env key is PROJECT_TOOL_<KEY>.
FEATURE_REGISTRY = {
    "MEMORY": {
        "label": "Memory",
        "desc": "Persistent user memory across conversations via Lakebase (requires LAKEBASE_INSTANCE_NAME)",
        "default": "false",
    },
    "CHART": {
        "label": "Graph plotting",
        "desc": "Agent can generate interactive charts (area, line, bar, pie) inline in chat",
        "default": "true",
    },
    "VOICE": {
        "label": "Voice input",
        "desc": "Speech-to-text input in the chat UI (requires OpenAI API key)",
        "default": "false",
    },
    "VISION": {
        "label": "Vision",
        "desc": "Upload images in chat for visual analysis (requires vision-capable model)",
        "default": "false",
    },
    "PERSONAS": {
        "label": "Personas",
        "desc": "Role selector in chat UI (Agent/Manager or custom roles)",
        "default": "false",
    },
    "DASHBOARD": {
        "label": "Dashboard",
        "desc": "Live data tables on the chat app home page -- auto-refreshes when the agent modifies data",
        "default": "false",
    },
}

# ── Bricks registry (Agent Bricks) ───────────────────────────────────────────
# Each entry: key suffix -> {label, desc, default}
# The full env key is PROJECT_BRICK_<KEY>.
BRICKS_REGISTRY = {
    "KA": {
        "label": "Knowledge Assistant",
        "desc": "RAG endpoint backed by your documents -- answers questions with cited sources",
        "default": "false",
    },
    "INFO_EXTRACTION": {
        "label": "Information Extraction",
        "desc": "Extract structured data from unstructured text (entities, dates, amounts, relationships)",
        "default": "false",
    },
    "DOC_PARSING": {
        "label": "Document Parsing",
        "desc": "Parse and chunk PDFs, Word docs, and HTML into structured content for downstream tools",
        "default": "false",
    },
    "TEXT_CLASSIFICATION": {
        "label": "Text Classification",
        "desc": "Classify text into categories (sentiment, intent, topic, urgency)",
        "default": "false",
    },
}

MULTI_INSTANCE_PREFIXES = {
    # "genie" removed — uses PROJECT_GENIE_SPACES (comma-separated) instead of prefix pattern
    "bricks": "PROJECT_BRICK_",
    "vs": "PROJECT_VS_",
    "mcp": "PROJECT_MCP_",
    "a2a": "PROJECT_A2A_",
    "api": "PROJECT_API_",
    "features": "PROJECT_TOOL_",
}


def _get_config():
    """Get the config provider from the server module."""
    from brickforge.server import config
    return config


def _get_forge_mode():
    from brickforge.server import FORGE_MODE
    return FORGE_MODE


def _get_workspace_client():
    """Build a WorkspaceClient from config (host + token). Avoids stale CLI profiles."""
    from databricks.sdk import WorkspaceClient
    config = _get_config()
    flat = config.flatten()
    return WorkspaceClient(host=flat.get("DATABRICKS_HOST"), token=flat.get("DATABRICKS_TOKEN"))


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/api/setup/status")
async def setup_status():
    config = _get_config()
    try:
        entries = config.list()
        env = {e["key"]: e["value"] for e in entries}
        steps: dict = {}

        for step, keys in STEP_ENV_KEYS.items():
            all_set = len(keys) > 0 and all(env.get(k, "").strip() for k in keys)
            status = "unknown" if len(keys) == 0 else ("configured" if all_set else "missing")
            values = {k: env.get(k, "") for k in keys}

            # Model: same-workspace hint (not auto-configured -- user must explicitly choose)
            if step == "model" and not all_set and env.get("DATABRICKS_HOST", "").strip():
                values["AGENT_MODEL"] = env["DATABRICKS_HOST"].rstrip("/") + " (same workspace)"

            # Tables: status based on whether schema is configured (test button does the real UC check)
            if step == "tables":
                schema_spec = env.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
                status = "configured" if schema_spec and "." in schema_spec else "missing"
                values["PROJECT_UNITY_CATALOG_SCHEMA"] = schema_spec

            # Functions: status based on whether schema is configured (test button does the real UC check)
            if step == "functions":
                schema_spec = env.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
                status = "configured" if schema_spec and "." in schema_spec else "missing"
                values["PROJECT_UNITY_CATALOG_SCHEMA"] = schema_spec

            # Prompt: file-based (project-scoped)
            if step == "prompt":
                from brickforge.lib.project_paths import prompt_dir as _prompt_dir
                prompt_dir = _prompt_dir()
                main_file = prompt_dir / "main.prompt"
                has_content = main_file.exists() and main_file.stat().st_size > 0
                status = "configured" if has_content else "missing"
                try:
                    files = [f.name for f in prompt_dir.iterdir() if not f.name.startswith(".")]
                except FileNotFoundError:
                    files = []
                values = {"PROMPT_FILES": ", ".join(files)}


            # Genie: comma-separated PROJECT_GENIE_SPACES
            if step == "genie":
                raw = env.get("PROJECT_GENIE_SPACES", "").strip()
                space_ids = [s.strip() for s in raw.split(",") if s.strip()] if raw else []
                status = "configured" if space_ids else "missing"
                genie_names = config.get("tools.genie_names") or {}
                # Backfill missing names from workspace API
                missing = [sid for sid in space_ids if sid not in genie_names]
                if missing and env.get("DATABRICKS_HOST") and env.get("DATABRICKS_TOKEN"):
                    try:
                        w = _get_workspace_client()
                        for sid in missing:
                            try:
                                sp = w.genie.get_space(space_id=sid)
                                genie_names[sid] = getattr(sp, 'title', sid[:16])
                            except Exception:
                                genie_names[sid] = sid[:16]
                        config.set("tools.genie_names", genie_names)
                    except Exception:
                        pass
                instances = [
                    {"key": f"PROJECT_GENIE_SPACES[{i}]", "value": sid, "enabled": True, "label": genie_names.get(sid, sid[:16])}
                    for i, sid in enumerate(space_ids)
                ]
                count = len(space_ids)
                label = f"{count} configured" if count else "not configured"
                values = {"PROJECT_GENIE_SPACES": raw}
                steps[step] = {"status": status, "values": values, "instances": instances, "label": label}
                continue

            # Multi-instance steps
            if step in MULTI_INSTANCE_PREFIXES:
                prefix = MULTI_INSTANCE_PREFIXES[step]
                instances = config.list_by_prefix(prefix)

                # Features: inject registry defaults for unconfigured, then sort to match registry order
                if step == "features":
                    configured_keys = {i["key"] for i in instances}
                    for key, meta in FEATURE_REGISTRY.items():
                        env_key = f"PROJECT_TOOL_{key}"
                        if env_key not in configured_keys:
                            instances.append({
                                "key": env_key,
                                "value": meta["default"],
                                "enabled": meta["default"].lower() == "true",
                                "label": meta["label"].lower(),
                            })
                    # Sort to match FEATURE_REGISTRY declaration order (MEMORY first)
                    registry_order = {f"PROJECT_TOOL_{k}": i for i, k in enumerate(FEATURE_REGISTRY)}
                    instances.sort(key=lambda x: registry_order.get(x["key"], 999))

                # Bricks: inject registry defaults, nest sub-entries under parent brick
                if step == "bricks":
                    configured_keys = {i["key"] for i in instances}
                    # Collect sub-entries per brick (e.g. PROJECT_KA_* under KA)
                    brick_children: dict[str, list] = {}
                    ka_instances = config.list_by_prefix("PROJECT_KA_")
                    brick_children["KA"] = ka_instances

                    for key, meta in BRICKS_REGISTRY.items():
                        env_key = f"PROJECT_BRICK_{key}"
                        if env_key not in configured_keys:
                            instances.append({
                                "key": env_key,
                                "value": meta["default"],
                                "enabled": meta["default"].lower() == "true",
                                "label": meta["label"].lower(),
                                "children": brick_children.get(key, []),
                            })
                        else:
                            # Add children + override label from registry
                            for inst in instances:
                                if inst["key"] == env_key:
                                    inst["children"] = brick_children.get(key, [])
                                    inst["label"] = meta["label"].lower()
                    registry_order = {f"PROJECT_BRICK_{k}": i for i, k in enumerate(BRICKS_REGISTRY)}
                    instances.sort(key=lambda x: registry_order.get(x["key"], 999))

                if step == "vs":
                    instances = [i for i in instances if "INDEX" in i["key"]]
                elif step == "mcp" or step == "a2a":
                    instances = [i for i in instances if not i["key"].endswith("_HEADER")]
                    values = {}
                elif step == "api":
                    api_instances = [i for i in instances if i["key"].endswith("_CONN") or i["key"].endswith("_URL")]
                    for i in api_instances:
                        slug = i["key"].replace("PROJECT_API_", "").replace("_CONN", "").replace("_URL", "").lower()
                        suffix = " (uc)" if i["key"].endswith("_CONN") else " (http)"
                        i["label"] = slug + suffix
                    instances = api_instances
                    values = {}

                has_enabled = any(i["enabled"] for i in instances)
                status = "configured" if has_enabled else "missing"
                steps[step] = {"status": status, "values": values, "instances": instances}
                continue

            steps[step] = {"status": status, "values": values}

        return {"steps": steps, "env": env, "forgeMode": _get_forge_mode()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Clear Step ────────────────────────────────────────────────────────────────

@router.post("/api/setup/clear-step")
async def clear_step(request: Request):
    config = _get_config()
    body = await request.json()
    step = body.get("step")
    if not step or step not in STEP_ENV_KEYS:
        return JSONResponse({"error": "invalid step"}, status_code=400)

    keys = STEP_ENV_KEYS[step]
    if keys:
        config.disable_many(keys)

    prefix = MULTI_INSTANCE_PREFIXES.get(step)
    if prefix:
        instances = config.list_by_prefix(prefix)
        instance_keys = [i["key"] for i in instances]
        if instance_keys:
            config.disable_many(instance_keys)

    return {"ok": True}


# ── Toggle ────────────────────────────────────────────────────────────────────

@router.put("/api/setup/toggle")
async def toggle_key(request: Request):
    config = _get_config()
    body = await request.json()
    key = body.get("key", "")
    allowed_prefixes = ("PROJECT_GENIE_SPACES", "PROJECT_KA_", "PROJECT_VS_", "PROJECT_MCP_", "PROJECT_API_", "PROJECT_A2A_", "PROJECT_TOOL_", "PROJECT_BRICK_", "PROJECT_FUNCTIONS")
    if not any(key.startswith(p) for p in allowed_prefixes):
        return JSONResponse({"error": "not a toggleable key"}, status_code=400)
    result = config.toggle(key)
    # Registry defaults: key may not exist in config yet -- create it
    if not result:
        for prefix, registry in [("PROJECT_TOOL_", FEATURE_REGISTRY), ("PROJECT_BRICK_", BRICKS_REGISTRY)]:
            if key.startswith(prefix):
                suffix = key.replace(prefix, "")
                if suffix in registry:
                    new_val = "false" if registry[suffix]["default"].lower() == "true" else "true"
                    config.set_many({key: new_val})
                    result = True
                break
    return {"ok": result}


# ── Delete Instance ───────────────────────────────────────────────────────────

@router.delete("/api/setup/instance")
async def delete_instance(request: Request):
    config = _get_config()
    body = await request.json()
    key = body.get("key", "")
    if not key:
        return JSONResponse({"error": "key required"}, status_code=400)
    config.delete_key(key)
    # Also delete suffix keys (e.g., _HEADER, _METHOD, _PATH, _DESC)
    for suffix in ["_HEADER", "_METHOD", "_PATH", "_DESC", "_PARAMS"]:
        config.delete_key(key + suffix)
    return {"ok": True}


# ── Saved Workspaces ─────────────────────────────────────────────────────────

from brickforge import USER_DIR
_WORKSPACES_FILE = USER_DIR / ".workspaces"


def _read_workspaces() -> list[dict]:
    if _WORKSPACES_FILE.exists():
        try:
            return json.loads(_WORKSPACES_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def _write_workspaces(workspaces: list[dict]) -> None:
    _WORKSPACES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _WORKSPACES_FILE.write_text(json.dumps(workspaces, indent=2) + "\n")


@router.get("/api/workspaces")
async def list_workspaces():
    return {"workspaces": _read_workspaces()}


@router.post("/api/workspaces")
async def save_workspace_entry(request: Request):
    """Save current workspace to .workspaces + token store."""
    config = _get_config()
    host = config.get("workspace.host") or ""
    token = os.environ.get("DATABRICKS_TOKEN", "")
    if not host:
        return JSONResponse({"error": "no workspace connected"}, status_code=400)

    # Save token to token store
    from brickforge.lib.token_store import get_token_store
    store = get_token_store()
    if token:
        store.set(host, token)

    # Derive label from host
    label = host.replace("https://", "").replace("http://", "").split(".")[0]

    # Update .workspaces file
    workspaces = _read_workspaces()
    # Replace if host already saved
    workspaces = [w for w in workspaces if w.get("host") != host]
    workspaces.append({"host": host, "label": label, "last_used": time.strftime("%Y-%m-%d")})
    _write_workspaces(workspaces)

    return {"ok": True, "label": label}


@router.delete("/api/workspaces")
async def delete_workspace_entry(request: Request):
    body = await request.json()
    host = body.get("host", "")
    if not host:
        return JSONResponse({"error": "host required"}, status_code=400)

    # Remove from token store
    from brickforge.lib.token_store import get_token_store
    store = get_token_store()
    store.delete(host)

    # Remove from .workspaces file
    workspaces = _read_workspaces()
    workspaces = [w for w in workspaces if w.get("host") != host]
    _write_workspaces(workspaces)

    return {"ok": True}


# ── GitHub Integration ──────────────────────────────────────────────────────

_github_device: dict | None = None


@router.get("/api/github/status")
async def github_status():
    """Check if GitHub is connected (token in keyring)."""
    from brickforge.lib.token_store import get_token_store
    store = get_token_store()
    token = store.get("github.com")
    config = _get_config()
    repo_name = config.get("github.repo_name") or ""
    repo_url = config.get("github.repo_url") or ""
    if token:
        try:
            from brickforge.lib.github_client import get_user
            username = get_user(token)
            return {"connected": True, "username": username, "repo_name": repo_name, "repo_url": repo_url}
        except Exception:
            return {"connected": False, "repo_name": repo_name, "repo_url": repo_url}
    return {"connected": False, "repo_name": repo_name, "repo_url": repo_url}


@router.post("/api/github/connect")
async def github_connect():
    """Start GitHub device flow."""
    global _github_device
    from brickforge.lib.github_client import start_device_flow
    _github_device = start_device_flow()
    return {
        "user_code": _github_device["user_code"],
        "verification_uri": _github_device["verification_uri"],
        "device_code": _github_device["device_code"],
        "interval": _github_device.get("interval", 5),
    }


@router.get("/api/github/poll")
async def github_poll():
    """Poll for device flow completion."""
    global _github_device
    if not _github_device:
        return {"status": "no_flow"}
    from brickforge.lib.github_client import poll_device_flow, get_user
    import asyncio
    token = await asyncio.to_thread(
        poll_device_flow, _github_device["device_code"],
        _github_device.get("interval", 5), timeout=10,
    )
    if token:
        from brickforge.lib.token_store import get_token_store
        get_token_store().set("github.com", token)
        username = get_user(token)
        _github_device = None
        return {"status": "connected", "username": username}
    return {"status": "pending"}


@router.post("/api/github/push")
async def github_push(request: Request):
    """Create repo + push code. SSE streaming."""
    body = await request.json()
    repo_name = body.get("name", "").strip()
    private = body.get("private", True)
    if not repo_name:
        return JSONResponse({"error": "repo name required"}, status_code=400)

    from brickforge.lib.token_store import get_token_store
    token = get_token_store().get("github.com")
    if not token:
        return JSONResponse({"error": "GitHub not connected"}, status_code=401)

    config = _get_config()

    async def generate():
        from brickforge.lib.sse import sse_line, sse_done
        from brickforge.lib.github_client import create_repo, push_bundle, get_user
        from brickforge.deploy.deploy_agent_app import build_agent_bundle
        import copy

        try:
            username = get_user(token)
            yield sse_line(f"[~] Connected as {username}\n")

            yield sse_line(f"[~] Creating repo {repo_name}...\n")
            clone_url = create_repo(token, repo_name, private)
            yield sse_line(f"[+] Repo: {clone_url}\n")

            yield sse_line("[~] Building agent bundle...\n")
            clean_config = copy.deepcopy(config.data)
            for section in ("workspace", "model"):
                if section in clean_config:
                    clean_config[section].pop("token", None)
            bundle = build_agent_bundle(clean_config)
            yield sse_line(f"[+] Bundle: {len(bundle)//1024}KB\n")

            yield sse_line("[~] Pushing to GitHub...\n")
            ok = push_bundle(token, clone_url, bundle)
            if ok:
                repo_url = f"https://github.com/{username}/{repo_name}"
                yield sse_line(f"[+] {repo_url}\n")
                # Save repo URL to config
                config.set("github.repo_url", repo_url)
                config.set("github.repo_name", repo_name)
                yield sse_done(True)
            else:
                yield sse_done(False, 1)
        except Exception as e:
            yield sse_line(f"[x] {e}\n")
            yield sse_done(False, 1)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Exec Log ──────────────────────────────────────────────────────────────────

STEP_ACTIONS: dict[str, list[str]] = {
    "deploy": ["exec-deploy-agent"],
    "tables": ["exec-tables", "exec-tables-uploaded"],
    "functions": ["exec-functions"],
    "genie": ["exec-genie"],
    "mlflow": ["exec-mlflow"],
    "lakebase": ["exec-lakebase"],
    "grants": ["exec-grants"],
    "build": ["exec-build"],
}


@router.get("/api/setup/exec-log")
async def exec_log(action: str = "", step: str = ""):
    log_dir = PROJECT_ROOT / "logs" / "exec"
    if step and not action:
        for a in STEP_ACTIONS.get(step, []):
            if (log_dir / f"{a}-latest.log").exists():
                action = a
                break
    if not action:
        return JSONResponse({"error": "action or step param required"}, status_code=400)
    latest = log_dir / f"{action}-latest.log"
    try:
        content = latest.read_text()
        return {"action": action, "log": content, "lines": [l for l in content.split("\n") if l]}
    except FileNotFoundError:
        return {"action": action, "log": "", "lines": []}


# ── Profiles ──────────────────────────────────────────────────────────────────

@router.get("/api/setup/profiles")
async def list_profiles():
    try:
        result = subprocess.run(
            ["databricks", "auth", "profiles"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PACKAGE_ROOT),
        )
        items = []
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 3:
                name = parts[0]
                host = parts[1]
                valid = parts[2].upper() == "YES"
                if host.startswith("http"):
                    items.append({"name": name, "host": host, "valid": valid})
        return {"items": items}
    except Exception as e:
        return {"items": [], "error": str(e)}


# ── Resources ─────────────────────────────────────────────────────────────────

@router.get("/api/setup/resources")
async def list_resources(type: str = ""):
    from brickforge.lib.env_utils import check_token_expiry, build_sub_env
    config = _get_config()

    expiry_err = check_token_expiry(config)
    if expiry_err:
        return {"items": [], "error": expiry_err}

    scripts = {
        "warehouses": """
from databricks.sdk import WorkspaceClient; import json
w = WorkspaceClient()
out = [{'id': wh.id, 'name': wh.name, 'state': str(wh.state).split('.')[-1]} for wh in w.warehouses.list()]
print(json.dumps(out))
""",
        "catalogs": """
from databricks.sdk import WorkspaceClient; import json
w = WorkspaceClient()
out = [c.name for c in w.catalogs.list() if c.name]
print(json.dumps(out))
""",
        "genie": """
from databricks.sdk import WorkspaceClient; import json
w = WorkspaceClient()
try:
  r = w.genie.list_spaces()
  spaces = getattr(r, 'spaces', []) or []
except: spaces = []
out = [{'id': getattr(s,'space_id',''), 'name': getattr(s,'title','')} for s in spaces]
print(json.dumps(out))
""",
        "endpoints": """
from databricks.sdk import WorkspaceClient; import json
w = WorkspaceClient()
eps = list(w.serving_endpoints.list())
fm = []
for e in eps:
    if not e.config: continue
    entities = e.config.served_entities or []
    is_ext = any(sc.external_model for sc in entities if sc.external_model)
    is_fm = any(sc.foundation_model for sc in entities if sc.foundation_model)
    if is_ext: fm.append({'name': e.name, 'type': 'external'})
    elif is_fm: fm.append({'name': e.name, 'type': 'foundation'})
if not fm:
    import re
    for e in eps:
        if re.search(r'claude|llama|mixtral|gpt|anthropic', e.name or '', re.I):
            fm.append({'name': e.name, 'type': 'pattern-match'})
print(json.dumps(fm))
""",
        "lakebase": """
from databricks.sdk import WorkspaceClient; import json
try:
  w = WorkspaceClient()
  instances = list(w.database.list_database_instances())
  out = [{'id': getattr(i,'name',''), 'name': getattr(i,'name',''), 'state': str(getattr(i,'state','UNKNOWN'))} for i in instances]
  print(json.dumps(out))
except Exception: print('[]')
""",
        "mlflow": """
import mlflow, json
from mlflow.tracking import MlflowClient
c = MlflowClient()
exps = c.search_experiments(order_by=['last_update_time DESC'], max_results=50)
out = [{'id': e.experiment_id, 'name': e.name, 'state': e.lifecycle_stage} for e in exps if e.lifecycle_stage == 'active']
print(json.dumps(out))
""",
    }

    # Features: return registry merged with current config (no subprocess needed)
    if type == "features":
        config = _get_config()
        entries = config.list()
        env_map = {e["key"]: e for e in entries}
        items = []
        for key, meta in FEATURE_REGISTRY.items():
            env_key = f"PROJECT_TOOL_{key}"
            entry = env_map.get(env_key)
            if entry:
                enabled = entry["value"].strip().lower() not in ("false", "0", "")
            else:
                enabled = meta["default"].lower() == "true"
            items.append({
                "key": key,
                "env_key": env_key,
                "label": meta["label"],
                "desc": meta["desc"],
                "default": meta["default"],
                "enabled": enabled,
                "configured": env_key in env_map,
            })
        return {"items": items}

    # Bricks: return registry merged with current config (no subprocess needed)
    if type == "bricks":
        config = _get_config()
        entries = config.list()
        env_map = {e["key"]: e for e in entries}
        items = []
        for key, meta in BRICKS_REGISTRY.items():
            env_key = f"PROJECT_BRICK_{key}"
            entry = env_map.get(env_key)
            if entry:
                enabled = entry["value"].strip().lower() not in ("false", "0", "")
            else:
                enabled = meta["default"].lower() == "true"
            items.append({
                "key": key,
                "env_key": env_key,
                "label": meta["label"],
                "desc": meta["desc"],
                "default": meta["default"],
                "enabled": enabled,
                "configured": env_key in env_map,
            })
        return {"items": items}

    script = scripts.get(type)
    if not script:
        return JSONResponse({"error": f"unknown type: {type}"}, status_code=400)

    try:
        env = build_sub_env(config)
        result = subprocess.run(
            [PYTHON,"-c", script.strip()],
            capture_output=True, text=True, timeout=20,
            cwd=str(PACKAGE_ROOT), env=env,
        )
        if result.returncode != 0:
            from brickforge.lib.env_utils import parse_subprocess_error; return {"items": [], "error": parse_subprocess_error(result.stderr, result.stdout)}
        items = json.loads(result.stdout.strip())
        return {"items": items}
    except Exception as e:
        return {"items": [], "error": str(e)}


# ── My IP ─────────────────────────────────────────────────────────────────────

@router.get("/api/setup/my-ip")
async def my_ip():
    """Return the server's public IP (for IP ACL whitelisting)."""
    try:
        import urllib.request
        ip = urllib.request.urlopen("https://api.ipify.org", timeout=5).read().decode().strip()
        return {"ip": ip}
    except Exception as e:
        return {"ip": None, "error": str(e)}


# ── Brand logo search ─────────────────────────────────────────────────────────

@router.get("/api/setup/brand")
async def brand_search(name: str = ""):
    """Search for a company logo via Brandfetch API."""
    import urllib.request, urllib.parse
    name = name.strip()
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)
    config = _get_config()
    api_key = os.environ.get("BRANDFETCH_API_KEY", "").strip() or (config.get("branding.brandfetch_api_key") or "")
    if not api_key:
        return JSONResponse({"error": "BRANDFETCH_API_KEY not configured — paste a logo URL directly instead"}, status_code=503)
    try:
        # Search by company name
        url = f"https://api.brandfetch.io/v2/search/{urllib.parse.quote(name)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if not isinstance(data, list) or not data:
            return JSONResponse({"error": "no results"}, status_code=404)
        first = data[0]
        logo_url = first.get("icon")
        # Fallback: Brand API by domain for logo formats
        if not logo_url and first.get("domain"):
            domain = str(first["domain"]).split("//")[-1].split("/")[0].lower()
            brand_url = f"https://api.brandfetch.io/v2/brands/domain/{urllib.parse.quote(domain)}"
            brand_req = urllib.request.Request(brand_url, headers={"Authorization": f"Bearer {api_key}"})
            try:
                with urllib.request.urlopen(brand_req, timeout=10) as brand_resp:
                    brand_data = json.loads(brand_resp.read())
                logos = brand_data.get("logos", [])
                preferred = next((l for l in logos if l.get("type") in ("logo", "icon")), logos[0] if logos else None)
                if preferred and preferred.get("formats"):
                    fmt = preferred["formats"]
                    svg = next((f for f in fmt if (f.get("format") or "").lower() == "svg"), None)
                    best = svg or fmt[0]
                    logo_url = best.get("src") or best.get("url")
            except Exception:
                pass
        if not logo_url:
            return JSONResponse({"error": "no logo found for this brand"}, status_code=404)
        return {"logoUrl": logo_url, "name": first.get("name", name), "domain": first.get("domain", "")}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ── Test ──────────────────────────────────────────────────────────────────────

TEST_SCRIPTS: dict[str, str] = {
    "host": """
import os, urllib.request, json, ssl
host = os.environ.get('DATABRICKS_HOST','').strip().rstrip('/')
token = os.environ.get('DATABRICKS_TOKEN','').strip()
if not host: print('[x] DATABRICKS_HOST not set'); exit(1)
ctx = ssl.create_default_context()
try:
    req = urllib.request.Request(host + '/oidc/.well-known/oauth-authorization-server')
    with urllib.request.urlopen(req, timeout=8, context=ctx) as r: json.loads(r.read())
except urllib.error.HTTPError as e:
    if e.code >= 500: print('[x] host unreachable: HTTP ' + str(e.code)); exit(1)
except Exception as e:
    print('[x] host unreachable: ' + str(e)[:100]); exit(1)
if not token:
    print('[+] reachable — ' + host.replace('https://',''));print('[~] no token set'); exit(0)
try:
    req = urllib.request.Request(host + '/api/2.0/preview/scim/v2/Me', headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
        d = json.loads(r.read()); print('[+] reachable — ' + d.get('userName', '?'));print('[+] authenticated')
except urllib.error.HTTPError as e:
    if e.code == 401: print('[x] token invalid (401 Unauthorized)'); exit(1)
    elif e.code == 403: print('[+] reachable — token valid (SCIM restricted)')
    else: print('[x] host reachable but auth failed: HTTP ' + str(e.code)); exit(1)
except Exception as e:
    print('[x] host reachable but auth failed: ' + str(e)[:100]); exit(1)
""".strip(),
    "warehouse": """
from databricks.sdk import WorkspaceClient; import os
wh_id = os.environ.get('DATABRICKS_WAREHOUSE_ID','').strip()
if not wh_id: print('[x] DATABRICKS_WAREHOUSE_ID not set'); exit(1)
w = WorkspaceClient()
try:
    wh = w.warehouses.get(wh_id); state = str(wh.state).split('.')[-1]
    print('[+] reachable — ' + wh.name + ' (' + state + ')')
except Exception as e:
    msg = str(e)[:150]
    if 'does not exist' in msg or '404' in msg or 'not found' in msg.lower():
        print('[x] warehouse not found in this workspace')
    else: print('[x] ' + msg)
    exit(1)
""".strip(),
    "schema": """
from databricks.sdk import WorkspaceClient; import os
spec = os.environ.get('PROJECT_UNITY_CATALOG_SCHEMA','').strip()
if not spec: print('[x] PROJECT_UNITY_CATALOG_SCHEMA not set'); exit(1)
w = WorkspaceClient()
try:
    s = w.schemas.get(full_name=spec); print('[+] found — ' + (s.full_name or spec))
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
""".strip(),
    "model": """
import os, urllib.request, json, ssl, time
endpoint = os.environ.get('AGENT_MODEL','').strip()
host = os.environ.get('DATABRICKS_HOST','').strip().rstrip('/')
if not endpoint:
    print('[x] AGENT_MODEL not set'); exit(1)
# Resolve bare endpoint name to full URL
if not endpoint.startswith('http'):
    if not host: print('[x] no host to resolve endpoint name'); exit(1)
    endpoint = host + '/serving-endpoints/' + endpoint + '/invocations'
token = (os.environ.get('AGENT_MODEL_TOKEN','') or os.environ.get('DATABRICKS_TOKEN','')).strip()
if not token: print('[x] no token'); exit(1)
payload = json.dumps({'messages': [{'role': 'user', 'content': 'Reply with exactly: pong'}], 'max_tokens': 10}).encode()
ctx = ssl.create_default_context()
try:
    t0 = time.time()
    req = urllib.request.Request(endpoint, data=payload, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        d = json.loads(r.read()); ms = int((time.time() - t0) * 1000)
        model = d.get('model','?'); reply = (d.get('choices',[{}])[0].get('message',{}).get('content','') or '').strip()[:40]
        print('[+] ' + model + ' — ' + str(ms) + 'ms — "' + reply + '"')
except urllib.error.HTTPError as e:
    print('[x] HTTP ' + str(e.code) + ' — ' + e.read().decode()[:120]); exit(1)
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
""".strip(),
    "mlflow": """
from databricks.sdk import WorkspaceClient; import os
eid = os.environ.get('MLFLOW_EXPERIMENT_ID','').strip()
if not eid: print('[x] MLFLOW_EXPERIMENT_ID not set'); exit(1)
w = WorkspaceClient()
try:
    exp = w.experiments.get_experiment(experiment_id=eid); print('[+] found — ' + getattr(exp, 'name', eid))
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
""".strip(),
    "deploy": """
from databricks.sdk import WorkspaceClient; import os
app_name = os.environ.get('DBX_APP_NAME', '').strip()
if not app_name: print('[x] DBX_APP_NAME not set'); exit(1)
w = WorkspaceClient()
try:
    app = w.apps.get(app_name)
    status = str(getattr(getattr(app, 'app_status', None), 'state', 'UNKNOWN'))
    url = getattr(app, 'url', '') or ''
    if 'RUNNING' in status: print('[+] running — ' + (url or app_name))
    elif 'STARTING' in status or 'PENDING' in status: print('[+] deploying — ' + status.lower())
    elif 'UNAVAILABLE' in status or 'STOPPED' in status: print('[+] app exists');print('[~] not running — ' + status.lower())
    else: print('[x] ' + app_name + ' — ' + status); exit(1)
except Exception as e:
    err = str(e)[:100]
    if 'not found' in err.lower() or '404' in err or 'does not exist' in err.lower(): print('[+] name configured');print('[~] not yet deployed')
    else: print('[x] ' + err); exit(1)
""".strip(),
    "tables": """
from databricks.sdk import WorkspaceClient; import os
from pathlib import Path
spec = os.environ.get('PROJECT_UNITY_CATALOG_SCHEMA','').strip()
if not spec: print('[x] schema not set'); exit(1)
root = Path('.')
csvs = []
for d in [root / 'data' / 'default' / 'csv', root / 'data' / 'gen' / 'csv', root / 'data' / 'upload' / 'csv']:
    if d.exists(): csvs.extend(d.glob('*.csv'))
if not csvs:
    # No CSVs but schema may still have tables (connect-existing mode)
    w = WorkspaceClient()
    try:
        tbls = list(w.tables.list(catalog_name=spec.split('.')[0], schema_name=spec.split('.')[1]))
        if tbls: print(f'[+] {len(tbls)} table(s) in {spec}'); exit(0)
        else: print(f'[+] schema exists');print(f'[~] no tables in {spec}'); exit(0)
    except Exception as e:
        print(f'[~] could not list tables: {e}')
    print('[x] no CSVs found and no tables in schema'); exit(1)
w = WorkspaceClient()
found = 0
for csv in csvs:
    tn = csv.stem.replace('-','_')
    try: w.tables.get(f'{spec}.{tn}'); found += 1
    except: pass
if found > 0: print(f'[+] {found}/{len(csvs)} table(s) in {spec}')
else: print(f'[+] schema exists');print(f'[~] no tables in {spec}')
""".strip(),
    "functions": """
import os
from databricks.sdk import WorkspaceClient
spec = os.environ.get('PROJECT_UNITY_CATALOG_SCHEMA','').strip()
if not spec: print('[x] schema not set'); exit(1)
cat, sch = spec.split('.', 1)
w = WorkspaceClient()
func_count = 0
try:
    funcs = list(w.functions.list(catalog_name=cat, schema_name=sch))
    func_count = len(funcs)
except Exception as e:
    print(f'[~] could not list functions: {e}')
proc_count = 0
try:
    wh = os.environ.get('DATABRICKS_WAREHOUSE_ID','')
    if wh:
        r = w.statement_execution.execute_statement(warehouse_id=wh, statement=f'SHOW PROCEDURES IN {spec}', wait_timeout='10s')
        proc_count = len(r.result.data_array) if r.result and r.result.data_array else 0
except Exception:
    pass
total = func_count + proc_count
if total == 0: print('[+] schema exists');print('[~] no functions or procedures in ' + spec); exit(0)
print(f'[+] {func_count} function(s) + {proc_count} procedure(s) in {spec}')
""".strip(),
}


@router.get("/api/setup/test")
async def setup_test(step: str = "", key: str = ""):
    from brickforge.lib.env_utils import check_token_expiry, build_sub_env
    config = _get_config()

    # Token expiry check (host test handles partial)
    if step != "host":
        expiry_err = check_token_expiry(config)
        if expiry_err:
            return {"ok": False, "message": expiry_err}

    # Dynamic test scripts for genie/ka per-instance
    script = TEST_SCRIPTS.get(step)

    if step == "genie":
        # Test first Genie space from PROJECT_GENIE_SPACES
        script = """
from databricks.sdk import WorkspaceClient; import os
raw = os.environ.get('PROJECT_GENIE_SPACES','').strip()
if not raw: print('[x] PROJECT_GENIE_SPACES not set'); exit(1)
space_ids = [s.strip() for s in raw.split(',') if s.strip()]
w = WorkspaceClient()
for sid in space_ids:
    try:
        sp = w.genie.get_space(space_id=sid); print('[+] ' + sid[:12] + '... — ' + getattr(sp, 'title', sid))
    except Exception as e:
        print('[x] ' + sid[:12] + '... — ' + str(e)[:100]); exit(1)
""".strip()

    elif step == "bricks":
        if key and key.startswith("PROJECT_BRICK_") and key != "PROJECT_BRICK_KA":
            val = config.get(key) or "false"
            suffix = key.replace("PROJECT_BRICK_", "")
            meta = BRICKS_REGISTRY.get(suffix)
            label = meta["label"] if meta else suffix.lower()
            enabled = val.strip().lower() not in ("false", "0", "")
            status = "enabled" if enabled else "disabled"
            return {"ok": True, "message": f"{label}: {status}"}
        instances = config.list_by_prefix("PROJECT_KA_")
        first_active = next((i for i in instances if i["enabled"]), None)
        env_key = key or (first_active["key"] if first_active else "PROJECT_KA_DEFAULT")
        script = f"""
from databricks.sdk import WorkspaceClient; import os
ka_name = os.environ.get('{env_key}','').strip()
if not ka_name: print('[x] {env_key} not set'); exit(1)
w = WorkspaceClient()
try:
    ep = w.serving_endpoints.get(name=ka_name)
    state = str(ep.state.ready).split('.')[-1] if ep.state else '?'
    print('[+] ' + ka_name + ' — ' + state)
except Exception as e:
    print('[x] ' + str(e)[:100]); exit(1)
""".strip()

    elif step == "features":
        # Feature toggles: just report current state
        env_key = key or ""
        if env_key:
            feat_key = env_key.replace("PROJECT_TOOL_", "")
            meta = FEATURE_REGISTRY.get(feat_key)
            val = config.get(env_key) or (meta["default"] if meta else "false")
            enabled = val.strip().lower() not in ("false", "0", "")
            label = meta["label"] if meta else feat_key.lower()
            if enabled:
                return {"ok": True, "message": f"{label} enabled"}
            else:
                return {"ok": True, "message": f"{label} disabled"}
        return {"ok": True, "message": "features configured"}

    if not script:
        return {"ok": False, "message": f"no test for step: {step}"}

    env = build_sub_env(config)
    try:
        result = subprocess.run(
            [PYTHON, "-c", script],
            capture_output=True, text=True, timeout=25,
            cwd=str(PACKAGE_ROOT), env=env,
        )
        raw = (result.stdout or "").strip() or (result.stderr or "").strip()
        ok = result.returncode == 0 and raw.startswith("[+]")
        if ok:
            lines = raw.split("\n")
            msg = lines[0].lstrip("[+] ") if lines else "ok"
            warn = next((l.lstrip("[~] ") for l in lines[1:] if l.startswith("[~]")), None)
            detail = next((l.lstrip("[+] ") for l in lines[1:] if l.startswith("[+]")), None)
            resp: dict = {"ok": True, "message": msg}
            if warn:
                resp["warning"] = warn
            if detail:
                resp["detail"] = detail
            return resp
        # Parse error for clean user message
        from brickforge.lib.env_utils import parse_subprocess_error
        return {"ok": False, "message": parse_subprocess_error(result.stderr, result.stdout) if "Traceback" in raw or "blocked" in raw else (raw.lstrip("[x] ") if raw else "no response")}
    except Exception as e:
        from brickforge.lib.env_utils import log_error
        log_error("/api/setup/test", str(e))
        return {"ok": False, "message": str(e)}


# ── Upload CSV ────────────────────────────────────────────────────────────────

MAX_CSV_SIZE = 100 * 1024 * 1024  # 100 MB

_COL_NAME_RE = re.compile(r"[^a-zA-Z0-9_]")


def _list_schema_tables(config) -> list[dict]:
    """List tables with columns from the configured UC schema. Returns [] on failure."""
    env = {e["key"]: e["value"] for e in config.list()}
    spec = env.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if not spec or "." not in spec:
        return []
    cat, sch = spec.split(".", 1)
    from databricks.sdk import WorkspaceClient
    from brickforge.lib.env_utils import build_sub_env
    sub = build_sub_env(config)
    old_env = dict(os.environ)
    os.environ.update(sub)
    try:
        w = WorkspaceClient()
        tables = []
        for t in w.tables.list(catalog_name=cat, schema_name=sch):
            if not t.name:
                continue
            ttype = str(t.table_type).split(".")[-1] if t.table_type else "TABLE"
            cols = []
            try:
                detail = w.tables.get(full_name=f"{cat}.{sch}.{t.name}")
                cols = [
                    {"name": c.name, "type": str(c.type_name).split(".")[-1] if c.type_name else "STRING"}
                    for c in (detail.columns or [])
                ]
            except Exception:
                pass
            tables.append({"name": t.name, "type": ttype, "columns": cols})
        return tables
    finally:
        os.environ.clear()
        os.environ.update(old_env)


@router.get("/api/setup/schema-tables")
async def schema_tables():
    """List tables in the configured UC schema. On-demand, not called on page load."""
    config = _get_config()
    spec = {e["key"]: e["value"] for e in config.list()}.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    try:
        tables = _list_schema_tables(config)
        return {"tables": tables, "count": len(tables), "schema": spec}
    except Exception as e:
        return {"tables": [], "count": 0, "schema": spec, "error": str(e)[:200]}


@router.get("/api/setup/serving-endpoints")
async def serving_endpoints_list(filter: str = ""):
    """List serving endpoints. Optional filter: 'ka' for knowledge assistants, 'fm' for foundation models."""
    config = _get_config()
    try:
        from databricks.sdk import WorkspaceClient
        from brickforge.lib.env_utils import build_sub_env
        sub = build_sub_env(config)
        old_env = dict(os.environ)
        os.environ.update(sub)
        try:
            w = WorkspaceClient()
            if filter == "ka":
                # Use KA API for human-readable names (SDK or REST fallback)
                try:
                    if hasattr(w, 'knowledge_assistants'):
                        kas = list(w.knowledge_assistants.list_knowledge_assistants())
                        results = [{"name": ka.display_name or ka.name or "?", "endpoint": ka.endpoint_name or "", "type": "ka"} for ka in kas if ka.endpoint_name]
                    else:
                        # REST fallback for older SDK
                        import json as _json
                        resp = w.api_client.do("GET", "/api/2.0/knowledge-assistants")
                        kas = resp.get("knowledge_assistants", [])
                        results = [{"name": ka.get("display_name", ka.get("name", "?")), "endpoint": ka.get("endpoint_name", ""), "type": "ka"} for ka in kas if ka.get("endpoint_name")]
                    if results:
                        return {"endpoints": results, "count": len(results)}
                except Exception:
                    pass  # Fall back to serving endpoints below
            eps = list(w.serving_endpoints.list())
            results = []
            for ep in eps:
                entities = ep.config.served_entities if ep.config else []
                is_external = any(e.external_model for e in (entities or []))
                is_foundation = any(e.foundation_model for e in (entities or []))
                is_agent = not is_external and not is_foundation
                ep_type = "external" if is_external else "foundation" if is_foundation else "agent"
                if filter == "ka" and not is_agent:
                    continue
                if filter == "fm" and not (is_external or is_foundation):
                    continue
                results.append({"name": ep.name, "endpoint": ep.name, "type": ep_type})
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        return {"endpoints": results, "count": len(results)}
    except Exception as e:
        return {"endpoints": [], "count": 0, "error": str(e)[:200]}


@router.get("/api/setup/schema-functions")
async def schema_functions():
    """List functions and procedures in the configured UC schema. On-demand."""
    config = _get_config()
    env = {e["key"]: e["value"] for e in config.list()}
    spec = env.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if not spec or "." not in spec:
        return {"functions": [], "count": 0, "schema": ""}
    cat, sch = spec.split(".", 1)
    try:
        from databricks.sdk import WorkspaceClient
        from brickforge.lib.env_utils import build_sub_env
        sub = build_sub_env(config)
        old_env = dict(os.environ)
        os.environ.update(sub)
        try:
            w = WorkspaceClient()
            funcs = [{"name": f.name, "type": str(f.data_type).split(".")[-1] if f.data_type else "FUNCTION"} for f in w.functions.list(catalog_name=cat, schema_name=sch) if f.name]
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        return {"functions": funcs, "count": len(funcs), "schema": spec}
    except Exception as e:
        return {"functions": [], "count": 0, "schema": spec, "error": str(e)[:200]}


# ── Upload CSV ────────────────────────────────────────────────────────────────

@router.post("/api/setup/upload-csv")
async def upload_csv(files: list[UploadFile] = File(...)):
    """Accept user-uploaded CSV files and save them to data/upload/csv/."""
    upload_dir = PROJECT_ROOT / "data" / "upload" / "csv"
    upload_dir.mkdir(parents=True, exist_ok=True)
    init_dir = PROJECT_ROOT / "data" / "upload" / "init"
    init_dir.mkdir(parents=True, exist_ok=True)

    uploaded = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith(".csv"):
            uploaded.append({"name": f.filename or "?", "ok": False, "error": "not a .csv file"})
            continue
        # Sanitize filename to prevent path traversal
        safe_name = Path(f.filename).name
        if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
            uploaded.append({"name": f.filename, "ok": False, "error": "invalid filename"})
            continue
        try:
            content = await f.read()
            if len(content) > MAX_CSV_SIZE:
                uploaded.append({"name": safe_name, "ok": False, "error": f"file exceeds {MAX_CSV_SIZE // (1024*1024)}MB limit"})
                continue
            dest = upload_dir / safe_name
            dest.write_bytes(content)
            # Generate a minimal CREATE TABLE SQL from the CSV header
            header_line = content.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
            cols = [c.strip().strip('"').strip("'") for c in header_line.split(",") if c.strip()]
            # Sanitize column names to alphanumeric + underscores only
            cols = [_COL_NAME_RE.sub("_", c).strip("_") or f"col_{i}" for i, c in enumerate(cols)]
            table_name = _COL_NAME_RE.sub("_", Path(safe_name).stem).strip("_").lower() or "unnamed_table"
            col_defs = ", ".join(f"`{c}` STRING" for c in cols)
            sql = f"CREATE TABLE IF NOT EXISTS ${{catalog}}.${{schema}}.{table_name} ({col_defs});\n"
            (init_dir / f"create_{table_name}.sql").write_text(sql)
            uploaded.append({"name": safe_name, "ok": True})
        except Exception as e:
            uploaded.append({"name": safe_name, "ok": False, "error": str(e)[:200]})

    return {"ok": all(u["ok"] for u in uploaded), "uploaded": uploaded}


# ── Exec (SSE) ────────────────────────────────────────────────────────────────

NO_AUTH_ACTIONS = {"save-deploy-name", "forge-bridge", "save-feature-toggle", "save-brick-toggle"}


@router.post("/api/setup/exec")
async def setup_exec(request: Request):
    from brickforge.lib.env_utils import check_token_expiry, build_sub_env
    config = _get_config()

    body = await request.json()
    action = body.get("action", "")
    params = body.get("params", {})

    async def generate():
        logger = ExecLogger(action)

        # Token expiry check
        if action not in NO_AUTH_ACTIONS:
            expiry_err = check_token_expiry(config)
            if expiry_err:
                yield sse_line(f"[x] {expiry_err}\n", "err")
                logger.log(f"[x] {expiry_err}")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return

        sub_env = build_sub_env(config)

        # ── Direct call actions ────────────────────────────────────────

        # exec-same removed: replaced by cfg-model picker + save-model-endpoint

        if action == "forge-bridge":
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-workspace":
            ws_host = params.get("host", "")
            ws_token = params.get("token", "")
            # Restore token from keyring if switching to a saved workspace
            if params.get("from_keyring") and ws_host and not ws_token:
                from brickforge.lib.token_store import get_token_store
                ws_token = get_token_store().get(ws_host) or ""
            if not ws_host or not ws_token:
                yield sse_line("[x] host and token required\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            if not ws_host.startswith("http"):
                ws_host = "https://" + ws_host
            ws_host = ws_host.rstrip("/")
            for k in ["DATABRICKS_CONFIG_PROFILE", "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET",
                       "DATABRICKS_REFRESH_TOKEN", "DATABRICKS_TOKEN_ENDPOINT"]:
                config.disable(k)
            config.set_many({"DATABRICKS_HOST": ws_host, "DATABRICKS_TOKEN": ws_token})
            # Persist token + auto-save workspace
            try:
                from brickforge.lib.token_store import get_token_store
                get_token_store().set(ws_host, ws_token)
                label = ws_host.replace("https://", "").replace("http://", "").split(".")[0]
                workspaces = _read_workspaces()
                workspaces = [w for w in workspaces if w.get("host") != ws_host]
                workspaces.append({"host": ws_host, "label": label, "last_used": time.strftime("%Y-%m-%d")})
                _write_workspaces(workspaces)
            except Exception:
                pass
            for line in [f"[+] DATABRICKS_HOST = {ws_host}", f"[+] DATABRICKS_TOKEN = {ws_token[:8]}..."]:
                yield sse_line(line + "\n")
                logger.log(line)
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-manual":
            key = params.get("key", "")
            value = params.get("value", "")
            if not key or not value:
                yield sse_line("[x] key and value required\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            if key == "DATABRICKS_HOST" and not value.startswith("http"):
                value = "https://" + value
            if key == "DATABRICKS_HOST":
                value = value.rstrip("/")
            if key == "PROJECT_UNITY_CATALOG_SCHEMA" and "." in value:
                config.set_many({key: value})
                catalog, schema = value.split(".", 1)
                cmd = [PYTHON,"-c", _save_schema_script(catalog, schema)]
                async for event in stream_subprocess(cmd, env=sub_env, cwd=PROJECT_ROOT, logger=logger):
                    yield event
                logger.finish(True)
                return
            config.set_many({key: value})
            display = f"{value[:8]}..." if "TOKEN" in key else value
            line = f"[+] {key} = {display}"
            yield sse_line(line + "\n")
            logger.log(line)
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-feature-toggle":
            key = params.get("key", "")
            enabled = params.get("enabled", "true")
            if not key or key not in FEATURE_REGISTRY:
                yield sse_line(f"[x] unknown feature: {key}\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            env_key = f"PROJECT_TOOL_{key}"
            config.set_many({env_key: enabled})
            state = "enabled" if enabled.lower() == "true" else "disabled"
            label = FEATURE_REGISTRY[key]["label"]
            yield sse_line(f"[+] {label} ({env_key}) {state}\n")
            logger.log(f"[+] {env_key} = {enabled}")
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-brick-toggle":
            key = params.get("key", "")
            enabled = params.get("enabled", "true")
            if not key or key not in BRICKS_REGISTRY:
                yield sse_line(f"[x] unknown brick: {key}\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            env_key = f"PROJECT_BRICK_{key}"
            config.set_many({env_key: enabled})
            state = "enabled" if enabled.lower() == "true" else "disabled"
            label = BRICKS_REGISTRY[key]["label"]
            yield sse_line(f"[+] {label} ({env_key}) {state}\n")
            logger.log(f"[+] {env_key} = {enabled}")
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-multi-instance":
            prefix = params.get("prefix", "")
            slug = params.get("slug", "")
            url = params.get("url", "")
            header = params.get("header", "")
            if not prefix or not slug or not url:
                yield sse_line("[x] prefix, slug, and url required\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            mkey = f"{prefix}{slug}"
            updates = {mkey: url}
            if header:
                updates[f"{mkey}_HEADER"] = header
            config.set_many(updates)
            yield sse_line(f"[+] {mkey} = {url}\n")
            logger.log(f"[+] {mkey} = {url}")
            if header:
                yield sse_line(f"[+] {mkey}_HEADER = {header.split(':')[0]}:***\n")
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-deploy-name":
            app_name = params.get("name", "")
            if not app_name:
                yield sse_line("[x] no app name provided\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            config.set_many({"DBX_APP_NAME": app_name})
            yield sse_line(f"[+] DBX_APP_NAME = {app_name}\n")
            logger.log(f"[+] DBX_APP_NAME = {app_name}")
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-warehouse":
            wh_id = params.get("id", "")
            if not wh_id:
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            config.set_many({"DATABRICKS_WAREHOUSE_ID": wh_id})
            yield sse_line(f"[+] DATABRICKS_WAREHOUSE_ID = {wh_id}\n")
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-model-endpoint":
            ep_name = params.get("name", "")
            if not ep_name:
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            config.set_many({"AGENT_MODEL": ep_name})
            # Clear cross-workspace token (same-workspace mode)
            config.set("model.token", None)
            yield sse_line(f"[+] same-workspace mode\n")
            yield sse_line(f"[+] AGENT_MODEL = {ep_name}\n")
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-schema":
            catalog = params.get("catalog", "")
            schema = params.get("schema", "")
            if not catalog or not schema:
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            config.set_many({"PROJECT_UNITY_CATALOG_SCHEMA": f"{catalog}.{schema}"})
            cmd = [PYTHON,"-c", _save_schema_script(catalog, schema)]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PROJECT_ROOT, logger=logger):
                yield event
            logger.finish(True)
            return

        if action == "save-genie":
            genie_id = params.get("id", "")
            genie_name = params.get("name", "")
            if not genie_id:
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            existing_arr = config.get("tools.genie_spaces") or []
            existing_ids = set(existing_arr) if isinstance(existing_arr, list) else set()
            existing_ids.discard("")
            existing_ids.add(genie_id)
            new_value = ",".join(sorted(existing_ids))
            config.set_many({"PROJECT_GENIE_SPACES": new_value})
            # Save name for display
            if genie_name:
                names = config.get("tools.genie_names") or {}
                names[genie_id] = genie_name
                config.set("tools.genie_names", names)
            yield sse_line(f"[+] {genie_name or genie_id} added\n")
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-genie-rename":
            space_id = params.get("space_id", "")
            new_name = params.get("name", "")
            if not space_id or not new_name:
                yield sse_line("[x] space_id and name required\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            try:
                w = _get_workspace_client()
                w.genie.update_space(space_id=space_id, title=new_name)
                # Update cached name
                names = config.get("tools.genie_names") or {}
                names[space_id] = new_name
                config.set("tools.genie_names", names)
                yield sse_line(f"[+] Genie space renamed to '{new_name}'\n")
                logger.finish(True)
                yield sse_done(True)
            except Exception as e:
                yield sse_line(f"[x] rename failed: {e}\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
            return

        if action == "save-lakebase":
            lb_name = params.get("name", "")
            if not lb_name:
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            config.set_many({"LAKEBASE_INSTANCE_NAME": lb_name})
            yield sse_line(f"[+] LAKEBASE_INSTANCE_NAME = {lb_name}\n")
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-mlflow":
            exp_id = params.get("id", "")
            if not exp_id:
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            config.set_many({"MLFLOW_EXPERIMENT_ID": exp_id})
            yield sse_line(f"[+] MLFLOW_EXPERIMENT_ID = {exp_id}\n")
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-api":
            slug = params.get("slug", "")
            if not slug:
                yield sse_line("[x] no API name provided\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            prefix = f"PROJECT_API_{slug}"
            updates: dict[str, str] = {}
            api_type = params.get("type", "")
            if api_type == "uc" and params.get("conn"):
                updates[f"{prefix}_CONN"] = params["conn"]
            if api_type == "direct" and params.get("url"):
                updates[f"{prefix}_URL"] = params["url"]
            if params.get("method", "GET") != "GET":
                updates[f"{prefix}_METHOD"] = params["method"]
            if params.get("path", "/") != "/":
                updates[f"{prefix}_PATH"] = params["path"]
            if params.get("desc"):
                updates[f"{prefix}_DESC"] = params["desc"]
            if params.get("apiParams"):
                updates[f"{prefix}_PARAMS"] = params["apiParams"]
            if params.get("header") and api_type == "direct":
                updates[f"{prefix}_HEADER"] = params["header"]
            if not updates:
                yield sse_line("[x] no connection or URL provided\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            config.set_many(updates)
            for k, v in updates.items():
                yield sse_line(f"[+] {k} = {v}\n")
                logger.log(f"[+] {k} = {v}")
            logger.finish(True)
            yield sse_done(True)
            return

        if action == "save-host":
            profile = params.get("profile", "")
            if not profile:
                yield sse_line("[x] no profile selected\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            cmd = [PYTHON,"-c", f"""
import subprocess, re
out = subprocess.check_output(['databricks', 'auth', 'profiles'], text=True)
host = None
for line in out.strip().split('\\n')[1:]:
    parts = re.split(r'\\s{{2,}}', line.strip())
    if len(parts) >= 2 and parts[0].strip() == '{profile}':
        host = parts[1].strip()
        break
if not host: print('[x] profile not found: {profile}'); exit(1)
if not host.startswith('http'): host = 'https://' + host
print('[+] DATABRICKS_HOST = ' + host)
print('[+] DATABRICKS_CONFIG_PROFILE = {profile}')
""".strip()]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PROJECT_ROOT, logger=logger):
                yield event
            logger.finish(True)
            return

        # ── Subprocess actions ─────────────────────────────────────────

        if action == "exec-pat":
            cmd = [PYTHON,"-c", _pat_script()]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PROJECT_ROOT, logger=logger):
                yield event
            logger.finish(True)
            return

        if action == "exec-genie":
            genie_name = params.get("name", "Project Data")
            sub_env["GENIE_ROOM_NAME"] = genie_name
            cmd = [PYTHON,"data/init/create_genie_space.py"]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PACKAGE_ROOT, logger=logger):
                yield event
            # Reload config (subprocess wrote genie space ID to config.json)
            _token_before = config._data.get("workspace", {}).get("token")
            config._data = config._load()
            if _token_before:
                config._data.setdefault("workspace", {})["token"] = _token_before
            config._save()  # syncs to project mirror
            config._sync_env()
            logger.finish(True)
            return

        if action == "exec-assets":
            schema_spec = params.get("schema", "")
            if schema_spec:
                config.set_many({"PROJECT_UNITY_CATALOG_SCHEMA": schema_spec})
                sub_env["PROJECT_UNITY_CATALOG_SCHEMA"] = schema_spec
            cmd = [PYTHON,"data/init/create_all_assets.py"]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PACKAGE_ROOT, logger=logger):
                yield event
            logger.finish(True)
            return

        if action == "exec-deploy-agent":
            config_dict = config.data  # structured JSON config
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=str(PROJECT_ROOT), prefix=".tmp-deploy-", delete=False) as f:
                json.dump(config_dict, f, indent=2)
                tmp_path = f.name
            # Single subprocess: deploy + grants
            app_name = config.get("app.name") or "brickforge-agent"
            schema = config.get("workspace.unity_catalog_schema") or ""
            deploy_and_grant_script = f"""
import subprocess, sys, os
ROOT = os.environ.get('BRICKFORGE_ROOT', '.')
PY = sys.executable

# Step 1: Deploy
print('[~] Deploying agent app...', flush=True)
r = subprocess.run([PY, 'deploy/deploy_agent_app.py', '--config', '{tmp_path}'], cwd=ROOT)
if r.returncode != 0:
    print('[x] Deploy failed', flush=True)
    sys.exit(1)

# Cleanup temp config
try:
    os.unlink('{tmp_path}')
except OSError:
    pass

# Step 2: Grants
print('\\n[~] Running grants for app service principal...', flush=True)
r = subprocess.run([PY, 'deploy/grant/run_all_grants.py', '{app_name}'], cwd=ROOT)
if r.returncode != 0:
    print('[x] Grants failed (non-blocking)', flush=True)

print('[+] Deploy complete', flush=True)
"""
            cmd = [PYTHON, "-c", deploy_and_grant_script.strip()]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PACKAGE_ROOT, logger=logger):
                yield event
            logger.finish(True)
            return

        if action == "exec-git-push":
            repo_url = params.get("repo_url", "")
            if not repo_url:
                yield sse_line("[x] repo_url required\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            config_dict = config.to_env_dict()
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=str(PROJECT_ROOT), prefix=".tmp-deploy-", delete=False) as f:
                json.dump(config_dict, f, indent=2)
                tmp_path = f.name
            cmd = [PYTHON,"deploy/git_push.py", "--repo-url", repo_url, "--config", tmp_path]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PACKAGE_ROOT, logger=logger):
                yield event
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            logger.finish(True)
            return

        if action == "exec-auth-login":
            host_val = params.get("host", "")
            if not host_val:
                yield sse_line("[x] no host provided\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            cmd = [PYTHON,"-c", _auth_login_script(host_val, params.get("profile", ""))]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PROJECT_ROOT, logger=logger):
                yield event
            logger.finish(True)
            return

        if action == "save-model-profile":
            profile = params.get("profile", "")
            if not profile:
                yield sse_line("[x] no profile selected\n", "err")
                logger.finish(False, 1)
                yield sse_done(False, 1)
                return
            cmd = [PYTHON,"-c", _model_profile_script(profile)]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PROJECT_ROOT, logger=logger):
                yield event
            logger.finish(True)
            return

        if action == "exec-build":
            # Prerequisites
            host = config.get("workspace.host") or ""
            token = config.get("workspace.token") or ""
            wh = config.get("workspace.warehouse_id") or ""
            schema_spec = config.get("workspace.unity_catalog_schema") or ""
            if not host or not token:
                yield sse_line("[x] Connect a workspace first\n", "err")
                yield sse_done(False, 1); logger.finish(False, 1); return
            if not wh:
                yield sse_line("[x] Select a SQL warehouse first\n", "err")
                yield sse_done(False, 1); logger.finish(False, 1); return
            if not schema_spec or "." not in schema_spec:
                yield sse_line("[x] Set a Unity Catalog schema first\n", "err")
                yield sse_done(False, 1); logger.finish(False, 1); return

            # Stash dir as parameter (not saved to config)
            stash_dir = params.get("stash_dir", "")
            if stash_dir:
                sub_env["FORGE_STASH_DIR"] = stash_dir

            # Step 1: Schema
            yield sse_line("\n[~] Schema - creating catalog and schema...\n")
            cmd = [PYTHON, "data/init/create_catalog_schema.py"]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PACKAGE_ROOT, logger=logger):
                yield event

            # Step 2: Tables
            yield sse_line("\n[~] Tables - provisioning tables...\n")
            cmd = [PYTHON, "-c", _tables_script()]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PACKAGE_ROOT, logger=logger):
                yield event

            # Step 2b: CSV data
            yield sse_line("\n[~] Tables - loading CSV data...\n")
            cmd = [PYTHON, str(PACKAGE_ROOT / "data" / "py" / "csv_to_delta.py")]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PACKAGE_ROOT, logger=logger):
                yield event

            # Step 3: Functions
            yield sse_line("\n[~] Functions - creating UC functions...\n")
            cmd = [PYTHON, str(PACKAGE_ROOT / "data" / "init" / "create_all_functions.py")]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PACKAGE_ROOT, logger=logger):
                yield event

            # Step 4: Procedures
            yield sse_line("\n[~] Procedures - creating UC procedures...\n")
            cmd = [PYTHON, str(PACKAGE_ROOT / "data" / "init" / "create_all_procedures.py")]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PACKAGE_ROOT, logger=logger):
                yield event

            # Step 5: Genie
            genie_ids = config.get("tools.genie_spaces") or []
            if not genie_ids:
                genie_name = config.get("genie_room.name") or config.get("workspace.unity_catalog_schema") or "Project Data"
                sub_env["GENIE_ROOM_NAME"] = genie_name
                yield sse_line("\n[~] Genie - creating space...\n")
                cmd = [PYTHON, "data/init/create_genie_space.py"]
                async for event in stream_subprocess(cmd, env=sub_env, cwd=PACKAGE_ROOT, logger=logger):
                    yield event
            else:
                yield sse_line("\n[+] Genie - already configured, skipping\n")

            # Step 6: MLflow
            mlflow_id = (config.get("app.mlflow_experiment_id") or "").strip()
            if not mlflow_id:
                yield sse_line("\n[~] MLflow - creating experiment...\n")
                cmd = [PYTHON, str(PACKAGE_ROOT / "data" / "init" / "create_mlflow_experiment.py")]
                async for event in stream_subprocess(cmd, env=sub_env, cwd=PACKAGE_ROOT, logger=logger):
                    yield event
            else:
                yield sse_line("\n[+] MLflow - already configured, skipping\n")

            # Reload config (subprocesses may have written genie ID, mlflow ID)
            _token_before = config._data.get("workspace", {}).get("token")
            config._data = config._load()
            if _token_before:
                config._data.setdefault("workspace", {})["token"] = _token_before
            config._save()
            config._sync_env()

            yield sse_line("\n[+] Build complete. Switch to Setup to configure model and deploy.\n")
            logger.finish(True)
            yield sse_done(True)
            return

        # Mapped commands
        cmd_map = {
            "exec-tables": [PYTHON,"-c", _tables_script()],
            "exec-tables-uploaded": [PYTHON,"-c", _tables_uploaded_script()],
            "exec-functions": [PYTHON,"-c", _functions_script()],
            "exec-lakebase": [PYTHON, str(PACKAGE_ROOT / "data" / "init" / "create_lakebase.py")],
            "exec-mlflow": [PYTHON, str(PACKAGE_ROOT / "data" / "init" / "create_mlflow_experiment.py")],
            "exec-grants": [PYTHON, str(PACKAGE_ROOT / "deploy" / "grant" / "run_all_grants.py")],
            "exec-ka": [PYTHON,"-c", _ka_script()],
        }

        if action in cmd_map:
            cmd = cmd_map[action]
            async for event in stream_subprocess(cmd, env=sub_env, cwd=PROJECT_ROOT, logger=logger):
                yield event
            # Reload config if subprocess may have written back (genie ID, mlflow ID, lakebase)
            if action in ("exec-mlflow", "exec-lakebase"):
                _token_before = config._data.get("workspace", {}).get("token")
                config._data = config._load()
                if _token_before:
                    config._data.setdefault("workspace", {})["token"] = _token_before
                config._save()
                config._sync_env()
            logger.finish(True)
            return

        # Unknown
        yield sse_line(f"[x] unknown action: {action}\n", "err")
        logger.finish(False, 1)
        yield sse_done(False, 1)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })


# ── Prompts ───────────────────────────────────────────────────────────────────

@router.get("/api/setup/prompts")
async def list_prompts():
    from brickforge.lib.project_paths import prompt_dir as _prompt_dir
    prompt_dir = _prompt_dir()
    try:
        files = []
        for f in sorted(prompt_dir.iterdir()):
            if f.name.startswith("."):
                continue
            files.append({"name": f.name, "content": f.read_text()})
        return {"files": files}
    except FileNotFoundError:
        return {"files": []}


@router.put("/api/setup/prompts")
async def save_prompt(request: Request):
    body = await request.json()
    name = body.get("name", "")
    content = body.get("content", "")
    if not name or "/" in name or ".." in name:
        return JSONResponse({"error": "invalid filename"}, status_code=400)
    from brickforge.lib.project_paths import prompt_dir as _prompt_dir
    prompt_dir = _prompt_dir()
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / name).write_text(content)
    return {"ok": True}


# ── Inline script templates ──────────────────────────────────────────────────

def _save_schema_script(catalog: str, schema: str) -> str:
    return f"""
from databricks.sdk import WorkspaceClient
import re; from pathlib import Path
w = WorkspaceClient()
spec = '{catalog}.{schema}'
try:
    w.schemas.get(full_name=spec)
    print('[+] schema exists:', spec)
except:
    cat_exists = False
    try:
        w.catalogs.get(name='{catalog}')
        cat_exists = True
    except: pass
    if cat_exists:
        try:
            w.schemas.create(name='{schema}', catalog_name='{catalog}')
            print('[+] schema created:', spec)
        except Exception as e2:
            print('[x] cannot create schema:', str(e2)[:200]); exit(1)
    else:
        try:
            w.api_client.do('POST', '/api/2.1/unity-catalog/catalogs', body={{'name': '{catalog}', 'storage_mode': 'DEFAULT_STORAGE'}})
            w.schemas.create(name='{schema}', catalog_name='{catalog}')
            print('[+] catalog + schema created:', spec)
        except Exception as e3:
            print('[x]', str(e3)[:200]); exit(1)
from brickforge.lib.config_json import read_config, write_config
cfg = read_config()
cfg.setdefault('workspace', {{}})['unity_catalog_schema'] = spec
write_config(cfg)
print('[+] PROJECT_UNITY_CATALOG_SCHEMA = ' + spec)
""".strip()


def _pat_script() -> str:
    return """
import os
import os, urllib.request, json, ssl, datetime
host = os.environ.get('DATABRICKS_HOST','').strip().rstrip('/')
token = os.environ.get('DATABRICKS_TOKEN','').strip()
if not host: print('[x] DATABRICKS_HOST not set'); exit(1)
if not token: print('[x] DATABRICKS_TOKEN not set'); exit(1)
today = datetime.date.today().strftime('%Y%m%d')
comment = f'brickforge-7days-{today}'
print(f'[~] Creating PAT "{comment}" on {host}...')
ctx = ssl.create_default_context()
try:
    data = json.dumps({{'lifetime_seconds': 604800, 'comment': comment}}).encode()
    req = urllib.request.Request(f'{{host}}/api/2.0/token/create', data=data, method='POST')
    req.add_header('Authorization', f'Bearer {{token}}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        resp = json.loads(r.read())
    pat = resp.get('token_value','')
    if not pat: print('[x] Empty PAT response'); exit(1)
    from pathlib import Path
    import re
    f = Path('.env.local')
    lines = f.read_text().splitlines() if f.exists() else []
    new = []; found = False
    for line in lines:
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
        if m and m.group(1) == 'DATABRICKS_TOKEN': new.append('DATABRICKS_TOKEN=' + pat); found = True
        else: new.append(line)
    if not found: new.append('DATABRICKS_TOKEN=' + pat)
    f.write_text('\\n'.join(new) + '\\n')
    print(f'[+] PAT created: {{pat[:12]}}... (7 days)')
except Exception as e:
    print(f'[x] {{str(e)[:150]}}'); exit(1)
""".strip()


def _tables_script() -> str:
    return """
import subprocess, sys, os
from pathlib import Path
ROOT = Path('.')
print('[~] Creating catalog and schema...')
sys.stdout.flush()
r = subprocess.run([sys.executable, 'data/init/create_catalog_schema.py'], cwd=ROOT)
if r.returncode != 0: print('[x] create_catalog_schema failed'); sys.exit(1)
print('[+] Catalog and schema ready')
sql_files = []
stash_dir = os.environ.get('FORGE_STASH_DIR', '').strip()
use_demo = (os.environ.get('USE_DEMO_DATA') or os.environ.get('USE_DEFAULT_DATA', 'true')).strip().lower()
if stash_dir:
    d = ROOT / stash_dir / 'data' / 'init'
    if d.exists(): sql_files.extend(sorted(d.glob('create_*.sql')))
if not stash_dir and use_demo in ('true', '1', 'yes'):
    d = ROOT / 'data' / 'demo' / 'init'
    if d.exists(): sql_files.extend(sorted(d.glob('create_*.sql')))
project_dir = os.environ.get('PROJECT_DIR', '').strip()
if project_dir:
    d = Path(project_dir) / 'gen' / 'init'
    if d.exists(): sql_files.extend(sorted(d.glob('create_*.sql')))
elif os.environ.get('USE_GEN_DATA', 'false').strip().lower() in ('true', '1', 'yes'):
    d = ROOT / 'data' / 'gen' / 'init'
    if d.exists(): sql_files.extend(sorted(d.glob('create_*.sql')))
if not sql_files: print('[~] No table SQL files found'); sys.exit(0)
print(f'[~] Provisioning {len(sql_files)} table(s)...')
for i, sf in enumerate(sql_files, 1):
    name = sf.stem.replace('create_', '')
    print(f'[~] ({i}/{len(sql_files)}) {name}...')
    sys.stdout.flush()
    r = subprocess.run([sys.executable, 'data/py/run_sql.py', str(sf)], cwd=ROOT)
    if r.returncode != 0: print(f'[x] Failed: {name}'); sys.exit(1)
    print(f'[+] {name}')
print(f'[+] All {len(sql_files)} table(s) provisioned')
""".strip()


def _tables_uploaded_script() -> str:
    return """
import subprocess, sys, os
from pathlib import Path
ROOT = Path('.')
print('[~] Creating catalog and schema...')
sys.stdout.flush()
r = subprocess.run([sys.executable, 'data/init/create_catalog_schema.py'], cwd=ROOT)
if r.returncode != 0: print('[x] create_catalog_schema failed'); sys.exit(1)
print('[+] Catalog and schema ready')
upload_init = ROOT / 'data' / 'upload' / 'init'
sql_files = sorted(upload_init.glob('create_*.sql')) if upload_init.exists() else []
if not sql_files: print('[x] No uploaded table SQL files found'); sys.exit(1)
# Also load the CSVs into the tables
upload_csv_dir = ROOT / 'data' / 'upload' / 'csv'
print(f'[~] Provisioning {len(sql_files)} uploaded table(s)...')
for i, sf in enumerate(sql_files, 1):
    rel = str(sf.relative_to(ROOT))
    name = sf.stem.replace('create_', '')
    print(f'[~] ({i}/{len(sql_files)}) {name}...')
    sys.stdout.flush()
    r = subprocess.run([sys.executable, 'data/py/run_sql.py', rel], cwd=ROOT)
    if r.returncode != 0: print(f'[x] Failed: {rel}'); sys.exit(1)
    # Load CSV data into the table
    csv_path = upload_csv_dir / f'{name}.csv'
    if not csv_path.exists():
        # Try original filename patterns
        candidates = list(upload_csv_dir.glob(f'{name}*.csv'))
        csv_path = candidates[0] if candidates else csv_path
    if csv_path.exists():
        print(f'[~] Loading data from {csv_path.name}...')
        sys.stdout.flush()
        r2 = subprocess.run([sys.executable, 'data/py/csv_to_delta.py', str(csv_path)], cwd=ROOT)
        if r2.returncode != 0: print(f'[~] CSV load warning: {csv_path.name}')
    print(f'[+] {name}')
print(f'[+] All {len(sql_files)} uploaded table(s) provisioned')
""".strip()


def _functions_script() -> str:
    funcs_path = str(PACKAGE_ROOT / "data" / "init" / "create_all_functions.py")
    procs_path = str(PACKAGE_ROOT / "data" / "init" / "create_all_procedures.py")
    return f"""
import subprocess, sys
print('[~] Creating UC functions...')
sys.stdout.flush()
r = subprocess.run([sys.executable, '{funcs_path}'])
if r.returncode != 0: print('[x] create_all_functions failed'); sys.exit(1)
print('[~] Creating UC procedures...')
sys.stdout.flush()
r = subprocess.run([sys.executable, '{procs_path}'])
if r.returncode != 0: print('[x] create_all_procedures failed'); sys.exit(1)
print('[+] All functions and procedures created')
""".strip()


def _ka_script() -> str:
    return """
import os
import subprocess, sys
print('[~] creating Knowledge Assistant from YAML...')
sys.stdout.flush()
subprocess.check_call([sys.executable, 'scripts/py/ka/create_kas_from_yml.py', '--skip-existing'], stdout=sys.stdout, stderr=sys.stderr)
print('[+] Knowledge Assistant provisioned')
""".strip()


def _auth_login_script(host: str, profile: str) -> str:
    host_url = host if host.startswith("http") else f"https://{host}"
    host_url = host_url.rstrip("/")
    safe_profile = profile.replace("'", "\\'") if profile else ""
    return f"""
import os
from pathlib import Path
import os, configparser, subprocess, sys

host = '{host_url}'
profile = '{safe_profile}' or host.split('//')[1].split('.')[0]

from lib.config_json import read_config, write_config
cfg = read_config()
cfg.setdefault('workspace', {{}})['host'] = host
cfg['workspace']['config_profile'] = profile
write_config(cfg)
print('[+] DATABRICKS_HOST = ' + host)
print('[+] DATABRICKS_CONFIG_PROFILE = ' + profile)

cfg_path = Path.home() / '.databrickscfg'
cfg = configparser.ConfigParser()
if cfg_path.exists(): cfg.read(str(cfg_path))
if not cfg.has_section(profile): cfg.add_section(profile)
cfg.set(profile, 'host', host)
cfg.set(profile, 'auth_type', 'databricks-cli')
with open(str(cfg_path), 'w') as f: cfg.write(f)
print('[+] profile "' + profile + '" added to ~/.databrickscfg')

print('[~] running databricks auth login...')
sys.stdout.flush()
try:
    result = subprocess.run(['databricks', 'auth', 'login', '--host', host, '--profile', profile], timeout=60, capture_output=True, text=True)
    if result.returncode == 0: print('[+] authenticated via OAuth')
    else: print('[~] auth login returned: ' + (result.stderr or result.stdout or '').strip()[:120])
except subprocess.TimeoutExpired:
    print('[~] auth login timed out')
except Exception as e:
    print('[~] auth login failed: ' + str(e)[:80])
print('[+] done')
""".strip()


def _model_profile_script(profile: str) -> str:
    return f"""
import os
from scripts.py.setup_dbx_env import _profile_for_host, _isolated_client, _redact
import subprocess, re
out = subprocess.check_output(['databricks', 'auth', 'profiles'], text=True)
host = None
for line in out.strip().split('\\n')[1:]:
    parts = re.split(r'\\s{{2,}}', line.strip())
    if len(parts) >= 2 and parts[0].strip() == '{profile}':
        host = parts[1].strip()
        break
if not host: print('[x] profile not found: {profile}'); exit(1)
if not host.startswith('http'): host = 'https://' + host
endpoint = host.rstrip('/') + '/serving-endpoints/databricks-claude-sonnet-4-6/invocations'
w = _isolated_client('{profile}')
t = w.tokens.create(comment='agent-forge-fm', lifetime_seconds=604800)
from lib.config_json import read_config, write_config
cfg = read_config()
cfg.setdefault('model', {{}})['endpoint'] = endpoint
cfg['model']['token'] = t.token_value
write_config(cfg)
print('[+] AGENT_MODEL = ' + endpoint)
print('[+] AGENT_MODEL_TOKEN = ' + _redact(t.token_value))
""".strip()
