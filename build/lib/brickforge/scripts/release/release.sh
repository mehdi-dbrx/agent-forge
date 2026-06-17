#!/bin/bash
# Full release pipeline: bump, build, upload
# Usage: bash scripts/release/release.sh 0.1.2 [--prod]
set -e
cd "$(dirname "$0")/../.."

VERSION="${1:?Usage: bash scripts/release/release.sh <version> [--prod]}"
TARGET="${2:-}"

echo "=== BrickForge Release ${VERSION} ==="
echo ""

bash scripts/release/bump.sh "$VERSION"
echo ""

bash scripts/release/build.sh
echo ""

bash scripts/release/upload.sh $TARGET
