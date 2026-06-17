#!/usr/bin/env python3
"""Initialise schema and (re)create all data assets. Verifies each asset after creation.

Logs everything to create_all_assets.log (including errors).

Order:
  1. create_catalog_schema.py
  2. create_<table>.sql for each CSV in data/demo/csv/ + data/gen/csv/ (derived dynamically)
  3. create_genie_space.py
  4. All *.sql in data/demo/proc

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
LOG_FILE = ROOT / "logs" / "create_all_assets.log"

def _active_sources() -> list[tuple[Path, Path]]:
    """Return (csv_dir, init_dir) pairs based on USE_DEMO_DATA / USE_GEN_DATA flags.
    When FORGE_STASH_DIR is set, uses stash directory data instead of data/demo/.
    """
    stash_dir = os.environ.get("FORGE_STASH_DIR", "").strip()
    sources = []
    if stash_dir:
        stash_path = ROOT / stash_dir if not Path(stash_dir).is_absolute() else Path(stash_dir)
        sources.append((stash_path / "data" / "csv", stash_path / "data" / "init"))
    else:
        if (os.environ.get("USE_DEMO_DATA") or os.environ.get("USE_DEFAULT_DATA", "true")).strip().lower() in ("true", "1", "yes"):
            sources.append((ROOT / "data" / "demo" / "csv", ROOT / "data" / "demo" / "init"))
    # Project-scoped gen dir (takes priority)
    project_dir = os.environ.get("PROJECT_DIR", "").strip()
    if project_dir:
        p = Path(project_dir) / "gen"
        sources.append((p / "csv", p / "init"))
    elif os.environ.get("USE_GEN_DATA", "false").strip().lower() in ("true", "1", "yes"):
        sources.append((ROOT / "data" / "gen" / "csv", ROOT / "data" / "gen" / "init"))
    return sources


def _get_init_sql() -> list[str]:
    """Derive init SQL paths from active data sources."""
    paths = []
    for csv_dir, init_dir in _active_sources():
        if not csv_dir.exists():
            continue
        for csv_path in sorted(csv_dir.glob("*.csv")):
            table = csv_path.stem.replace("-", "_")
            sql_path = init_dir / f"create_{table}.sql"
            if sql_path.exists():
                paths.append(str(sql_path))
    return paths


def _get_tables_to_verify() -> list[str]:
    tables = []
    for csv_dir, _ in _active_sources():
        if csv_dir.exists():
            tables.extend(p.stem.replace("-", "_") for p in csv_dir.glob("*.csv"))
    return sorted(set(tables))


INIT_SQL = _get_init_sql()
TABLES_TO_VERIFY = _get_tables_to_verify()

# ANSI (same as setup_dbx_env.py)
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
    # Reload env after each step so subsequent steps and verification pick up freshly written values
    return True


def verify_assets() -> bool:
    """Verify catalog, schema, tables, Genie space exist. Returns True if all ok."""

    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if "." not in spec:
        print(f"  {FAIL} PROJECT_UNITY_CATALOG_SCHEMA not set{W}")
        _log_plain("FAIL verify: PROJECT_UNITY_CATALOG_SCHEMA not set")
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

        # Genie spaces from PROJECT_GENIE_SPACES
        raw_genie = os.environ.get("PROJECT_GENIE_SPACES", "").strip()
        space_id = raw_genie.split(",")[0].strip() if raw_genie else ""
        if space_id:
            try:
                space = w.genie.get_space(space_id=space_id)
                print(f"  {OK} Genie space {C}({getattr(space, 'title', space_id)}){W}")
                _log_plain(f"OK verify genie space: {getattr(space, 'title', space_id)}")
            except Exception as e:
                print(f"  {FAIL} Genie space {C}({e}){W}")
                _log_plain(f"FAIL verify genie space {space_id}: {e}")
                ok = False

        # Lakebase instance
        lakebase_name = os.environ.get("LAKEBASE_INSTANCE_NAME", "").strip()
        if lakebase_name:
            try:
                import subprocess as _sp
                _args = ["databricks", "database", "get-database-instance", lakebase_name, "--output", "json"]
                _profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
                if _profile:
                    _args += ["-p", _profile]
                _r = _sp.run(_args, capture_output=True, text=True)
                if _r.returncode == 0:
                    import json as _json
                    _data = _json.loads(_r.stdout)
                    _state = _data.get("state", "UNKNOWN")
                    print(f"  {OK} Lakebase {C}({lakebase_name} — {_state}){W}")
                    _log_plain(f"OK verify lakebase: {lakebase_name} ({_state})")
                else:
                    print(f"  {FAIL} Lakebase {C}({lakebase_name}: {_r.stderr.strip()}){W}")
                    _log_plain(f"FAIL verify lakebase {lakebase_name}: {_r.stderr.strip()}")
                    ok = False
            except Exception as e:
                print(f"  {FAIL} Lakebase {C}({e}){W}")
                _log_plain(f"FAIL verify lakebase {lakebase_name}: {e}")
                ok = False

    except Exception as e:
        print(f"  {FAIL} {e}{W}")
        _log_plain(f"FAIL verify setup: {e}")
        ok = False

    return ok


def main() -> None:
    # 1 (schema) + tables + 1 (genie) + 1 (functions) + 1 (procedures) + 1 (lakebase) + 1 (verify)
    total_steps = 1 + len(INIT_SQL) + 1 + 1 + 1 + 1 + 1

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
        if not run_step(f"run_sql {sql}", ["uv", "run", "python", "data/py/run_sql.py", sql], step, total_steps):
            sys.exit(1)

    step += 1
    if not run_step("create_genie_space", ["uv", "run", "python", "data/init/create_genie_space.py"], step, total_steps):
        sys.exit(1)

    step += 1
    if not run_step("create_all_functions", ["uv", "run", "python", "data/init/create_all_functions.py"], step, total_steps):
        sys.exit(1)

    step += 1
    if not run_step("create_all_procedures", ["uv", "run", "python", "data/init/create_all_procedures.py"], step, total_steps):
        sys.exit(1)

    step += 1
    if not run_step("create_lakebase", ["uv", "run", "python", "data/init/create_lakebase.py"], step, total_steps):
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
