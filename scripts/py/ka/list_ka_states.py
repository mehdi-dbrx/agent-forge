#!/usr/bin/env python3
"""List every Databricks Knowledge Assistant with colored state (and errors).

Fetches full details per KA (one API call each). Prints progress as it goes.

Usage:
  uv run python scripts/py/ka/list_ka_states.py
  uv run python scripts/py/ka/list_ka_states.py --no-errors   # hide FAILED error lines
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
M = "\033[35m"
C = "\033[36m"
W = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"

OK = f"{G}✓{W}"
FAIL = f"{R}✗{W}"
WARN = f"{Y}⚠{W}"
INFO = f"{C}→{W}"
STEP = f"{B}●{W}"

NAME_W = 38
STATE_W = 14


def _header(text: str, subtitle: str = "") -> None:
    print(f"\n{BOLD}{B}{'═' * 60}{W}")
    print(f"{BOLD}{B}  {text}{W}", end="")
    if subtitle:
        print(f"  {DIM}{subtitle}{W}")
    else:
        print()
    print(f"{BOLD}{B}{'═' * 60}{W}\n")


def _state_color(raw: str) -> str:
    u = (raw or "").upper()
    if u == "ACTIVE":
        return f"{G}{raw}{W}"
    if u == "FAILED":
        return f"{R}{raw}{W}"
    if u in ("CREATING", "UPDATING", "DELETING"):
        return f"{Y}{raw}{W}"
    if u:
        return f"{M}{raw}{W}"
    return f"{DIM}(unknown){W}"


def _plain_len(s: str) -> int:
    import re
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def _pad_visible(s: str, width: int) -> str:
    return s + " " * max(0, width - _plain_len(s))


def _trunc(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _clear_progress_line() -> None:
    if sys.stdout.isatty():
        sys.stdout.write("\033[1A\033[K")
        sys.stdout.flush()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="List all Knowledge Assistants with colored state")
    parser.add_argument("--no-errors", action="store_true", help="Do not print error details for FAILED KAs")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local", override=True)

    try:
        from databricks.sdk import WorkspaceClient

        token = os.environ.get("DATABRICKS_TOKEN")
        if token:
            w = WorkspaceClient(host=os.environ.get("DATABRICKS_HOST"), token=token)
        else:
            w = WorkspaceClient()
    except Exception as e:
        print(f"{FAIL} Connection failed: {R}{e}{W}", file=sys.stderr)
        return 1

    print(f"  {INFO} Listing Knowledge Assistants…{W}", flush=True)
    summary = list(w.knowledge_assistants.list_knowledge_assistants())
    if not summary:
        print(f"\n  {WARN} No Knowledge Assistants in this workspace.{W}\n")
        return 0

    total = len(summary)
    sorted_kas = sorted(summary, key=lambda k: (k.display_name or "").lower())

    _header("Knowledge Assistant states", f"({total} total)")
    print(f"  {DIM}Fetching state for each KA (one request at a time).{W}\n", flush=True)

    hdr_name = f"{DIM}{'DISPLAY NAME':<{NAME_W}}{W}"
    hdr_state = f"{DIM}{'STATE':<{STATE_W}}{W}"
    print(f"  {STEP} {hdr_name} {hdr_state} {DIM}{'ENDPOINT'}{W}", flush=True)
    print(f"  {DIM}{'-' * (NAME_W + STATE_W + 46)}{W}", flush=True)

    n_active = n_failed = n_other = 0

    for i, sk in enumerate(sorted_kas, 1):
        name = sk.display_name or "(unnamed)"
        name_disp = _trunc(name, NAME_W)
        rid = sk.name or ""

        print(f"  {DIM}[{i}/{total}]{W} {INFO} {BOLD}{_trunc(name, 52)}{W} {DIM}…{W}", flush=True)

        if not rid:
            _clear_progress_line()
            state_cell = f"{DIM}—{W}"
            endpoint = f"{DIM}no resource name{W}"
            err = None
            n_other += 1
        else:
            try:
                ka = w.knowledge_assistants.get_knowledge_assistant(rid)
            except Exception as e:
                _clear_progress_line()
                state_cell = f"{DIM}—{W}"
                endpoint = f"{R}fetch error{W}"
                err = str(e)
                n_other += 1
                print(
                    f"  {STEP} {BOLD}{_pad_visible(name_disp, NAME_W)}{W} "
                    f"{_pad_visible(state_cell, STATE_W)} {endpoint}",
                    flush=True,
                )
                if err:
                    print(f"       {FAIL} {DIM}{err}{W}", flush=True)
                print(flush=True)
                continue

            _clear_progress_line()

            st = ka.state
            raw_state = ""
            if st:
                raw_state = st.value if hasattr(st, "value") else str(st)
            raw = raw_state or "?"
            state_cell = _state_color(raw)

            endpoint = ka.endpoint_name or f"{DIM}—{W}"
            err = None
            if not args.no_errors and (raw_state or "").upper() == "FAILED":
                ei = getattr(ka, "error_info", None)
                if ei:
                    err = str(ei).strip().replace("\n", " ")
                    if len(err) > 200:
                        err = err[:197] + "…"

            u = (raw_state or "").upper()
            if u == "ACTIVE":
                n_active += 1
            elif u == "FAILED":
                n_failed += 1
            else:
                n_other += 1

        print(
            f"  {STEP} {BOLD}{_pad_visible(name_disp, NAME_W)}{W} "
            f"{_pad_visible(state_cell, STATE_W)} {endpoint}",
            flush=True,
        )
        if err:
            print(f"       {FAIL} {DIM}{err}{W}", flush=True)
        print(flush=True)

    print(f"  {OK} {G}ACTIVE{W}: {n_active}   ", end="", flush=True)
    if n_failed:
        print(f"{FAIL} {R}FAILED{W}: {n_failed}   ", end="", flush=True)
    if n_other:
        print(f"{INFO} other: {n_other}   ", end="", flush=True)
    print(flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
