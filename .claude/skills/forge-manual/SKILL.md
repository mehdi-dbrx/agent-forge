---
name: forge-manual
description: Load Agent Forge documentation into context and recap what the project can do. Triggered when the user asks what Agent Forge is, what it can do, how to get started, or wants an overview of the project.
---

# Agent Forge — Manual

Loads the project docs into context so you have a full picture of what Agent Forge is and what it can do.

## What to do when this skill is invoked

1. Read the following files using the Read tool (in parallel):
   - `/Users/mehdi.lamrani/code/code/agent-forge/docs/agent-forge_guide.md`
   - `/Users/mehdi.lamrani/code/code/agent-forge/docs/agent-forge_overview.md`
   - `/Users/mehdi.lamrani/code/code/agent-forge/docs/Build & setup flow.md`

2. After reading, provide a structured recap covering:

### What the app is — user perspective
- A streaming chat UI on Databricks Apps
- An AI agent (LangGraph + Claude) that queries live data, explores it via Genie MCP (natural language SQL), takes operational actions via stored procedures, and answers document-grounded questions via Knowledge Assistants
- A live dashboard panel that reflects agent actions in real time
- Databricks-native auth — users just open the URL

### What the framework gives a builder
- **Automated setup**: `./run setup` configures `.env.local` and validates all Databricks resources from scratch; `data/init/create_all_assets.py` provisions the full data layer (UC schema, tables, procedures, functions, Genie space, MLflow experiment)
- **Automated deployment**: `./run deploy` runs the full pipeline end-to-end — env sync, bundle validate, workspace-change detection, deploy, bind app, run, grants. The React frontend builds remotely at app startup.
- **Add data**: drop a CSV + SQL file → auto-discovered by `create_all_assets.py`
- **Add tools**: SQL read, action (stored procedure), or KA (Knowledge Assistant HTTP) patterns — one file, one import, one list entry
- **Add Knowledge Assistants**: YAML config → PDF docs in UC Volume → `create_kas_from_yml.py` → endpoint auto-written to `.env.local`
- **Evaluate**: MLflow two-run eval pipeline with custom LLM judge
- **Reset**: `./run reset-workspace` tears down workspace resources without touching the catalog or KAs

### Key commands
```
./run install          # one-time PATH setup
./run setup            # interactive env setup
./run deploy           # full deploy pipeline
./run reset-workspace  # reset without losing catalog/KA
bash scripts/start_local.sh              # local dev (ports 8000/3001/3000)
uv run python data/init/create_all_assets.py  # provision data layer
```

### Available Claude Code skills
- `/forge-add-tool` — add a new agent tool
- `/forge-add-data` — add a dataset + Delta table
- `/forge-add-ka` — create a Knowledge Assistant
- `/dbx-eval` — run the MLflow evaluation

3. After the recap, ask: "What would you like to do?" and suggest the most relevant next skill based on the conversation context.
