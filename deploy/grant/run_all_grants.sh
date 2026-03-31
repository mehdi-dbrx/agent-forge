#!/usr/bin/env bash
# Run all grant scripts for the app service principal.
# Run from project root: ./deploy/grant/run_all_grants.sh [APP_NAME]
#
# Grants:
#   - UC tables (SELECT) via grant_app_tables.py
#   - UC functions/procedures (EXECUTE) via grant_app_functions.py
#   - SQL warehouse (CAN_USE) via authorize_warehouse_for_app.py
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
  exit 1
}

echo ""
echo "2. Granting UC functions/procedures access..."
uv run python deploy/grant/grant_app_functions.py "$APP_NAME" --schema "$SCHEMA" || {
  echo "Warning: grant_app_functions.py failed" >&2
  exit 1
}

echo ""
echo "3. Granting CAN_USE on SQL warehouse..."
uv run python deploy/grant/authorize_warehouse_for_app.py "$APP_NAME" || {
  echo "Warning: authorize_warehouse_for_app.py failed" >&2
  exit 1
}

echo ""
echo "Done. All grants applied."
