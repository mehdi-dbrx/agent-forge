import logging
import os
import re
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

import mlflow
import uuid_utils
from databricks.sdk import WorkspaceClient
from databricks_langchain import ChatDatabricks, DatabricksMCPServer, DatabricksMultiServerMCPClient
from databricks_langchain.multi_server_mcp_client import MCPServer
from langchain.agents import create_agent
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    to_chat_completions_input,
)

from agent.genie_capture import wrap_for_genie_capture
from agent.utils import (
    get_databricks_host_from_env,
    process_agent_astream_events,
)
from tools.get_current_time import get_current_time
from tools.generate_chart import generate_chart
from tools.ka_factory import discover_ka_tools
from tools.api_factory import discover_api_tools
from tools.a2a_factory import discover_a2a_tools
from tools.tool_factory import discover_forge_tools, discover_uc_function_tools

import importlib
import pkgutil

_FRAMEWORK_MODULES = {"sql_executor", "ka_factory", "api_factory", "a2a_factory", "generate_chart", "get_current_time", "tool_factory", "__init__"}


def _discover_domain_tools() -> list:
    """Auto-discover @tool functions from tools/ (excluding framework utilities)."""
    tools_dir = Path(__file__).resolve().parents[1] / "tools"
    discovered = []
    for _, name, _ in pkgutil.iter_modules([str(tools_dir)]):
        if name in _FRAMEWORK_MODULES:
            continue
        try:
            mod = importlib.import_module(f"tools.{name}")
            for attr in vars(mod).values():
                if callable(attr) and hasattr(attr, "name") and hasattr(attr, "args_schema"):
                    discovered.append(attr)
        except Exception as e:
            logging.getLogger(__name__).warning("Failed to load tool module '%s': %s", name, e)
    return discovered
mlflow.langchain.autolog()
_log = logging.getLogger(__name__)

# ── Lakebase memory context ─────────────────────────────────────────────────────

_LAKEBASE_INSTANCE = os.environ.get("LAKEBASE_INSTANCE_NAME", "").strip()
_MEMORY_SCHEMA = os.environ.get("LAKEBASE_AGENT_MEMORY_SCHEMA", "agent_memory").strip()


@asynccontextmanager
async def lakebase_context():
    """Yield (checkpointer, store) if Lakebase is configured and memory is enabled, else (None, None)."""
    memory_enabled = os.environ.get("PROJECT_TOOL_MEMORY", "false").strip().lower() != "false"
    if not memory_enabled:
        _log.info("Memory disabled (PROJECT_TOOL_MEMORY) — running without checkpointing/memory")
        yield None, None
        return
    if not _LAKEBASE_INSTANCE:
        _log.info("LAKEBASE_INSTANCE_NAME not set — running without checkpointing/memory")
        yield None, None
        return
    try:
        from databricks_langchain import AsyncCheckpointSaver, AsyncDatabricksStore
    except ImportError:
        _log.warning("databricks-langchain[memory] not installed — running without checkpointing/memory")
        yield None, None
        return
    async with AsyncCheckpointSaver(
        instance_name=_LAKEBASE_INSTANCE,
    ) as checkpointer, AsyncDatabricksStore(
        instance_name=_LAKEBASE_INSTANCE,
    ) as store:
        yield checkpointer, store


def _get_thread_id(request: "ResponsesAgentRequest") -> str:
    """Extract thread_id from request or generate a new one."""
    ci = dict(request.custom_inputs or {})
    if ci.get("thread_id"):
        return str(ci["thread_id"])
    if request.context and getattr(request.context, "conversation_id", None):
        return str(request.context.conversation_id)
    return str(uuid_utils.uuid7())


def _get_user_id(request: "ResponsesAgentRequest") -> Optional[str]:
    """Extract user_id from request context (SSO identity on Databricks Apps)."""
    ci = dict(request.custom_inputs or {})
    if ci.get("user_id"):
        return str(ci["user_id"])
    if request.context and getattr(request.context, "user_id", None):
        return str(request.context.user_id)
    return None

_sp_workspace_client = None


def _get_workspace_client() -> WorkspaceClient:
    """Lazy-init workspace client -- avoids SDK call at import time."""
    global _sp_workspace_client
    if _sp_workspace_client is None:
        _sp_workspace_client = WorkspaceClient()
    return _sp_workspace_client


def _build_mcp_servers(workspace_client: WorkspaceClient) -> list[MCPServer]:
    """Build list of MCP server configs (does not connect yet)."""
    host_name = get_databricks_host_from_env()
    servers: list[MCPServer] = []
    # Register Genie spaces from PROJECT_GENIE_SPACES (comma-separated IDs)
    genie_spaces = os.environ.get("PROJECT_GENIE_SPACES", "").strip()
    if genie_spaces:
        for i, space_id in enumerate(genie_spaces.split(","), 1):
            space_id = space_id.strip()
            if not space_id:
                continue
            servers.append(
                DatabricksMCPServer(
                    name=f"genie-{i}",
                    url=f"{host_name}/api/2.0/mcp/genie/{space_id}",
                    workspace_client=workspace_client,
                ),
            )

    # Vector Search MCP server (fallback when KA is unavailable)
    vs_index = os.environ.get("PROJECT_VS_INDEX", "").strip()
    if vs_index and "." in vs_index:
        parts = vs_index.rsplit(".", 2)
        if len(parts) >= 2:
            cat, sch = parts[0], parts[1]
            servers.append(
                DatabricksMCPServer(
                    name="vector-search-docs",
                    url=f"{host_name}/api/2.0/mcp/vector-search/{cat}/{sch}",
                    workspace_client=workspace_client,
                ),
            )

    # External MCP servers (PROJECT_MCP_<SLUG>=<url>)
    for key in sorted(os.environ):
        if key.startswith("PROJECT_MCP_") and not key.endswith("_HEADER") and os.environ[key].strip():
            url = os.environ[key].strip()
            slug = key.replace("PROJECT_MCP_", "").lower()
            # Optional auth header: PROJECT_MCP_<SLUG>_HEADER=HeaderName:HeaderValue
            headers = None
            header_val = os.environ.get(f"{key}_HEADER", "").strip()
            if header_val and ":" in header_val:
                hname, hval = header_val.split(":", 1)
                headers = {hname.strip(): hval.strip()}
            servers.append(
                MCPServer(
                    name=f"mcp-{slug}",
                    url=url,
                    headers=headers,
                ),
            )

    return servers


async def _get_mcp_tools_safe(workspace_client: WorkspaceClient) -> list:
    """Connect to each MCP server individually; skip unavailable ones."""
    servers = _build_mcp_servers(workspace_client)
    all_tools = []
    # _mcp_clients kept alive so tool callbacks remain valid
    _get_mcp_tools_safe._clients = []
    for server in servers:
        try:
            client = DatabricksMultiServerMCPClient([server])
            tools = await client.get_tools()
            all_tools.extend(tools)
            _get_mcp_tools_safe._clients.append(client)
            _log.info("MCP server '%s' connected — %d tools", server.name, len(tools))
        except BaseException as e:
            detail = str(e)
            if hasattr(e, 'exceptions'):
                detail = "; ".join(str(sub) for sub in e.exceptions)
            _log.warning("MCP server '%s' unavailable — skipping: %s", server.name, detail)
    return all_tools


async def init_agent(
    workspace_client: Optional[WorkspaceClient] = None,
    checkpointer: Any = None,
    store: Any = None,
    user_id: Optional[str] = None,
):
    """Returns (agent, llm_supports_streaming).

    llm_supports_streaming=False when the remote endpoint has output guardrails
    that reject streaming calls. The caller must then use stream_mode=["updates"]
    only — LangGraph's "messages" mode forces the LLM into streaming regardless
    of the ChatDatabricks.streaming attribute.
    """
    mcp_tools = await _get_mcp_tools_safe(workspace_client or _get_workspace_client())
    wrapped_tools = [wrap_for_genie_capture(t) for t in mcp_tools]
    # Brick-gated tool discovery: only load tools for enabled bricks
    _brick = lambda key, default="false": os.environ.get(f"PROJECT_BRICK_{key}", default).strip().lower() not in ("false", "0", "")
    ka_tools = discover_ka_tools() if _brick("KA") else []
    api_tools = discover_api_tools()
    a2a_tools = discover_a2a_tools()
    domain_tools = _discover_domain_tools()
    # .forge declarative tools (SQL read + action patterns from config)
    forge_tools = discover_forge_tools(dict(os.environ))
    # UC functions selected in Setup (PROJECT_FUNCTIONS env var)
    uc_func_tools = discover_uc_function_tools()
    _log.info("Discovered %d domain, %d forge, %d uc_func, %d KA, %d API, %d A2A tools", len(domain_tools), len(forge_tools), len(uc_func_tools), len(ka_tools), len(api_tools), len(a2a_tools))
    # Feature-gated tools
    chart_tools = [generate_chart] if os.environ.get("PROJECT_TOOL_CHART", "true").strip().lower() != "false" else []
    from agent.memory_tools import create_memory_tools
    memory_enabled = os.environ.get("PROJECT_TOOL_MEMORY", "false").strip().lower() != "false"
    memory_tools = create_memory_tools(store, user_id) if memory_enabled and store and user_id else []
    if memory_tools:
        _log.info("Memory tools enabled for user '%s'", user_id)
    tools = list(wrapped_tools) + ka_tools + api_tools + a2a_tools + forge_tools + uc_func_tools + chart_tools + memory_tools + [get_current_time] + domain_tools
    endpoint = os.environ.get("AGENT_MODEL", "").strip()
    databricks_host = os.environ.get("DATABRICKS_HOST", "").strip().rstrip("/")

    # If not set, derive from project workspace (same-workspace mode)
    if not endpoint:
        if not databricks_host:
            raise ValueError("AGENT_MODEL not set and DATABRICKS_HOST not set")
        endpoint = f"{databricks_host}/serving-endpoints/databricks-claude-sonnet-4-6/invocations"

    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        m = re.search(r"/serving-endpoints/([^/]+)/invocations", endpoint)
        if not m:
            raise ValueError(f"Cannot parse endpoint name from URL: {endpoint}")
        name = m.group(1)
        host = endpoint[: m.start()].rstrip("/")

        if host == databricks_host:
            # Same workspace — use local auth, no remote client needed
            llm = ChatDatabricks(endpoint=name)
            return create_agent(tools=tools, model=llm, checkpointer=checkpointer, store=store), True

        # Cross-workspace endpoint: build a WorkspaceClient for the remote host
        token = os.environ.get("AGENT_MODEL_TOKEN", "").strip()
        if not token:
            token = os.environ.get("DATABRICKS_TOKEN", "").strip()
            if token:
                import logging
                logging.getLogger(__name__).warning(
                    "AGENT_MODEL_TOKEN not set — falling back to DATABRICKS_TOKEN for cross-workspace endpoint. "
                    "Set AGENT_MODEL_TOKEN for a dedicated PAT."
                )
            else:
                raise ValueError(
                    "AGENT_MODEL_TOKEN (or DATABRICKS_TOKEN as fallback) must be set for cross-workspace endpoint"
                )
        # Temporarily remove local-workspace env vars so the SDK uses only the
        # explicitly passed remote host + token. Without this:
        # - On Databricks Apps: CLIENT_ID/SECRET cause "multiple auth methods"
        # - Locally: DATABRICKS_TOKEN (fevm PAT) overrides the remote PAT → "Invalid Token"
        _oauth_keys = [
            "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET",
            "DATABRICKS_CONFIG_PROFILE",
            "DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WORKSPACE_ID",
        ]
        _saved = {k: os.environ.pop(k) for k in _oauth_keys if k in os.environ}
        try:
            remote_client = WorkspaceClient(host=host, token=token)
        finally:
            os.environ.update(_saved)
        llm = ChatDatabricks(endpoint=name, workspace_client=remote_client)
        return create_agent(tools=tools, model=llm, checkpointer=checkpointer, store=store), False
    else:
        # Local endpoint name — same workspace
        llm = ChatDatabricks(endpoint=endpoint)
        return create_agent(tools=tools, model=llm, checkpointer=checkpointer, store=store), True


@invoke()
async def non_streaming(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    outputs = [
        event.item
        async for event in streaming(request)
        if event.type == "response.output_item.done"
    ]
    return ResponsesAgentResponse(output=outputs)


def _load_system_prompt() -> str:
    from lib.project_paths import prompt_dir
    base = prompt_dir()
    main_path = base / "main.prompt"
    kb_path = base / "knowledge.base"
    content = main_path.read_text(encoding="utf-8").strip() if main_path.exists() else ""
    kb_content = kb_path.read_text(encoding="utf-8").strip() if kb_path.exists() else ""
    return content.replace("{{KNOWLEDGE_BASE}}", kb_content)


async def _run_agent(request: ResponsesAgentRequest) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    async with lakebase_context() as (checkpointer, store):
        thread_id = _get_thread_id(request)
        user_id = _get_user_id(request)
        agent, llm_supports_streaming = await init_agent(
            checkpointer=checkpointer, store=store, user_id=user_id,
        )
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        if user_id:
            config["configurable"]["user_id"] = user_id
        mlflow.update_current_trace(metadata={"mlflow.trace.session": thread_id})

        user_messages = to_chat_completions_input([i.model_dump() for i in request.input])
        system_content = _load_system_prompt()
        messages = (
            {"messages": [{"role": "system", "content": system_content}] + user_messages}
            if system_content
            else {"messages": user_messages}
        )
        # "messages" stream_mode forces LangGraph to call the LLM with stream=True,
        # which breaks endpoints with output guardrails. Use "updates" only in that case.
        stream_mode = ["updates", "messages"] if llm_supports_streaming else ["updates"]
        async for event in process_agent_astream_events(
            agent.astream(input=messages, config=config, stream_mode=stream_mode)
        ):
            yield event


@stream()
async def streaming(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    try:
        async for event in _run_agent(request):
            yield event
    except BaseException as e:
        # Unwrap ExceptionGroup (e.g. from MCP/anyio TaskGroup) so the real error is surfaced
        if isinstance(e, BaseExceptionGroup) and len(e.exceptions) == 1:
            raise e.exceptions[0] from e
        raise
