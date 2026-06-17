"""
Mage route - SSE chat endpoint for the Mage assistant.
"""

import asyncio
import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from brickforge.lib.mage_agent import MageAgent

router = APIRouter(prefix="/api/mage", tags=["mage"])

# In-memory session (per server process)
_session: dict = {
    "agent": None,
    "mode": None,
    "domain": "",
    "requirements": "",
    "phase": "startup",  # startup | connected | ready
    "startup_step": 0,
    "model": None,
}


def _get_config():
    from brickforge.server import config
    return config


def _session_file() -> Path:
    """Get session file path (project-scoped if available)."""
    project_dir = os.environ.get("PROJECT_DIR")
    if project_dir:
        return Path(project_dir) / "mage_session.json"
    from brickforge import USER_DIR
    return USER_DIR / "mage_session.json"


def _load_session():
    """Load session from disk if exists."""
    path = _session_file()
    if path.exists():
        try:
            data = json.loads(path.read_text())
            _session["mode"] = data.get("mode")
            _session["domain"] = data.get("domain", "")
            _session["requirements"] = data.get("requirements", "")
        except Exception:
            pass


def _save_session():
    """Persist session to disk."""
    path = _session_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "mode": _session["mode"],
        "domain": _session["domain"],
        "requirements": _session["requirements"],
    }, indent=2))


def _state_summary(config) -> str:
    """Build compact state summary for system prompt injection."""
    host = config.get("workspace.host") or "not connected"
    wh = config.get("workspace.warehouse_id") or "not set"
    schema = config.get("workspace.unity_catalog_schema") or "not set"
    model = config.get("model.endpoint") or "not set"
    app = config.get("app.name") or "not set"
    domain = _session.get("domain", "")
    reqs = _session.get("requirements", "")

    return (
        f"Mode: {_session.get('mode', 'not set')}\n"
        f"Domain: {domain or 'not set'}\n"
        f"Requirements: {reqs or 'not gathered yet'}\n"
        f"Workspace: {host}\n"
        f"Warehouse: {wh}\n"
        f"Schema: {schema}\n"
        f"Model: {model}\n"
        f"App: {app}"
    )


# ── Scripted startup (4 questions, no LLM) ───────────────────────────────

STARTUP_PROMPTS = [
    "What's your project name?",
    "How do you want to work?\n\n**Magic** - I handle everything, you just describe your business\n**Author** - I walk you through each step, you make the calls",
    "Describe your business in a sentence or two. What should your agent help with?",
    "Let me connect your workspace...",
]


async def _init_agent(sse_queue: asyncio.Queue, config, preamble: str):
    """Initialize the LLM agent. Workspace must be connected (precondition)."""
    host = config.get("workspace.host") or os.environ.get("DATABRICKS_HOST", "")
    token = config.get("workspace.token") or os.environ.get("DATABRICKS_TOKEN", "")

    # Resolve auth via CLI profile fallback if needed
    if not (host and token):
        try:
            from databricks.sdk import WorkspaceClient
            if host:
                w = WorkspaceClient(host=host)
            else:
                w = WorkspaceClient()
            w.current_user.me()
            host = w.config.host or host
            token = getattr(w.config, "token", "") or token
        except Exception:
            pass

    agent = MageAgent(
        sse_queue=sse_queue,
        mode=_session["mode"],
        domain=_session["domain"],
        requirements=_session["requirements"],
    )
    model = await agent.init_llm(host, token if token else None)
    if not model:
        await sse_queue.put({"event": "message", "data": {"role": "assistant", "text": preamble}})
        await sse_queue.put({"event": "error", "data": {"message": "No AI model available on this workspace."}})
        return

    _session["agent"] = agent
    _session["model"] = model
    _session["phase"] = "ready"
    _session["startup_step"] = 4
    _save_session()

    await sse_queue.put({"event": "message", "data": {"role": "assistant", "text": f"{preamble}\n\nTell me more about what this agent should do. Who uses it and what do they need to accomplish?"}})


async def _handle_startup(user_message: str, sse_queue: asyncio.Queue, mode_from_ui: str | None = None):
    """Handle scripted startup steps. Returns True if still in startup."""
    step = _session["startup_step"]
    config = _get_config()

    if step == 0:
        # Store domain from the user's description
        _session["domain"] = user_message
        if mode_from_ui in ("magic", "author"):
            _session["mode"] = mode_from_ui

        # Use LLM to suggest 3 short project names from the description
        host = config.get("workspace.host") or os.environ.get("DATABRICKS_HOST", "")
        token = config.get("workspace.token") or os.environ.get("DATABRICKS_TOKEN", "")
        suggestions = []
        try:
            from brickforge.lib.mage_llm import detect_fmapi_model
            from databricks_langchain import ChatDatabricks
            from databricks.sdk import WorkspaceClient
            from langchain_core.messages import HumanMessage as HMsg, SystemMessage as SMsg

            # Resolve workspace auth: explicit host/token, then CLI profile fallback
            if host and token:
                w = WorkspaceClient(host=host, token=token)
            elif host:
                w = WorkspaceClient(host=host)
            else:
                w = WorkspaceClient()  # CLI profile fallback
            w.current_user.me()  # validate auth
            resolved_host = w.config.host or host
            resolved_token = getattr(w.config, "token", "") or token

            model_name = detect_fmapi_model(resolved_host, resolved_token if resolved_token else None)
            if model_name:
                if resolved_host: os.environ["DATABRICKS_HOST"] = resolved_host
                if resolved_token: os.environ["DATABRICKS_TOKEN"] = resolved_token
                llm = ChatDatabricks(endpoint=model_name)
                resp = await llm.ainvoke([
                    SMsg(content="Extract 3 short project name suggestions (2-3 words each, lowercase, hyphenated) from the user's description. Return ONLY a JSON array of 3 strings. Example: [\"space-pizza\", \"galactic-delivery\", \"pizza-express\"]"),
                    HMsg(content=user_message),
                ])
                import json as _json
                names = _json.loads(resp.content.strip())
                if isinstance(names, list) and len(names) >= 1:
                    suggestions = [n.strip().lower().replace(" ", "-") for n in names[:3]]
        except Exception as e:
            print(f"[mage] name suggestion LLM failed: {e}")

        if not suggestions:
            # Fallback: first 3 words slugified
            words = [w for w in user_message.strip().lower().split() if w not in ("a", "an", "the", "for", "and", "of", "to", "in", "keep", "it", "simple", "sci", "fi")]
            suggestions = ["-".join(words[:3])] if words else ["my-project"]

        _session["_name_suggestions"] = suggestions
        _session["startup_step"] = 1

        # Present as interactive choice cards
        options = [{"id": s, "label": s} for s in suggestions]
        await sse_queue.put({
            "event": "choice",
            "data": {"prompt": "Pick a project name or type your own:", "options": options}
        })

    elif step == 1:
        # User picks a name via choice card click or types their own
        name = user_message.strip().lower().replace(" ", "-")

        # Create the project
        import httpx
        port = os.environ.get("VISUAL_PORT", os.environ.get("DATABRICKS_APP_PORT", "9000"))
        try:
            async with httpx.AsyncClient(base_url=f"http://localhost:{port}", timeout=10) as c:
                resp = await c.post("/api/projects", json={"name": name})
                if resp.status_code == 409:
                    await c.post(f"/api/projects/{name}/load")
                elif resp.status_code != 200:
                    await sse_queue.put({"event": "error", "data": {"message": f"Failed to create project: {resp.text}"}})
                    return True
        except Exception as e:
            await sse_queue.put({"event": "error", "data": {"message": f"Failed to create project: {e}"}})
            return True

        if _session["mode"]:
            # Mode already set from UI toggle - init agent immediately
            mode_label = "Magic" if _session["mode"] == "magic" else "Author"
            await _init_agent(sse_queue, config, f"Project **{name}** created. **{mode_label}** mode.")
        else:
            await sse_queue.put({"event": "message", "data": {"role": "assistant", "text": f"Project **{name}** created.\n\n{STARTUP_PROMPTS[1]}"}})
            _session["startup_step"] = 2

    elif step == 2:
        # Mode selection (only if not set from UI)
        lower = user_message.strip().lower()
        if any(w in lower for w in ["magic", "auto", "automatic", "do it", "handle"]):
            _session["mode"] = "magic"
        elif any(w in lower for w in ["author", "manual", "guide", "step by step", "walk"]):
            _session["mode"] = "author"
        else:
            await sse_queue.put({"event": "message", "data": {"role": "assistant", "text": "Please pick **Magic** or **Author**."}})
            return True

        mode_label = "Magic" if _session["mode"] == "magic" else "Author"
        # Domain already captured in step 0 - init agent
        await _init_agent(sse_queue, config, f"**{mode_label}** mode. Got it.")

    return True


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/chat")
async def mage_chat(request: Request):
    """Main chat endpoint. Returns SSE stream."""
    body = await request.json()
    user_message = body.get("content", body.get("message", ""))
    mode_from_ui = body.get("mode")

    sse_queue: asyncio.Queue = asyncio.Queue()

    async def generate():
        try:
            # Startup phase
            if _session["phase"] == "startup":
                await _handle_startup(user_message, sse_queue, mode_from_ui=mode_from_ui)
                while not sse_queue.empty():
                    event = await sse_queue.get()
                    yield f"event:{event['event']}\ndata:{json.dumps(event['data'])}\n\n"
                return

            # Agent phase
            agent: MageAgent = _session.get("agent")
            if not agent:
                yield f"event:error\ndata:{json.dumps({'message': 'Mage not initialized. Reset and try again.'})}\n\n"
                return

            # Update queue for this request (each request gets a fresh queue)
            agent.sse_queue = sse_queue
            agent.toolkit.sse_queue = sse_queue

            config = _get_config()
            state = _state_summary(config)

            # Run agent in background, read from queue
            agent_task = asyncio.create_task(agent.run(user_message, state))

            while True:
                try:
                    event = await asyncio.wait_for(sse_queue.get(), timeout=0.1)
                    yield f"event:{event['event']}\ndata:{json.dumps(event['data'])}\n\n"
                    if event["event"] == "done":
                        break
                except asyncio.TimeoutError:
                    if agent_task.done():
                        # Drain remaining events
                        while not sse_queue.empty():
                            event = await sse_queue.get()
                            yield f"event:{event['event']}\ndata:{json.dumps(event['data'])}\n\n"
                        break

            # Check for agent exceptions
            if agent_task.done() and agent_task.exception():
                err = str(agent_task.exception())
                yield f"event:error\ndata:{json.dumps({'message': err})}\n\n"

            # Sync agent state back to session before saving
            if agent and agent.requirements:
                _session["requirements"] = agent.requirements
            _save_session()

        except Exception as e:
            yield f"event:error\ndata:{json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/status")
async def mage_status():
    """Return Mage session state + prerequisites."""
    config = _get_config()
    host = config.get("workspace.host") or os.environ.get("DATABRICKS_HOST", "")
    token = config.get("workspace.token") or os.environ.get("DATABRICKS_TOKEN", "")

    # Check workspace connectivity - try config/env first, then CLI profile
    workspace_ok = False
    try:
        from databricks.sdk import WorkspaceClient
        if host and token:
            w = WorkspaceClient(host=host, token=token)
        elif host:
            w = WorkspaceClient(host=host)
        else:
            w = WorkspaceClient()  # CLI profile fallback
        w.current_user.me()
        workspace_ok = True
        host = w.config.host or host  # capture resolved host
    except Exception:
        pass

    # Check model availability (only if workspace connected)
    model_ok = False
    model_name = _session.get("model")
    if workspace_ok and not model_name:
        try:
            from brickforge.lib.mage_llm import detect_fmapi_model
            model_name = detect_fmapi_model(host, token if token else None)
            model_ok = bool(model_name)
        except Exception:
            pass
    elif model_name:
        model_ok = True

    return JSONResponse({
        "phase": _session["phase"],
        "mode": _session["mode"],
        "domain": _session["domain"],
        "requirements": _session["requirements"],
        "model": model_name,
        "startup_step": _session["startup_step"],
        "prereqs": {
            "workspace": workspace_ok,
            "model": model_ok,
            "host": host or None,
            "modelName": model_name or None,
        },
    })


@router.post("/reset")
async def mage_reset():
    """Reset Mage session."""
    _session.update({
        "agent": None,
        "mode": None,
        "domain": "",
        "requirements": "",
        "phase": "startup",
        "startup_step": 0,
        "model": None,
    })
    path = _session_file()
    if path.exists():
        path.unlink()
    return JSONResponse({"ok": True})
