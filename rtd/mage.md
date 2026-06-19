# Mage

**Your AI agent that builds AI agents.**

Mage is a conversational assistant inside BrickForge. Describe what you need in plain English, and Mage designs the data model, generates tables and functions, writes the system prompt, and deploys a live agent -- all through chat.

---

## Two modes

### Magic Mode

For non-technical users. Say what your agent should do. Mage handles everything silently.

> **You:** "I need an agent for my pet hotel. Bookings, room availability, check-in/check-out."
>
> **Mage:** Setting up your data home... Teaching your agent new tricks... Launching into orbit.
>
> **Mage:** Your agent is live at `https://your-workspace.cloud.databricks.com/apps/pet-hotel`

You describe the domain. Mage:

1. Creates a project
2. Connects your workspace
3. Discovers the best available model
4. Designs a data model (tables, columns, relationships)
5. Generates synthetic data + UC functions + stored procedures
6. Writes a system prompt and knowledge base
7. Deploys to Databricks Apps with auto-grants

No tables, no jargon, no tech details shown. Just progress updates and a live URL at the end.

### Author Mode

For technical users. Mage shows the full spec -- tables, columns, functions, params, lifecycle. You review, adjust, and approve at every step.

> **Mage:** Here's the data model I'd recommend: 4 tables (rooms, bookings, guests, services), 6 UC functions...
>
> **You:** "Add a loyalty_points column to guests. And a check_loyalty function."
>
> **Mage:** Updated. Ready to generate?

Same pipeline, full visibility. Every choice is yours.

---

## How Mage works

### Startup sequence

1. You type a description on the Mage hero screen and pick Magic or Author mode
2. Mage creates a project (or loads an existing one)
3. Mage auto-connects the workspace from your current config
4. Mage auto-detects the best Foundation Model (prefers Claude Sonnet)

No model available = Mage is unavailable. No degraded mode.

### Discovery phase

Mage uses a 7-point framework to understand your domain:

1. **Who** is the end user?
2. **What's their first interaction** with the agent?
3. **New vs returning** -- does the agent need onboarding logic?
4. **Core actions** -- 3-5 verbs (book, check-in, cancel...)
5. **Entities** -- nouns (rooms, guests, bookings...)
6. **Identifiers** -- how humans refer to things (name, not ID)
7. **Lifecycle** -- create, use, modify, close

During discovery, Mage only has read-only tools. It cannot call generate or deploy endpoints.

### Self-critique

Before presenting the spec, Mage runs an internal critique:

> "Simulate the first real interaction. Day one, empty database, new user. What breaks?"

If gaps are found, Mage patches them before showing you anything. This catches missing onboarding flows, identity lookup issues, and dead-end conversations.

### Build phase

After you confirm the spec, Mage unlocks the full tool set:

- **Tables**: schema generation, per-table data gen, per-table save, provision
- **Routines**: routine schema, per-routine SQL gen, per-routine save, provision
- **Prompts**: generate and save
- **Deploy**: bundle, upload, create app, auto-grants

Each step streams progress to the chat via SSE. In Magic mode, you see friendly labels ("Teaching your agent new tricks"). In Author mode, you see tool calls and detailed output.

---

## Architecture

Mage reuses the existing BrickForge backend. It calls the same FastAPI endpoints the visual Setup Panel uses -- via `httpx` on localhost. No separate agent runtime, no duplicate logic.

```
MageView (React)
    |
    POST /api/mage/chat (SSE)
    |
    mage_agent.py (custom tool loop)
    |
    httpx -> setup.py, gen.py, projects.py (existing endpoints)
```

### Phased tool binding

- **Discovery phase**: 11 read-only tools (list warehouses, list schemas, get status, etc.)
- **Build phase**: 19 tools (all read tools + generate, provision, deploy, etc.)

This prevents the LLM from calling generate or deploy during the discovery conversation.

### SSE events

| Event | Purpose | Magic | Author |
|-------|---------|-------|--------|
| `message` | Chat text | Shown | Shown |
| `progress` | Terminal output | Collapsible | Collapsible |
| `tool_call` | Tool invocation | Hidden | Shown |
| `thinking` | Processing indicator | Dots | Dots |
| `step` | Stepper update | Shown | Shown |
| `error` | Error with suggestion | Shown | Shown |
| `done` | Final state + URL | Shown | Shown |

---

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/mage/chat` | POST | Send message, receive SSE stream |
| `/api/mage/status` | GET | Get current session state |
| `/api/mage/reset` | POST | Reset session for fresh start |

---

## Files

| File | Purpose |
|------|---------|
| `brickforge/lib/mage_agent.py` | Agent loop, system prompt, self-critique, phased tools |
| `brickforge/lib/mage_tools.py` | 19 tools with SSE streaming wrappers |
| `brickforge/lib/mage_llm.py` | FMAPI model auto-detect + ChatDatabricks client |
| `brickforge/routes/mage.py` | Startup sequence + SSE chat endpoint |
| `visual/frontend/src/components/MageView.tsx` | Chat UI with hero, mode toggle, stepper |
