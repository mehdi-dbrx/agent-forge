#!/usr/bin/env bash
# Save/load .env.local to/from a Databricks Unity Catalog Volume.
# Usage:
#   ./scripts/sh/env_store.sh save           # push .env.local to the store
#   ./scripts/sh/env_store.sh load           # pull .env.local from the store (interactive)
#   ./scripts/sh/env_store.sh save --dry-run # preview only
#   ./scripts/sh/env_store.sh load --dry-run # preview only
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "ERROR: .venv not found. Run 'uv sync' to install dependencies first."
  exit 1
fi

uv run python scripts/py/env_store.py "$@"
