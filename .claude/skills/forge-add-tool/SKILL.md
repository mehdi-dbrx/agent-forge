---
name: forge-add-tool
description: Create and register a new agent tool in agent-forge. Triggered when the user wants to add a tool, create a new tool, or extend the agent with a new capability.
---

# Agent Forge — Add Tool

Guides through creating a new LangChain tool under `tools/` and wiring it into the agent.

## Key Files

- `tools/<tool_name>.py` — tool implementation (one file per tool)
- `tools/__init__.py` — package marker (no imports needed here)
- `tools/sql_executor.py` — shared SQL helpers: `get_warehouse`, `execute_query`, `execute_statement`, `format_query_result`, `_escape_sql_string`
- `agent/agent.py:23-24` — tool imports
- `agent/agent.py:58-60` — tool list passed to `create_agent(tools=[...])`
- `data/sql_utils.py` — `substitute_schema()`, `get_schema_qualified()` for UC-qualified SQL
- `data/func/` — SQL function files (`.sql`) used by query tools

## Tool File Pattern

Use `query_flights_at_risk.py` as the reference for read tools, `update_flight_risk.py` for write/action tools.

### Read tool (queries data, returns formatted string)

```python
"""Agent tool to <one-line description>."""

from pathlib import Path

from langchain_core.tools import tool

from data.sql_utils import substitute_schema
from tools.sql_executor import execute_query, format_query_result, get_warehouse, _escape_sql_string

_FUNC_DIR = Path(__file__).resolve().parents[1] / "data" / "func"


@tool
def <tool_name>(<param>: str, ...) -> str:
    """<Short docstring — this is what the LLM sees to decide when to use the tool.>"""
    w, wh_id = get_warehouse()
    sql = substitute_schema((_FUNC_DIR / "<sql_file>.sql").read_text().strip())
    stmt = sql.replace("{param}", _escape_sql_string(<param>))
    try:
        columns, rows = execute_query(w, wh_id, stmt)
        return format_query_result(columns, rows)
    except RuntimeError as e:
        return f"Error: {e}"
```

### Action tool (executes a statement, no return data)

```python
"""Agent tool to <one-line description>."""

from langchain_core.tools import tool

from data.sql_utils import get_schema_qualified
from tools.sql_executor import execute_statement, get_warehouse


@tool
def <tool_name>(<param>: str, ...) -> str:
    """<Short docstring — this is what the LLM sees to decide when to use the tool.>"""
    w, wh_id = get_warehouse()
    schema = get_schema_qualified()
    escaped = <param>.replace("'", "''")
    stmt = f"CALL {schema}.<procedure_name>('{escaped}', ...)"
    try:
        execute_statement(w, wh_id, stmt)
        return f"Done: <param> updated."
    except RuntimeError as e:
        return f"Error: {e}"
```

## Workflow

### Step 1 — Understand the tool

Ask the user:
1. What does the tool do? (query data, call a procedure, call an API, etc.)
2. What parameters does it take?
3. Does it need a SQL function/procedure in `data/func/` or `data/proc/`? If so, does it already exist?
4. What should the LLM-facing docstring say? (Keep it concise — the LLM uses this to decide when to invoke the tool.)

### Step 2 — Create the SQL backing (if needed)

If the tool needs a new UC function or procedure, create the SQL file first:
- Functions: `data/func/<name>.sql` — then run `uv run python data/init/create_all_functions.py`
- Procedures: `data/proc/<name>.sql` — then run `uv run python data/init/create_all_procedures.py`

Use `substitute_schema()` in the tool to make SQL UC-schema-agnostic.

### Step 3 — Create `tools/<tool_name>.py`

Follow the pattern above. Rules:
- One `@tool`-decorated function per file, filename = function name
- Docstring must be concise and tell the LLM exactly when/how to use it
- Use `_escape_sql_string()` for any user-provided string params injected into SQL
- Return a plain string — the agent reads it as text
- Never raise exceptions out of the tool — catch and return `f"Error: {e}"`

### Step 4 — Register in `agent/agent.py`

**Add import** (after existing tool imports, ~line 24):
```python
from tools.<tool_name> import <tool_name>
```

**Add to tools list** (~line 58-60):
```python
tools = list(wrapped_tools) + [
    query_flights_at_risk,
    update_flight_risk,
    <tool_name>,       # ← add here
]
```

### Step 5 — Test locally

```bash
# Restart local stack
bash scripts/start_local.sh

# Or quick smoke test without full stack:
uv run python -c "from tools.<tool_name> import <tool_name>; print(<tool_name>.name)"
```

Then ask the agent a question that should trigger the tool and verify it appears in the tool call trace.

## Notes

- `get_warehouse()` uses `DATABRICKS_WAREHOUSE_ID` from env — always set in `.env.local`
- `substitute_schema()` replaces `{catalog}.{schema}` placeholders using `PROJECT_UNITY_CATALOG_SCHEMA`
- `get_schema_qualified()` returns `catalog.schema` string directly
- MCP tools (Genie spaces) are added separately via `DatabricksMCPServer` in `init_mcp_client()` — not via this pattern
- The agent comment at `agent/agent.py:26` says: _"New same-domain tools: append to tools in init_agent and implement under tools/<name>/"_ — follow this exactly
