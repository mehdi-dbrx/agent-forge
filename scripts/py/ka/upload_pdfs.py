#!/usr/bin/env python3
"""Upload PDFs from data/pdf/ to the UC volume for Knowledge Assistants.

Volume path is derived from PROJECT_UNITY_CATALOG_SCHEMA in .env.local:
  e.g. vibe.main → /Volumes/vibe/main/doc

Usage:
  uv run python scripts/py/ka/upload_pdfs.py
  uv run python scripts/py/ka/upload_pdfs.py --dry-run
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data" / "pdf"

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


def _volume_path() -> str | None:
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if not spec or "." not in spec:
        return None
    catalog, schema = spec.split(".", 1)
    return f"/Volumes/{catalog.strip()}/{schema.strip()}/doc"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Upload PDFs to UC volume for KA documents")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be uploaded without uploading")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local", override=True)

    vol_path = _volume_path()
    if not vol_path:
        print(f"{FAIL} PROJECT_UNITY_CATALOG_SCHEMA not set or invalid (expected catalog.schema){W}", file=sys.stderr)
        return 1

    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"{WARN} No PDF files found in {DATA_DIR}{W}")
        return 0

    print(f"\n{BOLD}Uploading {len(pdfs)} PDF(s) to {vol_path}{W}\n")

    if args.dry_run:
        for pdf in pdfs:
            print(f"  {INFO} {DIM}would upload:{W} {pdf.name} {DIM}→ {vol_path}/{pdf.name}{W}")
        print(f"\n  {WARN} {DIM}--dry-run: no files uploaded{W}\n")
        return 0

    try:
        from databricks.sdk import WorkspaceClient

        token = os.environ.get("DATABRICKS_TOKEN")
        if token:
            w = WorkspaceClient(host=os.environ.get("DATABRICKS_HOST"), token=token)
        else:
            w = WorkspaceClient()
    except Exception as e:
        print(f"{FAIL} Connection failed: {e}{W}", file=sys.stderr)
        return 1

    failed = 0
    for pdf in pdfs:
        dest = f"{vol_path}/{pdf.name}"
        print(f"  {INFO} {pdf.name} {DIM}→ {dest}{W}", end=" ", flush=True)
        try:
            with open(pdf, "rb") as f:
                w.files.upload(dest, f, overwrite=True)
            print(f"{OK}")
        except Exception as e:
            print(f"{FAIL} {e}{W}")
            failed += 1

    print()
    if failed:
        print(f"{FAIL} {failed} file(s) failed to upload.{W}")
        return 1
    print(f"{OK} All {len(pdfs)} file(s) uploaded successfully.{W}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
