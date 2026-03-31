#!/usr/bin/env python3
"""Initialise schema and (re)create all data assets. Verifies each asset after creation.

Logs everything to create_all_assets.log (including errors).

Order:
  1. create_catalog_schema.py
  2. create_checkin_metrics.sql, create_flights.sql, create_checkin_agents.sql, create_border_officers.sql, create_border_terminals.sql
  3. create_genie_space.py
  4. All *.sql in data/proc

Usage: uv run python data/init/create_all_assets.py
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
LOG_FILE = ROOT / "create_all_assets.log"

INIT_SQL = [
    "data/init/create_checkin_metrics.sql",
    "data/init/create_flights.sql",
    "data/init/create_checkin_agents.sql",
    "data/init/create_border_officers.sql",
    "data/init/create_border_terminals.sql",
]

TABLES_TO_VERIFY = ["checkin_metrics", "flights", "checkin_agents", "border_officers", "border_terminals"]

# ANSI (same as init_check_dbx_env.py)
R, G, Y, B, M, C, W = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m", "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
OK, FAIL, WARN = f"{G}✓{W}", f"{R}✗{W}", f"{Y}⚠{W}"
BAR_FILL, BAR_EMPTY = "█", "░"

_step_stop = threading.Event()


def _log_plain(msg: str) -> None:
    """Append plain text to log file (no ANSI)."""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(re.sub(r"\033\[[0-9;]*m", "", msg) + "\n")


def _step_bar_loop(step_name: str, current: int, total: int, width: int = 20) -> None:
    """Animate per-step progress bar (indeterminate) while step runs."""
    i = 0
    step_count = f" {C}({current}/{total}){W}" if total > 0 else ""
    while not _step_stop.is_set():
        pos = i % (width + 2) - 1
        bar_chars = [BAR_EMPTY] * width
        if 0 <= pos < width:
            bar_chars[pos] = BAR_FILL
        bar = "".join(bar_chars)
        line = f"\r  {DIM}[{W}{G}{bar}{W}{DIM}]{W} {step_name}{step_count}{W}"
        print(line, end="", flush=True)
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
    print("\r\033[K", end="")  # clear bar line (cursor to end)
    if r.stdout:
        out = r.stdout.strip()
        if name == "create_catalog_schema":
            for line in out.splitlines():
                print(f"  {C}{line}{W}")
                _log_plain(line)
        else:
            _log_plain(out)
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


def verify_assets() -> bool:
    """Verify catalog, schema, tables, Genie space exist. Returns True if all ok."""
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env.local", override=True)
    spec = os.environ.get("AMADEUS_UNITY_CATALOG_SCHEMA", "").strip()
    if "." not in spec:
        print(f"  {FAIL} AMADEUS_UNITY_CATALOG_SCHEMA not set{W}")
        _log_plain("FAIL verify: AMADEUS_UNITY_CATALOG_SCHEMA not set")
        return False

    catalog, schema = spec.split(".", 1)
    full_schema = f"{catalog}.{schema}"
    ok = True

    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()

        # Catalog
        try:
            w.catalogs.get(name=catalog)
            print(f"  {OK} catalog {C}({catalog}){W}")
            _log_plain(f"OK verify catalog: {catalog}")
        except Exception as e:
            print(f"  {FAIL} catalog {C}({e}){W}")
            _log_plain(f"FAIL verify catalog {catalog}: {e}")
            ok = False

        # Schema
        try:
            w.schemas.get(full_name=full_schema)
            print(f"  {OK} schema {C}({full_schema}){W}")
            _log_plain(f"OK verify schema: {full_schema}")
        except Exception as e:
            print(f"  {FAIL} schema {C}({e}){W}")
            _log_plain(f"FAIL verify schema {full_schema}: {e}")
            ok = False

        # Tables
        for name in TABLES_TO_VERIFY:
            full_name = f"{full_schema}.{name}"
            try:
                w.tables.get(full_name)
                print(f"  {OK} {name} {C}({full_name}){W}")
                _log_plain(f"OK verify table: {full_name}")
            except Exception as e:
                print(f"  {FAIL} {name} {C}({e}){W}")
                _log_plain(f"FAIL verify table {full_name}: {e}")
                ok = False

        # Genie space (if env set)
        space_id = os.environ.get("AMADEUS_GENIE_CHECKIN", "").strip()
        if space_id:
            try:
                space = w.genie.get_space(space_id=space_id)
                print(f"  {OK} Genie space {C}({getattr(space, 'title', space_id)}){W}")
                _log_plain(f"OK verify genie space: {getattr(space, 'title', space_id)}")
            except Exception as e:
                print(f"  {FAIL} Genie space {C}({e}){W}")
                _log_plain(f"FAIL verify genie space {space_id}: {e}")
                ok = False

    except Exception as e:
        print(f"  {FAIL} {e}{W}")
        _log_plain(f"FAIL verify setup: {e}")
        ok = False

    return ok


def main() -> None:
    proc_dir = ROOT / "data" / "proc"
    proc_sql = sorted(proc_dir.glob("*.sql"))
    total_steps = 1 + len(INIT_SQL) + 1 + len(proc_sql) + 1

    print(f"\n{BOLD}{M}╔══════════════════════════════════════════╗{W}")
    print(f"{BOLD}{M}║  Create All Assets                       ║{W}")
    print(f"{BOLD}{M}╚══════════════════════════════════════════╝{W}\n")
    _log_plain(f"=== create_all_assets started {datetime.now().isoformat()} ===")

    step = 0
    step += 1
    if not run_step("create_catalog_schema", ["uv", "run", "python", "data/init/create_catalog_schema.py"], step, total_steps):
        print(f"\n  {FAIL} Aborting after create_catalog_schema failed{W}")
        _log_plain("Aborting after create_catalog_schema failed")
        sys.exit(1)

    for sql in INIT_SQL:
        step += 1
        if not run_step(f"run_sql {sql}", ["uv", "run", "python", "data/run_sql.py", sql], step, total_steps):
            sys.exit(1)

    step += 1
    if not run_step("create_genie_space", ["uv", "run", "python", "data/init/create_genie_space.py"], step, total_steps):
        sys.exit(1)

    for sql_path in proc_sql:
        step += 1
        rel = str(sql_path.relative_to(ROOT))
        if not run_step(f"run_sql {rel}", ["uv", "run", "python", "data/run_sql.py", rel], step, total_steps):
            sys.exit(1)

    step += 1
    section("verification", step, total_steps)
    if not verify_assets():
        print(f"\n  {FAIL} Verification failed. See {LOG_FILE}{W}")
        _log_plain(f"Verification failed. See {LOG_FILE}")
        sys.exit(1)

    print(f"\n  {OK} {G}create_all_assets completed{W}\n")
    _log_plain("=== create_all_assets completed ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {WARN} Interrupted by user{W}")
        _log_plain("Interrupted by user (Ctrl+C)")
        sys.exit(130)
    except Exception as e:
        print(f"\n  {FAIL} Fatal error: {e}{W}")
        _log_plain(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
