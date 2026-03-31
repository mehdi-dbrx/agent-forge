#!/usr/bin/env python3
"""Create (or replace) all UC SQL functions from data/func/*.sql.

Only files that contain a CREATE statement are executed (SELECT-only
query templates are skipped automatically).

Runs each SQL file through data/py/run_sql.py which handles
__SCHEMA_QUALIFIED__ substitution and Databricks auth.

Usage: uv run python data/init/create_all_functions.py
"""
import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
LOG_FILE = ROOT / "create_all_functions.log"

R, G, Y, B, M, C, W = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m", "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
OK, FAIL, WARN = f"{G}✓{W}", f"{R}✗{W}", f"{Y}⚠{W}"
BAR_FILL, BAR_EMPTY = "█", "░"

_step_stop = threading.Event()


def _log_plain(msg: str) -> None:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(re.sub(r"\033\[[0-9;]*m", "", msg) + "\n")


def _step_bar_loop(step_name: str, current: int, total: int, width: int = 20) -> None:
    i = 0
    step_count = f" {C}({current}/{total}){W}" if total > 0 else ""
    while not _step_stop.is_set():
        pos = i % (width + 2) - 1
        bar_chars = [BAR_EMPTY] * width
        if 0 <= pos < width:
            bar_chars[pos] = BAR_FILL
        bar = "".join(bar_chars)
        print(f"\r  {DIM}[{W}{G}{''.join(bar_chars)}{W}{DIM}]{W} {step_name}{step_count}{W}", end="", flush=True)
        i += 1
        _step_stop.wait(0.06)


def section(title: str, current: int = 0, total: int = 0) -> None:
    step_count = f" {DIM}({current}/{total}){W}" if total > 0 else ""
    s = f"\n{BOLD}{B}═══ {title}{step_count} ═══{W}"
    print(s)
    _log_plain(s)


def run_step(name: str, cmd: list[str], current: int = 0, total: int = 0) -> bool:
    section(name, current, total)
    _log_plain(f"Running: {' '.join(cmd)}")
    _step_stop.clear()
    bar_thread = threading.Thread(target=_step_bar_loop, args=(name, current, total, 20), daemon=True)
    bar_thread.start()
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    finally:
        _step_stop.set()
        bar_thread.join(timeout=0.5)
    print("\r\033[K", end="")
    if r.stdout:
        _log_plain(r.stdout.strip())
    if r.stderr:
        _log_plain(f"stderr: {r.stderr.strip()}")
    if r.returncode != 0:
        err = f"  {FAIL} {name} (exit {r.returncode}): {r.stderr.strip() or r.stdout.strip()}{W}"
        print(err)
        _log_plain(err)
        return False
    print(f"  {OK} {name}{W}")
    _log_plain(f"OK {name}")
    return True


def _is_ddl(sql_path: Path) -> bool:
    """Return True if the SQL file contains a CREATE statement (DDL, not a query template)."""
    content = sql_path.read_text()
    return bool(re.search(r"\bCREATE\b", content, re.IGNORECASE))


def main() -> None:
    func_dir = ROOT / "data" / "func"
    all_sql = sorted(func_dir.glob("*.sql"))
    ddl_sql = [p for p in all_sql if _is_ddl(p)]
    skipped = len(all_sql) - len(ddl_sql)

    print(f"\n{BOLD}{M}╔══════════════════════════════════════════╗{W}")
    print(f"{BOLD}{M}║  Create All Functions                    ║{W}")
    print(f"{BOLD}{M}╚══════════════════════════════════════════╝{W}\n")
    _log_plain(f"=== create_all_functions started {datetime.now().isoformat()} ===")

    if skipped:
        print(f"  {DIM}Skipping {skipped} query template(s) without CREATE statement{W}")

    if not ddl_sql:
        print(f"  {WARN} No CREATE function SQL files found in {func_dir.relative_to(ROOT)}{W}")
        return

    total = len(ddl_sql)
    for i, sql_path in enumerate(ddl_sql, 1):
        rel = str(sql_path.relative_to(ROOT))
        if not run_step(rel, ["uv", "run", "python", "data/py/run_sql.py", rel], i, total):
            print(f"\n  {FAIL} Aborting after {rel} failed{W}")
            _log_plain(f"Aborting after {rel} failed")
            sys.exit(1)

    print(f"\n  {OK} {G}All functions created ({total}){W}\n")
    _log_plain("=== create_all_functions completed ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {WARN} Interrupted by user{W}")
        sys.exit(130)
    except Exception as e:
        print(f"\n  {FAIL} Fatal error: {e}{W}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
