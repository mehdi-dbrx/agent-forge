---
name: forge-setup-check
description: Full environment status check. Claude runs --check, parses output, presents clean [+]/[x] summary, offers to fix or create missing resources. No terminal needed.
---

# Agent Forge — Setup: check

Runs a full verification pass of all configured resources and presents a clean summary.

## Flow

### 1. Run the check

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python scripts/py/setup_dbx_env.py --check 2>&1
```

### 2. Parse and present

Parse the output looking for `✓` (OK) and `✗` (FAIL) lines per section. Present a clean summary:

```
Agent Forge — Environment Check

Connection
  [+]  DATABRICKS_HOST    https://fevm-agent-forge.cloud.databricks.com
  [+]  Auth               token
  [+]  Connection         OK → fevm-agent-forge (mehdi.lamrani@...)

Warehouse
  [+]  DATABRICKS_WAREHOUSE_ID   8ba51d8cad2a3d9a (Starter Warehouse)

Unity Catalog
  [+]  PROJECT_UNITY_CATALOG_SCHEMA   agent_forge_catalog.main
  [+]  Tables
        [+]  checkin_metrics
        [+]  flights
        [x]  checkin_agents   (table not found)

Genie
  [+]  PROJECT_GENIE_CHECKIN   01f139de...  (Checkin Metrics)

Knowledge Assistants
  [+]  PROJECT_KA_PASSENGERS   ka-087003b9-endpoint (ACTIVE)

MLflow
  [+]  MLFLOW_EXPERIMENT_ID   3688767017703470

Model Endpoint
  [+]  AGENT_MODEL_ENDPOINT   URL (https://e2-demo-field-eng.../invocations)
  [+]  AGENT_MODEL_TOKEN      set

App Grants
  [x]  UC tables: app has no SELECT/ALL_PRIVILEGES

Summary
  [x]  2 checks failed
```

### 3. Offer remediation

For each [x], show which skill to run:

```
To fix:
  [x] checkin_agents missing    → /forge-setup-tables
  [x] app grants not applied    → run: ! ./deploy/grant/run_all_grants.sh

Run a specific step? Or type "all good" to exit.
```

If user names a step → immediately invoke that skill's flow.

If all [+] → show:
```
[+] All resources OK — Agent Forge is ready to deploy.

Run /dbx-deploy when you're ready.
```

## Error cases

- `--check` command fails entirely (auth broken): show error and suggest `/forge-setup-auth` first
- Grants failing: remind user the app must be deployed first before grants can be applied
