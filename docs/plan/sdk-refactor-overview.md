# Plan: Pluggable Agent Runtime for BrickForge

> Status: PLANNING
> Created: 2026-06-20

## The Big Picture

BrickForge's deployed agent should not be locked to one framework. The tool layer (UC functions, Genie, Vector Search) is shared. The agent loop is pluggable. The user picks the runtime at deploy time.

```
                    ┌─────────────────────┐
                    │   BrickForge Tools   │
                    │                     │
                    │  UC Functions (auto) │
                    │  Genie Spaces (MCP)  │
                    │  Vector Search       │
                    │  Chart / Card        │
                    │  Memory (Lakebase)   │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    │  Tool Adapter Layer  │
                    │                     │
                    │  Same UC discovery  │
                    │  Same SQL executor  │
                    │  Same card fences   │
                    │  Different wrappers │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼───────┐ ┌──────▼───────┐
    │   LangGraph    │ │ Claude SDK   │ │ OpenAI SDK   │
    │   (default)    │ │ (optional)   │ │ (optional)   │
    │                │ │              │ │              │
    │ ChatDatabricks │ │ ClaudeSDK    │ │ Agent()      │
    │ + bind_tools   │ │ Client +     │ │ + Runner     │
    │ + StateGraph   │ │ MCP server   │ │ + @fn_tool   │
    │                │ │              │ │              │
    │ Any FMAPI      │ │ opus-4-6     │ │ Any FMAPI    │
    │ model          │ │ only         │ │ model        │
    └────────────────┘ └──────────────┘ └──────────────┘
              │                │                │
              └────────────────┼────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Same Deploy       │
                    │   Same Chat UI      │
                    │   Same Config       │
                    │   Same Grants       │
                    └─────────────────────┘
```

## Config

```json
{
  "agent": {
    "runtime": "langgraph"
  }
}
```

Values: `"langgraph"` (default) | `"openai-sdk"` | `"claude-sdk"`

Flattened to `AGENT_RUNTIME` env var. Read by `start_server.py` at boot.

## Three Runtimes

| | LangGraph | Claude Agent SDK | OpenAI Agents SDK |
|---|---|---|---|
| **Plan** | Current (no changes) | [sdk-refactor-claude.md](sdk-refactor-claude.md) | [sdk-refactor-openai.md](sdk-refactor-openai.md) |
| **Model** | Any FMAPI | opus-4-6 only | Any FMAPI |
| **Loop** | Custom (you own it) | SDK (it owns it) | SDK (it owns it) |
| **Tools** | LangChain @tool | SDK @tool + MCP | @function_tool + MCP |
| **MCP** | Custom wrappers | Native | Native (first-class) |
| **Streaming** | Custom → ResponsesAgentStreamEvent | Custom → convert | **Native match** |
| **Memory** | Lakebase checkpointer | None | None |
| **Server** | Node.js + Python MLflow | Node.js + Python | Built-in AgentServer |
| **Tracing** | Manual | None | MLflow autolog |
| **Eval** | None | None | Built-in |
| **Dep** | langchain, langgraph | claude-agent-sdk | openai-agents, databricks-openai |
| **Lines** | ~400 (agent.py) | ~360 (3 new files) | ~220 (2 new files) |

## Shared Layer (no changes needed)

These files are used by ALL three runtimes:

| File | Path | What it provides |
|------|------|-----------------|
| SQL executor | `brickforge/tools/sql_executor.py` | `execute_query()`, `execute_statement()`, `get_warehouse()` |
| Tool helpers | `brickforge/tools/tool_factory.py` | `_humanize()`, `_card_fence()`, `discover_uc_function_tools()` (LangGraph only) |
| SQL utils | `brickforge/data/py/sql_utils.py` | `get_schema_qualified()` |
| Config | `brickforge/lib/config_provider.py` | Config system, env flattening |
| Project paths | `brickforge/lib/project_paths.py` | `gen_dir()`, `prompt_dir()` |
| Deploy | `brickforge/deploy/deploy_agent_app.py` | Bundle builder (include new agent files) |

## New Files Per Runtime

### Claude Agent SDK
| File | Lines | Purpose |
|------|-------|---------|
| `brickforge/agent/sdk_tools.py` | ~120 | UC function → MCP tool adapter |
| `brickforge/agent/sdk_loop.py` | ~160 | claude-agent-sdk runner (from FleetMind) |
| `brickforge/agent/sdk_agent.py` | ~80 | Entry point for SDK-based agent |

### OpenAI Agents SDK
| File | Lines | Purpose |
|------|-------|---------|
| `brickforge/agent/openai_tools.py` | ~100 | UC function → @function_tool adapter |
| `brickforge/agent/openai_agent.py` | ~120 | Agent + @stream handler |

## Implementation Order

1. **OpenAI SDK spike first** — model-agnostic, closer to existing patterns, less friction
2. **Claude SDK spike second** — model-locked, more complex (worker thread), but proves MCP pattern
3. **Feature flag in start_server.py** — `AGENT_RUNTIME` routing
4. **Mage integration** — add runtime selector to Mage build flow (choice card during discovery)
5. **Deploy integration** — include new agent files in bundle, set AGENT_RUNTIME in config

## Spike Priority

OpenAI SDK first because:
- No model lock-in (works with current Sonnet default)
- Streaming format is native (no converter needed)
- `@function_tool` is closer to LangChain's `@tool` (simpler adapter)
- MCP support is first-class (Genie spaces work natively)
- Built-in evaluation is a bonus
- Less code (~220 lines vs ~360 for Claude SDK)

## Decision After Spikes

Once both spikes prove out:
- If OpenAI SDK works well → make it the recommended runtime, keep LangGraph as fallback
- If both work → let user choose in Mage ("Which framework?")
- If neither works well → stay on LangGraph, adopt MCP patterns only
