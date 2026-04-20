## Build & setup flow

### Entry point: `run`

```
./run install          # one-time: add repo root to PATH
./run setup            # configure .env.local and verify Databricks resources
./run deploy           # full deploy pipeline (validate → bundle deploy → run → grants)
./run reset-workspace  # tear down workspace resources, keep catalog + KA
```

---

### `scripts/`
| Script | Description |
|---|---|
| `setup_dbx_env.sh` / `setup_dbx_env.py` | Interactive setup — configure env vars, verify all Databricks resources; warns on FM workspace flavor mismatch (Azure vs AWS) |
| `start_local.sh` | Boot backend (8000) + Node API (3001) + frontend (3000) locally |
| `reset_workspace.py` | Delete workspace resources (Genie space, tables, procs, functions, MLflow experiment); keeps Unity Catalog and Knowledge Assistants |
| `ka/create_kas_from_yml.py` | Create Knowledge Assistants from `config/ka/` YAML files; writes `PROJECT_KA_<SLUG>` to `.env.local` on ACTIVE |

↓

### `data/`
| Directory | Description |
|---|---|
| `csv/` | Raw seed data (auto-discovered by `create_all_assets.py`) |
| `init/` | Create schema, tables, Genie space, functions, procedures — *run once* |
| `proc/` | Stored procedure definitions |
| `func/` | SQL query templates (used by tools) |
| `py/` | Low-level SQL runners & CSV-to-Delta loader |

`create_all_assets.py` scans `csv/*.csv` and runs the matching `init/create_<name>.sql` — no script edits needed to add a table.

↓

### `tools/`
| Tool | Description |
|---|---|
| `query_flights_at_risk` | Reads `func/` SQL, hits SQL warehouse |
| `update_flight_risk` | Calls stored procedure via UC |
| KA tools (optional) | HTTP POST to Knowledge Assistant serving endpoints |

New tools: use `.claude/skills/forge-add-tool` (SQL read, action, or KA patterns).

↓

### `agent/`
| File | Description |
|---|---|
| `agent.py` | Wires tools + model + Genie MCP; tool list at `~line 58` |
| `start_server.py` | Exposes agent + table endpoints via MLflow AgentServer |
| `prompt/` | System prompt + knowledge base + user starters |

↓

### `e2e-chatbot-app-next/`
| Layer | Description |
|---|---|
| `client/` | React + Vite frontend (built **remotely at app startup** — not pre-built) |
| `server/` | Express.js backend — proxies agent, handles Databricks auth |
| `app.yaml` | Startup: `npm install && npm run build:client && npm run start` |

`.databricksignore` excludes `client/dist/` from DAB upload — the remote build produces it fresh on each startup.

↓

### `deploy/`
| File | Description |
|---|---|
| `sync_databricks_yml_from_env.py` | Writes `.env.local` values into `databricks.yml` bundle config |
| `grant/` | UC + warehouse + endpoint permission scripts |
| `deploy.sh` | Full pipeline: env check → config sync → Python import check → bundle validate → workspace-change detection → bundle deploy → bind app → run → grants |

Workspace-change detection: compares `.databricks/bundle/default/sync-snapshots/*.json` host field against `DATABRICKS_HOST`. Clears stale state automatically when switching workspaces.
