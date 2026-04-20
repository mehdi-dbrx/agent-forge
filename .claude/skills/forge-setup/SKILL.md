---
name: forge-setup
description: Entry point for Agent Forge setup. Runs state check, presents [+]/[x]/[-] summary, and guides step by step through the full configuration flow. Claude does all the work — no terminal needed. Triggered when user says /forge-setup, "start setup", "setup forge", "walk me through setup", "what step am I on", or wants to configure agent-forge from scratch.
---

# Agent Forge — Setup Orchestrator

Entry point. Claude discovers the current state, presents a summary, and guides through each step interactively — no terminal commands for the user.

## What to do when this skill is invoked

### 1. Load current state (run in parallel)

```bash
grep -E "^(DATABRICKS_HOST|DATABRICKS_TOKEN|DATABRICKS_WAREHOUSE_ID|PROJECT_UNITY_CATALOG_SCHEMA|PROJECT_GENIE_CHECKIN|PROJECT_KA_PASSENGERS|MLFLOW_EXPERIMENT_ID|AGENT_MODEL_ENDPOINT|DBX_APP_NAME|ENV_STORE_CATALOG_VOLUME_PATH)=" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null
```

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python scripts/py/setup_dbx_env.py --check 2>&1
```

Run both in parallel.

### 2. Classify each step

Map `--check` output sections to step names. Classify each as:
- `[+]` — configured AND verified (all checks in that section passed)
- `[x]` — configured but failing (check ran but reported errors)
- `[-]` — not configured (env var missing from .env.local)

### 3. Present summary

```
Agent Forge — Setup Status

[+]  host          https://fevm-agent-forge.cloud.databricks.com
[+]  auth          token (mehdi.lamrani@...)
[+]  warehouse     8ba51d8cad2a3d9a
[+]  schema        agent_forge_catalog.main
[x]  tables        checkin_agents missing
[-]  functions     (not configured)
[-]  procedures    (not configured)
[+]  genie         01f139de... (Checkin Metrics)
[+]  ka            ka-087003b9-endpoint (ACTIVE)
[+]  mlflow        3688767017703470
[+]  model         cross-workspace (e2-demo-field-eng)
[-]  model-test    (not run yet)
[+]  app-name      agent-vibe-app-no-dist
[-]  env-store     (optional, not configured)

Suggested next step: /forge-setup-tables  (tables missing)
```

### 4. Ask user

"Where would you like to start? Type a step name, 'next' to continue from the first issue, or 'all good' if done."

### 5. Guide

- "next" or "continue" → immediately execute the flow for the first `[x]` or `[-]` step (using the step's skill instructions)
- Step name (e.g. "tables", "model", "host") → execute that step's flow
- Step number (1–14) → execute that step's flow
- "all good" / "done" → confirm and stop
- "check" → re-run `--check` and refresh the summary

**Important:** After each step completes, re-read `.env.local` and re-run `--check`, then update the summary and suggest the next step automatically. Keep the flow going until the user stops or everything is [+].

### Step reference

| # | Step | Env var / resource |
|---|------|--------------------|
| 1 | host | DATABRICKS_HOST |
| 2 | auth | DATABRICKS_TOKEN / CLI profile |
| 3 | warehouse | DATABRICKS_WAREHOUSE_ID |
| 4 | schema | PROJECT_UNITY_CATALOG_SCHEMA |
| 5 | tables | Delta tables |
| 6 | functions | UC functions (data/func/) |
| 7 | procedures | UC procedures (data/proc/) |
| 8 | genie | PROJECT_GENIE_CHECKIN |
| 9 | ka | Knowledge Assistants |
| 10 | mlflow | MLFLOW_EXPERIMENT_ID |
| 11 | model | AGENT_MODEL_ENDPOINT + TOKEN |
| 12 | model-test | Foundation model connection test |
| 13 | app-name | DBX_APP_NAME |
| 14 | env-store | Env Store (optional) |

Each step's skill (`/forge-setup-{step}`) contains the full interactive flow — Claude runs commands, presents choices, takes input, writes to .env.local. Embed that flow directly rather than just naming the skill.
