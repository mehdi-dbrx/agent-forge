#!/bin/bash
# Build pip package: copy frontend dist into brickforge/static/, build wheel + sdist
set -e
cd "$(dirname "$0")/../.."

echo "[1/3] Syncing frontend dist -> brickforge/static/"
rm -rf brickforge/static
cp -r visual/frontend/dist brickforge/static
echo "  $(find brickforge/static -type f | wc -l | tr -d ' ') files"

echo "[2/3] Cleaning old builds"
rm -rf dist/ build/ *.egg-info brickforge.egg-info

echo "[3/3] Building wheel + sdist"
uv run python -m build

echo ""
echo "[+] Built:"
ls -lh dist/
echo ""
echo "[+] Static files in wheel:"
uv run python -c "import zipfile; files=[f for f in zipfile.ZipFile('dist/$(ls dist/*.whl | head -1 | xargs basename)').namelist() if 'static' in f]; print(f'  {len(files)} files'); [print(f'  {f}') for f in files]"
