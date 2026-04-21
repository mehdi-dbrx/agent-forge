#!/usr/bin/env bash
# Start the visual architecture viewer.
# Backend (graph API) on port 9001, frontend (React Flow) on port 9000.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── uv / Python deps ─────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  echo "[visual] uv not found. Installing via pip..."
  pip install uv || { echo "[visual] ERROR: uv install failed. Install manually: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
fi

if [ ! -d "$PROJECT_ROOT/.venv" ] || [ "$PROJECT_ROOT/pyproject.toml" -nt "$PROJECT_ROOT/.venv/pyvenv.cfg" ]; then
  echo "[visual] Syncing Python deps (uv sync)..."
  (cd "$PROJECT_ROOT" && uv sync) || { echo "[visual] ERROR: uv sync failed. Aborting."; exit 1; }
  echo "[visual] Python deps ready."
fi

# ── Node deps ────────────────────────────────────────────────────────────────
install_node_deps() {
  local name=$1 dir=$2
  echo "[visual] Installing $name deps..."
  (cd "$dir" && npm ci) || { echo "[visual] ERROR: $name install failed. Aborting."; exit 1; }
  echo "[visual] $name deps ready."
}

# Install if node_modules is missing or lockfile is newer (catches partial/stale installs)
if [ ! -f "$SCRIPT_DIR/backend/node_modules/.package-lock.json" ] || \
   [ "$SCRIPT_DIR/backend/package-lock.json" -nt "$SCRIPT_DIR/backend/node_modules/.package-lock.json" ]; then
  install_node_deps "backend" "$SCRIPT_DIR/backend"
fi
if [ ! -f "$SCRIPT_DIR/frontend/node_modules/.package-lock.json" ] || \
   [ "$SCRIPT_DIR/frontend/package-lock.json" -nt "$SCRIPT_DIR/frontend/node_modules/.package-lock.json" ]; then
  install_node_deps "frontend" "$SCRIPT_DIR/frontend"
fi

trap 'kill 0' SIGINT SIGTERM

echo "[visual] Backend  → http://localhost:9001/api/graph"
echo "[visual] Frontend → http://localhost:9000"
echo "[visual] Stop with Ctrl+C"
echo ""

(cd "$SCRIPT_DIR/backend"  && node index.js) &
(cd "$SCRIPT_DIR/frontend" && npx vite --port 9000) &

wait
