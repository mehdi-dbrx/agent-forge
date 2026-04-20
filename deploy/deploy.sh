#!/usr/bin/env bash
# Deploy agent-forge to Databricks Apps via bundle (DAB).
# Run from project root: ./deploy/deploy.sh [--dry-run]
#
# Pre-flight checks ensure everything is correct before touching Databricks.
# Pass --dry-run to validate without deploying.
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ── ANSI ──────────────────────────────────────────────────────────────────────
R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[34m'; C=$'\033[36m'; W=$'\033[0m'
BOLD=$'\033[1m'; DIM=$'\033[2m'; ORANGE=$'\033[38;5;214m'
OK="  ${G}✓${W}"; FAIL="  ${R}✗${W}"; WARN="  ${Y}⚠${W}"
BAR_FILL="█"; BAR_EMPTY="░"

TOTAL_STEPS=6
STEP=0
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# ── Helpers ───────────────────────────────────────────────────────────────────
section() {
  STEP=$(( STEP + 1 ))
  echo -e "\n${BOLD}${B}═══ $1 (${STEP}/${TOTAL_STEPS}) ═══${W}"
}

ok()   { echo -e "${OK}  $*"; }
fail() { echo -e "${FAIL}  $*" >&2; }
warn() { echo -e "${WARN}  $*"; }
info() { echo -e "  ${DIM}▸${W}  $*"; }
conf() { echo -e "\n  ${BOLD}${ORANGE}✓  $*${W}"; }

abort() {
  fail "$1"
  echo -e "\n  ${R}${BOLD}Deployment aborted.${W}\n" >&2
  exit 1
}

# Animated progress bar — run_step "label" cmd [args...]
run_step() {
  local label="$1"; shift
  local log_file; log_file=$(mktemp)
  local width=20 i=0 pos bar j rc=0
  "$@" >"$log_file" 2>&1 &
  local pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    pos=$(( i % (width + 2) - 1 ))
    bar=""
    for (( j=0; j<width; j++ )); do
      [[ $j -eq $pos ]] && bar+="${BAR_FILL}" || bar+="${BAR_EMPTY}"
    done
    printf "\r  ${DIM}[${W}${G}%s${W}${DIM}]${W} %s" "$bar" "$label"
    sleep 0.06
    i=$(( i + 1 ))
  done
  printf "\r\033[K"
  wait "$pid" || rc=$?
  if [[ $rc -ne 0 ]]; then
    fail "$label ${DIM}(exit ${rc})${W}"
    uniq "$log_file" | sed 's/^/    /' >&2
    rm -f "$log_file"
    return $rc
  fi
  ok "$label"
  rm -f "$log_file"
}

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}${B}╔══════════════════════════════════════════╗${W}"
echo -e "${BOLD}${B}║  Agent Forge  —  Deploy                  ║${W}"
echo -e "${BOLD}${B}╚══════════════════════════════════════════╝${W}"
$DRY_RUN && echo -e "\n  ${WARN}  ${DIM}Dry-run — validation only, no deployment${W}"

# ── Step 1: Environment ───────────────────────────────────────────────────────
section "Environment"

if [[ ! -f "$ROOT/.env.local" ]]; then
  abort ".env.local not found — copy config/.env.example and fill in values"
fi
set -a; source "$ROOT/.env.local"; set +a
ok "Loaded .env.local"

# Required vars — abort if any missing
REQUIRED=(
  DBX_APP_NAME
  PROJECT_UNITY_CATALOG_SCHEMA
  DATABRICKS_HOST
  DATABRICKS_WAREHOUSE_ID
  AGENT_MODEL_ENDPOINT
  PROJECT_GENIE_CHECKIN
)
missing=()
for var in "${REQUIRED[@]}"; do
  val="${!var:-}"
  if [[ -z "$val" ]]; then
    missing+=("$var")
  else
    info "${C}${var}${W} = ${DIM}${val:0:70}${W}"
  fi
done
if [[ ${#missing[@]} -gt 0 ]]; then
  echo ""
  for var in "${missing[@]}"; do fail "${R}${var}${W} not set in .env.local"; done
  abort "Run ./scripts/sh/setup_dbx_env.sh to configure missing values"
fi

# Auth — need token or profile
if [[ -z "${DATABRICKS_TOKEN:-}" && -z "${DATABRICKS_CONFIG_PROFILE:-}" ]]; then
  abort "DATABRICKS_TOKEN or DATABRICKS_CONFIG_PROFILE must be set"
fi
[[ -n "${DATABRICKS_TOKEN:-}" ]] && ok "Auth via DATABRICKS_TOKEN"
[[ -n "${DATABRICKS_CONFIG_PROFILE:-}" && -z "${DATABRICKS_TOKEN:-}" ]] && ok "Auth via profile ${C}${DATABRICKS_CONFIG_PROFILE}${W}"

# Soft warnings (don't abort)
[[ -z "${AGENT_MODEL_TOKEN:-}" ]] && warn "AGENT_MODEL_TOKEN not set — cross-workspace model token may be missing from secrets"
[[ -z "${MLFLOW_EXPERIMENT_ID:-}" ]] && warn "MLFLOW_EXPERIMENT_ID not set — experiment tracking may not work"

# ── Step 2: Config Sync ───────────────────────────────────────────────────────
section "Config Sync"

info "Syncing databricks.yml / app.yaml from .env.local..."
if ! uv run python deploy/sync_databricks_yml_from_env.py; then
  warn "sync script reported errors — review output above"
fi

# Abort if any PLACEHOLDER values remain after sync
LEFTOVERS=$(grep -n "PLACEHOLDER_" databricks.yml app.yaml 2>/dev/null || true)
if [[ -n "$LEFTOVERS" ]]; then
  echo ""
  fail "PLACEHOLDER values remain after sync:"
  echo "$LEFTOVERS" | while IFS= read -r line; do
    echo -e "    ${DIM}${line}${W}" >&2
  done
  echo ""
  abort "Set the missing env vars in .env.local and re-run"
fi
ok "databricks.yml — no PLACEHOLDERs"
ok "app.yaml       — no PLACEHOLDERs"

# ── Step 3: Pre-flight Checks ─────────────────────────────────────────────────
section "Pre-flight Checks"

if ! run_step "Python imports (agent.start_server)" \
    uv run python -c "from agent.start_server import app"; then
  abort "Fix import errors before deploying"
fi

if ! run_step "databricks bundle validate" databricks bundle validate; then
  abort "Bundle validation failed — review databricks.yml"
fi

if $DRY_RUN; then
  echo -e "\n  ${Y}${BOLD}Dry-run complete — all checks passed.${W}\n"
  exit 0
fi

# ── Step 4: Deploy ────────────────────────────────────────────────────────────
section "Deploy"

# ── Detect workspace switch — clear stale bundle state if host changed ─────
_snap_dir=".databricks/bundle/default/sync-snapshots"
if [[ -d "$_snap_dir" ]]; then
  _state_host=$(python3 -c "
import json, glob, sys
snaps = glob.glob('$_snap_dir/*.json')
if not snaps: sys.exit(0)
d = json.load(open(snaps[0]))
print(d.get('host', '').rstrip('/'))
" 2>/dev/null)
  _cur_host="${DATABRICKS_HOST%/}"
  if [[ -n "$_state_host" && "$_state_host" != "$_cur_host" ]]; then
    warn "Workspace changed (${DIM}${_state_host}${W} → ${C}${_cur_host}${W}) — clearing stale bundle state"
    rm -rf .databricks/bundle/default/
    ok "Bundle state cleared"
  fi
fi

# ── Bind MLflow experiment if it already exists ────────────────────────────
info "Checking MLflow experiment..."
_username=$(timeout 10 databricks current-user me --output json 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('userName',''))" 2>/dev/null || true)
if [[ -z "$_username" ]]; then
  warn "Could not resolve current user — skipping experiment bind (will be created on deploy)"
else
  _exp_name="/Users/${_username}/agent-forge-default"
  _exp_id=$(timeout 10 databricks experiments get-by-name "$_exp_name" --output json 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('experiment',{}).get('experiment_id',''))" 2>/dev/null || true)
  if [[ -n "$_exp_id" ]]; then
    databricks bundle deployment bind agent_experiment "$_exp_id" --auto-approve 2>/dev/null || true
    ok "Experiment bound (${DIM}${_exp_id}${W})"
  else
    ok "Experiment will be created on first deploy"
  fi
fi

# ── Bind or create app ─────────────────────────────────────────────────────
info "Checking app ${C}${DBX_APP_NAME}${W}..."
if databricks apps get "$DBX_APP_NAME" --output json &>/dev/null; then
  info "App ${C}${DBX_APP_NAME}${W} already exists — binding to bundle..."
  databricks bundle deployment bind agent_app "$DBX_APP_NAME" --auto-approve 2>/dev/null || true
  ok "Bound to existing app"
else
  # Databricks Terraform provider cannot create apps from scratch via bundle deploy —
  # the Read call errors out instead of returning empty state.
  # Pre-create the app so bundle deploy can bind + update it.
  info "App ${C}${DBX_APP_NAME}${W} not found — pre-creating via API..."
  if ! databricks apps create "$DBX_APP_NAME" --description "LangGraph agent application" --no-wait 2>/tmp/app_create_err; then
    fail "Failed to create app ${DBX_APP_NAME}:"
    sed 's/^/    /' /tmp/app_create_err >&2
    abort "Create the app manually in the Databricks UI and re-run"
  fi
  ok "App ${C}${DBX_APP_NAME}${W} created"
  databricks bundle deployment bind agent_app "$DBX_APP_NAME" --auto-approve 2>/dev/null || true
  ok "Bound to bundle"

  # Wait for compute to leave STARTING before bundle deploy can update the app
  _cs="STARTING"
  _wi=0
  while [[ "$_cs" == "STARTING" ]]; do
    _pos=$(( _wi % (20 + 2) - 1 ))
    _bar=""
    for (( _j=0; _j<20; _j++ )); do
      [[ $_j -eq $_pos ]] && _bar+="${BAR_FILL}" || _bar+="${BAR_EMPTY}"
    done
    printf "\r  ${DIM}[${W}${G}%s${W}${DIM}]${W} App compute starting..." "$_bar"
    sleep 3
    _wi=$(( _wi + 1 ))
    _cs=$(databricks apps get "$DBX_APP_NAME" --output json 2>/dev/null \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('compute_status',{}).get('state','STARTING'))" 2>/dev/null)
  done
  printf "\r\033[K"
  ok "App compute is ${C}${_cs}${W}"
fi


if ! run_step "databricks bundle deploy" databricks bundle deploy; then
  abort "Bundle deploy failed"
fi

# ── Secret scope grant must happen before bundle run (secret resolved at start time) ──
_sp_client_id=$(databricks apps get "$DBX_APP_NAME" --output json 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('service_principal_client_id',''))" 2>/dev/null)
if [[ -n "$_sp_client_id" ]]; then
  databricks secrets put-acl agent-forge "$_sp_client_id" READ 2>/dev/null || true
fi

if ! run_step "Starting app ${DBX_APP_NAME}" databricks bundle run agent_app; then
  abort "App failed to start"
fi

# ── Step 5: Grants ────────────────────────────────────────────────────────────
section "Grants"

info "UC table access..."
if uv run python deploy/grant/grant_app_tables.py "$DBX_APP_NAME" \
    --schema "$PROJECT_UNITY_CATALOG_SCHEMA" 2>/dev/null; then
  ok "UC table grants applied"
else
  warn "grant_app_tables failed — run manually:"
  echo -e "  ${DIM}uv run python deploy/grant/grant_app_tables.py ${DBX_APP_NAME} --schema ${PROJECT_UNITY_CATALOG_SCHEMA}${W}"
fi

info "SQL warehouse access..."
if uv run python deploy/grant/authorize_warehouse_for_app.py "$DBX_APP_NAME" 2>/dev/null; then
  ok "Warehouse grant applied"
else
  warn "authorize_warehouse_for_app failed — run manually:"
  echo -e "  ${DIM}uv run python deploy/grant/authorize_warehouse_for_app.py ${DBX_APP_NAME}${W}"
fi

info "Secret scope access..."
_sp_client_id=$(databricks apps get "$DBX_APP_NAME" --output json 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('service_principal_client_id',''))" 2>/dev/null)
if [[ -n "$_sp_client_id" ]]; then
  if databricks secrets put-acl agent-forge "$_sp_client_id" READ 2>/tmp/acl_err; then
    ok "Secret scope ${C}agent-forge${W} → READ granted to app SP"
  else
    warn "Failed to grant secret scope ACL: $(cat /tmp/acl_err)"
  fi
  # Verify
  _acl=$(databricks secrets list-acls agent-forge 2>/dev/null \
    | python3 -c "import sys,json; acls=json.load(sys.stdin); print(next((a['permission'] for a in acls if a['principal']=='$_sp_client_id'), 'MISSING'))" 2>/dev/null)
  if [[ "$_acl" == "MISSING" || -z "$_acl" ]]; then
    warn "Secret ACL verification failed — ${C}AGENT_MODEL_TOKEN${W} may not be accessible to app"
  else
    ok "Verified: app SP ${DIM}${_sp_client_id}${W} has ${C}${_acl}${W} on scope ${C}agent-forge${W}"
  fi
else
  warn "Could not retrieve app service principal — skipping secret scope grant"
fi

# ── Step 6: Done ──────────────────────────────────────────────────────────────
section "Complete"

APP_URL=$(databricks apps get "$DBX_APP_NAME" --output json 2>/dev/null | jq -r '.url // empty' || true)
conf "Deployment complete — ${DBX_APP_NAME}"
[[ -n "$APP_URL" ]] && echo -e "  ${C}App URL:${W} ${BOLD}${APP_URL}${W}"
echo ""
