#!/bin/bash
# Bump version in pyproject.toml and brickforge/__init__.py
# Usage: bash scripts/release/bump.sh 0.1.2
set -e
VERSION="${1:?Usage: bash scripts/release/bump.sh <version>}"

sed -i '' "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml
sed -i '' "s/__version__ = \".*\"/__version__ = \"${VERSION}\"/" brickforge/__init__.py

echo "[+] Bumped to ${VERSION}"
grep 'version' pyproject.toml | head -1
grep '__version__' brickforge/__init__.py
