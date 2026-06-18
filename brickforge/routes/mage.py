"""
Mage route - SSE chat endpoint for the Mage assistant.

Session state uses the project config system (config.json) as source of truth.
mage.mode and mage.domain persist across server restarts.
The agent object is in-memory only — auto-reinited from config on first message after restart.
"""

import asyncio
import json
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from brickforge.lib.mage_agent import MageAgent

router = APIRouter(prefix="/api/mage", tags=["mage"])

# In-memory only (agent can't be serialized)
_agent: MageAgent | None = None
_model: str | None = None
_startup_step: int = 0


def _get_config():
    from brickforge.server import config
    return config


def _get_phase(config) -> str:
    """Derive phase from config state — no separate phase tracking.
    Ready if mage was used (mode+domain both set)."""
    if config.get("mage.mode") and config.get("mage.domain"):
        return "ready"
    return "startup"


def _state_summary(config) -> str:
    """Build compact state summary for system prompt injection."""
    return (
        f"Mode: {config.get('mage.mode') or 'not set'}\n"
        f"Domain: {config.get('mage.domain') or 'not set'}\n"
        f"Workspace: {config.get('workspace.host') or 'not connected'}\n"
        f"Warehouse: {config.get('workspace.warehouse_id') or 'not set'}\n"
        f"Schema: {config.get('workspace.unity_catalog_schema') or 'not set'}\n"
        f"Model: {config.get('model.endpoint') or 'not set'}\n"
        f"App: {config.get('app.name') or 'not set'}"
    )


# ── Scripted startup ────────────────────────────────────────────────────


async def _init_agent(sse_queue: asyncio.Queue, config, preamble: str):
    """Initialize the LLM agent. Workspace must be connected (precondition)."""
    global _agent, _model

    host = config.get("workspace.host") or os.environ.get("DATABRICKS_HOST", "")
    token = config.get("workspace.token") or os.environ.get("DATABRICKS_TOKEN", "")

    agent = MageAgent(
        sse_queue=sse_queue,
        mode=config.get("mage.mode") or "magic",
        domain=config.get("mage.domain") or "",
        requirements="",
    )
    model = await agent.init_llm(host, token if token else None)
    if not model:
        await sse_queue.put({"event": "message", "data": {"role": "assistant", "text": preamble}})
        await sse_queue.put({"event": "error", "data": {"message": "No AI model available on this workspace."}})
        return

    _agent = agent
    _model = model

    if preamble:
        await sse_queue.put({"event": "message", "data": {"role": "assistant", "text": preamble}})


async def _handle_startup(user_message: str, sse_queue: asyncio.Queue, mode_from_ui: str | None = None):
    """Handle scripted startup steps. Returns True if still in startup."""
    global _startup_step
    config = _get_config()

    if _startup_step == 0:
        # Store domain in config
        config.set("mage.domain", user_message)
        if mode_from_ui in ("magic", "author"):
            config.set("mage.mode", mode_from_ui)

        # Use LLM to suggest 3 short project names from the description
        host = config.get("workspace.host") or os.environ.get("DATABRICKS_HOST", "")
        token = config.get("workspace.token") or os.environ.get("DATABRICKS_TOKEN", "")
        suggestions = []
        try:
            from brickforge.lib.mage_llm import detect_fmapi_model
            from databricks_langchain import ChatDatabricks
            from langchain_core.messages import HumanMessage as HMsg, SystemMessage as SMsg
            model_name = detect_fmapi_model(host, token if token else None)
            if model_name:
                if host: os.environ["DATABRICKS_HOST"] = host
                if token: os.environ["DATABRICKS_TOKEN"] = token
                llm = ChatDatabricks(endpoint=model_name)
                resp = await llm.ainvoke([
                    SMsg(content="Extract 3 short project name suggestions (2-3 words each, lowercase, hyphenated) from the user's description. Return ONLY a JSON array of 3 strings. Example: [\"space-pizza\", \"galactic-delivery\", \"pizza-express\"]"),
                    HMsg(content=user_message),
                ])
                import json as _json
                names = _json.loads(resp.content.strip())
                if isinstance(names, list) and len(names) >= 1:
                    suggestions = [n.strip().lower().replace(" ", "-") for n in names[:3]]
        except Exception:
            pass

        if not suggestions:
            # Fallback: first 3 words slugified
            words = [w for w in user_message.strip().lower().split() if w not in ("a", "an", "the", "for", "and", "of", "to", "in", "keep", "it", "simple", "sci", "fi")]
            suggestions = ["-".join(words[:3])] if words else ["my-project"]

        _startup_step = 1

        # Present as interactive choice cards
        options = [{"id": s, "label": s} for s in suggestions]
        await sse_queue.put({
            "event": "choice",
            "data": {"prompt": "Pick a project name or type your own:", "options": options}
        })

    elif _startup_step == 1:
        # User picks a name via choice card click or types their own
        name = user_message.strip().lower().replace(" ", "-")

        # Create the project
        import httpx
        port = os.environ.get("VISUAL_PORT", os.environ.get("DATABRICKS_APP_PORT", "9000"))
        try:
            async with httpx.AsyncClient(base_url=f"http://localhost:{port}", timeout=10) as c:
                resp = await c.post("/api/projects", json={"name": name})
                if resp.status_code == 409:
                    await c.get(f"/api/projects/{name}")
                elif resp.status_code != 200:
                    await sse_queue.put({"event": "error", "data": {"message": f"Failed to create project: {resp.text}"}})
                    return True
        except Exception as e:
            await sse_queue.put({"event": "error", "data": {"message": f"Failed to create project: {e}"}})
            return True

        # Re-read config after project creation (it switches the active config)
        config = _get_config()
        mode = config.get("mage.mode")

        if mode:
            mode_label = "Magic" if mode == "magic" else "Author"
            await _init_agent(sse_queue, config, f"Project **{name}** created. **{mode_label}** mode.")
        else:
            await sse_queue.put({"event": "message", "data": {"role": "assistant", "text": f"Project **{name}** created.\n\nHow do you want to work?\n\n**Magic** - I handle everything, you just describe your business\n**Author** - I walk you through each step, you make the calls"}})
            _startup_step = 2

    elif _startup_step == 2:
        # Mode selection (only if not set from UI)
        lower = user_message.strip().lower()
        if any(w in lower for w in ["magic", "auto", "automatic", "do it", "handle"]):
            config.set("mage.mode", "magic")
        elif any(w in lower for w in ["author", "manual", "guide", "step by step", "walk"]):
            config.set("mage.mode", "author")
        else:
            await sse_queue.put({"event": "message", "data": {"role": "assistant", "text": "Please pick **Magic** or **Author**."}})
            return True

        mode_label = "Magic" if config.get("mage.mode") == "magic" else "Author"
        await _init_agent(sse_queue, config, f"**{mode_label}** mode. Got it.")

    return True


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/chat")
async def mage_chat(request: Request):
    """Main chat endpoint. Returns SSE stream."""
    global _agent
    body = await request.json()
    user_message = body.get("content", body.get("message", ""))
    mode_from_ui = body.get("mode")

    sse_queue: asyncio.Queue = asyncio.Queue()
    config = _get_config()

    async def generate():
        global _agent
        try:
            phase = _get_phase(config)

            # Startup phase
            if phase == "startup":
                await _handle_startup(user_message, sse_queue, mode_from_ui=mode_from_ui)
                while not sse_queue.empty():
                    event = await sse_queue.get()
                    yield f"event:{event['event']}\ndata:{json.dumps(event['data'])}\n\n"
                return

            # Ready phase — auto-reinit agent if lost (server restart)
            if not _agent:
                await _init_agent(sse_queue, config, "")
            if not _agent:
                yield f"event:error\ndata:{json.dumps({'message': 'Mage not initialized. Reset and try again.'})}\n\n"
                return

            # Update queue for this request
            _agent.sse_queue = sse_queue
            _agent.toolkit.sse_queue = sse_queue

            state = _state_summary(config)

            # Run agent
            agent_task = asyncio.create_task(_agent.run(user_message, state))

            while True:
                try:
                    event = await asyncio.wait_for(sse_queue.get(), timeout=0.1)
                    yield f"event:{event['event']}\ndata:{json.dumps(event['data'])}\n\n"
                    if event["event"] == "done":
                        break
                except asyncio.TimeoutError:
                    if agent_task.done():
                        while not sse_queue.empty():
                            event = await sse_queue.get()
                            yield f"event:{event['event']}\ndata:{json.dumps(event['data'])}\n\n"
                        break

            if agent_task.done() and agent_task.exception():
                err = str(agent_task.exception())
                yield f"event:error\ndata:{json.dumps({'message': err})}\n\n"

        except Exception as e:
            yield f"event:error\ndata:{json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/status")
async def mage_status():
    """Return Mage session state + prerequisites."""
    config = _get_config()
    host = config.get("workspace.host") or os.environ.get("DATABRICKS_HOST", "")
    token = config.get("workspace.token") or os.environ.get("DATABRICKS_TOKEN", "")

    workspace_ok = False
    try:
        from databricks.sdk import WorkspaceClient
        if host and token:
            w = WorkspaceClient(host=host, token=token)
        elif host:
            w = WorkspaceClient(host=host)
        else:
            w = WorkspaceClient()
        w.current_user.me()
        workspace_ok = True
        host = w.config.host or host
    except Exception:
        pass

    model_ok = False
    model_name = _model
    if workspace_ok and not model_name:
        try:
            from brickforge.lib.mage_llm import detect_fmapi_model
            model_name = detect_fmapi_model(host, token if token else None)
            model_ok = bool(model_name)
        except Exception:
            pass
    elif model_name:
        model_ok = True

    phase = _get_phase(config)

    return JSONResponse({
        "phase": phase,
        "mode": config.get("mage.mode"),
        "domain": config.get("mage.domain") or "",
        "model": model_name,
        "startup_step": _startup_step,
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
    global _agent, _model, _startup_step
    _agent = None
    _model = None
    _startup_step = 0

    config = _get_config()
    config.set("mage.mode", None)
    config.set("mage.domain", "")

    return JSONResponse({"ok": True})
