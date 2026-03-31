#!/usr/bin/env bash
# Deploy app to Databricks Apps via bundle (DAB).
# Run from project root: ./deploy/deploy.sh
#
# Requires in .env.local:
#   DBX_APP_NAME              - Databricks app name
#   PROJECT_UNITY_CATALOG_SCHEMA - catalog.schema for UC grants
#
# If "App already exists" error: bind first:
#   databricks bundle deployment bind agent_app <DBX_APP_NAME> --auto-approve
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

[ -f "$ROOT/.env.local" ] && set -a && source "$ROOT/.env.local" && set +a

if [ -z "${DBX_APP_NAME:-}" ]; then
  echo "Error: DBX_APP_NAME not set in .env.local" >&2
  exit 1
fi

if [ -z "${PROJECT_UNITY_CATALOG_SCHEMA:-}" ]; then
  echo "Error: PROJECT_UNITY_CATALOG_SCHEMA not set in .env.local" >&2
  exit 1
fi

echo "Deploying app: $DBX_APP_NAME"
echo ""

# Sync databricks.yml / app.yaml from .env.local (init if not exists)
uv run python deploy/sync_databricks_yml_from_env.py 2>/dev/null || true

# If app exists but isn't bound to bundle, bind it first
if databricks apps get "$DBX_APP_NAME" --output json &>/dev/null; then
  echo "Binding existing app $DBX_APP_NAME to bundle..."
  databricks bundle deployment bind agent_app "$DBX_APP_NAME" --auto-approve 2>/dev/null || true
fi

echo "Validating bundle..."
databricks bundle validate

# Verify backend imports before deploying (fail fast on SyntaxError etc.)
uv run python -c "from agent.start_server import app" || { echo "Backend import failed. Fix before deploying."; exit 1; }

echo "Deploying (bundle uploads source and links to app)..."
databricks bundle deploy

echo "Starting app..."
databricks bundle run agent_app

echo ""
echo "Granting UC table access to app service principal..."
uv run python deploy/grant/grant_app_tables.py "$DBX_APP_NAME" --schema "$PROJECT_UNITY_CATALOG_SCHEMA" || {
  echo "Warning: grant_app_tables.py failed. Run manually: uv run python deploy/grant/grant_app_tables.py $DBX_APP_NAME --schema $PROJECT_UNITY_CATALOG_SCHEMA"
}

echo ""
echo "Granting CAN_USE on SQL warehouse to app service principal..."
uv run python deploy/grant/authorize_warehouse_for_app.py "$DBX_APP_NAME" || {
  echo "Warning: authorize_warehouse_for_app.py failed. Run manually: uv run python deploy/grant/authorize_warehouse_for_app.py $DBX_APP_NAME"
}

echo ""
echo "Done."
APP_URL=$(databricks apps get "$DBX_APP_NAME" --output json 2>/dev/null | jq -r '.url // empty')
[ -n "$APP_URL" ] && echo "App URL: $APP_URL"
