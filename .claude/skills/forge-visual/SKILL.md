# Agent Forge — Visual App

Graphical architecture explorer + interactive setup wizard for agent-forge.
Two processes: Express backend (9001) + Vite frontend (9000).

## Launch

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge/visual
bash start.sh
```

Opens at **http://localhost:9000**. `start.sh` installs node_modules on first run then starts both processes. Ctrl+C kills both.

**Restart backend only** (after editing `backend/index.js`):
```bash
lsof -ti:9001 | xargs kill -9 2>/dev/null
cd /Users/mehdi.lamrani/code/code/agent-forge/visual && node backend/index.js >> /tmp/visual-backend.log 2>&1 &
sleep 1 && curl -s http://localhost:9001/health
```

**Manual two-terminal start:**
```bash
# Terminal 1
cd /Users/mehdi.lamrani/code/code/agent-forge/visual/backend && node index.js

# Terminal 2
cd /Users/mehdi.lamrani/code/code/agent-forge/visual/frontend && npx vite --port 9000
```

---

## Directory Structure

```
visual/
├── start.sh                  # Main launch script (both processes)
├── graph-layout.json         # Persisted node drag positions
├── backend/
│   ├── index.js              # Express app — all API endpoints (~600 lines)
│   └── lib/graph-builder.js  # Parses app.yaml → builds node/edge graph
└── frontend/
    ├── vite.config.ts        # port 9000, proxy /api → :9001
    ├── tailwind.config.js    # darkMode: 'class', Geist font
    ├── src/
    │   ├── App.tsx           # Root: arch/setup views, dark mode toggle
    │   ├── types.ts          # All TypeScript types
    │   ├── setupSteps.ts     # Setup step definitions + choices
    │   ├── components/
    │   │   ├── ArchCanvas.tsx      # React Flow canvas, node drag → PUT /api/layout
    │   │   ├── Legend.tsx          # Node color/type legend
    │   │   ├── NodeDetailPanel.tsx # Right panel on node click
    │   │   ├── EnvEditor.tsx       # .env.local viewer/editor
    │   │   ├── SetupView.tsx       # Setup wizard root (phase state machine)
    │   │   ├── SetupDag.tsx        # DAG of 9 setup steps with status orbs
    │   │   └── SetupDrawer.tsx     # Drawer: choose → configure → execute → done
    │   └── nodeTypes/
    │       ├── index.ts      # Registry export
    │       ├── AgentNode.tsx
    │       ├── LlmNode.tsx
    │       ├── ToolNode.tsx
    │       ├── GenieNode.tsx
    │       └── DataNode.tsx
```

---

## Backend API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | `{ok:true}` |
| GET | `/api/graph` | Architecture graph from `app.yaml` + saved layout |
| PUT | `/api/layout` | Save node positions `{nodeId: {x,y}}` |
| GET | `/api/env` | List `.env.local` entries (sensitive keys masked) |
| PUT | `/api/env` | Update `.env.local` `{KEY: value}` |
| GET | `/api/setup/status` | Per-step config status from `.env.local` |
| GET | `/api/setup/profiles` | Databricks CLI profiles |
| GET | `/api/setup/resources?type=warehouses\|catalogs\|genie` | Live workspace resources via Python SDK |
| POST | `/api/setup/exec` | SSE stream — runs setup actions |
| GET | `/api/setup/test?step=<id>` | Live connection test per step |

**`/api/setup/exec` actions:**
`exec-pat`, `exec-assets`, `exec-mlflow`, `exec-grants`, `exec-genie`, `exec-same`,
`save-warehouse` (params: id, name), `save-schema` (params: catalog, schema), `save-genie` (params: id, name)

**`/api/setup/test` steps:**
`host`, `auth`, `warehouse`, `schema`, `model`, `genie`, `ka`, `mlflow`

---

## Setup Wizard — Step Reference

| Step | Env Key | Test |
|------|---------|------|
| host | `DATABRICKS_HOST` | HTTP GET /api/2.0/preview/scim/v2/Me |
| auth | `DATABRICKS_TOKEN` | SCIM Me endpoint with token |
| warehouse | `DATABRICKS_WAREHOUSE_ID` | SDK warehouses.get(id) |
| schema | `PROJECT_UNITY_CATALOG_SCHEMA` | SDK schemas.get(full_name) |
| model | `AGENT_MODEL_ENDPOINT` | POST test message to endpoint |
| genie | `PROJECT_GENIE_CHECKIN` | SDK genie.get_space(space_id) |
| ka | `PROJECT_KA_PASSENGERS` | SDK serving_endpoints.get(name) |
| mlflow | `MLFLOW_EXPERIMENT_ID` | SDK experiments.get_experiment(id) |
| grants | — | re-runnable, no test |

Setup phase flow: **choose → configure → execute → done**

The `configure` phase appears when the selected action is in:
`cfg-profile`, `cfg-warehouse`, `cfg-catalog`, `cfg-genie`, `cfg-grants`, `cfg-new`, `cfg-ka`, `manual`, `exec-genie`

---

## Key Config Files

| File | Location | Purpose |
|------|----------|---------|
| `.env.local` | Project root | All Databricks config — read at request time by backend |
| `app.yaml` | Project root | Agent manifest — parsed by graph-builder to build architecture view |
| `graph-layout.json` | `visual/` | Persisted node positions (auto-saved on drag) |

Backend loads `.env.local` from `../../.env.local` relative to `visual/backend/index.js`.

---

## Front-End Views

**Architecture tab** (`view === 'arch'`):
- React Flow canvas with 6 custom node types
- Node click → `NodeDetailPanel` (right side)
- Gear icon → `EnvEditor` overlay
- Drag nodes → debounced PUT `/api/layout` after 300 ms

**Setup tab** (`view === 'setup'`):
- Left: `SetupDag` — 9 step nodes, single column, flex fills height, status orbs (green=done, red=error, gray=missing)
- Right: `SetupDrawer` — 480px fixed, shows current env value in green + test button for configured steps

**Dark mode**: toggled by Moon/Sun button in nav; applies `dark` class to root div; full `dark:` coverage in Tailwind.

---

## Subprocess Execution

Backend runs Python via `uv run python -c <script>` for:
- Resource listing (warehouses, catalogs, genie spaces)
- Connection tests per step
- Setup actions (create assets, save to .env.local, run grants)

All subprocesses inherit env vars parsed from `.env.local` at call time.
Working directory for all subprocess calls: project root (`../../` from backend).

---

## Troubleshooting

**Backend port already in use:**
```bash
lsof -ti:9001 | xargs kill -9
```

**Frontend can't reach backend (HTML instead of JSON):**
Backend needs restart — the Vite proxy correctly targets `:9001` but the route may not exist in the running process.

**`test ↗` returns HTML error:**
Backend not running the latest code. Restart it.

**`uv` not found in subprocess:**
`uv` must be on PATH. Run `which uv` to confirm. If missing: `pip install uv` or `brew install uv`.

**graph-builder fails / empty architecture view:**
`app.yaml` is missing or malformed. Run `cat /Users/mehdi.lamrani/code/code/agent-forge/app.yaml` to inspect.

---

## Educational Docs

`/Users/mehdi.lamrani/code/code/agent-forge/edu/index.html`

Static HTML presentation (no server needed — open directly in browser):
```bash
open /Users/mehdi.lamrani/code/code/agent-forge/edu/index.html
```

Two tabs: **Databricks Platform** (11 slides — platform intro/sales deck) and **Getting Started** (13 slides — Agent Forge walkthrough).
