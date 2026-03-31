#!/usr/bin/env python3
"""Interactive init/check of Databricks resources in .env.local.

For each resource: if not configured, prompt to enter. If configured, verify and offer
to keep, add new, or activate an inactive entry. Inactive (commented) entries are
parsed and shown; user can activate [1], [2], etc.

Usage:
  uv run python scripts/init_check_dbx_env.py       # interactive init
  uv run python scripts/init_check_dbx_env.py --check   # quick check only
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

ENV_FILE = ROOT / ".env.local"

# ANSI
R, G, Y, B, M, C, W = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m", "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
OK, FAIL, WARN = f"{G}✓{W}", f"{R}✗{W}", f"{Y}⚠{W}"

FIX_FIRST_MSG = f"\n  {WARN} This needs to be fixed first before moving forward with the other configurations.{W}\n"


def abort_step() -> None:
    """Interrupt gracefully and exit."""
    print(FIX_FIRST_MSG)
    sys.exit(1)


def section(title: str) -> None:
    print(f"\n{BOLD}{B}═══ {title} ═══{W}")


def parse_env_file(path: Path) -> tuple[dict[str, str], dict[str, list[tuple[int, str]]], list[str]]:
    """Return (active, inactive, raw_lines). active[key]=value; inactive[key]=[(line_idx, value), ...]"""
    if not path.exists():
        return {}, {}, []
    lines = path.read_text().splitlines()
    active: dict[str, str] = {}
    inactive: dict[str, list[tuple[int, str]]] = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") and "=" not in stripped.lstrip("#"):
            continue
        m = re.match(r"^#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", stripped)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip().strip("'\"").strip()
        if stripped.startswith("#"):
            inactive.setdefault(key, []).append((i, val))
        else:
            active[key] = val
    return active, inactive, lines


def write_env_entry(path: Path, key: str, value: str, comment_active: bool = False) -> None:
    """Set key=value. If comment_active, comment any existing active line and append new."""
    lines = path.read_text().splitlines() if path.exists() else []
    new_lines: list[str] = []
    replaced = False
    for line in lines:
        m = re.match(r"^(\s*)(#?\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(3) == key:
            if line.strip().startswith("#"):
                new_lines.append(line)
            elif comment_active:
                new_lines.append("#" + line.lstrip())
                new_lines.append(f"{key}={value}")
                replaced = True
            else:
                new_lines.append(f"{key}={value}")
                replaced = True
            continue
        new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines) + "\n")


def uncomment_line(path: Path, line_idx: int) -> None:
    """Uncomment the line at line_idx."""
    lines = path.read_text().splitlines()
    if 0 <= line_idx < len(lines) and lines[line_idx].strip().startswith("#"):
        lines[line_idx] = lines[line_idx].lstrip("#").lstrip()
        path.write_text("\n".join(lines) + "\n")


def comment_active_for_key(path: Path, key: str) -> None:
    """Comment the active line for key."""
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(#?\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(3) == key and not line.strip().startswith("#"):
            lines[i] = "#" + line.lstrip()
            path.write_text("\n".join(lines) + "\n")
            return


def prompt_choice(prompt: str, choices: list[str]) -> str:
    """Return choice string. choices like ['keep', 'add new', 'activate [1]']"""
    while True:
        print(f"\n  {C}{prompt}{W}")
        for i, c in enumerate(choices, 1):
            print(f"    {B}[{i}]{W} {c}")
        try:
            raw = input(f"  Choice (1-{len(choices)}): ").strip()
            idx = int(raw)
            if 1 <= idx <= len(choices):
                return choices[idx - 1]
        except (ValueError, EOFError):
            pass
        print(f"  {WARN} Invalid choice{W}")


def run_resource_warehouse() -> bool:
    """Interactive config for DATABRICKS_WAREHOUSE_ID with workspace list as choices."""
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)

    key = "DATABRICKS_WAREHOUSE_ID"
    active, inactive, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()
    inact = inactive.get(key, [])

    section("DATABRICKS_WAREHOUSE_ID")

    whs = list_warehouses()
    if whs:
        for name, wh_id in whs:
            print(f"  {C}Available :{W} {name} {DIM}({wh_id}){W}")

    ok, msg = False, ""
    if cur:
        load_env_for_key(key, cur)
        ok, msg = verify_warehouse()
        if ok:
            print(f"  {OK} Active: {C}{cur}{W} {G}({msg}){W}")
        else:
            print(f"  {FAIL} Active: {C}{cur}{W} {R}({msg}){W}")
    else:
        print(f"  {WARN} Not configured{W}")

    if inact:
        print(f"  {DIM}Inactive:{W}")
        for i, (_, val) in enumerate(inact, 1):
            print(f"    {DIM}[{i}] {val[:50]}{'...' if len(val) > 50 else ''}{W}")

    choices: list[str] = []
    if cur and ok:
        choices.append("keep")
    elif cur:
        choices.append("add new")
    else:
        choices.append("enter new")
    keep_count = len(choices)
    if whs:
        for name, wh_id in whs:
            choices.append(f"Available : {name} ({wh_id})")
        choices.append("enter ID manually")
    for i in range(1, len(inact) + 1):
        choices.append(f"activate [{i}]")
    if not choices:
        choices = ["enter new"]

    while True:
        print(f"\n  {C}Action?{W}")
        for i, c in enumerate(choices, 1):
            print(f"    {B}[{i}]{W} {c}")
        try:
            raw = input(f"  Choice (1-{len(choices)}): ").strip()
            idx = int(raw)
            if 1 <= idx <= len(choices):
                choice = choices[idx - 1]
                break
        except (ValueError, EOFError):
            pass
        print(f"  {WARN} Invalid choice{W}")

    if choice == "keep":
        return True
    if choice.startswith("activate ["):
        num = int(choice.split("[")[1].rstrip("]"))
        if 1 <= num <= len(inact):
            line_idx = inact[num - 1][0]
            comment_active_for_key(ENV_FILE, key)
            uncomment_line(ENV_FILE, line_idx)
            load_dotenv(ENV_FILE, override=True)
            load_env_for_key(key, inact[num - 1][1])
            ok, msg = verify_warehouse()
            if ok:
                print(f"  {OK} Activated and verified: {msg}{W}")
            else:
                print(f"  {FAIL} Activated but verify failed: {msg}{W}")
                abort_step()
        return True

    # Pick from list or manual
    wh_choices = [f"Available : {n} ({i})" for n, i in whs]
    if choice in wh_choices:
        val = whs[wh_choices.index(choice)][1]
    else:
        val = input(f"  Enter {key}: ").strip()
    if not val:
        return True
    if cur:
        comment_active_for_key(ENV_FILE, key)
    write_env_entry(ENV_FILE, key, val)
    load_dotenv(ENV_FILE, override=True)
    load_env_for_key(key, val)
    ok, msg = verify_warehouse()
    if ok:
        print(f"  {OK} Set and verified: {msg}{W}")
    else:
        print(f"  {FAIL} Set but verify failed: {msg}{W}")
        abort_step()
    return True


def run_resource_profile() -> bool:
    """Interactive config for DATABRICKS_CONFIG_PROFILE with CLI profile list as choices."""
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)

    key = "DATABRICKS_CONFIG_PROFILE"
    active, inactive, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()
    inact = inactive.get(key, [])

    section("DATABRICKS_CONFIG_PROFILE")

    profiles = list_dbx_profiles()
    if profiles:
        for name, valid in profiles:
            status = f"{G}[valid]{W}" if valid else f"{DIM}[invalid]{W}"
            print(f"  {C}Available :{W} {name} {status}")
    else:
        print(f"  {DIM}No profiles found (databricks auth profiles){W}")

    ok, msg = False, ""
    if cur:
        load_env_for_key(key, cur)
        ok, msg = verify_host_token()
        if ok:
            print(f"  {OK} Active: {C}{cur}{W} {G}({msg}){W}")
        else:
            print(f"  {FAIL} Active: {C}{cur}{W} {R}({msg}){W}")
    else:
        print(f"  {WARN} Not configured{W}")

    if inact:
        print(f"  {DIM}Inactive:{W}")
        for i, (_, val) in enumerate(inact, 1):
            print(f"    {DIM}[{i}] {val}{W}")

    choices: list[str] = []
    if cur and ok:
        choices.append("keep")
    valid_profiles = [(n, v) for n, v in profiles if v]
    invalid_profiles = [(n, v) for n, v in profiles if not v]
    for name, _ in valid_profiles:
        choices.append(f"[+] {name}")
    for name, _ in invalid_profiles:
        choices.append(f"[-] {name}")
    choices.append("enter manually")
    for i in range(1, len(inact) + 1):
        choices.append(f"activate [{i}]")
    if not choices:
        choices = ["enter manually"]

    while True:
        print(f"\n  {C}Action?{W}")
        for i, c in enumerate(choices, 1):
            print(f"    {B}[{i}]{W} {c}")
        try:
            raw = input(f"  Choice (1-{len(choices)}): ").strip()
            idx = int(raw)
            if 1 <= idx <= len(choices):
                choice = choices[idx - 1]
                break
        except (ValueError, EOFError):
            pass
        print(f"  {WARN} Invalid choice{W}")

    if choice == "keep":
        return True
    if choice.startswith("activate ["):
        num = int(choice.split("[")[1].rstrip("]"))
        if 1 <= num <= len(inact):
            line_idx = inact[num - 1][0]
            comment_active_for_key(ENV_FILE, key)
            uncomment_line(ENV_FILE, line_idx)
            load_dotenv(ENV_FILE, override=True)
            load_env_for_key(key, inact[num - 1][1])
            ok, msg = verify_host_token()
            if ok:
                print(f"  {OK} Activated and verified: {msg}{W}")
            else:
                print(f"  {FAIL} Activated but verify failed: {msg}{W}")
                abort_step()
        return True

    # Pick from profile list or enter manually
    profile_choices = [f"[+] {n}" for n, _ in valid_profiles] + [f"[-] {n}" for n, _ in invalid_profiles]
    if choice in profile_choices:
        val = choice.split("] ", 1)[1]
    else:
        val = input(f"  Enter profile name: ").strip()
    if not val:
        return True
    if cur:
        comment_active_for_key(ENV_FILE, key)
    write_env_entry(ENV_FILE, key, val)
    load_dotenv(ENV_FILE, override=True)
    load_env_for_key(key, val)
    ok, msg = verify_host_token()
    if ok:
        print(f"  {OK} Set and verified: {msg}{W}")
    else:
        print(f"  {FAIL} Set but verify failed: {msg}{W}")
        abort_step()
    return True


def run_resource_genie() -> bool:
    """Interactive config for PROJECT_GENIE_CHECKIN with Genie space list as choices."""
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)

    key = "PROJECT_GENIE_CHECKIN"
    active, inactive, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()
    inact = inactive.get(key, [])

    section("PROJECT_GENIE_CHECKIN")

    spaces = list_genie_spaces()
    if spaces:
        for title, space_id in spaces:
            print(f"  {C}Available :{W} {title} {DIM}({space_id}){W}")

    ok, msg = False, ""
    if cur:
        load_env_for_key(key, cur)
        ok, msg = verify_genie()
        if ok:
            print(f"  {OK} Active: {C}{cur}{W} {G}({msg}){W}")
        else:
            print(f"  {FAIL} Active: {C}{cur}{W} {R}({msg}){W}")
    else:
        print(f"  {WARN} Not configured{W}")

    if inact:
        print(f"  {DIM}Inactive:{W}")
        for i, (_, val) in enumerate(inact, 1):
            print(f"    {DIM}[{i}] {val[:50]}{'...' if len(val) > 50 else ''}{W}")

    choices: list[str] = []
    if cur and ok:
        choices.append("keep")
    if spaces:
        for title, space_id in spaces:
            choices.append(f"Available : {title} ({space_id})")
    choices.append("enter space ID")
    choices.append("Create Genie Room")
    for i in range(1, len(inact) + 1):
        choices.append(f"activate [{i}]")

    # When no spaces from API: still show choices (enter space ID, Create Genie Room)
    # Don't block - list_spaces can return empty due to permissions/API behavior
    choice = prompt_choice("Action?", choices)

    if choice == "keep":
        return True
    if choice == "Create Genie Room":
        try:
            room_name = input(f"  {C}Genie room name: {W}").strip()
            if not room_name:
                print(f"  {WARN} No name entered. Skipped.{W}\n")
                return True
            env = {**os.environ, "GENIE_ROOM_NAME": room_name}
            print(f"  {B}Creating Genie space '{room_name}' ...{W}\n")
            rc = subprocess.call(
                ["uv", "run", "python", "data/init/create_genie_space.py"],
                cwd=ROOT,
                env=env,
            )
            if rc == 0:
                load_dotenv(ENV_FILE, override=True)
                new_id = os.environ.get(key, "").strip()
                if new_id:
                    print(f"\n  {OK} {G}Genie Room created: {new_id}{W}\n")
                else:
                    print(f"\n  {OK} {G}Genie Room created. Re-run to verify.{W}\n")
            else:
                print(f"\n  {FAIL} Genie creation exited with {rc}{W}\n")
                abort_step()
        except (EOFError, KeyboardInterrupt):
            print(f"  {DIM}Skipped{W}\n")
        return True
    if choice.startswith("activate ["):
        num = int(choice.split("[")[1].rstrip("]"))
        if 1 <= num <= len(inact):
            line_idx = inact[num - 1][0]
            comment_active_for_key(ENV_FILE, key)
            uncomment_line(ENV_FILE, line_idx)
            load_dotenv(ENV_FILE, override=True)
            load_env_for_key(key, inact[num - 1][1])
            ok, msg = verify_genie()
            if ok:
                print(f"  {OK} Activated and verified: {msg}{W}")
            else:
                print(f"  {FAIL} Activated but verify failed: {msg}{W}")
                abort_step()
        return True

    # Pick from list or manual
    space_choices = [f"Available : {t} ({i})" for t, i in spaces]
    if choice in space_choices:
        val = spaces[space_choices.index(choice)][1]
    else:
        val = input(f"  Enter {key}: ").strip()
    if not val:
        return True
    if cur:
        comment_active_for_key(ENV_FILE, key)
    write_env_entry(ENV_FILE, key, val)
    load_dotenv(ENV_FILE, override=True)
    load_env_for_key(key, val)
    ok, msg = verify_genie()
    if ok:
        print(f"  {OK} Set and verified: {msg}{W}")
    else:
        print(f"  {FAIL} Set but verify failed: {msg}{W}")
        abort_step()
    return True


def verify_host_only() -> tuple[bool, str]:
    """Verify DATABRICKS_HOST is set and looks like a URL."""
    host = os.environ.get("DATABRICKS_HOST", "").strip()
    if not host:
        return False, "not set"
    if not host.startswith("https://") and not host.startswith("http://"):
        return False, "should be https://... or http://..."
    return True, host


def verify_host_token() -> tuple[bool, str]:
    """Verify DATABRICKS_HOST + token/profile work. Return (ok, msg)."""
    host = os.environ.get("DATABRICKS_HOST", "").strip()
    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "").strip()
    if not host:
        return False, "DATABRICKS_HOST not set"
    if not token and not profile:
        return False, "Need DATABRICKS_TOKEN or DATABRICKS_CONFIG_PROFILE"
    try:
        from databricks.sdk import WorkspaceClient
        WorkspaceClient()
        return True, "Connection OK"
    except Exception as e:
        return False, str(e)


def verify_warehouse() -> tuple[bool, str]:
    wh = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
    if not wh:
        return False, "not set"
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        wh_obj = w.warehouses.get(wh)
        return True, getattr(wh_obj, "name", wh)
    except Exception as e:
        return False, str(e)


def list_warehouses() -> list[tuple[str, str]]:
    """Return [(name, id), ...] for warehouses in workspace."""
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        whs = list(w.warehouses.list())
        return [(getattr(wh, "name", "") or str(wh.id), str(wh.id)) for wh in whs]
    except Exception:
        return []


def list_dbx_profiles() -> list[tuple[str, bool]]:
    """Return [(name, valid), ...] from `databricks auth profiles`."""
    try:
        result = subprocess.run(
            ["databricks", "auth", "profiles"],
            capture_output=True, text=True, timeout=10,
        )
        profiles = []
        for line in result.stdout.splitlines()[1:]:  # skip header
            parts = line.split()
            if len(parts) >= 3:
                name = parts[0]
                valid = parts[-1].upper() == "YES"
                profiles.append((name, valid))
        return profiles
    except Exception:
        return []


def list_genie_spaces() -> list[tuple[str, str]]:
    """Return [(title, space_id), ...] for Genie spaces in workspace."""
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        r = w.genie.list_spaces()
        spaces = getattr(r, "spaces", []) or []
        return [
            (getattr(s, "title", "") or "?", str(getattr(s, "space_id", None) or getattr(s, "id", "") or ""))
            for s in spaces
        ]
    except Exception:
        return []


def get_csv_tables() -> list[str]:
    """Return table names derived from data/csv/*.csv (stem, - replaced with _)."""
    csv_dir = ROOT / "data" / "csv"
    if not csv_dir.exists():
        return []
    return sorted(p.stem.replace("-", "_") for p in csv_dir.glob("*.csv"))


TABLES_TO_VERIFY = get_csv_tables()


def _infer_sql_type(col: str) -> str:
    low = col.lower()
    if any(k in low for k in ("time", "date", "timestamp", "at", "created", "updated")):
        return "TIMESTAMP_NTZ"
    if any(k in low for k in ("id",)):
        return "BIGINT"
    return "STRING"


def _generate_create_sql(table: str, csv_path: Path) -> str:
    """Generate a CREATE OR REPLACE TABLE stub from CSV header."""
    import csv as csv_mod
    from io import StringIO
    header = csv_path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    if header:
        row = next(csv_mod.reader(StringIO(header[0])))
        col_defs = ",\n".join(f"    {c} {_infer_sql_type(c)}" for c in row)
    else:
        col_defs = "    -- no columns detected"
    return (
        f"CREATE OR REPLACE TABLE __SCHEMA_QUALIFIED__.{table} (\n"
        f"{col_defs}\n"
        f")\n"
        f"USING DELTA\n"
        f"TBLPROPERTIES (delta.enableChangeDataFeed = true);\n"
    )


def ensure_init_sql_files() -> list[Path]:
    """Check data/csv/*.csv against data/init/create_<table>.sql. Generate stubs for missing ones.
    Returns list of all init SQL paths (existing + newly created)."""
    csv_dir = ROOT / "data" / "csv"
    init_dir = ROOT / "data" / "init"
    if not csv_dir.exists():
        return []
    csvs = sorted(csv_dir.glob("*.csv"))
    if not csvs:
        return []

    print(f"\n  {C}Checking SQL init files for {len(csvs)} CSV(s):{W}")
    sql_paths: list[Path] = []
    for csv_path in csvs:
        table = csv_path.stem.replace("-", "_")
        sql_path = init_dir / f"create_{table}.sql"
        if sql_path.exists():
            print(f"  [+] {sql_path.relative_to(ROOT)}  {DIM}(exists){W}")
        else:
            content = _generate_create_sql(table, csv_path)
            sql_path.write_text(content)
            print(f"  [+] {sql_path.relative_to(ROOT)}  {G}(generated){W}")
        sql_paths.append(sql_path)
    return sql_paths


def print_asset_checks() -> None:
    """Print catalog, schema, tables, volume checks (same as create_all_assets, excluding Genie)."""
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if "." not in spec:
        return
    catalog, schema_name = spec.split(".", 1)
    full_schema = f"{catalog}.{schema_name}"
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        try:
            w.catalogs.get(name=catalog)
            print(f"  {OK} catalog {C}({catalog}){W}")
        except Exception as e:
            print(f"  {FAIL} catalog {C}({e}){W}")
        try:
            w.schemas.get(full_name=full_schema)
            print(f"  {OK} schema {C}({full_schema}){W}")
        except Exception as e:
            print(f"  {FAIL} schema {C}({e}){W}")
        for name in TABLES_TO_VERIFY:
            full_name = f"{full_schema}.{name}"
            try:
                w.tables.get(full_name)
                print(f"  {OK} {name} {C}({full_name}){W}")
            except Exception as e:
                print(f"  {FAIL} {name} {C}({e}){W}")
    except Exception as e:
        print(f"  {FAIL} assets {C}({e}){W}")


def verify_schema() -> tuple[bool, str]:
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if "." not in spec:
        return False, "need catalog.schema"
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        w.schemas.get(full_name=spec)
        return True, spec
    except Exception as e:
        return False, str(e)


def verify_tables() -> tuple[bool, str]:
    """Verify checkin_metrics, flights, checkin_agents, border_officers, border_terminals exist. Return (ok, msg)."""
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if "." not in spec:
        return False, "PROJECT_UNITY_CATALOG_SCHEMA not set"
    catalog, schema_name = spec.split(".", 1)
    full_schema = f"{catalog}.{schema_name}"
    tables = TABLES_TO_VERIFY
    missing = []
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        for name in tables:
            try:
                w.tables.get(full_name=f"{full_schema}.{name}")
            except Exception:
                missing.append(name)
        if missing:
            return False, f"missing: {', '.join(missing)}"
        return True, full_schema
    except Exception as e:
        return False, str(e)


def verify_genie() -> tuple[bool, str]:
    sid = os.environ.get("PROJECT_GENIE_CHECKIN", "").strip()
    if not sid:
        return False, "not set"
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        sp = w.genie.get_space(space_id=sid)
        return True, getattr(sp, "title", sid)
    except Exception as e:
        return False, str(e)


def run_resource_mlflow() -> bool:
    """Interactive config for MLFLOW_EXPERIMENT_ID with keep, enter ID manually, create new experiment."""
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)

    key = "MLFLOW_EXPERIMENT_ID"
    active, inactive, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()
    inact = inactive.get(key, [])

    section("MLFLOW_EXPERIMENT_ID")

    ok, msg = False, ""
    if cur:
        load_env_for_key(key, cur)
        ok, msg = verify_mlflow()
        if ok:
            print(f"  {OK} Active: {C}{cur}{W} {G}({msg}){W}")
        else:
            print(f"  {FAIL} Active: {C}{cur}{W} {R}({msg}){W}")
    else:
        print(f"  {WARN} Not configured{W}")

    if inact:
        print(f"  {DIM}Inactive:{W}")
        for i, (_, val) in enumerate(inact, 1):
            print(f"    {DIM}[{i}] {val[:50]}{'...' if len(val) > 50 else ''}{W}")

    choices: list[str] = []
    if cur and ok:
        choices.append("keep")
    choices.append("enter ID manually")
    choices.append("create new experiment")
    for i in range(1, len(inact) + 1):
        choices.append(f"activate [{i}]")

    choice = prompt_choice("Action?", choices)

    if choice == "keep":
        return True
    if choice == "create new experiment":
        try:
            print(f"  {B}Creating MLflow experiment ...{W}\n")
            rc = subprocess.call(
                ["uv", "run", "python", "data/init/create_mlflow_experiment.py"],
                cwd=ROOT,
            )
            if rc == 0:
                load_dotenv(ENV_FILE, override=True)
                new_id = os.environ.get(key, "").strip()
                if new_id:
                    print(f"\n  {OK} {G}MLflow experiment created: {new_id}{W}\n")
                else:
                    print(f"\n  {OK} {G}MLflow experiment created. Re-run to verify.{W}\n")
            else:
                print(f"\n  {FAIL} MLflow creation exited with {rc}{W}\n")
                abort_step()
        except (EOFError, KeyboardInterrupt):
            print(f"  {DIM}Skipped{W}\n")
        return True
    if choice.startswith("activate ["):
        num = int(choice.split("[")[1].rstrip("]"))
        if 1 <= num <= len(inact):
            line_idx = inact[num - 1][0]
            comment_active_for_key(ENV_FILE, key)
            uncomment_line(ENV_FILE, line_idx)
            load_dotenv(ENV_FILE, override=True)
            load_env_for_key(key, inact[num - 1][1])
            ok, msg = verify_mlflow()
            if ok:
                print(f"  {OK} Activated and verified: {msg}{W}")
            else:
                print(f"  {FAIL} Activated but verify failed: {msg}{W}")
                abort_step()
        return True

    # enter ID manually
    val = input(f"  Enter {key}: ").strip()
    if not val:
        return True
    if cur:
        comment_active_for_key(ENV_FILE, key)
    write_env_entry(ENV_FILE, key, val)
    load_dotenv(ENV_FILE, override=True)
    load_env_for_key(key, val)
    ok, msg = verify_mlflow()
    if ok:
        print(f"  {OK} Set and verified: {msg}{W}")
    else:
        print(f"  {FAIL} Set but verify failed: {msg}{W}")
        abort_step()
    return True


def verify_mlflow() -> tuple[bool, str]:
    eid = os.environ.get("MLFLOW_EXPERIMENT_ID", "").strip()
    if not eid:
        return False, "not set"
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        exp = w.experiments.get_experiment(experiment_id=eid)
        return True, getattr(exp, "name", eid)
    except Exception as e:
        return False, str(e)


def verify_app_grants() -> tuple[bool, list[str]]:
    """Verify all grants from run_all_grants.sh are effective for the app service principal.
    Returns (ok, list of issue messages).
    """
    from tools.sql_executor import execute_query, get_warehouse

    app_name = os.environ.get("DBX_APP_NAME", "").strip()
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    wh_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()

    issues: list[str] = []

    if not app_name:
        return False, ["DBX_APP_NAME not set"]
    if "." not in spec:
        return False, ["PROJECT_UNITY_CATALOG_SCHEMA not set (need catalog.schema)"]
    catalog, schema_name = spec.split(".", 1)

    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        w_client, wh_id_sql = get_warehouse()

        # Get app service principal ID
        try:
            app = w.apps.get(name=app_name)
        except Exception as e:
            return False, [f"App '{app_name}' not yet deployed — grants will be applied after deployment, then re-run to verify"]

        sp_id = getattr(app, "service_principal_client_id", None) or getattr(
            app, "oauth2_app_client_id", None
        )
        if not sp_id:
            return False, [f"App '{app_name}' has no service_principal_client_id"]

        # 1. Check UC catalog/schema/table privileges (run_all_grants: grant_app_tables)
        table_priv_sql = f"""
        SELECT table_name, privilege_type
        FROM `{catalog}`.information_schema.table_privileges
        WHERE table_schema = '{schema_name}' AND grantee = '{sp_id}'
        """
        try:
            _, table_rows = execute_query(w_client, wh_id_sql, table_priv_sql)
        except Exception as e:
            issues.append(f"UC table privileges: could not verify ({e})")
        else:
            granted_tables = {
                r[0]
                for r in table_rows
                if r[1] and ("SELECT" in r[1] or "ALL PRIVILEGES" in r[1])
            }
            for t in TABLES_TO_VERIFY:
                if t not in granted_tables:
                    issues.append(f"Table {t}: app has no SELECT/ALL_PRIVILEGES")
            if not table_rows and TABLES_TO_VERIFY:
                issues.append("UC tables: app has no table privileges")

        # 2. Check UC routine privileges (run_all_grants: grant_app_functions)
        routine_priv_sql = f"""
        SELECT routine_name, privilege_type
        FROM `{catalog}`.information_schema.routine_privileges
        WHERE routine_schema = '{schema_name}' AND grantee = '{sp_id}'
        """
        try:
            _, routine_rows = execute_query(w_client, wh_id_sql, routine_priv_sql)
        except Exception as e:
            issues.append(f"UC routine privileges: could not verify ({e})")
        else:
            has_execute = any(r[1] and "EXECUTE" in r[1] for r in routine_rows)
            if not has_execute:
                issues.append("UC routines: app has no EXECUTE on procedures")

        # 3. Check warehouse CAN_USE (run_all_grants: authorize_warehouse_for_app)
        if not wh_id:
            issues.append("DATABRICKS_WAREHOUSE_ID not set")
        else:
            try:
                perm = w.permissions.get(
                    request_object_type="warehouses",
                    request_object_id=wh_id,
                )
                acl = getattr(perm, "access_control_list", []) or []
                has_can_use = False
                for entry in acl:
                    plevel = str(getattr(entry, "permission_level", "") or "")
                    if "CAN_USE" not in plevel.upper():
                        continue
                    sp_name = str(getattr(entry, "service_principal_name", "") or "")
                    sp_id_attr = str(getattr(entry, "service_principal_id", "") or "")
                    if sp_id in (sp_name, sp_id_attr) or sp_id in sp_name:
                        has_can_use = True
                        break
                if not has_can_use:
                    issues.append(f"Warehouse {wh_id}: app has no CAN_USE")
            except Exception as e:
                issues.append(f"Warehouse permissions: could not verify ({e})")

        return len(issues) == 0, issues

    except Exception as e:
        return False, [str(e)]


def load_env_for_key(key: str, value: str) -> None:
    os.environ[key] = value


def run_resource(
    key: str,
    label: str,
    verify_fn,
    prompt_hint: str = "",
    value_choices_fn=None,
) -> bool:
    """Interactive config for one resource. Returns True to continue."""
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)

    active, inactive, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()
    inact = inactive.get(key, [])

    section(label)
    if key == "PROJECT_UNITY_CATALOG_SCHEMA":
        load_env_for_key(key, cur or "")
        print_asset_checks()
    ok, msg = False, ""
    if cur:
        load_env_for_key(key, cur)
        ok, msg = verify_fn()
        if ok:
            print(f"  {OK} Active: {C}{cur[:50]}{'...' if len(cur) > 50 else ''}{W} {G}({msg}){W}")
        else:
            print(f"  {FAIL} Active: {C}{cur[:50]}{'...' if len(cur) > 50 else ''}{W} {R}({msg}){W}")
    else:
        print(f"  {WARN} Not configured{W}")

    if inact:
        print(f"  {DIM}Inactive:{W}")
        for i, (_, val) in enumerate(inact, 1):
            print(f"    {DIM}[{i}] {val[:50]}{'...' if len(val) > 50 else ''}{W}")

    ADD_NEW_CATALOG = "add new catalog (this will create all related assets)"
    CREATE_ASSETS_NOW = "create all assets now"
    KEEP_AND_CREATE_ASSETS = "keep + create all missing assets"
    choices: list[str] = []
    tables_ok = True
    if key == "PROJECT_UNITY_CATALOG_SCHEMA" and cur:
        tables_ok, _ = verify_tables()
    if cur and ok:
        if key == "PROJECT_UNITY_CATALOG_SCHEMA":
            choices = ["keep", ADD_NEW_CATALOG]
            if not tables_ok:
                choices.insert(1, KEEP_AND_CREATE_ASSETS)
        else:
            choices = ["keep", "add new"]
    elif cur and key == "PROJECT_UNITY_CATALOG_SCHEMA":
        choices = [CREATE_ASSETS_NOW, ADD_NEW_CATALOG]
    elif cur:
        choices = ["add new"]
    else:
        choices = [ADD_NEW_CATALOG] if key == "PROJECT_UNITY_CATALOG_SCHEMA" else ["enter new"]
    for i, (_, val) in enumerate(inact, 1):
        choices.append(f"activate [{i}]")
    if not choices:
        choices = ["enter new"]

    # Schema invalid and only add-new-catalog (no cur) → run create_all_assets (mandatory)
    if key == "PROJECT_UNITY_CATALOG_SCHEMA" and choices == [ADD_NEW_CATALOG]:
        hint = " (catalog.schema)"
        val = input(f"  Enter {key}{hint}: ").strip()
        if not val:
            abort_step()
        if cur:
            comment_active_for_key(ENV_FILE, key)
        write_env_entry(ENV_FILE, key, val)
        load_dotenv(ENV_FILE, override=True)
        load_env_for_key(key, val)
        print(f"  {B}Creating schema, tables, volume, Genie ...{W}\n")
        rc = subprocess.call(
            ["uv", "run", "python", "data/init/create_all_assets.py"],
            cwd=ROOT,
        )
        if rc == 0:
            print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
        else:
            print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
            abort_step()
        return True

    # Genie invalid and only "add new" → branch to asset creation dialog
    ASSET_KEYS = ("PROJECT_GENIE_CHECKIN",)
    if key in ASSET_KEYS and choices == ["add new"]:
        try:
            raw = input(f"  {C}Create project assets now? [y/N]: {W}").strip().lower()
            if raw in ("y", "yes"):
                print(f"  {B}Creating schema, tables, volume, Genie ...{W}\n")
                rc = subprocess.call(
                    ["uv", "run", "python", "data/init/create_all_assets.py"],
                    cwd=ROOT,
                )
                if rc == 0:
                    print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
                else:
                    print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
                    abort_step()
            else:
                print(f"  {DIM}Skipped{W}\n")
                abort_step()
        except (EOFError, KeyboardInterrupt):
            print(f"  {DIM}Skipped{W}\n")
            abort_step()

    choice = prompt_choice("Action?" if prompt_hint else "Action?", choices)

    if choice == "keep":
        return True
    if choice == KEEP_AND_CREATE_ASSETS and key == "PROJECT_UNITY_CATALOG_SCHEMA" and cur:
        print(f"  {B}Creating tables, procedures, Genie ...{W}\n")
        rc = subprocess.call(
            ["uv", "run", "python", "data/init/create_all_assets.py"],
            cwd=ROOT,
        )
        if rc == 0:
            print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
        else:
            print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
            abort_step()
        return True
    if choice == CREATE_ASSETS_NOW and key == "PROJECT_UNITY_CATALOG_SCHEMA" and cur:
        print(f"  {B}Creating schema, tables, Genie ...{W}\n")
        rc = subprocess.call(
            ["uv", "run", "python", "data/init/create_all_assets.py"],
            cwd=ROOT,
        )
        if rc == 0:
            print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
        else:
            print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
            abort_step()
        return True
    if choice == ADD_NEW_CATALOG and key == "PROJECT_UNITY_CATALOG_SCHEMA":
        hint = " (catalog.schema)"
        val = input(f"  Enter {key}{hint}: ").strip()
        if not val:
            return True
        if cur:
            comment_active_for_key(ENV_FILE, key)
        write_env_entry(ENV_FILE, key, val)
        load_dotenv(ENV_FILE, override=True)
        load_env_for_key(key, val)
        print(f"  {B}Creating schema, tables, volume, Genie ...{W}\n")
        rc = subprocess.call(
            ["uv", "run", "python", "data/init/create_all_assets.py"],
            cwd=ROOT,
        )
        if rc == 0:
            print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
        else:
            print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
            abort_step()
        return True
    if choice.startswith("activate ["):
        num = int(choice.split("[")[1].rstrip("]"))
        if 1 <= num <= len(inact):
            line_idx = inact[num - 1][0]
            comment_active_for_key(ENV_FILE, key)
            uncomment_line(ENV_FILE, line_idx)
            load_dotenv(ENV_FILE, override=True)
            load_env_for_key(key, inact[num - 1][1])
            ok, msg = verify_fn()
            if ok:
                print(f"  {OK} Activated and verified: {msg}{W}")
            else:
                print(f"  {FAIL} Activated but verify failed: {msg}{W}")
                abort_step()
        return True
    # enter new / add new
    if value_choices_fn:
        val = value_choices_fn()
    else:
        hint = f" ({prompt_hint})" if prompt_hint else ""
        val = input(f"  Enter {key}{hint}: ").strip()
    if not val:
        return True
    if cur:
        comment_active_for_key(ENV_FILE, key)
    write_env_entry(ENV_FILE, key, val)
    load_dotenv(ENV_FILE, override=True)
    load_env_for_key(key, val)
    ok, msg = verify_fn()
    if ok:
        print(f"  {OK} Set and verified: {msg}{W}")
    else:
        print(f"  {FAIL} Set but verify failed: {msg}{W}")
        abort_step()
    return True


def run_check_only() -> None:
    """Quick check of all resources (non-interactive)."""
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)

    print(f"\n{BOLD}{M}╔══════════════════════════════════════════╗{W}")
    print(f"{BOLD}{M}║  Databricks Environment Check            ║{W}")
    print(f"{BOLD}{M}╚══════════════════════════════════════════╝{W}")

    all_ok = True

    section("Connection")
    host = os.environ.get("DATABRICKS_HOST", "").strip()
    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "").strip()
    if not host:
        print(f"  {FAIL} DATABRICKS_HOST not set")
        all_ok = False
    else:
        print(f"  {OK} DATABRICKS_HOST {C}({host}){W}")
    if not token and not profile:
        print(f"  {FAIL} DATABRICKS_TOKEN or DATABRICKS_CONFIG_PROFILE not set")
        all_ok = False
    else:
        print(f"  {OK} Auth {C}({'token' if token else f'profile={profile}'}){W}")

    if all_ok:
        ok, msg = verify_host_token()
        if ok:
            print(f"  {OK} Connection {C}({msg}){W}")
        else:
            print(f"  {FAIL} Connection {C}({msg}){W}")
            all_ok = False

    section("Warehouse")
    ok, msg = verify_warehouse()
    print(f"  {OK if ok else FAIL} DATABRICKS_WAREHOUSE_ID {C}({msg}){W}")
    if not ok:
        all_ok = False

    uc_failed = False
    section("Unity Catalog")
    ok, msg = verify_schema()
    print(f"  {OK if ok else FAIL} PROJECT_UNITY_CATALOG_SCHEMA {C}({msg}){W}")
    if not ok:
        all_ok = False
        uc_failed = True

    # Tables (tree format)
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    tables = get_csv_tables()
    if "." in spec:
        catalog, schema_name = spec.split(".", 1)
        full_schema = f"{catalog}.{schema_name}"
        try:
            from databricks.sdk import WorkspaceClient
            w = WorkspaceClient()
            print(f"  Tables")
            for i, name in enumerate(tables):
                branch = "  \\-- " if i == len(tables) - 1 else "  |-- "
                full_name = f"{full_schema}.{name}"
                try:
                    w.tables.get(full_name)
                    print(f"  {branch}{OK} {name} {C}({full_name}){W}")
                except Exception as e:
                    print(f"  {branch}{FAIL} {name} {C}({e}){W}")
                    all_ok = False
                    uc_failed = True
        except Exception as e:
            print(f"  Tables")
            print(f"  \\-- {FAIL} {e}{W}")
            all_ok = False
            uc_failed = True

    section("Genie")
    ok, msg = verify_genie()
    print(f"  {OK if ok else FAIL} PROJECT_GENIE_CHECKIN {C}({msg}){W}")
    if not ok:
        all_ok = False

    section("MLflow")
    ok, msg = verify_mlflow()
    print(f"  {OK if ok else FAIL} MLFLOW_EXPERIMENT_ID {C}({msg}){W}")
    if not ok:
        all_ok = False

    section("App grants (run_all_grants)")
    grants_ok, grants_issues = verify_app_grants()
    grants_failed = not grants_ok
    if grants_ok:
        app_name = os.environ.get("DBX_APP_NAME", "").strip()
        print(f"  {OK} UC tables, routines, warehouse {C}({app_name}){W}")
    else:
        for issue in grants_issues:
            print(f"  {FAIL} {issue}")
        all_ok = False

    section("Summary")
    if all_ok:
        print(f"  {OK} {G}All resources OK{W}\n")
    else:
        print(f"  {FAIL} {R}Some checks failed{W}\n")
        assets_created = False
        grants_applied = False
        if uc_failed:
            try:
                raw = input(f"  {C}Create project assets now? [y/N]: {W}").strip().lower()
                if raw in ("y", "yes"):
                    print(f"  {B}Creating schema, tables, volume, Genie ...{W}\n")
                    rc = subprocess.call(
                        ["uv", "run", "python", "data/init/create_all_assets.py"],
                        cwd=ROOT,
                    )
                    if rc == 0:
                        print(f"\n  {OK} {G}Assets created. Re-run --check to verify.{W}\n")
                        assets_created = True
                    else:
                        print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
                        abort_step()
            except (EOFError, KeyboardInterrupt):
                print(f"  {DIM}Skipped{W}\n")
        if grants_failed:
            try:
                raw = input(f"  {C}Run apply grants (run_all_grants.sh)? [y/N]: {W}").strip().lower()
                if raw in ("y", "yes"):
                    print(f"  {B}Applying grants ...{W}\n")
                    rc = subprocess.call(
                        ["bash", str(ROOT / "deploy" / "grant" / "run_all_grants.sh")],
                        cwd=ROOT,
                    )
                    if rc == 0:
                        print(f"\n  {OK} {G}Grants applied. Re-run --check to verify.{W}\n")
                        grants_applied = True
                    else:
                        print(f"\n  {FAIL} Grants script exited with {rc}{W}\n")
            except (EOFError, KeyboardInterrupt):
                print(f"  {DIM}Skipped{W}\n")
        if not assets_created and not grants_applied:
            print(FIX_FIRST_MSG)
        sys.exit(1)


def main() -> None:
    if "--check" in sys.argv:
        run_check_only()
        return

    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)

    print(f"\n{BOLD}{M}╔══════════════════════════════════════════════════╗{W}")
    print(f"{BOLD}{M}║  Init & Check Databricks Environment (.env.local) ║{W}")
    print(f"{BOLD}{M}╚══════════════════════════════════════════════════╝{W}")

    # Connection: HOST + TOKEN (or PROFILE)
    section("Connection: DATABRICKS_HOST")
    run_resource("DATABRICKS_HOST", "DATABRICKS_HOST", verify_host_only, "https://....databricks.com")

    load_dotenv(ENV_FILE, override=True)
    if not os.environ.get("DATABRICKS_HOST"):
        print(f"  {FAIL} DATABRICKS_HOST required. Aborting.{W}")
        sys.exit(1)

    section("Connection: DATABRICKS_TOKEN or DATABRICKS_CONFIG_PROFILE")
    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "").strip()
    if token:
        run_resource("DATABRICKS_TOKEN", "DATABRICKS_TOKEN", lambda: verify_host_token(), "dapi...")
    elif profile:
        run_resource_profile()
    else:
        choices = ["DATABRICKS_TOKEN", "DATABRICKS_CONFIG_PROFILE"]
        c = prompt_choice("Which auth?", choices)
        if "TOKEN" in c:
            run_resource("DATABRICKS_TOKEN", "DATABRICKS_TOKEN", lambda: verify_host_token(), "dapi...")
        else:
            run_resource_profile()

    load_dotenv(ENV_FILE, override=True)
    run_resource_warehouse()
    run_resource("PROJECT_UNITY_CATALOG_SCHEMA", "PROJECT_UNITY_CATALOG_SCHEMA", verify_schema, "catalog.schema")

    # Step 1: ensure SQL init files exist for all CSVs
    load_dotenv(ENV_FILE, override=True)
    if os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA"):
        sql_paths = ensure_init_sql_files()

        # Step 2: tables check + offer to run SQL files
        ok, msg = verify_tables()
        if not ok:
            section(f"Tables ({', '.join(get_csv_tables())})")
            print(f"  {FAIL} {msg}{W}")
            if sql_paths:
                print(f"\n  SQL files to execute:")
                for i, p in enumerate(sql_paths):
                    branch = "  \\-- " if i == len(sql_paths) - 1 else "  |-- "
                    print(f"{branch}{p.relative_to(ROOT)}")
            try:
                raw = input(f"\n  {C}Run all SQL files and create assets? [y/N]: {W}").strip().lower()
                if raw in ("y", "yes"):
                    print(f"  {B}Creating schema, tables, volume, Genie ...{W}\n")
                    rc = subprocess.call(
                        ["uv", "run", "python", "data/init/create_all_assets.py"],
                        cwd=ROOT,
                    )
                    if rc == 0:
                        print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
                    else:
                        print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
                        abort_step()
                else:
                    print(f"  {DIM}Skipped{W}\n")
                    abort_step()
            except (EOFError, KeyboardInterrupt):
                print(f"  {DIM}Skipped{W}\n")
                abort_step()

    run_resource_genie()
    run_resource_mlflow()
    run_resource("DBX_APP_NAME", "DBX_APP_NAME", lambda: (True, os.environ.get("DBX_APP_NAME", "")), "my-app-name")

    section("Done")
    print(f"  {OK} {G}Configuration saved to {ENV_FILE}{W}\n")
    grants_ok, grants_issues = verify_app_grants()
    if not grants_ok:
        print(f"  {WARN} App grants: {', '.join(grants_issues)}{W}")
        print(f"  {DIM}Run: ./deploy/grant/run_all_grants.sh{W}\n")
    print(f"  {BOLD}{G}╔════════════════════════════════════╗{W}")
    print(f"  {BOLD}{G}║  {OK} You're All Set!{W}                 {BOLD}{G}║{W}")
    print(f"  {BOLD}{G}╚════════════════════════════════════╝{W}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {WARN} Interrupted{W}")
        sys.exit(130)
    except Exception as e:
        print(f"\n  {FAIL} {e}{W}")
        print(FIX_FIRST_MSG)
        sys.exit(1)
