# Plan: OpenAI Agents SDK as BrickForge Deploy Option

> Status: SPIKE
> Created: 2026-06-20

## Context

Databricks provides an official [agent-openai-agents-sdk](https://github.com/databricks/app-templates/tree/main/agent-openai-agents-sdk) app template. It uses the OpenAI Agents SDK (`openai-agents`) with `AsyncDatabricksOpenAI()` client — routing through FMAPI, NOT native OpenAI. Any Databricks-served model works.

BrickForge currently uses LangGraph + LangChain. This plan adds OpenAI Agents SDK as a third runtime option alongside LangGraph and Claude Agent SDK.

## Why This Matters

Unlike the Claude Agent SDK (locked to opus-4-6), the OpenAI Agents SDK is **model-agnostic on Databricks**. It uses `AsyncDatabricksOpenAI()` which wraps FMAPI — so any served model (Claude Sonnet, GPT, Llama, DBRX) works. This makes it a stronger candidate than the Claude SDK for a universal runtime.

## Architecture: OpenAI Agents SDK on Databricks

```
OpenAI Agents SDK (openai-agents)
    ↓
Agent(name, instructions, model, tools, mcp_servers)
    ↓
Runner.run_streamed(agent, input=messages)
    ↓
AsyncDatabricksOpenAI() client (from databricks-openai)
    ↓
Databricks Foundation Model API (FMAPI)
    ↓
Any served model (Claude, GPT, Llama, DBRX)
```

## Key Pattern Differences from BrickForge

| Concern | BrickForge (LangGraph) | OpenAI Agents SDK |
|---------|----------------------|-------------------|
| Agent creation | `create_agent(tools=tools, model=ChatDatabricks(...))` | `Agent(name=..., model=..., tools=..., mcp_servers=...)` |
| Agent loop | Custom StateGraph or `while True` | `Runner.run()` / `Runner.run_streamed()` — SDK owns the loop |
| Tool definition | LangChain `@tool` decorator, `bind_tools()` | `@function_tool` decorator OR MCP servers |
| MCP support | Custom MCP client wrappers | Native `McpServer` class, first-class support |
| Model client | `ChatDatabricks(endpoint=model)` | `AsyncDatabricksOpenAI()` + `set_default_openai_client()` |
| Streaming | `process_agent_astream_events` → ResponsesAgentStreamEvent | `Runner.run_streamed().stream_events()` → ResponsesAgentStreamEvent |
| Server | Custom MLflow pyfunc + Node.js | `AgentServer("ResponsesAgent")` — built-in FastAPI + chat UI |
| Handlers | Custom `streaming()` function | `@invoke()` and `@stream()` decorators |
| Auth | Ambient env vars | Same + on-behalf-of user (OBO) pattern |
| Tracing | Manual | `mlflow.openai.autolog()` — automatic |
| Evaluation | Not integrated | Built-in `ConversationSimulator` + scorers |

## What Maps Cleanly

| Concern | BrickForge | OpenAI SDK | Compatible? |
|---------|-----------|------------|-------------|
| UC function discovery | `discover_uc_function_tools()` | N/A (static) | Yes — wrap as `@function_tool` |
| SQL execution | `execute_query()` / `execute_statement()` | N/A | Yes — reuse directly |
| MCP servers | Custom wrappers for Genie, VS | Native `McpServer` class | Yes — cleaner with SDK |
| System prompt | From project prompt files | `Agent(instructions=...)` | Yes — same source |
| Auth | SP ambient env | SP ambient env + OBO | Yes |
| Card fences | `_card_fence()` returns string | Tool returns string | Yes — same pattern |
| Streaming format | ResponsesAgentStreamEvent | Same format (both MLflow) | **Yes — native match** |

## What's Better Than LangGraph

1. **Streaming format is native** — OpenAI SDK outputs ResponsesAgentStreamEvent directly. No converter needed. LangGraph needs `process_agent_astream_events` wrapper.
2. **MCP is first-class** — `McpServer` class, health-check pattern, graceful degradation. LangGraph needs custom MCP wrappers.
3. **AgentServer built-in** — FastAPI + chat UI + `/invocations` endpoint. No Node.js server needed.
4. **MLflow autologging** — automatic tracing. LangGraph needs manual instrumentation.
5. **Evaluation built-in** — `ConversationSimulator` + scorers. LangGraph has no equivalent.
6. **Model-agnostic** — any FMAPI model. No lock-in.

## What's Worse Than LangGraph

1. **No checkpointing** — no built-in memory/state persistence. LangGraph has Lakebase checkpointer.
2. **Simpler agent loop** — no multi-step planning, no graph-based workflows. Single agent with tools.
3. **Less control** — SDK owns the loop. Can't inject custom logic between tool calls.

## Spike Steps

### Step 1: Tool Adapter — `brickforge/agent/openai_tools.py` (new, ~100 lines)

Convert BrickForge UC function tools to OpenAI Agents SDK format.

```python
from agents import function_tool
import asyncio
from tools.sql_executor import execute_query, execute_statement, get_warehouse, _escape_sql_string
from tools.tool_factory import _humanize, _card_fence
from data.py.sql_utils import get_schema_qualified

def create_openai_read_tool(name: str, function_name: str, params: list[str], description: str):
    """Wrap a UC function as an OpenAI Agents SDK function tool."""

    async def read_fn(**kwargs: str) -> str:
        try:
            w, wh_id = get_warehouse()
            schema = get_schema_qualified()
            args_sql = ", ".join(f"'{_escape_sql_string(str(kwargs.get(p, '')))}'" for p in params)
            stmt = f"SELECT * FROM {schema}.{function_name}({args_sql})"
            columns, rows = await asyncio.to_thread(execute_query, w, wh_id, stmt)
            title = _humanize(name.removeprefix("query_"))
            card = {"type": "list", "title": title, "columns": columns, "rows": rows}
            return _card_fence(card)
        except Exception as e:
            card = {"type": "error", "title": f"{_humanize(name)} Failed",
                    "fields": [{"label": "Error", "value": f"{type(e).__name__}: {e}"}]}
            return _card_fence(card)

    read_fn.__name__ = name
    read_fn.__doc__ = description
    # Set parameter annotations for schema introspection
    read_fn.__annotations__ = {p: str for p in params}
    read_fn.__annotations__["return"] = str
    return function_tool(read_fn)

def create_openai_action_tool(name: str, procedure_name: str, params: list[str], description: str):
    """Wrap a UC procedure as an OpenAI Agents SDK function tool."""

    async def action_fn(**kwargs: str) -> str:
        try:
            w, wh_id = get_warehouse()
            schema = get_schema_qualified()
            args_sql = ", ".join(f"'{_escape_sql_string(str(kwargs.get(p, '')))}'" for p in params)
            stmt = f"CALL {schema}.{procedure_name}({args_sql})"
            await asyncio.to_thread(execute_statement, w, wh_id, stmt)
            title = _humanize(name)
            fields = [{"label": _humanize(p), "value": str(kwargs.get(p, ""))} for p in params]
            card = {"type": "confirmation", "title": f"{title} Completed", "fields": fields}
            return _card_fence(card)
        except Exception as e:
            card = {"type": "error", "title": f"{_humanize(name)} Failed",
                    "fields": [{"label": "Error", "value": f"{type(e).__name__}: {e}"}]}
            return _card_fence(card)

    action_fn.__name__ = name
    action_fn.__doc__ = description
    action_fn.__annotations__ = {p: str for p in params}
    action_fn.__annotations__["return"] = str
    return function_tool(action_fn)

def discover_openai_tools() -> list:
    """Discover UC functions, wrap as OpenAI function tools. Returns list of tools."""
    import os
    schema_spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if not schema_spec or "." not in schema_spec:
        return []

    cat, sch = schema_spec.split(".", 1)
    raw = os.environ.get("PROJECT_FUNCTIONS", "").strip()
    selected = set(raw.split(",")) if raw else None

    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    tools = []

    try:
        uc_functions = list(w.functions.list(catalog_name=cat, schema_name=sch))
    except Exception:
        return []

    for func_info in uc_functions:
        if not func_info.name:
            continue
        if selected is not None and func_info.name not in selected:
            continue
        try:
            detail = w.functions.get(name=f"{cat}.{sch}.{func_info.name}")
        except Exception:
            continue
        params = [p.name for p in (detail.input_params.parameters or []) if p.name] if detail.input_params else []
        dt = str(func_info.data_type) if func_info.data_type else ""

        if "TABLE" in dt:
            desc = detail.comment or f"Look up data from {func_info.name}"
            tool_name = f"query_{func_info.name}"
            t = create_openai_read_tool(tool_name, func_info.name, params, desc)
        else:
            desc = detail.comment or f"Execute {func_info.name}"
            t = create_openai_action_tool(func_info.name, func_info.name, params, desc)
        tools.append(t)

    return tools
```

**Key difference from Claude SDK adapter:** OpenAI `@function_tool` uses Python kwargs + docstrings for schema, not explicit schema dicts. Tools return plain strings, not MCP content blocks. This is closer to BrickForge's existing LangChain pattern.

### Step 2: Agent Module — `brickforge/agent/openai_agent.py` (new, ~120 lines)

```python
import os
from pathlib import Path
from agents import Agent, Runner, set_default_openai_api, set_default_openai_client
from databricks.openai import AsyncDatabricksOpenAI
from mlflow.genai.agent_server import invoke, stream
from mlflow.genai.agent_server.types import (
    ResponsesAgentRequest, ResponsesAgentResponse, ResponsesAgentStreamEvent,
)
from agent.openai_tools import discover_openai_tools
from agent.utils import process_agent_stream_events  # From Databricks template

# Wire Databricks FMAPI as the OpenAI backend
set_default_openai_client(AsyncDatabricksOpenAI())
set_default_openai_api("chat_completions")

def _load_system_prompt() -> str:
    """Load prompt from project prompt files."""
    project_dir = os.environ.get("PROJECT_DIR", "")
    if project_dir:
        prompt_dir = Path(project_dir) / "prompt"
        parts = []
        for name in ["main.prompt", "knowledge.base", "user.prompt"]:
            f = prompt_dir / name
            if f.exists():
                parts.append(f.read_text())
        if parts:
            return "\n\n".join(parts)
    # Fallback to conf/prompt/
    from brickforge import PACKAGE_ROOT
    prompt_dir = PACKAGE_ROOT / "conf" / "prompt"
    parts = []
    for name in ["main.prompt", "knowledge.base"]:
        f = prompt_dir / name
        if f.exists():
            parts.append(f.read_text())
    return "\n\n".join(parts) if parts else "You are a helpful assistant."

def create_agent() -> Agent:
    model = os.environ.get("AGENT_MODEL", "databricks-claude-sonnet-4-6")
    tools = discover_openai_tools()
    instructions = _load_system_prompt()

    # Optional: MCP servers for Genie spaces
    mcp_servers = []
    genie_spaces = os.environ.get("PROJECT_GENIE_SPACES", "").strip()
    if genie_spaces:
        from agents import McpServer
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        host = w.config.host
        for space_id in genie_spaces.split(","):
            space_id = space_id.strip()
            if space_id:
                mcp_servers.append(McpServer(
                    url=f"{host}/api/2.0/mcp/genie/{space_id}",
                    name=f"genie_{space_id[:8]}",
                    workspace_client=w,
                ))

    return Agent(
        name="BrickForge Agent",
        instructions=instructions,
        model=model,
        tools=tools,
        mcp_servers=mcp_servers,
    )

@stream()
async def streaming(request: ResponsesAgentRequest):
    """OpenAI Agents SDK streaming handler — drop-in replacement for LangGraph."""
    from contextlib import AsyncExitStack
    async with AsyncExitStack() as stack:
        agent = create_agent()
        # Health-check MCP servers
        if agent.mcp_servers:
            from agent.utils import connect_healthy_mcp_servers
            healthy, unavailable = await connect_healthy_mcp_servers(stack, agent.mcp_servers)
            agent = Agent(**{**agent.__dict__, "mcp_servers": healthy})

        messages = [i.model_dump() for i in request.input]
        result = Runner.run_streamed(agent, input=messages)
        async for event in process_agent_stream_events(result.stream_events()):
            yield event
```

**Key advantage:** The `@stream()` decorator + `ResponsesAgentStreamEvent` output is the SAME interface as BrickForge's current LangGraph agent. The Node server doesn't need to change.

### Step 3: Feature Flag — `brickforge/agent/start_server.py` (modify)

```python
AGENT_RUNTIME = os.environ.get("AGENT_RUNTIME", "langgraph")

if AGENT_RUNTIME == "openai-sdk":
    import agent.openai_agent  # Registers @stream() handler
elif AGENT_RUNTIME == "claude-sdk":
    import agent.sdk_agent     # Claude Agent SDK path
else:
    import agent.agent         # LangGraph (default)
```

### Step 4: Dependencies — `requirements.txt` (modify)

```
openai-agents>=0.4.1
databricks-openai>=0.13.0
```

Check for conflicts with `langchain`, `databricks-langchain`.

### Step 5: Config — `config_provider.py` (modify)

Add to DEFAULT_CONFIG:
```python
"agent": {
    "runtime": "langgraph",  # "langgraph" | "openai-sdk" | "claude-sdk"
}
```

Flatten to `AGENT_RUNTIME` env var.

### Step 6: Test End-to-End

1. Set `AGENT_RUNTIME=openai-sdk` in config
2. Deploy via Mage
3. "show me the menu" → UC function fires → list card renders
4. "place an order" → UC procedure fires → confirmation card renders
5. Test with different models: Claude Sonnet, GPT, Llama
6. Compare latency/quality with LangGraph

## Blockers

| # | Blocker | Severity | Mitigation |
|---|---------|----------|-----------|
| 1 | `@function_tool` schema introspection | Medium | May need explicit type annotations + docstrings for UC function params. Test with dynamic creation. |
| 2 | `process_agent_stream_events` util | Medium | Need to vendor from Databricks template or reimplement (~50 lines). |
| 3 | MCP health-check pattern | Low | Copy `connect_healthy_mcp_servers` from template. |
| 4 | No checkpointing/memory | Medium | Accept for now. Add later via custom memory tool. |
| 5 | Dependency size | Low | `openai-agents` is lightweight. `databricks-openai` may conflict with `databricks-langchain`. |

## Success Criteria

- [ ] UC function tools fire correctly via `@function_tool`
- [ ] Card fences render in existing chat UI (no frontend changes)
- [ ] Streaming format matches LangGraph output (ResponsesAgentStreamEvent)
- [ ] Works with multiple FMAPI models (not locked to one)
- [ ] Genie MCP servers connect and function
- [ ] Can switch via `AGENT_RUNTIME` config flag
- [ ] No regressions on LangGraph path

## Comparison: Three Runtime Options

| Aspect | LangGraph | Claude Agent SDK | OpenAI Agents SDK |
|--------|-----------|-----------------|-------------------|
| Model support | Any FMAPI | opus-4-6 only | Any FMAPI |
| Tool format | LangChain @tool | SDK @tool + MCP | @function_tool + MCP |
| MCP support | Custom wrappers | Native | Native (first-class) |
| Streaming | Custom converter | Custom converter | **Native match** |
| Memory | Lakebase checkpointer | Session ID only | None (add later) |
| Agent loop | You own it | SDK owns it | SDK owns it |
| Server | Custom Node + Python | Custom | Built-in AgentServer |
| Tracing | Manual | None | MLflow autolog |
| Evaluation | None | None | Built-in |
| Complexity | High (most control) | Medium | Low (least code) |

## Reference Files

### Databricks Template (reference only)
| File | URL | Role |
|------|-----|------|
| Agent | [agent.py](https://github.com/databricks/app-templates/tree/main/agent-openai-agents-sdk) | Agent creation + @stream/@invoke handlers |
| Utils | Same repo `/agent_server/utils.py` | MCP health-check, stream processing |
| Multi-agent | [multiagent](https://github.com/databricks/app-templates/tree/main/agent-openai-agents-sdk-multiagent) | Orchestrator + sub-agents pattern |

### BrickForge (modify/reference)
| File | Path | Role |
|------|------|------|
| Current agent | `brickforge/agent/agent.py` | LangGraph runtime — reference for interface |
| Server startup | `brickforge/agent/start_server.py` | Feature flag routing |
| Tool factory | `brickforge/tools/tool_factory.py` | UC discovery + `_humanize`, `_card_fence` |
| SQL executor | `brickforge/tools/sql_executor.py` | `execute_query`, `execute_statement` |
| Config | `brickforge/lib/config_provider.py` | Add `agent.runtime` to DEFAULT_CONFIG |
| Requirements | `brickforge/requirements.txt` | Add `openai-agents`, `databricks-openai` |
| Deploy | `brickforge/deploy/deploy_agent_app.py` | Include new agent files in bundle |

Sources:
- [agent-openai-agents-sdk template](https://github.com/databricks/app-templates/tree/main/agent-openai-agents-sdk)
- [agent-openai-agents-sdk-multiagent](https://github.com/databricks/app-templates/tree/main/agent-openai-agents-sdk-multiagent)
- [Databricks agent authoring docs](https://docs.databricks.com/aws/en/generative-ai/agent-framework/author-agent)
- [Databricks managed MCP](https://docs.databricks.com/aws/en/generative-ai/mcp/managed-mcp)
