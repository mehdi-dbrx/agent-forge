#!/usr/bin/env bash
# Initialize the env store: configure ENV_STORE_CATALOG_VOLUME_PATH in .env.local.
# Usage:
#   ./scripts/sh/init_env_store.sh
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "ERROR: .venv not found. Run 'uv sync' to install dependencies first."
  exit 1
fi

uv run python scripts/py/init_env_store.py "$@"
