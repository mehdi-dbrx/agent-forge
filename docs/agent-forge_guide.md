# Agent Forge — What You Can Do With It

A practical guide to Agent Forge: what the app is, what it delivers, and how to extend it.

---

## From a user's perspective

Agent Forge ships a **production-ready agentic Databricks application** you can interact with from day one.

### The chat interface

The app is a streaming chat UI running on Databricks Apps. You open a browser, authenticate, and talk to an AI agent in natural language. The agent understands your domain, uses live data, and takes actions — not just answering questions.

What the agent can do out of the box (flight operations reference app):

- **Query live data** — "Which flights are at risk in terminal 2 in the next 90 minutes?" — the agent pulls from Unity Catalog via SQL warehouse.
- **Explore your data with natural language** — Genie MCP lets the agent turn free-form questions into SQL without you writing a query. Ask anything about your tables.
- **Take operational actions** — "Mark flight BA312 as AT_RISK" — the agent calls a stored procedure and confirms the change.
- **Answer policy and regulatory questions** — the Knowledge Assistant answers questions grounded in your documents (e.g. EU passenger rights regulation), citing sources verbatim.

### The dashboard

The chat UI includes a live data panel that refreshes as the agent acts. You see flight risk status update in real time — no page reload, no manual refresh. The agent and the dashboard are in sync.

### What it feels like

You describe a situation. The agent figures out what tools to use, fetches data, optionally takes action, and explains what it did — in plain language, with sources when it cites documents. It is not a chatbot wrapper around a search index. It is an agent with real capabilities on real Databricks infrastructure.

---

## From an agentic app builder's perspective

Agent Forge is a **framework and accelerator**. The flight ops app is the reference — your job is to swap in your domain.

### Automated workspace setup

One command configures everything from scratch in a fresh Databricks workspace:

```bash
./run setup
```

This interactive script:
- Detects or prompts for your Databricks host, warehouse, model endpoint, Unity Catalog schema
- Validates that each resource actually exists and is reachable
- Warns you if your FM workspace flavor (Azure vs AWS) does not match your fevm, which would cause IP ACL blocks
- Writes `.env.local` with all required vars
- Optionally configures cross-workspace model endpoints, Genie spaces, KA endpoints, MLflow experiment IDs, and secret scopes

After setup, provision the full data layer in one more command:

```bash
uv run python data/init/create_all_assets.py
```

This creates: Unity Catalog schema, Delta tables, stored procedures, SQL functions, Genie space, MLflow experiment — everything the agent needs to run.

### Automated deployment

```bash
./run deploy
```

This runs the full deployment pipeline without manual steps:

1. Loads and validates `.env.local`
2. Syncs env vars into `databricks.yml` (no manual YAML editing)
3. Checks for PLACEHOLDER values — aborts if any remain
4. Validates Python imports and bundle config
5. Detects workspace changes — clears stale DAB state automatically if you switched workspaces
6. Binds or creates the Databricks App
7. Deploys the bundle
8. Grants UC table access, SQL warehouse access, and secret scope access to the app service principal

The React frontend is **built remotely at app startup** (`npm install && npm run build:client && npm run start`) — you never need to pre-build or commit compiled assets. First startup after a deploy takes ~1-2 min for the client build; subsequent restarts are fast.

### Add your own data

Use the `forge-add-data` skill (or follow the pattern manually):

1. Drop a CSV in `data/csv/<table_name>.csv`
2. Write a DDL file at `data/init/create_<table_name>.sql` (use `__SCHEMA_QUALIFIED__` placeholder)
3. Run `uv run python data/py/run_sql.py data/init/create_<table_name>.sql`

`create_all_assets.py` auto-discovers both files — no script modification needed. The Genie space picks up new tables on its next run.

### Add your own tools

Use the `forge-add-tool` skill. Three patterns are supported:

| Pattern | When to use |
|---|---|
| **SQL read** | Query a warehouse via a SQL template in `data/func/` |
| **Action** | Call a stored procedure in `data/proc/` |
| **KA** | HTTP POST to a Knowledge Assistant endpoint, extract answer |

Each tool is one `@tool`-decorated function in `tools/<tool_name>.py`. Register it in `agent/agent.py` with one import and one list entry.

### Add a Knowledge Assistant

Use the `forge-add-ka` skill:

1. Write `config/ka/ka_<slug>.yml` — display name, instructions, knowledge sources (PDF files in a UC Volume)
2. Dry-run validate: `uv run python scripts/py/ka/create_kas_from_yml.py config/ka/ka_<slug>.yml --dry-run`
3. Deploy and wait for ACTIVE: `uv run python scripts/py/ka/create_kas_from_yml.py config/ka/ka_<slug>.yml`
4. The endpoint is written to `.env.local` automatically as `PROJECT_KA_<SLUG>`
5. Wire it as an agent tool using the KA tool pattern in `forge-add-tool`

### Evaluate and improve

The MLflow eval pipeline (`eval/`) lets you measure answer quality objectively:

- A curated test dataset of questions is scored by a custom LLM judge (`cites_regulation_precisely`)
- Two-run workflow: baseline run → change KA guideline → second run → compare in MLflow UI
- Use `./run` + `dbx-eval` skill to walk through the full flow

### Reset and iterate

```bash
./run reset-workspace
```

Drops tables, stored procedures, functions, Genie space, and MLflow experiment — without touching Unity Catalog or Knowledge Assistants. Use this to start fresh in the same workspace.

---

## Command reference

| Command | What it does |
|---|---|
| `./run install` | Add repo root to PATH (run once after cloning) |
| `./run setup` | Interactive Databricks env setup |
| `./run deploy [--dry-run]` | Full deploy pipeline |
| `./run reset-workspace` | Delete workspace resources, keep catalog + KA |
| `bash scripts/sh/start_local.sh` | Start full local dev stack (ports 8000 / 3001 / 3000) |
| `uv run python data/init/create_all_assets.py` | Provision all data layer resources |

---

## Claude Code skills

| Skill | What it does |
|---|---|
| `/forge-manual` | Load docs into context and recap what Agent Forge can do |
| `/forge-add-tool` | Guide: create and register a new agent tool |
| `/forge-add-data` | Guide: add a synthetic dataset + Delta table |
| `/forge-add-ka` | Guide: create and deploy a Knowledge Assistant |
| `/dbx-eval` | Guide: run the MLflow evaluation pipeline |

---

## Further reading

| File | Contents |
|---|---|
| `docs/agent-forge_overview.md` | Full component-by-component reference |
| `docs/Build & setup flow.md` | Layered build and setup flow diagram |
| `config/.env.example` | All environment variable definitions |
| `config/ka/ka_passengers.yml` | Example KA configuration |
| `e2e-chatbot-app-next/CLAUDE.md` | Frontend conventions and commands |
