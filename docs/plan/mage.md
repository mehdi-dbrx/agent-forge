# Mage - BrickForge Chat Assistant

> Status: IN PROGRESS
> Created: 2026-06-16
> Last review: Plan-code reconciliation after implementation session

## What Mage Is

The third interface layer for BrickForge: CLI -> Visual UI -> **Mage**. A conversational AI agent that builds, manages, and troubleshoots Databricks agents through chat.

**Two modes:**
- **Magic**: non-technical. "I want an agent for my pet hotel." Mage handles everything silently.
- **Author**: technical. Mage explains and lets user choose at each step.

## Architecture (implemented)

```
┌─────────────────────────────────────────────────┐
│  React Frontend                                  │
│  ┌────────────┐  ┌───────────────────────────┐  │
│  │ SetupView  │  │ MageView (tab, 1st pos)   │  │
│  │ (DAG)      │  │ - hero + mode toggle      │  │
│  │            │  │ - chat + stepper           │  │
│  └────────────┘  └───────────────────────────┘  │
│        │                    │                    │
│        └──────┬─────────────┘                    │
│               │ same config state                │
└───────────────┼──────────────────────────────────┘
                │
   ┌────────────▼──────────────────────┐
   │  FastAPI Server                    │
   │  ┌──────────────────────────┐     │
   │  │ routes/mage.py           │     │
   │  │  POST /api/mage/chat     │     │
   │  │  GET  /api/mage/status   │     │
   │  │  POST /api/mage/reset    │     │
   │  └──────────┬───────────────┘     │
   │             │                     │
   │  ┌──────────▼───────────────┐     │
   │  │ lib/mage_agent.py        │     │
   │  │  Custom tool loop        │     │
   │  │  Phased tool binding     │     │
   │  │  Self-critique loop      │     │
   │  └──────────┬───────────────┘     │
   │             │ httpx on localhost   │
   │  ┌──────────▼───────────────┐     │
   │  │ Existing endpoints       │     │
   │  │ setup.py + gen.py +      │     │
   │  │ projects.py              │     │
   │  └──────────────────────────┘     │
   └───────────────────────────────────┘
```

## Startup Sequence (implemented)

4 scripted questions, then LLM takes over:

1. User types description on hero screen. Mode selected via UI toggle (sent with first message). Project created via `POST /api/projects`. If exists (409), loaded instead.
2. If mode not from UI: ask Magic or Author (accepts synonyms: auto/automatic = Magic, manual/guide = Author)
3. If domain not captured in step 1: ask for business description
4. Auto-connect workspace (from env/config). Auto-detect FMAPI model (prefer latest Claude Sonnet -> any Claude -> any FMAPI). No model = Mage unavailable, full stop. No degraded mode.

Steps 3->4 and 1->4 (when domain captured early) fall through automatically. No dead stops.

## Phased Tool Binding (implemented)

Discovery phase: LLM only has read tools (11 tools). Cannot see exec/gen/deploy tools.
Build phase: after user confirms spec, `_upgrade_to_build_phase()` rebinds LLM with full tool set (19 tools).

This prevents the LLM from calling gen/deploy during discovery. No BLOCKED responses, no retry loops.

## Discovery Phase (implemented)

7-point framework in system prompt:
1. Who is the end user
2. What's their first interaction
3. New vs returning (onboarding needed?)
4. Core actions (3-5 verbs)
5. Entities (nouns)
6. Identifiers (how humans refer to things - name, not ID)
7. Lifecycle (create -> use -> modify -> close)

Domain-agnostic. Works for hotels, hospitals, fleet management, anything.

## Self-Critique Loop (implemented)

After discovery, before presenting spec:
- LLM generates spec internally
- Code detects spec-like response (3+ of: entity, action, function, lifecycle, table, register, booking)
- Runs critique: "Simulate first real interaction. Day one, empty database, new user. What breaks?"
- If gaps found: fix and return polished spec
- `MAX_CRITIQUE_ROUNDS = 1` (was 3, reduced for latency - 40s vs 257s)
- `spec_presented` flag set after critique passes

## Spec Presentation - Two Layers (implemented in prompt)

**Internal spec**: full technical detail (tables, columns, functions, params, lifecycle, identity flow). Stored in session `requirements` field. Fed to gen endpoints.

**User-facing**:
- Magic: 5-7 bullet capability list, human language, no tech
- Author: full spec with tables, functions, params

Stopping condition: explicit user confirmation. Code checks for confirm keywords ("yes", "build", "looks good", etc.) + `spec_presented` flag. Then `_upgrade_to_build_phase()` unlocks exec tools.

## Data Generation Protocol (in system prompt)

Explicit multi-step instructions to prevent KeyError retries:

**Tables**: schema (returns table objects) -> per-table data gen -> per-table save -> provision
**Routines**: routine-schema -> per-routine SQL gen -> per-routine save -> provision
**Prompts**: generate -> save

Each step's output feeds the next. LLM told to save schema result and loop per table/routine.

## Custom Agent Loop (implemented)

Not LangGraph. Custom `while True` loop for streaming control:
1. Call LLM with tools via `ainvoke`
2. No tool_calls = text response -> emit to frontend
3. Has tool_calls = execute each, stream progress via `asyncio.Queue`
4. Feed tool results back, loop

~30 lines. Full control over streaming during long operations (deploy, gen).

## LLM Client (implemented)

`ChatDatabricks` from `databricks_langchain` with `.bind_tools()`.
Own instance, not shared with deployed agent's `AGENT_MODEL`.
Accepts `token=None` for OAuth/CLI profile auth (not just PAT).
Model preference: latest Claude Sonnet -> any Claude -> any FMAPI.

## SSE Protocol (implemented)

| Event | Data | Frontend |
|-------|------|----------|
| `message` | `{role, text}` | Chat bubble |
| `progress` | `{line}` | Collapsible terminal block |
| `error` | `{message, suggestion}` | Red bubble + retry |
| `tool_call` | `{tool, args}` | Hidden in Magic, shown in Author |
| `thinking` | `{active}` | Bouncing dots |
| `step` | `{index, status, label}` | Stepper dot update |
| `done` | `{ok, url}` | Final state, input stays open |

Frontend -> Backend: `{type: "text"/"choice", content/choice_id}`

## Progress Stepper (implemented)

`ProgressStepper` extracted to shared component (`ProgressStepper.tsx`). Used by both StashHealthView and MageView.

Default stages in MageView:
- Connecting workspace, Setting up data home, Building knowledge base, Teaching new tricks, Writing personality, Powering up questions, Launching into orbit

Driven by `event:step` SSE events. Green=done, amber=running, gray=pending.

**TODO**: Backend doesn't emit `event:step` yet. Stepper widget exists but won't activate until mage_agent.py emits step events during build.

## Gamified Labels (implemented in prompt)

Magic mode system prompt includes fun domain-adaptive labels:
- "Connecting to the mothership" / "Setting up a home for your data" / "Teaching your agent new tricks" / "Launching into orbit"
- LLM adapts to domain ("Setting up patient records" for healthcare)

## Concise Formatting (implemented in prompt)

Magic mode strict rules:
- 2-3 sentences max per message
- No tables, no headers, no jargon, no emoji spam
- Ask 1-2 things at a time, not 5-question lists

Author mode:
- Structured, technical, tables OK
- Still not verbose

## Config and Project System (implemented)

- Step 0 creates project via `POST /api/projects` (was missing, fixed)
- If project exists (409), loads it instead
- gen.py reloads in-memory config after subprocess writeback (`reload_config=True` on provision and routine-provision endpoints)
- Prevents stale config overwriting function names written by subprocesses

## Test Framework (implemented)

`brickforge/data/gen/test_generator.py` - generates and runs E2E tests for functions/procedures.

Flow: read SQL files + seed data -> LLM generates test cases -> execute against warehouse -> verify results

Endpoints: `/api/gen/test-generate`, `/api/gen/test-run`, `/api/gen/test` (both)

Catches: silent 0-row INSERTs, wrong SQL syntax, missing functions, parameter issues.

Slots into pipeline: gen -> provision -> **test** -> deploy

## SQL Generation Fixes (implemented)

**routine_sql_generator.py**:
- Function prompt: added qualified parameter rule (`search_rooms.p_check_in` not bare `p_check_in`)
- Sanitizer: auto-adds `SQL SECURITY INVOKER` to procedures when missing
- Sanitizer: auto-adds `LANGUAGE SQL` when missing

**test_generator.py prompt**:
- Correct table function syntax: `SELECT * FROM schema.func(args)` not `TABLE()`
- No subqueries as CALL args (causes "args must be foldable")

## Other Fixes Applied

- `setup.py:1805`: `cwd=PACKAGE_ROOT` (was PROJECT_ROOT - file not found)
- `config_provider.py`: CHART default disabled (was enabled)
- `mage.py` discovery prompt: domain-agnostic ("who uses it" not "when a customer walks in")
- System prompt: "you are the BUILDER not the deployed agent" (LLM confused the two)
- System prompt: "NEVER call exec-grants directly" (grants bundled in deploy)
- SSE parsing: `_stream_gen/_stream_exec` now parse event types and capture `event:result` payloads

## Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `brickforge/lib/mage_agent.py` | 405 | Agent + system prompt + custom tool loop + self-critique |
| `brickforge/lib/mage_tools.py` | 331 | 19 tools (phased: 11 read, 8 exec) + SSE streaming |
| `brickforge/lib/mage_llm.py` | 59 | FMAPI model auto-detect + ChatDatabricks instance |
| `brickforge/routes/mage.py` | 296 | Startup sequence + SSE chat endpoint |
| `brickforge/data/gen/test_generator.py` | 309 | E2E test generation and execution |
| `visual/frontend/src/components/MageView.tsx` | 368 | Chat UI + stepper + hero |
| `visual/frontend/src/components/ProgressStepper.tsx` | 30 | Shared stepper component |

## Files Modified

| File | Change |
|------|--------|
| `brickforge/server.py` | Mount mage_router |
| `brickforge/lib/config_provider.py` | CHART default disabled |
| `brickforge/routes/setup.py` | cwd fix (PACKAGE_ROOT) |
| `brickforge/routes/gen.py` | Config reload after subprocess + test endpoints |
| `brickforge/data/gen/routine_sql_generator.py` | Qualified params + SECURITY INVOKER sanitizer |
| `visual/frontend/src/App.tsx` | Mage tab (first position) + import |
| `visual/frontend/src/components/StashHealthView.tsx` | Uses shared ProgressStepper |

## Known Issues / TODOs

### Backend doesn't emit event:step
The stepper widget exists in MageView but mage_agent.py never emits `event:step` SSE events during the build flow. The stepper won't activate until this is wired. Need to emit step events from the tool execution sequence.

### Deploy verification unsolved
App URL handed to user without confirming it's reachable. "Give it 2 minutes" is unacceptable. Need health check polling or readiness probe. Recurring issue across sessions.

### Data gen not additive
"Add a table" means regenerate all tables with the new one included. Additive gen is a future enhancement.

### Table function params may still fail
The qualified params fix is in the prompt but not verified through a clean regeneration cycle. The manual SQL file fixes work but the LLM may still generate unqualified params. Needs a sanitizer layer (auto-qualify params in RETURNS TABLE functions).

### Self-critique latency
One round = ~40s (critique + fix). Acceptable but noticeable. Could be optimized with a lighter critique prompt or by skipping critique when the spec clearly covers the basics.

### mage.enabled feature flag not added
Plan says tab only shows when enabled. Currently always shows. Need to add to DEFAULT_CONFIG and conditionally render tab.

### Session requirements field not persisted
Self-critique produces internal spec but it's not saved to `mage_session.json` `requirements` field. Gen endpoints don't receive the confirmed spec - they get whatever the LLM passes in tool args.

### 8 interaction types: only First Run tested
Amend, Inspect, Diagnose, Extend, Redo, Export, Explain - none tested. Architecture supports them (same agent, same tools) but no verification.

### Author mode not tested
All testing was Magic mode. Choice cards, skip, go-back not implemented in frontend.

## Design Decisions (final)

| Decision | Choice | Why |
|----------|--------|-----|
| Agent architecture | Custom tool loop, not LangGraph | Streaming control during long operations |
| Tool binding | Phased (discovery=read, build=all) | Prevents LLM from calling gen tools prematurely |
| LLM client | ChatDatabricks + bind_tools | Proven pattern from deployed agent, supports tool calling |
| Action reuse | httpx to localhost, not extracted functions | Zero refactor of setup.py, zero risk to existing UI |
| Self-critique | 1 round (was 3), ~40s | Catches real gaps without burning 4+ minutes |
| Spec presentation | Two layers (internal + user-facing) | Magic users see capabilities, Author users see full spec |
| Config writeback | gen.py reloads after subprocess | Prevents stale in-memory config from overwriting disk |
| Project creation | Step 0 of startup, via HTTP | All gen data goes to project-scoped directory |
| No degraded mode | No FMAPI = Mage unavailable | One code path, no dual maintenance |
| Discovery prompt | Domain-agnostic | "Who uses it" not "when a customer walks in" |
| Grants | Only post-deploy, bundled in exec-deploy | No wasted pre-deploy grant calls |
| SQL generation | Qualified params + sanitizer | Databricks requires function-name-qualified refs in TABLE bodies |

## Setup Block Coverage Gap

The visual UI has 18 setup blocks. Mage currently handles some and skips others. Here's the full map:

### Handled by Mage (in the build flow)

| Block | How Mage handles it |
|-------|-------------------|
| host | Scripted startup step 4 - auto-connect from env/config |
| warehouse | LLM calls save_config with save-warehouse |
| schema | LLM calls save_config with save-schema |
| tables | Gen protocol: schema -> data -> save -> provision |
| functions | Gen protocol: routine-schema -> SQL -> save -> provision |
| model | LLM calls save_config with save-model-endpoint |
| prompt | Gen protocol: prompt-generate -> prompt-save |
| genie | LLM calls save_config with save-genie + exec_provision with exec-genie |
| mlflow | LLM calls exec_provision with exec-mlflow |
| deploy | LLM calls exec_deploy (includes grants) |

### Auto-created by Mage (Magic mode defaults)

| Block | Behavior |
|-------|----------|
| genie | Auto-created with domain-meaningful name. No user input needed. |
| mlflow | Auto-created. No user input needed. |
| deploy | App name auto-generated from domain. No user input needed. |

### Missing - needs user opt-in (not auto-enabled)

| Block | What's needed | Magic mode | Author mode |
|-------|--------------|------------|-------------|
| features | Toggle MEMORY, CHART, VOICE, VISION, PERSONAS, DASHBOARD | Agent asks after deploy: "Want to add memory, charts, or voice?" User says yes/no. | Present toggles, user picks. |
| bricks | Toggle KA, INFO_EXTRACTION, DOC_PARSING, TEXT_CLASSIFICATION | Agent asks after deploy: "Want to add document search or text classification?" | Present toggles, user picks. |
| vs | Vector Search index path | Only if user asks for document search. Requires a provisioned VS index. | Present as option during setup. |
| ka | Knowledge Assistant endpoint | Only if KA brick enabled. Requires document upload. | Present as option during setup. |

### Missing - optional integrations (user-initiated only)

| Block | What's needed | When Mage handles it |
|-------|--------------|---------------------|
| mcp | External MCP server URL + auth | Only when user says "connect a Slack MCP" or "add weather API." Mage calls save_config with save-multi-instance. |
| api | External REST API config | Only when user says "connect an API." Mage calls save_config with save-api. |
| a2a | Remote agent URL + auth | Only when user says "connect another agent." Mage calls save_config with save-multi-instance. |
| git | GitHub push | Only when user says "push to GitHub." Mage calls push_github. |

### Mage build flow order (complete)

Magic mode executes these in order after spec confirmation:

```
1. save-warehouse (auto-select first serverless)
2. save-schema (domain-meaningful name)
3. save-model-endpoint (auto-detect best FMAPI)
4. Gen tables: schema -> per-table data+save -> provision
5. Gen routines: routine-schema -> per-routine SQL+save -> provision
6. Gen prompt: generate -> save
7. save-genie + exec-genie (auto-name from domain)
8. exec-mlflow (auto-create)
9. save-deploy-name (auto from domain)
10. exec-deploy (includes grants)
```

After deploy, Mage asks: "Your agent is live. Want to add any extras? (memory, charts, document search)"

If user says yes to any:
- Features: toggle_feature calls
- Bricks: toggle_brick calls
- KA/VS: requires additional setup (document upload, VS index) - guide user to Setup tab or handle inline

Then re-deploy to apply.

Author mode: present each block as a choice point. User can skip, configure, or let Mage auto-fill.
