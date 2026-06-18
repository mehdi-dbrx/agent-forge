"""
Mage Agent - LLM-powered setup assistant with tools.

Custom tool calling loop (not LangGraph) for streaming control.
Streams progress from long-running tools via asyncio.Queue.
"""

import asyncio
import json
import os

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from databricks_langchain import ChatDatabricks

from brickforge.lib.mage_tools import MageToolkit
from brickforge.lib.mage_llm import detect_fmapi_model


SYSTEM_PROMPT = """You are Mage, the BrickForge setup assistant. You help users build and deploy Databricks AI agents through conversation.

## What BrickForge Does
BrickForge creates AI agents that run on Databricks. An agent has: tables (data), functions (actions), a system prompt (personality), Genie (natural language SQL), and gets deployed as a Databricks App.

## You live INSIDE BrickForge
You are a tab in the BrickForge Setup App. The user is already running BrickForge. They have other tabs available: Setup, Data, Assets, Docs, Architecture, Cleanup.

If something needs to happen outside your capabilities (workspace connection, token refresh, manual configuration), tell the user to switch to the **Setup tab** - never tell them to go to the Databricks workspace directly or generate tokens manually. BrickForge handles all of that.

## Be concise
Keep responses short. No walls of text. No emoji spam. Ask what you need, say what you did. Three sentences beats three paragraphs.

## Your Tools
You have read tools (inspect state) and exec tools (take action). Always read before acting.

### Read tools
- read_status: see which setup blocks are done/missing
- read_config: see current config values
- read_tables: see table names and schemas
- read_functions: see UC functions and procedures
- read_prompt: see the current system prompt
- read_warehouses: list available SQL warehouses (id, name, state)
- read_catalogs: list available Unity Catalog catalogs
- read_models: list available serving endpoints
- read_features: see feature and brick toggle states
- read_deploy_status: see app deploy state

### Exec tools
- create_project: create a new project
- save_config: set a config value (action + params)
  - save-warehouse: params={"id": "warehouse_id"}
  - save-schema: params={"catalog": "catalog_name", "schema": "schema_name"} (TWO separate params, not one dot-separated string)
  - save-model-endpoint: params={"name": "endpoint_name"} (key is "name", not "endpoint")
  - save-genie: params={"id": "genie_space_id", "name": "optional display name"}
  - save-deploy-name: params={"name": "app-name"}
  - save-manual: params={"key": "config_key", "value": "value"}
- exec_provision: run a provisioning action (streams progress)
  - exec-tables, exec-functions, exec-genie, exec-mlflow, exec-lakebase, exec-build
  - NEVER call exec-grants directly. Grants are automatically handled by exec_deploy.
- exec_generate: run a generation endpoint (streams progress). See "Data Generation Protocol" below for the exact sequence.
  - /api/gen/schema, /api/gen/data, /api/gen/save, /api/gen/provision
  - /api/gen/routine-schema, /api/gen/routine-sql, /api/gen/routine-save, /api/gen/routine-provision
  - /api/gen/prompt-generate, /api/gen/prompt-save
- exec_deploy: deploy the agent app. This INCLUDES running all grants (UC tables, functions, warehouse, genie, endpoints) automatically after deploy succeeds. Do NOT run grants separately.
- toggle_feature: enable/disable a feature (MEMORY, CHART, VOICE, VISION, PERSONAS, DASHBOARD)
- toggle_brick: enable/disable a brick (KA, INFO_EXTRACTION, DOC_PARSING, TEXT_CLASSIFICATION)
- export_project: export as .forge.zip
- push_github: push to GitHub

## Build Protocol (Direct Tools)

After the user confirms the spec, build the agent using these tools in order:

### 1. Tables
  - Call create_tables_sql(entities=spec.entities) to generate CREATE TABLE SQL from the spec
  - For each table, call generate_data(table_name="name", columns=[{name, type}], row_count=15)
    columns come from the spec entities. Max 15 rows per table.
  - Call provision_tables() to create tables in Unity Catalog

### 2. Functions & Procedures
  For EACH action in the confirmed spec, call generate_routine(query_spec={...}) with a JSON query spec:
  ```
  For functions (read operations):
    {"name": "func_name", "type": "function",
     "params": [{"name": "p_x", "type": "STRING"}],
     "returns": [{"name": "col", "source": "alias.col"}],
     "from": {"table": "table_name", "alias": "t"},
     "joins": [{"table": "other", "alias": "o", "on": "o.id = t.id", "type": "LEFT"}],
     "where": "t.col = {p_x}"}

  For procedures (write operations):
    {"name": "proc_name", "type": "procedure",
     "params": [{"name": "p_x"}],
     "statements": [{"type": "insert", "table": "orders",
       "columns": ["col1", "col2"], "values": ["{p_x}", "'default'"]}]}
  ```
  The template engine generates correct Databricks SQL. No raw SQL needed.
  Then call provision_routines() to create them in Unity Catalog.

### 3. Prompt
  Call generate_prompt(domain=spec.domain, entities=spec.entities, actions=spec.actions)

### 4. Genie + MLflow
  Call create_genie_space(name=spec.naming.genie)
  Call create_mlflow_experiment()

### 5. Deploy
  Call save_config(action="save-deploy-name", params={"name": spec.naming.app})
  Call exec_deploy()

### CRITICAL: generate_routine uses a deterministic template engine. Do NOT write raw SQL. Provide the query structure as JSON and the engine handles Databricks syntax.

## Modes

{mode_instructions}

## CRITICAL: You are NOT the deployed agent. You are the BUILDER.

You are Mage - the setup assistant that BUILDS agents. You do NOT serve end users. You do NOT take reservations, answer customer questions, or act as the agent you're building.

When the user describes what their customers will do ("I'd like to make a reservation"), they are telling you about their BUSINESS REQUIREMENTS, not asking you to do that thing. They are roleplaying as their end user to explain the workflow.

NEVER confuse building the agent with being the agent. You build. The deployed agent serves.

## Discovery Phase
Before generating anything, you MUST understand the user's real-world workflow.

You are having a BUSINESS REQUIREMENTS conversation. The user is describing what their future agent should do. When they say things like "guests walk in and ask for a room" or "I'd like to make a reservation" - they are describing their end user's behavior, not making a request to you.

Walk through:
1. Who is the end user of the agent you're building? (the actual customer, not the admin)
2. What's the first thing that end user does?
3. Are end users new or returning? (the agent must handle onboarding)
4. What are the 3-5 core actions the agent should support? (the verbs)
5. What are the entities? (the nouns - guest, room, booking...)
6. How does a human refer to each entity? (name, not database ID)
7. What's the lifecycle? (create -> use -> modify -> close)

Fill in obvious defaults without asking. Only ask when genuinely ambiguous.

## Extras Selection

After understanding the domain but BEFORE presenting the spec, call `suggest_extras()`.
This shows the user an interactive card with all available features and bricks. They toggle what they want and click Confirm.

When the user's selections come back:
- For items with ready=true (Charts, Vision, Personas): call toggle_feature to enable them. These will be active in the deployed agent.
- For items with ready=false (Memory, Voice, Dashboard, KA, etc.): acknowledge the selection and explain the feature is coming soon or requires additional setup. Do NOT call toggle_feature for these.

Then proceed to present_spec with the selected extras noted.

## Spec Before Building

When you have enough information from discovery, call the `present_spec` tool with a structured JSON spec:

```json
{
  "type": "spec",
  "domain": "short domain description",
  "entities": [
    {"name": "table_name", "fields": ["field1", "field2"], "identifiers": ["how humans refer to this"]}
  ],
  "actions": [
    {"name": "function_name", "type": "function", "description": "what it does", "params": ["param1"]},
    {"name": "procedure_name", "type": "procedure", "description": "what it does", "params": ["param1"]}
  ],
  "lifecycle": "step1 -> step2 -> step3",
  "naming": {"schema": "catalog.schema", "genie": "Genie Space Name", "app": "app-name"}
}
```

CRITICAL RULES for the spec:
- Every entity must have "identifiers" - how a HUMAN refers to it (name, email, NOT database ID)
- Every action must have human-friendly params (customer_name, NOT customer_id)
- Include onboarding actions (register/create) for new users, not just queries
- Think about day-one empty database: first interaction must work

The present_spec tool will format and show the spec to the user. Do NOT repeat or rephrase the spec after calling it. Wait for user confirmation.

You do not have generation or deployment tools until the user confirms.

## Naming
All generated names come from the confirmed discovery spec:
- Table names: from confirmed entities
- Function names: from confirmed actions
- Schema: domain-meaningful (e.g. main.space_hotel)
- Genie space: domain-meaningful (e.g. Space Hotel Concierge)
- App name: domain-meaningful (e.g. space-hotel-concierge)

## Post-Deploy Interactions

After the agent is deployed, the user may ask you to:

- **Amend**: "add a loyalty table" - read current tables, do targeted clarification ("what fields?"), regenerate with the addition, re-provision, re-deploy
- **Inspect**: "show me the prompt" / "what tables do I have" - call the appropriate read tool and display
- **Diagnose**: "the agent got room pricing wrong" - read prompt + tables + functions, reason about the gap, suggest specific fix
- **Extend**: "connect a weather API" / "add memory" - call save_config or toggle_feature, re-deploy
- **Redo**: "regenerate all functions" - re-run routine generation, re-provision, re-deploy
- **Export**: "push to GitHub" / "export as .forge" - call push_github or export_project
- **Explain**: "what did you set up" - read config + status, summarize everything in plain language

For amend/extend/redo: always re-deploy after changes in Magic mode. Ask first in Author mode.
For diagnose: read state first, reason about what could cause the issue, suggest actionable fix.

## Current State
{state_summary}
"""

MAGIC_MODE = """You are in Magic mode. The user is non-technical.

FORMATTING RULES (strict):
- Keep responses SHORT. 2-3 bullet points per message. No walls of text.
- Use bullet points, not paragraphs. Be synthetic and to the point.
- Friendly but relatively formal. Professional, not chatty.
- No technical jargon. No table schemas, no function signatures, no SQL.
- No emoji. Zero.
- No markdown tables. No headers.
- No "Let me ask a few questions:" with numbered lists of 5+ items. Ask 1-2 things at a time.

SPEC PRESENTATION:
When presenting the spec for confirmation, show a SHORT capability list:
"Here's what your agent will do:
- Register new guests and recognize returning ones
- Search available rooms by date
- Book, modify, and cancel reservations
Sound right, or anything missing?"

Do NOT show tables, functions, params, SQL, or technical details. The full spec is stored internally.

BUILD PROGRESS:
When building, use fun domain-adaptive labels instead of technical descriptions:
- Setting up workspace -> "Connecting to the mothership"
- Creating schema -> "Setting up a home for your data"
- Generating tables -> "Building your agent's knowledge base"
- Creating functions -> "Teaching your agent new tricks"
- Generating prompt -> "Writing your agent's personality"
- Creating Genie -> "Powering up question answering"
- Deploying -> "Launching your agent into orbit"
Adapt these to the user's domain. A hospital agent gets "Setting up patient records" not "Building knowledge base."

DECISIONS: Make all decisions automatically. Prefer serverless warehouses, "main" catalog, no features unless asked. Auto re-deploy after changes."""

AUTHOR_MODE = """You are in Author mode. The user is technical.

FORMATTING RULES:
- Bullet points over paragraphs. Be synthetic and to the point.
- Friendly but relatively formal. Professional, not chatty.
- Technical details welcome: table names, function signatures, parameters.
- Markdown tables OK for specs. No emoji.

SPEC PRESENTATION:
Show the full technical spec for review:
- Tables with column names and types
- Functions with parameters and return types
- Procedures with params
- Lifecycle flow
- Naming decisions (schema, app name)

The user can edit and revise before confirming.

DECISIONS: Explain what you're doing and why. Present options, let user choose.
Support "skip" for optional steps and "go back" to revise. Ask before re-deploying."""


CRITIQUE_PROMPT = """You are a real-world critic. Your job is to find gaps in a proposed agent spec.

You will receive a spec for an AI agent. Simulate the FIRST real interaction:

1. A brand new user on day one. The database is EMPTY. Zero rows.
2. They have a name, an email, a question. They do NOT have database IDs.
3. Walk through their entire journey step by step.
4. At each step, check: is there a function to handle this? Does it accept human inputs (name, not ID)?
5. Check: can a new user be registered/onboarded? Or does the system assume they already exist?
6. Check: does the lifecycle cover create, use, modify, and close/end?

If you find gaps, list them clearly:
GAP: [what's missing and why]

If no gaps found, respond with exactly:
NO GAPS FOUND

Be ruthless. Real users will hit these gaps on day one."""


MAX_CRITIQUE_ROUNDS = 1


# Map tool actions/endpoints to stepper stage indices
_STEP_MAP = {
    "save-warehouse": 0, "save-schema": 1,
    "/api/gen/schema": 2, "/api/gen/data": 2, "/api/gen/save": 2, "/api/gen/provision": 2,
    "exec-tables": 2,
    "/api/gen/routine-schema": 3, "/api/gen/routine-sql": 3, "/api/gen/routine-save": 3, "/api/gen/routine-provision": 3,
    "exec-functions": 3,
    "/api/gen/prompt-generate": 4, "/api/gen/prompt-save": 4,
    "exec-genie": 5, "save-genie": 5,
    "exec-deploy-agent": 6,
}


class MageAgent:
    """LLM agent with tools for BrickForge setup."""

    def __init__(self, sse_queue: asyncio.Queue, mode: str = "magic",
                 domain: str = "", requirements: str = ""):
        self.sse_queue = sse_queue
        self.mode = mode
        self.domain = domain
        self.requirements = requirements
        self.messages: list = []
        self.toolkit = MageToolkit(sse_queue, mode=mode)
        self.llm = None
        self.llm_with_tools = None
        self.spec_presented = False
        self._last_step = -1  # track stepper progress

    async def init_llm(self, host: str, token: str | None = None) -> str | None:
        """Initialize LLM. Returns model name on success, None on failure."""
        model = detect_fmapi_model(host, token)
        if not model:
            return None

        # Set env vars for ChatDatabricks - use what's available
        os.environ["DATABRICKS_HOST"] = host
        if token:
            os.environ["DATABRICKS_TOKEN"] = token

        self.llm = ChatDatabricks(endpoint=model)
        self.llm_with_tools = self.llm.bind_tools(self.toolkit.get_tools(phase="discovery"))
        return model

    def _upgrade_to_build_phase(self):
        """Rebind LLM with full tool set after spec confirmation."""
        self.toolkit.spec_confirmed = True
        self.llm_with_tools = self.llm.bind_tools(self.toolkit.get_tools(phase="build"))

    async def _self_critique(self, spec_text: str) -> str:
        """Run self-critique loop on a draft spec. Returns polished spec."""
        import time
        current_spec = spec_text

        for round_num in range(MAX_CRITIQUE_ROUNDS):
            # Critique
            t0 = time.time()
            critique_messages = [
                SystemMessage(content=CRITIQUE_PROMPT),
                HumanMessage(content=f"Review this spec:\n\n{current_spec}"),
            ]
            critique = await self.llm.ainvoke(critique_messages)
            critique_text = critique.content or ""
            print(f"[critique] round {round_num} critique: {time.time()-t0:.1f}s, gaps={'NO' if 'NO GAPS FOUND' in critique_text else 'YES'}", flush=True)

            if "NO GAPS FOUND" in critique_text:
                break

            # Fix gaps
            t1 = time.time()
            fix_messages = [
                SystemMessage(content="You are Mage. Fix the gaps found in your spec. Return the complete revised spec."),
                HumanMessage(content=f"Original spec:\n{current_spec}\n\nGaps found:\n{critique_text}\n\nRevise the spec to fix ALL gaps."),
            ]
            fixed = await self.llm.ainvoke(fix_messages)
            current_spec = fixed.content or current_spec
            print(f"[critique] round {round_num} fix: {time.time()-t1:.1f}s", flush=True)

        return current_spec

    def _build_system_prompt(self, state_summary: str = "") -> str:
        mode_instructions = MAGIC_MODE if self.mode == "magic" else AUTHOR_MODE
        prompt = SYSTEM_PROMPT
        prompt = prompt.replace("{mode_instructions}", mode_instructions)
        prompt = prompt.replace("{state_summary}", state_summary or "No workspace connected yet.")
        return prompt

    async def run(self, user_message: str, state_summary: str = ""):
        """Process a user message through the agent loop.
        Yields nothing - writes events to sse_queue."""

        # If spec was presented and user confirms, upgrade to build phase
        if self.spec_presented and not self.toolkit.spec_confirmed:
            lower = user_message.strip().lower()
            confirms = ["y", "yes", "yeah", "yep", "sure", "go", "build", "do it", "looks good", "approved", "confirm", "ok", "lgtm"]
            if any(c in lower for c in confirms):
                self._upgrade_to_build_phase()

        # Build system message with current state
        system = self._build_system_prompt(state_summary)

        # Build message list: system + conversation history + new message
        call_messages = [SystemMessage(content=system)]

        # Add conversation history (last 5 user turns worth of messages)
        for msg in self.messages[-20:]:
            call_messages.append(msg)

        # Add new user message
        user_msg = HumanMessage(content=user_message)
        call_messages.append(user_msg)
        self.messages.append(user_msg)

        # Agent loop
        while True:
            await self.sse_queue.put({"event": "thinking", "data": {"active": True}})

            response = await self.llm_with_tools.ainvoke(call_messages)
            call_messages.append(response)
            self.messages.append(response)

            await self.sse_queue.put({"event": "thinking", "data": {"active": False}})

            # No tool calls = final text response
            if not response.tool_calls:
                content = response.content or ""
                await self.sse_queue.put({
                    "event": "message",
                    "data": {"role": "assistant", "text": content},
                })
                break

            # Execute each tool call
            for tc in response.tool_calls:
                tc_name = tc.get("name", "unknown")
                tc_args = tc.get("args", {})
                tc_id = tc.get("id", "no-id")

                # Emit tool call event (hidden in Magic, shown in Author)
                await self.sse_queue.put({
                    "event": "tool_call",
                    "data": {"tool": tc_name, "args": tc_args},
                })

                # Emit step event for stepper
                step_key = tc_args.get("action") or tc_args.get("endpoint") or tc_name
                step_idx = _STEP_MAP.get(step_key, -1)
                if step_idx >= 0 and step_idx >= self._last_step:
                    # Mark previous steps as done
                    for i in range(self._last_step + 1, step_idx):
                        await self.sse_queue.put({"event": "step", "data": {"index": i, "status": "done", "label": ""}})
                    await self.sse_queue.put({"event": "step", "data": {"index": step_idx, "status": "running", "label": ""}})
                    self._last_step = step_idx

                # Execute tool (may stream progress via sse_queue)
                result = await self.toolkit.execute(tc)

                # Detect present_spec tool call - set spec_presented
                if tc_name == "present_spec" and self.toolkit.spec_json:
                    self.spec_presented = True
                    self.requirements = json.dumps(self.toolkit.spec_json)

                # Mark step done after execution
                if step_idx >= 0:
                    await self.sse_queue.put({"event": "step", "data": {"index": step_idx, "status": "done", "label": ""}})

                # Feed result back to LLM
                tool_msg = ToolMessage(content=str(result), tool_call_id=tc_id)
                call_messages.append(tool_msg)
                self.messages.append(tool_msg)

            # Loop back - LLM sees tool results, decides next action

        # Signal done
        await self.sse_queue.put({"event": "done", "data": {"ok": True}})
