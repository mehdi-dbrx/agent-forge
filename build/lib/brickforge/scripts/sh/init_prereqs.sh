#!/usr/bin/env bash
# Check and install local prerequisites for agent-forge.
# Installs uv if missing, then delegates to Python for full checks/installs.
# Usage:
#   ./scripts/sh/init_prereqs.sh         # check + auto-fix
#   ./scripts/sh/init_prereqs.sh --check # check only, no changes
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

BOLD="\033[1m"
B="\033[34m" G="\033[32m" R="\033[31m" Y="\033[33m" W="\033[0m" DIM="\033[2m"

printf "\n${BOLD}${B}╔══════════════════════════════════════════════╗${W}\n"
printf "${BOLD}${B}║       agent-forge  ·  init prerequisites      ║${W}\n"
printf "${BOLD}${B}╚══════════════════════════════════════════════╝${W}\n\n"

# ── uv bootstrap (must happen in shell before we can use uv run) ──────────────
if command -v uv &>/dev/null; then
  printf "  ${G}✓${W} uv $(uv --version 2>/dev/null | awk '{print $2}')\n"
else
  printf "  ${Y}⚠${W} uv not found\n"
  if [[ "${1:-}" == "--check" ]]; then
    printf "  ${DIM}Run without --check to install automatically.${W}\n\n"
    exit 1
  fi
  printf "  ${B}→${W} Installing uv via pip...\n"
  pip install uv --quiet && printf "  ${G}✓${W} uv installed\n" || {
    printf "  ${R}✗${W} pip install failed.\n"
    printf "  ${DIM}Install manually: curl -Ls https://astral.sh/uv/install.sh | sh${W}\n\n"
    exit 1
  }
fi

# ── delegate remaining checks to Python ──────────────────────────────────────
exec uv run python scripts/py/init_prereqs.py "$@"
