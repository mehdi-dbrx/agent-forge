#!/bin/bash
# Upload to test.pypi.org or pypi.org
# Usage: bash scripts/release/upload.sh [--prod]
set -e
cd "$(dirname "$0")/../.."

if [ ! -d dist ] || [ -z "$(ls dist/*.whl 2>/dev/null)" ]; then
  echo "[x] No dist/ found. Run scripts/release/build.sh first."
  exit 1
fi

if [ "$1" = "--prod" ]; then
  REPO="pypi"
  echo "[!] Uploading to PRODUCTION pypi.org"
  read -p "  Are you sure? (y/N) " confirm
  [ "$confirm" = "y" ] || { echo "[x] Aborted"; exit 1; }
else
  REPO="testpypi"
  echo "[+] Uploading to test.pypi.org"
fi

uv run twine upload --repository "$REPO" dist/*

echo ""
if [ "$REPO" = "testpypi" ]; then
  VERSION=$(uv run python -c "from brickforge import __version__; print(__version__)")
  echo "[+] View: https://test.pypi.org/project/brickforge/${VERSION}/"
  echo "[+] Install: pip install -i https://test.pypi.org/simple/ brickforge==${VERSION}"
else
  echo "[+] View: https://pypi.org/project/brickforge/"
  echo "[+] Install: pip install brickforge"
fi
