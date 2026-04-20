#!/usr/bin/env python3
"""Create Unity Catalog volume for Knowledge Assistant documents.

Volume path is derived from PROJECT_UNITY_CATALOG_SCHEMA in .env.local:
  e.g. vibe.main → /Volumes/vibe/main/doc

Skips creation if the volume already exists.

Usage:
  uv run python scripts/py/ka/create_volume.py
  uv run python scripts/py/ka/create_volume.py --dry-run
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

G = "\033[32m"
R = "\033[31m"
Y = "\033[33m"
C = "\033[36m"
W = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

OK = f"{G}✓{W}"
FAIL = f"{R}✗{W}"
WARN = f"{Y}⚠{W}"
INFO = f"{C}→{W}"


def _volume_parts() -> tuple[str, str, str] | None:
    """Derive (catalog, schema, volume_name) from PROJECT_UNITY_CATALOG_SCHEMA."""
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if not spec or "." not in spec:
        return None
    catalog, schema = spec.split(".", 1)
    return catalog.strip(), schema.strip(), "doc"


def volume_path() -> str | None:
    parts = _volume_parts()
    if not parts:
        return None
    return f"/Volumes/{parts[0]}/{parts[1]}/{parts[2]}"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Create UC volume for KA documents")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without creating")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local", override=True)

    parts = _volume_parts()
    if not parts:
        print(f"{FAIL} PROJECT_UNITY_CATALOG_SCHEMA not set or invalid (expected catalog.schema){W}", file=sys.stderr)
        return 1

    catalog, schema, vol_name = parts
    vpath = f"/Volumes/{catalog}/{schema}/{vol_name}"

    if args.dry_run:
        print(f"\n  {INFO} Dry run: would create volume {BOLD}{vpath}{W}\n")
        return 0

    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.catalog import VolumeType

        token = os.environ.get("DATABRICKS_TOKEN")
        if token:
            w = WorkspaceClient(host=os.environ.get("DATABRICKS_HOST"), token=token)
        else:
            w = WorkspaceClient()
    except Exception as e:
        print(f"{FAIL} Connection failed: {e}{W}", file=sys.stderr)
        return 1

    # Check if volume already exists
    try:
        existing = list(w.volumes.list(catalog_name=catalog, schema_name=schema))
        for vol in existing:
            if vol.name == vol_name:
                print(f"{WARN} Volume {vpath} already exists — skipping.{W}")
                return 0
    except Exception as e:
        print(f"{FAIL} Failed to list volumes: {e}{W}", file=sys.stderr)
        return 1

    # Create volume
    try:
        w.volumes.create(
            catalog_name=catalog,
            schema_name=schema,
            name=vol_name,
            volume_type=VolumeType.MANAGED,
        )
        print(f"{OK} Volume {BOLD}{vpath}{W} created.{W}")
        return 0
    except Exception as e:
        err = str(e)
        if "already exists" in err.lower():
            print(f"{WARN} Volume {vpath} already exists — skipping.{W}")
            return 0
        print(f"{FAIL} Failed to create volume: {e}{W}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
