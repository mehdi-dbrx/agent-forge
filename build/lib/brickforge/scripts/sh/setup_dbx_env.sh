#!/usr/bin/env bash
# Setup & check Databricks resources in .env.local
# Usage:
#   ./scripts/sh/setup_dbx_env.sh         # interactive setup
#   ./scripts/sh/setup_dbx_env.sh --check # quick check only
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "ERROR: .venv not found. Run 'uv sync' to install dependencies first."
  exit 1
fi

uv run python scripts/py/setup_dbx_env.py "$@"
