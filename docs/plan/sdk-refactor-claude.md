# Plan: claude-agent-sdk as BrickForge Deploy Option

> Status: SPIKE
> Created: 2026-06-20

## Context

FleetMind (`/Users/mehdi.lamrani/code/code/FleetMind/`) uses `claude-agent-sdk` (bundled Claude Code CLI) as its agent runtime, with tools exposed as MCP servers. BrickForge (`/Users/mehdi.lamrani/code/code/agent-forge/`) uses LangGraph + LangChain. Both deploy to Databricks Apps, both use UC functions for data access.

Goal: prove BrickForge's dynamically-discovered UC function tools can run on the claude-agent-sdk loop. If yes, offer "Deploy with Claude Agent SDK" as an alternative runtime.

## BrickForge Agent Architecture (current — what we're adding to)

### How the deployed agent works today

```
brickforge/app/                          # Node.js monorepo (chat UI)
├── client/                              # React + Vite frontend
│   └── src/components/message.tsx       # Renders messages, parses ```card``` fences
└── server/                              # Express backend
    └── src/index.ts                     # Routes, calls Python agent via HTTP

brickforge/agent/                        # Python agent runtime
├── agent.py                             # LangGraph agent: init_agent(), create_agent(), streaming()
│   ├── Tool sources: tool_factory, MCP servers, UC auto-discovery, KA, chart
│   ├── Model: ChatDatabricks(endpoint=AGENT_MODEL)
│   ├── Memory: LangGraph checkpointer + Lakebase store
│   └── Streaming: process_agent_astream_events → ResponsesAgentStreamEvent
└── start_server.py                      # MLflow pyfunc server, wraps agent.py

brickforge/tools/                        # Tool implementations
├── tool_factory.py                      # Dynamic tool creation from UC functions
│   ├── create_sql_read_tool()           # SELECT * FROM TABLE(schema.func(args))
│   ├── create_action_tool()             # CALL schema.proc(args)
│   ├── discover_uc_function_tools()     # Auto-discover from UC catalog
│   ├── _humanize(name)                  # "p_customer_name" → "Customer Name"
│   └── _card_fence(card)               # Returns ```card\n{json}\n```
├── sql_executor.py                      # execute_query(), execute_statement(), get_warehouse()
│   ├── execute_query(w, wh_id, stmt)    # Returns (columns: list[str], rows: list[list])
│   ├── execute_statement(w, wh_id, stmt)# Fire-and-forget (procedures)
│   └── get_warehouse()                  # Returns (WorkspaceClient, warehouse_id)
└── generate_chart.py                    # Chart tool: returns ```chart\n{json}\n```
```

### Key config env vars (set by config.json flattening)

```
DATABRICKS_HOST              — workspace URL
DATABRICKS_TOKEN             — PAT or SP token
DATABRICKS_WAREHOUSE_ID      — SQL warehouse
AGENT_MODEL                  — serving endpoint name (e.g. databricks-claude-sonnet-4-6)
PROJECT_UNITY_CATALOG_SCHEMA — catalog.schema (e.g. space.pizza_delivery)
PROJECT_FUNCTIONS            — comma-separated function filter (empty = discover all)
PROJECT_GENIE_SPACES         — comma-separated genie space IDs
```

### How tools are discovered and registered

`agent.py:init_agent()` (called once per request):
1. Reads `FORGE_TOOLS_JSON` env var → `discover_forge_tools()` → LangChain @tool wrappers
2. Reads `PROJECT_FUNCTIONS` → `discover_uc_function_tools()` → UC function auto-discovery
3. Both return `list[@tool]` → passed to `create_agent(tools=tools, model=ChatDatabricks(...))`
4. LangGraph `StateGraph` wraps them with checkpointing

### How streaming works

```
agent.py:streaming() → process_agent_astream_events()
  → yields ResponsesAgentStreamEvent (MLflow format)
  → start_server.py wraps as MLflow pyfunc
  → Node server calls /invocations endpoint
  → Express streams to React client via Vercel AI SDK
```

### Deploy flow

```
deploy_agent_app.py:build_agent_bundle()
  → Zips: agent/, tools/, lib/, conf/, app/client/dist.tar.gz, app/server/dist.tar.gz
  → Uploads to workspace via w.workspace.import_()
  → start.sh extracts, installs deps, starts Node server + Python agent
  → w.apps.deploy() triggers deployment
```

## FleetMind Architecture (reference — what we're learning from)

### Key files

```
/Users/mehdi.lamrani/code/code/FleetMind/src/
├── app.py                # Gradio ChatInterface + FastAPI, streams agent events
├── agent_loop.py         # claude-agent-sdk runner (ClaudeSDKClient in worker thread)
├── tools.py              # MCP tools: execute_sql, get_table_schema
├── genie_tools.py        # 4 Genie evidence tools
├── system_prompt.py      # Handwritten analyst persona
├── config.py             # Model, warehouse, allowed tables
└── databricks_tools_core/# Vendored from AI Dev Kit (auth, SQL, warehouse)
```

### How claude-agent-sdk works

```python
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

options = ClaudeAgentOptions(
    cwd=working_dir,
    allowed_tools=["mcp__databricks__execute_sql", ...],
    permission_mode="bypassPermissions",
    resume=session_id,                    # Session resume
    mcp_servers={"databricks": server},   # MCP tool servers
    system_prompt=system_prompt,
    env={**os.environ, **claude_env},     # FMAPI env vars merged with OS env
    include_partial_messages=True,        # Token streaming
)

async with ClaudeSDKClient(options=options) as client:
    await client.query(message)
    async for msg in client.receive_response():
        # AssistantMessage, ResultMessage, SystemMessage, StreamEvent
        for block in msg.content:
            # TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock
```

### How tools are defined

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool(
    "execute_sql",                           # Tool ID
    "Run a READ-ONLY SQL query...",          # Description
    {"sql_query": str},                      # Input schema (dict of param→type)
)
async def execute_sql(args: dict) -> dict:   # Single args dict, returns content blocks
    rows = await asyncio.to_thread(_execute_sql, sql_query=args["sql_query"], ...)
    return {"content": [{"type": "text", "text": markdown_table}]}
    # On error:
    return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}

server = create_sdk_mcp_server(name="databricks", tools=[execute_sql, ...])
```

### MCP tool naming convention

Tools registered under server name "databricks" become: `mcp__databricks__<tool_name>`

### FMAPI env wiring

```python
claude_env = {
    "ANTHROPIC_BASE_URL": f"https://{host}/serving-endpoints/anthropic",
    "ANTHROPIC_API_KEY": token,
    "ANTHROPIC_AUTH_TOKEN": token,
    "ANTHROPIC_MODEL": "databricks-claude-opus-4-6",
    "ANTHROPIC_CUSTOM_HEADERS": "x-databricks-use-coding-agent-mode: true",
    "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
    "CLAUDE_CODE_STREAM_CLOSE_TIMEOUT": "3600000",
}
```

### Worker thread pattern (uvicorn workaround)

The claude-agent-sdk subprocess transport fails inside uvicorn's event loop. FleetMind works around this by running the agent in a fresh event loop on a worker thread:

```python
def _run_agent_in_fresh_loop(message, options, result_queue, context):
    def run_with_context():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def run_client():
            async with ClaudeSDKClient(options=options) as client:
                await client.query(message)
                async for msg in client.receive_response():
                    result_queue.put(("message", msg))
            result_queue.put(("done", None))
        loop.run_until_complete(run_client())
    context.run(run_with_context)

# Called from async context:
thread = threading.Thread(target=_run_agent_in_fresh_loop, args=(...), daemon=True)
thread.start()
# Read results from queue with keepalive timeout
```

## What Maps Cleanly

| Concern | BrickForge | FleetMind | Compatible? |
|---------|-----------|-----------|-------------|
| UC function discovery | `discover_uc_function_tools()` in `tool_factory.py` | N/A (static) | Yes — same discovery logic, different wrapper |
| SQL execution | `execute_query()` / `execute_statement()` in `sql_executor.py` | `_execute_sql()` (vendored) | Yes — reuse BrickForge's |
| Auth | Ambient env vars from SP | Ambient env vars from SP | Yes |
| Tool results | Card fences (`\`\`\`card\n{json}\n\`\`\``) | MCP content blocks | Yes — embed fence in text block |
| System prompt | Generated by Mage, stored in `projects/{name}/prompt/` | Handwritten | Yes — read from project's prompt files |
| Warehouse ID | `DATABRICKS_WAREHOUSE_ID` env var | `config.SQL_WAREHOUSE_ID` | Yes — same env var |

## What Doesn't Map

| Concern | Issue | Impact |
|---------|-------|--------|
| **Model lock-in** | SDK requires `databricks-claude-opus-4-6` with `x-databricks-use-coding-agent-mode: true` header. Cannot use Sonnet, Haiku, or non-Claude models. | **Critical** — users on Sonnet can't use this path |
| **Tool format** | LangChain `@tool(**kwargs) -> str` vs SDK `@tool("name", "desc", schema)(args: dict) -> {"content": [...]}` | Adapter needed — ~120 lines |
| **Streaming format** | SDK emits `AssistantMessage`/`StreamEvent` dicts vs LangGraph emits `ResponsesAgentStreamEvent` (MLflow format) | Converter needed — ~60 lines |
| **Session state** | SDK `session_id` resume vs LangGraph Lakebase checkpointing | Different mechanisms. SDK path won't have memory/checkpointing initially. |
| **Threading** | SDK needs fresh event loop in worker thread (uvicorn conflict, issue #462) | Copy FleetMind's proven workaround |
| **Node server integration** | BrickForge's Node server calls Python agent via MLflow pyfunc `/invocations`. SDK path needs same interface or a different route. | May need a parallel endpoint |

## Spike Steps

### Step 1: Tool Adapter — `brickforge/agent/sdk_tools.py` (new, ~120 lines)

Convert BrickForge UC function tools to claude-agent-sdk MCP format. Reuses:
- `tools/sql_executor.py:execute_query()` — same SQL execution
- `tools/sql_executor.py:execute_statement()` — same procedure calls
- `tools/sql_executor.py:get_warehouse()` — same auth
- `tools/sql_executor.py:_escape_sql_string()` — same SQL escaping
- `tools/tool_factory.py:_humanize()` — same name cleaning
- `tools/tool_factory.py:_card_fence()` — same card formatting
- `data/py/sql_utils.py:get_schema_qualified()` — same schema resolution

Key function: `build_mcp_server()` — discovers UC functions (same logic as `discover_uc_function_tools()`), wraps each as SDK `@tool`, returns `create_sdk_mcp_server()`.

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

def create_sdk_read_tool(name, function_name, params, description):
    @tool(name, description, {p: str for p in params})
    async def sdk_read_tool(args: dict) -> dict:
        w, wh_id = get_warehouse()
        schema = get_schema_qualified()
        args_sql = ", ".join(f"'{_escape_sql_string(str(args.get(p, '')))}'" for p in params)
        stmt = f"SELECT * FROM {schema}.{function_name}({args_sql})"
        columns, rows = await asyncio.to_thread(execute_query, w, wh_id, stmt)
        card = {"type": "list", "title": _humanize(name.removeprefix("query_")), "columns": columns, "rows": rows}
        return {"content": [{"type": "text", "text": _card_fence(card)}]}
    return sdk_read_tool

def create_sdk_action_tool(name, procedure_name, params, description):
    @tool(name, description, {p: str for p in params})
    async def sdk_action_tool(args: dict) -> dict:
        w, wh_id = get_warehouse()
        schema = get_schema_qualified()
        args_sql = ", ".join(f"'{_escape_sql_string(str(args.get(p, '')))}'" for p in params)
        stmt = f"CALL {schema}.{procedure_name}({args_sql})"
        await asyncio.to_thread(execute_statement, w, wh_id, stmt)
        fields = [{"label": _humanize(p), "value": str(args.get(p, ""))} for p in params]
        card = {"type": "confirmation", "title": f"{_humanize(name)} Completed", "fields": fields}
        return {"content": [{"type": "text", "text": _card_fence(card)}]}
    return sdk_action_tool

def build_mcp_server():
    """Discover UC functions, wrap as SDK tools, return MCP server + allowed names."""
    # Same logic as discover_uc_function_tools() but returns SDK format
    # Uses w.functions.list() + w.functions.get() for params
    # TABLE_TYPE → create_sdk_read_tool, else → create_sdk_action_tool
    # Returns (create_sdk_mcp_server(name="brickforge", tools=[...]), allowed_names)
```

### Step 2: Agent Loop — `brickforge/agent/sdk_loop.py` (new, ~160 lines)

Adapt FleetMind's `agent_loop.py` (`/Users/mehdi.lamrani/code/code/FleetMind/src/agent_loop.py`):

Key functions to lift:
- `_build_claude_env(host, token, model)` — builds FMAPI env vars
- `_run_agent_in_fresh_loop(message, options, result_queue, context)` — worker thread
- `stream_agent_response(message, system_prompt, ...)` — async generator yielding events

Key differences from FleetMind:
- System prompt loaded from project config (`projects/{name}/prompt/main.prompt`)
- MCP server built from UC function discovery (step 1), not static tools
- Model from config env var, not hardcoded
- No Genie tools initially (add later)

Event types yielded:
```python
{"type": "text", "text": "..."}          # Assistant text
{"type": "text_delta", "text": "..."}    # Streaming token
{"type": "thinking", "thinking": "..."}  # Extended thinking
{"type": "tool_use", "tool_id": "...", "tool_name": "...", "tool_input": {...}}
{"type": "tool_result", "tool_use_id": "...", "content": "...", "is_error": bool}
{"type": "result", "session_id": "...", "duration_ms": N, "num_turns": N}
{"type": "error", "error": "..."}
{"type": "keepalive"}
```

### Step 3: Agent Entry Point — `brickforge/agent/sdk_agent.py` (new, ~80 lines)

Wire the SDK loop into BrickForge's serving infrastructure.

Key challenge: BrickForge's Node server calls the Python agent via MLflow's ResponsesAgent interface. The SDK agent needs to either:
- **Option A**: Implement the same `@mlflow_model` / `streaming()` interface, converting SDK events to ResponsesAgentStreamEvent
- **Option B**: Expose a separate HTTP endpoint (e.g., `/sdk-stream`) that the Node server calls

Option A is cleaner — same interface, transparent to the Node server.

```python
# Load system prompt from project prompt files
def _load_system_prompt():
    prompt_dir = os.environ.get("PROJECT_DIR", "")
    if prompt_dir:
        main = Path(prompt_dir) / "prompt" / "main.prompt"
        kb = Path(prompt_dir) / "prompt" / "knowledge.base"
        # Read and concatenate
    # Fallback to conf/prompt/

# Build MCP server from UC functions
server, allowed = build_mcp_server()

# Get FMAPI credentials from service principal
w = WorkspaceClient()
host = w.config.host
token = w.config.authenticate().get("Authorization", "").split()[-1]

# Stream
async for event in stream_agent_response(
    message=user_message,
    system_prompt=prompt,
    fmapi_host=host,
    fmapi_token=token,
    model=os.environ.get("AGENT_MODEL", "databricks-claude-opus-4-6"),
    mcp_servers={"brickforge": server},
    allowed_tools=allowed,
):
    yield convert_to_responses_agent_format(event)
```

### Step 4: Feature Flag — `brickforge/agent/start_server.py` (modify, ~10 lines)

```python
AGENT_RUNTIME = os.environ.get("AGENT_RUNTIME", "langgraph")

if AGENT_RUNTIME == "claude-sdk":
    from agent.sdk_agent import streaming  # SDK path
else:
    from agent.agent import streaming      # LangGraph path (default)
```

Config key: `agent.runtime` in config.json → flattened to `AGENT_RUNTIME` env var.

### Step 5: Dependencies — `requirements.txt` (modify)

Add:
```
claude-agent-sdk>=0.1.50
```

Verify no conflicts with existing deps:
- `langchain-core`, `langgraph`, `databricks-langchain` — should coexist (different packages)
- `mlflow` — should coexist
- Check transitive deps of `claude-agent-sdk`

### Step 6: Test End-to-End

1. Set config: `AGENT_RUNTIME=claude-sdk`, `AGENT_MODEL=databricks-claude-opus-4-6`
2. Deploy via Mage or manual deploy
3. Test read tool: "show me the menu" → UC function fires → list card renders
4. Test action tool: "place an order" → UC procedure fires → confirmation card renders
5. Test error: bad input → error card renders
6. Test streaming: tokens appear incrementally in chat UI
7. Compare latency/quality with LangGraph runtime on same tools

## Blockers

| # | Blocker | Severity | Mitigation |
|---|---------|----------|-----------|
| 1 | Model lock-in to `opus-4-6` | **Critical** | Accept for SDK path only. LangGraph remains default. Document clearly. |
| 2 | Node server streaming format | Medium | Convert SDK events → ResponsesAgentStreamEvent in `sdk_agent.py` |
| 3 | Dependency conflicts | Medium | Test in same venv. Fallback: conditional import behind `AGENT_RUNTIME` flag. |
| 4 | Worker thread per request | Low | Same pattern as FleetMind, proven in Databricks Apps production. |
| 5 | `start_server.py` interface | Medium | Must match MLflow pyfunc `streaming()` signature exactly. |

## Success Criteria

- [ ] UC function tools fire correctly through MCP
- [ ] Card fences render in existing chat UI (no frontend changes)
- [ ] Streaming works without breaking Node server
- [ ] Can switch between LangGraph and SDK via `AGENT_RUNTIME` config flag
- [ ] No regressions on the LangGraph path
- [ ] Deploy bundle includes `claude-agent-sdk` without bloating

## NOT in Scope

- Replacing LangGraph as primary runtime
- Changing Mage's agent loop (stays on ChatDatabricks + bind_tools)
- MCP tools for Genie, Vector Search, KA (separate concern)
- Session resume / memory / checkpointing on SDK path
- Non-Claude model support on SDK path
- UI changes (same chat app, same card rendering)

## Decision Point (after spike)

- **Option A**: Ship as "Deploy with Claude Agent SDK" option in Mage. User picks runtime at deploy time.
- **Option B**: Make SDK the default for Claude models, keep LangGraph for non-Claude.
- **Option C**: Learn from the patterns (MCP, skills), apply to LangGraph. Don't ship SDK path.

## Reference Files

### BrickForge (modify/reference)
| File | Path | Role |
|------|------|------|
| Agent runtime | `brickforge/agent/agent.py` | Current LangGraph agent — reference for interface |
| Server startup | `brickforge/agent/start_server.py` | Where feature flag goes |
| Tool factory | `brickforge/tools/tool_factory.py` | UC function discovery + tool creation |
| SQL executor | `brickforge/tools/sql_executor.py` | execute_query, execute_statement, get_warehouse |
| SQL utils | `brickforge/data/py/sql_utils.py` | get_schema_qualified() |
| Deploy | `brickforge/deploy/deploy_agent_app.py` | Bundle builder — needs to include sdk_*.py |
| Config | `brickforge/lib/config_provider.py` | DEFAULT_CONFIG — add `agent.runtime` key |
| Requirements | `brickforge/requirements.txt` | Add claude-agent-sdk |

### FleetMind (reference only — do not modify)
| File | Path | Role |
|------|------|------|
| Agent loop | `/Users/mehdi.lamrani/code/code/FleetMind/src/agent_loop.py` | ClaudeSDKClient runner — LIFT THIS |
| Tools | `/Users/mehdi.lamrani/code/code/FleetMind/src/tools.py` | @tool + create_sdk_mcp_server pattern |
| Genie tools | `/Users/mehdi.lamrani/code/code/FleetMind/src/genie_tools.py` | Genie MCP tools (future reference) |
| App | `/Users/mehdi.lamrani/code/code/FleetMind/src/app.py` | Gradio UI + FMAPI credential minting |
| Config | `/Users/mehdi.lamrani/code/code/FleetMind/src/config.py` | Model, warehouse, allowed tables |
