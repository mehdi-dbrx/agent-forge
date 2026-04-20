# Agent Forge — Overview

A **Databricks-native framework and accelerator** for building production-ready agentic AI solutions. Agent Forge bundles the scaffolding, patterns, and integrations Databricks builders need to go from zero to a deployed AI agent — without wiring everything from scratch.

The framework ships with two reference applications:
- **Flight operations AI assistant** — operators chat with an agent that monitors real-time flight risk, queries data via Genie MCP, and takes operational actions on Databricks
- **EU Passenger Rights Knowledge Assistant** — a YAML-configured KA backed by regulatory PDFs, with a full MLflow evaluation pipeline for testing and improving answer quality

---

## What it gives you

| Layer | What's included |
|---|---|
| **Agent** | LangGraph agent + LangChain tools wired to Claude via Databricks model serving |
| **Genie MCP** | Out-of-the-box Databricks Genie integration for natural language SQL |
| **Data layer** | Unity Catalog schema, Delta tables, stored procedures, SQL functions — all scripted |
| **Frontend** | React + Node.js chat app with streaming, table refresh blocks, Databricks auth |
| **Knowledge Assistants** | YAML-driven KA configs with PDF knowledge sources and shared output formatting |
| **Evaluation** | MLflow GenAI eval pipeline with custom LLM judge scorers and two-run comparison |
| **Deployment** | Databricks Asset Bundle (DAB) pipeline from local dev to prod app — client built remotely at startup |
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
| `sql_executor.py` | Shared Databricks SQL execution utility (warehouse, query, format helpers) |

New tools follow two patterns: **SQL read** (query warehouse via `data/func/` SQL template) or **action** (call stored procedure via `data/proc/`). KA tools use a third pattern — HTTP POST to a Knowledge Assistant serving endpoint. See `.claude/skills/forge-add-tool/SKILL.md` for the full guide.

### `data/`
Everything needed to stand up the data layer from scratch.

| Directory | Contents |
|---|---|
| `init/` | One-time setup: catalog/schema, flights table, Genie space, functions, procedures, MLflow experiment |
| `csv/` | Seed data (`flights.csv` and any additional synthetic datasets) |
| `func/` | SQL query templates used by agent tools |
| `proc/` | Stored procedure definitions |
| `py/` | Low-level SQL runners, CSV-to-Delta loader |
| `pdf/` | Source documents for Knowledge Assistants (e.g. EU regulation EC 261/2004) |

`create_all_assets.py` auto-discovers CSV files and matching `create_<name>.sql` files — adding both files is all that's needed to provision a new table.

### `prompt/`
| File | Purpose |
|---|---|
| `main.prompt` | Agent system prompt (ops advisor role and behavior) |
| `knowledge.base` | Operational FAQ injected as knowledge blocks |
| `user.prompt` | Starter user-facing prompts |

### `e2e-chatbot-app-next/`
Full-stack chat application (npm monorepo). The React client is **built remotely at app startup** (`npm install && npm run build:client && npm run start`) — no pre-built dist is committed or uploaded.

| Package | Role |
|---|---|
| `client/` | React + Vite frontend — chat UI, streaming, table refresh |
| `server/` | Express.js backend — proxies agent, handles Databricks auth |
| `packages/core` | Domain types and errors |
| `packages/auth` | Authentication utilities |
| `packages/ai-sdk-providers` | Databricks AI SDK integration |
| `packages/db` | Drizzle ORM + Lakebase schema for optional chat history |

### `config/`
Configuration files shared across the framework.

| Path | Contents |
|---|---|
| `config/ka/ka_passengers.yml` | KA definition: display name, instructions, examples for EU passenger rights |
| `config/ka/output_format.yml` | Shared output schema — JSON with answer + verbatim source excerpts |
| `config/.env.example` | Environment variable reference template |

### `scripts/`
| Script | Purpose |
|---|---|
| `setup_dbx_env.py` / `setup_dbx_env.sh` | Interactive setup — configures and verifies all Databricks resources; warns on FM workspace flavor mismatch |
| `start_local.sh` | Starts full local dev stack (backend + Node API + frontend) |
| `reset_workspace.py` / `reset_workspace.sh` | Deletes workspace resources (Genie space, tables, procedures, functions, MLflow experiment) while keeping Unity Catalog and Knowledge Assistants |
| `create_eval_dataset.py` | Pushes the EC 261/2004 eval dataset to Databricks MLflow |

### `scripts/ka/`
Utilities for creating and managing Databricks Knowledge Assistants.

| Script | Purpose |
|---|---|
| `create_kas_from_yml.py` | Creates KAs from `config/ka/` YAML files; waits for ACTIVE; writes `PROJECT_KA_<SLUG>` to `.env.local` |
| `ka_instructions_merger.py` | Merges shared output format with KA-specific instructions |
| `upload_pdfs.py` | Uploads PDF files to Databricks Volumes |
| `create_volume.py` | Creates UC Volumes for storing KA source documents |
| `list_ka_states.py` | Lists KA deployment states |
| `delete_kas_by_display_name.py` | Deletes KAs by name |

### `deploy/`
| File | Purpose |
|---|---|
| `deploy.sh` | Full deployment orchestrator (env check → config sync → validate → bundle deploy → run → grants) |
| `sync_databricks_yml_from_env.py` | Syncs `.env.local` values into `databricks.yml` bundle config |
| `grant/` | UC + SQL warehouse + endpoint permission scripts |

Workspace-change detection: if the sync-snapshot host in `.databricks/bundle/default/sync-snapshots/` differs from `DATABRICKS_HOST`, stale bundle state is cleared automatically before deploy.

### `eval/`
MLflow GenAI evaluation pipeline for Knowledge Assistants.

| File | Purpose |
|---|---|
| `run_eval.py` | Orchestrates two-run workflow: baseline → with guideline → compare in MLflow |
| `predict.py` | Calls KA endpoint via HTTP, handles retries, extracts responses |
| `scorer.py` | Custom MLflow scorer (`cites_regulation_precisely`) — uses Claude as LLM judge |
| `eval_dataset.py` | 13 curated EC 261/2004 test questions covering edge cases |
| `data/ec261_eval_dataset.jsonl` | JSONL source of truth for all eval questions |

The two-run pattern lets you measure the impact of prompt/guideline changes objectively before pushing to production.

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
| Evaluation | MLflow GenAI eval + custom LLM judge (Claude) |
| Knowledge Assistants | Databricks Knowledge Assistants (YAML-configured, PDF-backed) |
| Testing | Playwright (E2E), MSW (mocking) |

---

## Typical workflow

### 0. One-time install
```bash
./run install    # adds repo root to PATH so you can call `run` from anywhere
```

### 1. Initialize
```bash
./run setup                                    # configure .env.local, verify resources
uv run python data/init/create_all_assets.py   # create UC schema, tables, Genie space, functions, procedures
```

### 2. Develop locally
```bash
bash scripts/start_local.sh    # boots backend (8000) + Node API (3001) + frontend (3000)
```

### 3. Deploy to Databricks
```bash
./run deploy                   # full pipeline: validate → sync → bundle deploy → run → grants
# or with dry-run first:
./run deploy --dry-run
```

The deployed app builds the React client at startup — no pre-build step needed.

### 4. Reset workspace (teardown without losing catalog / KA)
```bash
./run reset-workspace          # drops tables, procedures, functions, Genie space, MLflow experiment
```

---

## `run` command reference

| Command | What it does |
|---|---|
| `./run install` | Adds repo root to PATH in shell config (run once after cloning) |
| `./run setup` | Interactive Databricks env setup (`scripts/setup_dbx_env.sh`) |
| `./run deploy [--dry-run]` | Full deploy pipeline (`deploy/deploy.sh`) |
| `./run reset-workspace` | Delete workspace resources, keep UC catalog + KA (`scripts/reset_workspace.py`) |

---

## Forge skills (Claude Code)

Agent Forge ships Claude Code skills under `.claude/skills/` that guide you through common extension tasks:

| Skill | Trigger |
|---|---|
| `forge-add-tool` | Add a new agent tool (SQL read, action, or KA) |
| `forge-add-data` | Add a new synthetic dataset + Delta table |
| `forge-add-ka` | Create and deploy a new Knowledge Assistant |
| `dbx-ka` | General KA creation workflow |
| `dbx-eval` | Run the MLflow evaluation pipeline |

---

## Adapting for your use case

Agent Forge is a template. To build your own agent:

1. **Swap the domain** — replace `flights.csv`, the flights table, and Genie space with your data
2. **Add or replace tools** — use the `forge-add-tool` skill or drop new `@tool` functions in `tools/` and register them in `agent/agent.py`
3. **Update prompts** — edit `prompt/main.prompt` and `prompt/knowledge.base` for your domain
4. **Extend the data layer** — use the `forge-add-data` skill or add SQL functions/procedures in `data/func/` and `data/proc/`
5. **Customize the UI** — the chat app is a generic streaming UI; extend as needed
6. **Add a Knowledge Assistant** — use the `forge-add-ka` skill: create a YAML in `config/ka/`, upload PDFs via `scripts/ka/`, run `create_kas_from_yml.py`
7. **Wire a KA as an agent tool** — use the `forge-add-tool` skill (KA tool pattern) to call a KA endpoint from the agent
8. **Evaluate and improve** — write test questions in `eval/data/`, run `eval/run_eval.py` to compare runs in MLflow

All infrastructure (DAB, MLflow, UC schema) is config-driven via `.env.local` and `databricks.yml`.

---

## Related docs

| File | Contents |
|---|---|
| `docs/Build & setup flow.md` | Step-by-step initialization flow with folder map |
| `e2e-chatbot-app-next/README.md` | Chat app setup, deployment, testing |
| `e2e-chatbot-app-next/CLAUDE.md` | Claude Code context, commands, conventions for the frontend |
| `config/.env.example` | All environment variable definitions |
| `config/ka/ka_passengers.yml` | Example KA configuration (EU passenger rights) |
