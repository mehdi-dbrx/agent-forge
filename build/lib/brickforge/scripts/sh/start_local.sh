#!/usr/bin/env bash
# Run full stack locally: backend (8000) + Node API (3001) + Vite frontend (3000).
# Kills any process on 8000, 3000, 3001 at start. Env from .env.local.
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -d app ]]; then
  echo "Frontend not found. Run 'uv run start-app' once to clone it, then run this script again."
  exit 1
fi

# Free ports 8000, 3000, 3001 if in use (e.g. previous run)
# Only kill LISTEN processes, not clients (e.g. Firefox with localhost:3000 open)
for port in 8000 3000 3001; do
  pid=$(lsof -ti :$port -sTCP:LISTEN 2>/dev/null) || true
  [[ -n "$pid" ]] && kill $pid 2>/dev/null || true
done
sleep 1

# Load .env.local so DATABRICKS_* and API_PROXY are set for all children
set -a
[[ -f .env       ]] && source .env
[[ -f .env.local ]] && source .env.local
set +a
export API_PROXY="${API_PROXY:-http://localhost:8000/invocations}"

BACKEND_PID=""
NODE_PID=""
FRONTEND_PID=""
cleanup() {
  [[ -n $BACKEND_PID  ]] && kill $BACKEND_PID  2>/dev/null || true
  [[ -n $NODE_PID     ]] && kill $NODE_PID     2>/dev/null || true
  [[ -n $FRONTEND_PID ]] && kill $FRONTEND_PID 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM

echo "Starting backend (8000), Node API (3001), and frontend (3000)..."
echo "Backend:  http://localhost:8000"
echo "Node API: http://localhost:3001  (/api/session)"
echo "Frontend: http://localhost:3000"
echo "Stop with Ctrl+C"
echo ""

# Wait for a URL to return 200 (max 60s), so frontend doesn't hit Node before it's ready
wait_for() {
  local url="$1" name="$2" n=0 max=60
  until curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -q 200; do
    n=$((n + 1)); [[ $n -ge $max ]] && { echo "Timeout waiting for $name"; return 1; }
    sleep 1
  done
  echo "$name ready"
}

# Build Node server (ensures latest routes, e.g. /api/tables)
(cd app && npm run build:server) || true

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Error: .venv not found. Run 'uv sync' to install all dependencies."
  exit 1
fi

# Verify backend imports before starting (fail fast on SyntaxError etc.)
"$PYTHON" -c "from agent.start_server import app" || { echo "Backend import failed. Check logs/backend.log."; exit 1; }

mkdir -p "$ROOT/logs"

# Start each process, capture the subshell PID
"$PYTHON" -m uvicorn agent.start_server:app --host 0.0.0.0 --port 8000 --reload >> "$ROOT/logs/backend.log" 2>&1 &
BACKEND_PID=$!
wait_for "http://127.0.0.1:8000/health" "Backend" || true

env CHAT_APP_PORT=3001 PORT=3001 API_PROXY="$API_PROXY" LOG_SSE_EVENTS="${LOG_SSE_EVENTS:-true}" \
  bash -c 'cd app && npm run dev:built --workspace=@databricks/chatbot-server' \
  >> "$ROOT/logs/node.log" 2>&1 &
NODE_PID=$!
wait_for "http://127.0.0.1:3001/ping" "Node API" || true

bash -c 'cd app && npm run dev:client' >> "$ROOT/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
sleep 5

while true; do
  for pid in $BACKEND_PID $NODE_PID $FRONTEND_PID; do
    if ! kill -0 "$pid" 2>/dev/null; then
      kill $BACKEND_PID $NODE_PID $FRONTEND_PID 2>/dev/null || true
      exit 1
    fi
  done
  sleep 1
done
