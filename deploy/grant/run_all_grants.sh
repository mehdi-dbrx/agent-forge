#!/usr/bin/env bash
# Run all grant scripts for the app service principal.
# Run from project root: ./deploy/grant/run_all_grants.sh [APP_NAME]
#
# Grants:
#   1. UC tables (SELECT) via grant_app_tables.py
#   2. UC functions/procedures (EXECUTE) via grant_app_functions.py
#   3. SQL warehouse (CAN_USE) via authorize_warehouse_for_app.py
#   4. Serving endpoints (CAN_QUERY) via authorize_endpoint_for_app.py
#   5. Genie space (CAN_RUN) via authorize_genie_for_app.py
#   6. Secret scope (READ) via databricks secrets put-acl
#
# Uses DBX_APP_NAME and PROJECT_UNITY_CATALOG_SCHEMA from .env.local by default.
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

[ -f "$ROOT/.env.local" ] && set -a && source "$ROOT/.env.local" && set +a

APP_NAME="${1:-${DBX_APP_NAME:-}}"
SCHEMA="${PROJECT_UNITY_CATALOG_SCHEMA:-}"

if [ -z "$APP_NAME" ]; then
  echo "Error: DBX_APP_NAME not set. Pass app name as argument or set in .env.local" >&2
  exit 1
fi

if [ -z "$SCHEMA" ]; then
  echo "Error: PROJECT_UNITY_CATALOG_SCHEMA not set in .env.local" >&2
  exit 1
fi

echo "Running all grants for app: $APP_NAME (schema: $SCHEMA)"
echo ""

echo "1. Granting UC table access..."
uv run python deploy/grant/grant_app_tables.py "$APP_NAME" --schema "$SCHEMA" || {
  echo "Warning: grant_app_tables.py failed" >&2
}

echo ""
echo "2. Granting UC functions/procedures access..."
uv run python deploy/grant/grant_app_functions.py "$APP_NAME" --schema "$SCHEMA" || {
  echo "Warning: grant_app_functions.py failed" >&2
}

echo ""
echo "3. Granting CAN_USE on SQL warehouse..."
uv run python deploy/grant/authorize_warehouse_for_app.py "$APP_NAME" || {
  echo "Warning: authorize_warehouse_for_app.py failed" >&2
}

echo ""
echo "4. Granting CAN_QUERY on serving endpoints..."
uv run python deploy/grant/authorize_endpoint_for_app.py "$APP_NAME" || {
  echo "Warning: authorize_endpoint_for_app.py failed" >&2
}

echo ""
echo "5. Granting CAN_RUN on Genie space..."
uv run python deploy/grant/authorize_genie_for_app.py || {
  echo "Warning: authorize_genie_for_app.py failed (non-blocking)" >&2
}

echo ""
echo "6. Granting secret scope READ access..."
_sp_client_id=$(databricks apps get "$APP_NAME" --output json 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('service_principal_client_id',''))" 2>/dev/null)
if [ -n "$_sp_client_id" ]; then
  databricks secrets put-acl agent-forge "$_sp_client_id" READ 2>/dev/null && \
    echo "  [+] Secret scope agent-forge -> READ granted to $_sp_client_id" || \
    echo "  [-] Failed to grant secret scope ACL" >&2
else
  echo "  [~] No SP client ID — skipping secret scope grant"
fi

echo ""
echo "Done. All grants applied."
