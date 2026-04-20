---
name: forge-deploy
description: Deploy agent-forge to Databricks Apps interactively. Claude checks env, syncs config, runs pre-flight, confirms with user, deploys, applies grants, and reports the app URL. No terminal needed. Triggered when user says /forge-deploy, "deploy", "deploy the app", "push to databricks", or similar.
---

# Agent Forge — Deploy

Deploys agent-forge to Databricks Apps via Asset Bundle. Claude handles all steps — pre-flight, sync, deploy, grants. User just answers a confirmation question.

## Flow

### 1. Pre-flight: check required env vars

```bash
grep -E "^(DBX_APP_NAME|PROJECT_UNITY_CATALOG_SCHEMA|DATABRICKS_HOST|DATABRICKS_WAREHOUSE_ID|AGENT_MODEL_ENDPOINT|PROJECT_GENIE_CHECKIN|DATABRICKS_TOKEN|AGENT_MODEL_TOKEN|MLFLOW_EXPERIMENT_ID)=" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null
```

Required vars (abort if missing):
- `DBX_APP_NAME`
- `PROJECT_UNITY_CATALOG_SCHEMA`
- `DATABRICKS_HOST`
- `DATABRICKS_WAREHOUSE_ID`
- `AGENT_MODEL_ENDPOINT`
- `PROJECT_GENIE_CHECKIN`
- At least one of: `DATABRICKS_TOKEN` or a matching CLI profile for `DATABRICKS_HOST`

Optional (warn if missing):
- `AGENT_MODEL_TOKEN` — needed for cross-workspace endpoints
- `MLFLOW_EXPERIMENT_ID` — experiment tracking

Present the check result:
```
forge-deploy — Pre-flight

[+]  DATABRICKS_HOST              https://fevm-agent-forge.cloud.databricks.com
[+]  DATABRICKS_TOKEN             dapiXXXX...
[+]  DBX_APP_NAME                 agent-vibe-app-no-dist
[+]  DATABRICKS_WAREHOUSE_ID      8ba51d8cad2a3d9a
[+]  PROJECT_UNITY_CATALOG_SCHEMA agent_forge_catalog.main
[+]  PROJECT_GENIE_CHECKIN        01f139de...
[+]  AGENT_MODEL_ENDPOINT         https://e2-demo-field-eng.../invocations
[~]  AGENT_MODEL_TOKEN            not set  (needed for cross-workspace endpoint)
[~]  MLFLOW_EXPERIMENT_ID         not set  (experiment tracking disabled)
```

If any required var is missing → show which ones and say:
"Run /forge-setup to configure missing values before deploying."
Then stop.

If `AGENT_MODEL_ENDPOINT` is a cross-workspace URL (starts with `https://` and host differs from `DATABRICKS_HOST`) AND `AGENT_MODEL_TOKEN` is not set → show:
"[!] Cross-workspace endpoint detected but AGENT_MODEL_TOKEN is missing. The deployed app won't be able to call the model."
Ask: "[1] continue anyway  [2] run /forge-setup-model to fix first"

### 2. Config sync

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python deploy/sync_databricks_yml_from_env.py 2>&1
```

Show output. If sync fails or PLACEHOLDERs remain → stop and report.

Verify no PLACEHOLDERs:
```bash
grep -n "PLACEHOLDER_" /Users/mehdi.lamrani/code/code/agent-forge/databricks.yml /Users/mehdi.lamrani/code/code/agent-forge/app.yaml 2>/dev/null
```

If any found → show which lines and stop: "Set the missing env vars in .env.local and re-run /forge-deploy."

### 3. Python imports + bundle validate

Run in parallel:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "from agent.start_server import app" 2>&1
```
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && databricks bundle validate 2>&1
```

Show results:
```
[+]  Python imports OK
[+]  databricks bundle validate OK
```

If either fails → show error output and stop. Do not proceed to deploy.

### 4. Confirm with user

Show a deploy summary:
```
Ready to deploy:

  App      : agent-vibe-app-no-dist
  Workspace: https://fevm-agent-forge.cloud.databricks.com
  Schema   : agent_forge_catalog.main
  Warehouse: 8ba51d8cad2a3d9a

[1]  Deploy now
[2]  Dry-run only (validate, no deploy)
[3]  Cancel
```

Wait for user's reply.

### 5. Run deploy

If [2] dry-run:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && ./deploy/deploy.sh --dry-run 2>&1
```

If [1] deploy:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && ./deploy/deploy.sh 2>&1
```

Stream the full output. The script has its own progress reporting — show it all.

This script handles internally:
- Workspace change detection (clears stale bundle state)
- MLflow experiment bind
- App create/bind (pre-creates app if it doesn't exist, waits for compute)
- `databricks bundle deploy`
- `databricks bundle run agent_app`
- UC table grants
- Warehouse grants
- Secret scope ACL

### 6. Report result

If exit code 0:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && databricks apps get "$DBX_APP_NAME" --output json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('url',''))"
```

Show:
```
[+] Deployment complete

  App     : agent-vibe-app-no-dist
  URL     : https://fevm-agent-forge.cloud.databricks.com/apps/agent-vibe-app-no-dist
  Grants  : UC tables, warehouse, secrets applied
```

If exit code non-zero → show the last error lines from deploy output and suggest:
- Bundle errors → "Check databricks.yml and run /forge-setup-check"
- Auth errors → "Run /forge-setup-auth to verify credentials"
- App not starting → "Check app logs with /dbx-app-logs"

## Error cases

- `.env.local` missing → "No .env.local found. Run /forge-setup to create one."
- `databricks` CLI not found → "Databricks CLI not installed. Run: `! pip install databricks-cli`"
- Bundle validate fails → show full error, stop before deploy
- App fails to start → suggest `/dbx-app-logs`
- Grants fail → show which failed and the manual commands to run them
