# Agent Forge — Known Issues & Fixes

Issues observed during real deployments, with root cause, fix, and fresh-deploy safety assessment.

---

## 1. Stale PAT after workspace switch

**Symptom:** Auth errors after changing `DATABRICKS_HOST` — token was valid on the old workspace, rejected on the new one.

**Root cause:** `DATABRICKS_TOKEN` is workspace-scoped. Switching hosts invalidates the existing PAT.

**Fix:** Regenerate a PAT for the new workspace:
```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from scripts.py.setup_dbx_env import _profile_for_host, _isolated_client, _redact, write_env_entry, ENV_FILE
import os
host = os.environ['DATABRICKS_HOST'].strip()
profile = _profile_for_host(host)
w = _isolated_client(profile)
t = w.tokens.create(comment='agent-forge-init', lifetime_seconds=604800)
write_env_entry(ENV_FILE, 'DATABRICKS_TOKEN', t.token_value)
print('[+] PAT generated (7d):', _redact(t.token_value))
"
```
Or run `/forge-setup-auth` → option 3.

**Long-term fix:** Yes. The setup flow handles this automatically.

**Fresh deploy safe?** Yes — `/forge-setup-auth` re-generates the PAT if a valid CLI profile exists for the target host.

---

## 2. `create_all_assets.py` fails when no CSV files present

**Symptom:** Script aborts at step 2/5 (create_genie_space) with: *"No tables in airties.main. Run csv_to_delta.py first."*

**Root cause:** `data/csv/` is gitignored. The assets script assumes tables pre-exist before creating the Genie space. On a fresh environment with no CSVs, the ordering fails.

**Fix:** Create the `flights` table manually using the SQL fallback:
```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
import os; from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState
spec = os.environ['PROJECT_UNITY_CATALOG_SCHEMA'].strip()
wh_id = os.environ['DATABRICKS_WAREHOUSE_ID'].strip()
w = WorkspaceClient()
sql = open('data/init/create_flights.sql').read().replace('__SCHEMA_QUALIFIED__', spec)
for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
    r = w.statement_execution.execute_statement(statement=stmt, warehouse_id=wh_id, wait_timeout='30s')
    print('[+]' if r.status.state == StatementState.SUCCEEDED else '[x]', stmt[:60].replace('\n',' '))
"
```
Then re-run Genie creation: `GENIE_ROOM_NAME="My Genie" uv run python data/init/create_genie_space.py`

**Long-term fix:** No — `create_all_assets.py` needs a guard that skips or defers Genie creation if no tables exist. `/forge-setup-tables` handles this correctly; the all-assets script does not.

**Fresh deploy safe?** Partially — `create_flights.sql` fallback works for the `flights` table, but other tables requiring CSV data (checkin_agents, border_officers, etc.) remain absent. Add seed CSVs to `data/csv/` or extend `create_flights.sql` to cover all tables.

---

## 3. `databricks bundle validate` picks wrong profile

**Symptom:** Running `databricks bundle validate` standalone fails with a token error pointing at a different, invalid workspace.

**Root cause:** The Databricks CLI picks the `DEFAULT` profile when no profile is specified and no env vars are set. If `DEFAULT` is expired or points to a different host, the command fails even though `.env.local` has valid credentials.

**Fix:** Source `.env.local` before running CLI commands:
```bash
source .env.local && databricks bundle validate
```
Or set env vars explicitly:
```bash
DATABRICKS_HOST=https://... DATABRICKS_TOKEN=dapi... databricks bundle validate
```

**Long-term fix:** Yes for `deploy.sh` — it sources `.env.local` before all CLI calls. Only affects manual standalone CLI usage.

**Fresh deploy safe?** Yes — `deploy.sh` handles this correctly.

---

## 4. `deploy.sh` exits non-zero on first deploy (grants timing)

**Symptom:** `deploy.sh` returns exit code 1 even though the app is `RUNNING`. The app deployed and started successfully.

**Root cause:** The post-deploy grants step (`run_all_grants.sh`) runs before the app's service principal is fully provisioned. Grant commands fail non-fatally but still propagate exit code 1.

**Fix:** Verify the app status independently:
```bash
DATABRICKS_HOST=https://... DATABRICKS_TOKEN=... databricks apps get <app-name>
```
If `app_status.state == RUNNING`, the deploy succeeded. Re-run the grants check after the app is fully up:
```bash
uv run python scripts/py/setup_dbx_env.py --check
```

**Long-term fix:** No — `deploy.sh` should catch grants failures as warnings, not abort with exit 1. The grants step should be idempotent and non-fatal on first deploy.

**Fresh deploy safe?** Mostly — deploy works, but CI pipelines checking exit code will see a false failure on first deploy to a new workspace.

---

## 5. Bundle deploy fails with "app already exists" on first deploy

**Symptom:** `databricks bundle deploy` fails with: *"Failed to create app <name>. An app with the same name already exists."*

**Root cause:** `deploy.sh` pre-creates the app via `databricks apps create` (needed because the Terraform provider cannot create apps from scratch). The `bind` command is called before the first deploy, but has no effect — there is no Terraform state yet for it to attach to. When `bundle deploy` runs, Terraform tries to create the app and fails because it already exists.

**Fix applied:** `deploy.sh` now detects the "already exists" error, runs `databricks bundle deployment bind` (which works after the failed apply creates initial state entries), and retries the deploy. The retry succeeds because Terraform now knows to update the existing app rather than create a new one.

**Long-term fix:** Yes — the retry logic is in `deploy.sh` and handles this automatically.

**Fresh deploy safe?** Yes — the retry is transparent and adds a few seconds on first deploy only.

---

## 6. Bundle deploy lock left by interrupted run

**Symptom:** Subsequent deploy attempts fail immediately: *"deploy lock acquired by ... Use --force-lock to override"*

**Root cause:** An interrupted `databricks bundle deploy` leaves the lock unreleased.

**Fix:**
```bash
DATABRICKS_HOST=https://... DATABRICKS_TOKEN=... databricks bundle deploy --force-lock
```

**Long-term fix:** Yes — `--force-lock` is the standard resolution. No code change needed.

**Fresh deploy safe?** Yes — only occurs after an interrupted deploy, not on clean first runs.

---

## 7. Frontend `client/dist/` not deployed — 500 on GET /

**Symptom:** App starts but every request to `/` returns `500 Internal Server Error`. Logs show: *"ENOENT: no such file or directory, stat '.../e2e-chatbot-app-next/client/dist/index.html'"*

**Root cause:** `client/dist/` is gitignored and excluded from the bundle. The Node server starts but has no built frontend to serve. The Python startup event only spawned the Node process without checking or building the frontend.

**Fix applied:** Added a remote build step to `agent/start_server.py`. On startup, if `client/dist/index.html` is absent, it runs `npm install` then `npm run build:client` before spawning the Node server:

```python
_CLIENT_DIST = Path(__file__).resolve().parents[1] / "e2e-chatbot-app-next" / "client" / "dist" / "index.html"

@app.on_event("startup")
async def start_frontend():
    if not _CLIENT_DIST.exists() and _NODE_SERVER.exists():
        _frontend_root = str(_NODE_SERVER.parents[2])
        subprocess.run(["npm", "install"], cwd=_frontend_root, check=True)
        subprocess.run(["npm", "run", "build:client"], cwd=_frontend_root, check=True)
    if _NODE_SERVER.exists():
        ...
```

**Long-term fix:** Yes. Build runs once on first startup (or after a cache miss), then skipped. Adds ~30–40s to first startup on a cold environment (npm install + vite build).

**Fresh deploy safe?** Yes — this fix is in the codebase and will run automatically on any environment where `client/dist/` is absent.

---

## Quick reference — fresh deploy checklist

| Check | Command |
|-------|---------|
| Validate env | `uv run python scripts/py/setup_dbx_env.py --check` |
| Tables missing | `uv run python -c "..." # see issue 2 above` |
| Wrong profile on CLI | `source .env.local && databricks bundle validate` |
| Deploy lock stuck | `databricks bundle deploy --force-lock` |
| App shows 500 | Check logs: `databricks apps logs <app> --profile <p> \| grep -E "build\|ENOENT\|Error"` |
| Grants failed post-deploy | Re-run `--check` after app is RUNNING |
