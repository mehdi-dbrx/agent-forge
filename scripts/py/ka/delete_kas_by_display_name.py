#!/usr/bin/env python3
"""Delete Databricks Knowledge Assistants by display name (case-insensitive match).

Without --yes, only prints what would be deleted (dry-run).

Usage:
  uv run python scripts/py/ka/delete_kas_by_display_name.py --dry-run "agent-forge-passenger-rights"
  uv run python scripts/py/ka/delete_kas_by_display_name.py --yes "agent-forge-passenger-rights"
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

R = "\033[31m"
G = "\033[32m"
Y = "\033[33m"
B = "\033[34m"
W = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"

OK = f"{G}✓{W}"
FAIL = f"{R}✗{W}"
WARN = f"{Y}⚠{W}"
INFO = f"{B}→{W}"


def _workspace_client():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local", override=True)

    from databricks.sdk import WorkspaceClient

    token = os.environ.get("DATABRICKS_TOKEN")
    if token:
        return WorkspaceClient(host=os.environ.get("DATABRICKS_HOST"), token=token)
    return WorkspaceClient()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Delete Knowledge Assistants by display name")
    parser.add_argument("names", nargs="+", metavar="DISPLAY_NAME", help="Display name(s) to match (case-insensitive)")
    parser.add_argument("--yes", action="store_true", help="Actually delete; without this, dry-run only")
    parser.add_argument("--dry-run", action="store_true", help="Print matches only (default when --yes is not set)")
    args = parser.parse_args()

    if args.yes and args.dry_run:
        print(f"{FAIL} Use either --yes or --dry-run, not both.{W}", file=sys.stderr)
        return 2

    dry = not args.yes

    try:
        w = _workspace_client()
    except Exception as e:
        print(f"{FAIL} Connection failed: {e}{W}", file=sys.stderr)
        return 1

    want = {n.strip().lower() for n in args.names if n.strip()}
    if not want:
        print(f"{FAIL} No display names given.{W}", file=sys.stderr)
        return 1

    kas = list(w.knowledge_assistants.list_knowledge_assistants())
    matches: list[tuple[str, str]] = []
    for ka in kas:
        dn = (ka.display_name or "").strip()
        if dn.lower() in want:
            rid = ka.name or ""
            if rid:
                matches.append((dn, rid))

    found_lower = {m[0].lower() for m in matches}
    missing = want - found_lower

    print(f"\n{BOLD}{B}{'═' * 60}{W}")
    print(f"{BOLD}{B}  Delete Knowledge Assistants by display name{W}")
    print(f"{BOLD}{B}{'═' * 60}{W}\n")

    if not matches:
        print(f"  {WARN} No matching KAs for: {', '.join(sorted(want))}{W}\n")
        if missing:
            print(f"  {DIM}(all requested names missing){W}\n")
        return 1 if want else 0

    for dn, rid in sorted(matches, key=lambda x: x[0].lower()):
        action = f"{WARN} would delete{W}" if dry else f"{R}deleting{W}"
        print(f"  {INFO} {BOLD}{dn}{W}")
        print(f"       {DIM}{rid}{W}")
        print(f"       {action}")
        if not dry:
            try:
                w.knowledge_assistants.delete_knowledge_assistant(rid)
                print(f"       {OK} Deleted")
            except Exception as e:
                print(f"       {FAIL} {e}")
                return 1
        print()

    if missing:
        print(f"  {WARN} Not found (no delete): {', '.join(sorted(missing))}{W}\n")

    if dry:
        print(f"  {INFO} Dry-run only. Pass {BOLD}--yes{W} to delete.{W}\n")
    else:
        print(f"  {OK} Done.{W}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
