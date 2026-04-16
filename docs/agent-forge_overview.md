# Agent Forge — Overview

A **Databricks-native framework and accelerator** for building production-ready agentic AI solutions. Agent Forge bundles the scaffolding, patterns, and integrations Databricks builders need to go from zero to a deployed AI agent — without wiring everything from scratch.

The included reference application is a flight operations AI assistant: operators chat with an agent that monitors real-time flight risk, answers questions via Genie (natural language SQL), and takes operational actions directly on Databricks data.

---

## What it gives you

| Layer | What's included |
|---|---|
| **Agent** | LangGraph agent + LangChain tools wired to Claude via Databricks model serving |
| **Genie MCP** | Out-of-the-box Databricks Genie integration for natural language SQL |
| **Data layer** | Unity Catalog schema, Delta tables, stored procedures, SQL functions — all scripted |
| **Frontend** | React + Node.js chat app with streaming, table refresh blocks, Databricks auth |
| **Deployment** | Databricks Asset Bundle (DAB) pipeline from local dev to prod app |
| **Observability** | MLflow experiment tracking baked in from the start |

---

## Architecture at a glance

```
User (chat UI)
    |
    v
React frontend  [port 3000]
    |
    v
Node.js API / proxy  [port 3001]
    |
    v
MLflow AgentServer (FastAPI)  [port 8000]
    |
    +-- LangGraph agent
    |       |-- Tool: query_flights_at_risk  --> Databricks SQL Warehouse
    |       |-- Tool: update_flight_risk     --> Stored procedure (UC)
    |       +-- Genie MCP                   --> Databricks Genie space (NL SQL)
    |
    +-- Claude model endpoint (Databricks serving / cross-workspace)
```

---

## Key components

### `agent/`
Core backend application.

| File | Role |
|---|---|
| `agent.py` | Initializes LangGraph agent — model, tools, Genie MCP client |
| `start_server.py` | Wraps agent in MLflow AgentServer; exposes `/invocations` + `/tables/flights` |
| `genie_capture.py` | Intercepts Genie MCP calls and logs the generated SQL for audit/debug |
| `utils.py` | Streaming helpers, Databricks auth, workspace client setup |

### `tools/`
LangChain `@tool`-decorated functions the agent can call.

| Tool | What it does |
|---|---|
| `query_flights_at_risk` | Queries flights checking in through a zone within a time window |
| `update_flight_risk` | Calls stored procedure to mark a flight AT_RISK or NORMAL |
| `sql_executor.py` | Shared Databricks SQL execution utility |

### `data/`
Everything needed to stand up the data layer from scratch.

| Directory | Contents |
|---|---|
| `init/` | One-time setup: catalog/schema, flights table, Genie space, functions, procedures, MLflow experiment |
| `csv/` | Seed data (`flights.csv`) |
| `func/` | SQL query templates used by agent tools |
| `proc/` | Stored procedure definitions |
| `py/` | Low-level SQL runners, CSV-to-Delta loader |

### `prompt/`
| File | Purpose |
|---|---|
| `main.prompt` | Agent system prompt (ops advisor role and behavior) |
| `knowledge.base` | Operational FAQ injected as knowledge blocks |
| `user.prompt` | Starter user-facing prompts |

### `e2e-chatbot-app-next/`
Full-stack chat application (npm monorepo).

| Package | Role |
|---|---|
| `client/` | React + Vite frontend — chat UI, streaming, table refresh |
| `server/` | Express.js backend — proxies agent, handles Databricks auth |
| `packages/core` | Domain types and errors |
| `packages/auth` | Authentication utilities |
| `packages/ai-sdk-providers` | Databricks AI SDK integration |
| `packages/db` | Drizzle ORM + Lakebase schema for optional chat history |

### `scripts/`
| Script | Purpose |
|---|---|
| `setup_dbx_env.py` | Interactive setup — configures and verifies all Databricks resources |
| `start_local.sh` | Starts full local dev stack (backend + Node API + frontend) |

### `deploy/`
| File | Purpose |
|---|---|
| `deploy.sh` | Full deployment orchestrator (validate → bundle deploy → run) |
| `sync_databricks_yml_from_env.py` | Syncs `.env.local` values into `databricks.yml` bundle config |
| `grant/` | UC + SQL warehouse + endpoint permission scripts |

### `visual/`
Architecture visualization tool (React Flow + GraphQL) for exploring the agent graph interactively.

---

## Tech stack

| Area | Technology |
|---|---|
| Agent framework | LangChain / LangGraph + MLflow AgentServer |
| Model | Claude via Databricks model serving endpoint (cross-workspace capable) |
| MCP integration | Databricks Genie MCP |
| Data platform | Databricks Unity Catalog, Delta Lake, SQL Warehouse, Lakebase |
| Backend | Python 3.11+, FastAPI (via MLflow) |
| Frontend | React 18, TypeScript, Vite, Vercel AI SDK |
| API layer | Express.js 5 |
| ORM | Drizzle ORM (PostgreSQL / Lakebase) |
| Deployment | Databricks Asset Bundle (DAB) |
| Observability | MLflow (experiment tracking, run logging) |
| Testing | Playwright (E2E), MSW (mocking) |

---

## Typical workflow

### 1. Initialize
```bash
python scripts/setup_dbx_env.py   # configure .env.local, verify resources
python data/init/create_all_assets.py  # create UC schema, tables, Genie space, functions, procedures
```

### 2. Develop locally
```bash
bash scripts/start_local.sh            # boots backend (8000) + Node API (3001) + frontend (3000)
```

### 3. Deploy to Databricks
```bash
python deploy/sync_databricks_yml_from_env.py   # sync env → bundle config
databricks bundle deploy                         # deploy app + resources
databricks bundle run databricks_chatbot         # start app
```

---

## Adapting for your use case

Agent Forge is a template. To build your own agent:

1. **Swap the domain** — replace `flights.csv`, the flights table, and Genie space with your data
2. **Add or replace tools** — drop new `@tool` functions in `tools/` and register them in `agent/agent.py`
3. **Update prompts** — edit `prompt/main.prompt` and `prompt/knowledge.base` for your domain
4. **Extend the data layer** — add SQL functions/procedures in `data/func/` and `data/proc/`
5. **Customize the UI** — the chat app is a generic streaming UI; extend as needed

All infrastructure (DAB, MLflow, UC schema) is config-driven via `.env.local` and `databricks.yml`.

---

## Related docs

| File | Contents |
|---|---|
| `docs/Build & setup flow.md` | Step-by-step initialization flow with folder map |
| `e2e-chatbot-app-next/README.md` | Chat app setup, deployment, testing |
| `e2e-chatbot-app-next/CLAUDE.md` | Claude Code context, commands, conventions for the frontend |
| `.env.example` | All environment variable definitions |
