#!/usr/bin/env bash
# BrickForge Bridge Auth - connects local CLI to cloud Setup App
# Usage: bash connect.sh <setup-app-url> <nonce>
#   or: curl -sL <app-url>/api/auth/bridge-script?nonce=<id> | bash
# When served by the Setup App, APP_URL/NONCE/NONCE_ID/WS_DEFAULT are pre-filled below.
set -e

# --- Config (replaced by Setup App when served as download) ---
APP_URL="${1:?Usage: bash connect.sh <setup-app-url> <nonce>}"
NONCE="${2:?Usage: bash connect.sh <setup-app-url> <nonce>}"
NONCE_ID="${NONCE}"
WS_DEFAULT=""
APP_URL="${APP_URL%/}"

# ── ANSI ─────────────────────────────────────────────────────────────────────
BOLD="\033[1m"
B="\033[34m" G="\033[32m" R="\033[31m" Y="\033[33m" C="\033[36m" M="\033[35m" W="\033[0m" DIM="\033[2m"
OK="  ${G}✓${W}" FAIL="  ${R}✗${W}" WARN="  ${Y}⚠${W}" INFO="  ${C}→${W}" RUN="  ${B}~${W}"

# ── Header ───────────────────────────────────────────────────────────────────
printf "\n${BOLD}${M}╔══════════════════════════════════════════════╗${W}\n"
printf "${BOLD}${M}║       BrickForge  ·  bridge auth              ║${W}\n"
printf "${BOLD}${M}╚══════════════════════════════════════════════╝${W}\n\n"

printf "${INFO} App URL:  ${DIM}${APP_URL}${W}\n"
printf "${INFO} Nonce:    ${DIM}${NONCE_ID:0:8}...${W}\n"
printf "${INFO} OS:       ${DIM}$(uname -s 2>/dev/null || echo 'unknown')${W}\n"
printf "${INFO} Shell:    ${DIM}${SHELL}${W}\n\n"

# ── Step 1: Databricks CLI ───────────────────────────────────────────────────
printf "${BOLD}${B}═══ CLI check ═══${W}\n"

if ! command -v databricks &>/dev/null; then
  printf "${WARN} Databricks CLI not found\n"
  OS="$(uname -s 2>/dev/null || echo Windows)"
  case "$OS" in
    Darwin)
      if command -v brew &>/dev/null; then
        printf "${RUN} Installing via Homebrew...\n"
        brew tap databricks/tap && brew install databricks
      else
        printf "${RUN} Installing via curl...\n"
        curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh
      fi
      ;;
    Linux)
      printf "${RUN} Installing via curl...\n"
      curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh
      ;;
    MINGW*|MSYS*|CYGWIN*)
      if command -v winget &>/dev/null; then
        printf "${RUN} Installing via winget...\n"
        winget install Databricks.DatabricksCLI
      elif command -v pip &>/dev/null; then
        printf "${RUN} Installing via pip...\n"
        pip install databricks-cli --quiet
      else
        printf "${FAIL} Cannot install CLI automatically\n"
        printf "  ${DIM}Install manually: https://docs.databricks.com/dev-tools/cli/install${W}\n"
        exit 1
      fi
      ;;
    *)
      printf "${FAIL} Unknown OS: ${OS}\n"
      printf "  ${DIM}Install manually: https://docs.databricks.com/dev-tools/cli/install${W}\n"
      exit 1
      ;;
  esac
  printf "${OK} Databricks CLI installed\n"
else
  printf "${OK} CLI: ${DIM}$(which databricks)${W}\n"
fi
printf "${OK} Version: ${DIM}$(databricks --version 2>/dev/null || echo 'unknown')${W}\n\n"

# ── Step 2: Target workspace ────────────────────────────────────────────────
printf "${BOLD}${B}═══ Workspace ═══${W}\n"

if [ -z "${WS:-}" ]; then
  if [ -n "$WS_DEFAULT" ]; then
    WS="$WS_DEFAULT"
    printf "${OK} Using configured workspace: ${C}${WS}${W}\n"
  elif [ -t 0 ]; then
    printf "${INFO} Enter target workspace URL:\n"
    read -p "     > " WS
  else
    printf "${INFO} Enter target workspace URL:\n"
    printf "     > "
    read WS < /dev/tty
  fi
fi
WS="${WS%/}"
if [ -z "$WS" ]; then
  printf "${FAIL} No workspace URL provided\n"
  exit 1
fi
printf "${INFO} Target: ${C}${WS}${W}\n\n"

# ── Step 3: Authenticate ────────────────────────────────────────────────────
printf "${BOLD}${B}═══ Authentication ═══${W}\n"
printf "${RUN} Opening browser for OAuth...\n"
printf "  ${DIM}If the browser doesn't open, copy the URL from the CLI output.${W}\n\n"

echo "brickforge-tmp" | databricks auth login --host "$WS" 2>/dev/null
printf "\n${OK} Authenticated\n\n"

# ── Step 4: Retrieve token ──────────────────────────────────────────────────
printf "${BOLD}${B}═══ Token ═══${W}\n"
printf "${RUN} Retrieving token...\n"

TOKEN_JSON=$(databricks auth token --host "$WS" 2>/dev/null)
if [ -z "$TOKEN_JSON" ]; then
  printf "${FAIL} Failed to get token\n"
  printf "  ${DIM}Try: databricks auth login --host ${WS}${W}\n"
  exit 1
fi
TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token', d) if isinstance(d, dict) else d)" 2>/dev/null)
if [ -z "$TOKEN" ]; then
  printf "${FAIL} Failed to parse token\n"
  exit 1
fi
printf "${OK} Token acquired ${DIM}(${#TOKEN} chars, ${TOKEN:0:6}...)${W}\n"

# User info
BRIDGE_USER=$(databricks current-user me --host "$WS" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('userName','unknown'))" 2>/dev/null || echo "unknown")
printf "${OK} User: ${C}${BRIDGE_USER}${W}\n\n"

# ── Step 5: Encrypt ─────────────────────────────────────────────────────────
printf "${BOLD}${B}═══ Encryption ═══${W}\n"
printf "${RUN} Encrypting token...\n"

ENCRYPTED=$(echo -n "$TOKEN" | openssl enc -aes-256-cbc -a -A -pass "pass:${NONCE}" -pbkdf2 2>/dev/null)
if [ -z "$ENCRYPTED" ]; then
  printf "${WARN} openssl not available -- sending over HTTPS only\n"
  ENCRYPTED="PLAIN:${TOKEN}"
else
  printf "${OK} Encrypted ${DIM}(${#ENCRYPTED} chars)${W}\n"
fi
printf "\n"

# ── Step 6: Send to Setup App via browser ───────────────────────────────────
printf "${BOLD}${B}═══ Connect ═══${W}\n"

# URL-encode the encrypted token (base64 has +/= which need encoding)
ENCODED=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$ENCRYPTED" 2>/dev/null || echo "$ENCRYPTED")
ENCODED_HOST=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$WS" 2>/dev/null || echo "$WS")
ENCODED_USER=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$BRIDGE_USER" 2>/dev/null || echo "$BRIDGE_USER")

BRIDGE_URL="${APP_URL}/#bridge/${NONCE_ID}/${ENCODED}/${ENCODED_HOST}/${ENCODED_USER}"

printf "${RUN} Opening Setup App in browser...\n"
printf "  ${DIM}Token will be delivered via browser (SSO authenticated)${W}\n\n"

# Open URL in default browser (cross-platform)
OS="$(uname -s 2>/dev/null || echo Windows)"
case "$OS" in
  Darwin)  open "$BRIDGE_URL" ;;
  Linux)   xdg-open "$BRIDGE_URL" 2>/dev/null || sensible-browser "$BRIDGE_URL" ;;
  MINGW*|MSYS*|CYGWIN*)  start "$BRIDGE_URL" ;;
  *)       printf "${WARN} Cannot open browser automatically.\n"
           printf "  ${DIM}Open this URL manually:${W}\n"
           printf "  ${C}${BRIDGE_URL}${W}\n\n"
           exit 0 ;;
esac

printf "${OK} Browser opened\n\n"
printf "${BOLD}${G}╔══════════════════════════════════════════════╗${W}\n"
printf "${BOLD}${G}║  Token sent to browser.                      ║${W}\n"
printf "${BOLD}${G}║  Check the Setup App -- it should update.    ║${W}\n"
printf "${BOLD}${G}║  You can close this window.                  ║${W}\n"
printf "${BOLD}${G}╚══════════════════════════════════════════════╝${W}\n\n"
