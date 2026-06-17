#!/usr/bin/env python3
"""CLI orchestrator for SQL function/procedure generation.

Invoked by the visual backend via subprocess. Communicates progress via
[+]/[~]/[x] prefixed stdout lines and returns results via __RESULT__:{json}.

Modes:
  --mode=schema  --domain="..." [--tables-json="[...]"]  Generate routine schemas
  --mode=sql                                              Generate SQL for one routine (stdin JSON)
  --mode=save                                             Write SQL file for one routine (stdin JSON)
  --mode=provision-gen                                    Provision generated procedures to Databricks
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))



def _emit_result(data: dict | list) -> None:
    """Print a result line the backend can parse."""
    print(f"__RESULT__:{json.dumps(data)}", flush=True)


def mode_schema(domain: str, tables_json: str | None) -> None:
    from data.gen.routine_schema_generator import generate_routine_schema

    table_schemas = None
    if tables_json:
        try:
            table_schemas = json.loads(tables_json)
        except json.JSONDecodeError:
            print("[~] Could not parse --tables-json, proceeding without table context")

    try:
        routines = generate_routine_schema(domain, table_schemas)
        _emit_result({"routines": routines})
    except Exception as e:
        print(f"[x] Schema generation failed: {e}")
        traceback.print_exc()
        sys.exit(1)


def mode_sql() -> None:
    from data.gen.routine_sql_generator import generate_routine_sql

    try:
        input_data = json.loads(sys.stdin.read())
        routine = input_data["routine"]
        table_schemas = input_data.get("tableSchemas")
        sql = generate_routine_sql(routine, table_schemas)
        _emit_result({"sql": sql})
    except Exception as e:
        print(f"[x] SQL generation failed: {e}")
        traceback.print_exc()
        sys.exit(1)


def mode_save() -> None:
    from data.gen.routine_writer import (
        write_function_sql,
        write_procedure_sql,
    )

    try:
        input_data = json.loads(sys.stdin.read())
        routine = input_data["routine"]
        sql = input_data["sql"]

        if routine["type"] == "procedure":
            write_procedure_sql(routine["name"], sql)
        else:
            write_function_sql(routine["name"], sql)

        _emit_result({"ok": True, "routine": routine["name"]})
    except Exception as e:
        print(f"[x] Save failed: {e}")
        traceback.print_exc()
        sys.exit(1)


_MAX_HEAL_RETRIES = 2

_HEAL_SYSTEM = """\
You write Databricks SQL. The SQL below failed on Databricks Unity Catalog.
Fix it and return ONLY the corrected raw SQL. No markdown fences. No explanation.
Do NOT add features, parameters, or clauses that were not in the original."""


def _self_heal(sql_file: Path, error_msg: str, kind: str) -> str | None:
    """Attempt to fix SQL using the LLM. Returns corrected SQL or None."""
    from data.gen.llm_client import call_llm
    from data.gen.routine_sql_generator import _sanitize_sql, _load_reference

    original_sql = sql_file.read_text()
    ref = _load_reference()
    system = f"{_HEAL_SYSTEM}\n\n{ref}" if ref else _HEAL_SYSTEM
    user = f"SQL:\n{original_sql}\n\nDatabricks error:\n{error_msg}\n\nReturn ONLY the fixed SQL."

    try:
        raw = call_llm(system, user, max_tokens=4096)
        # Strip markdown fences
        import re
        cleaned = re.sub(r"^```(?:sql)?\s*\n?", "", raw.strip())
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
        # Run through sanitizer
        fixed = _sanitize_sql(cleaned, kind)
        return fixed
    except Exception as e:
        print(f"[x] Self-heal LLM call failed: {e}")
        return None


def _learn_constraint(error_msg: str) -> None:
    """Append a new constraint to the reference doc if not already known."""
    import re
    ref_path = ROOT / "data" / "gen" / "databricks_sql_reference.md"
    if not ref_path.exists():
        return

    # Extract error code like [USER_DEFINED_FUNCTIONS.NOT_A_VALID_DEFAULT_PARAMETER_POSITION]
    m = re.search(r'\[([A-Z_]+(?:\.[A-Z_]+)*)\]', error_msg)
    error_key = m.group(1) if m else None

    # Extract first meaningful line of error
    lines = error_msg.strip().split('\n')
    # Find the actual error message (not the raise statement)
    summary = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("RuntimeError:"):
            summary = stripped.split(":", 1)[-1].strip()
            break
        if stripped.startswith("Operation not allowed") or stripped.startswith("["):
            summary = stripped
            break
    if not summary:
        summary = lines[-1].strip() if lines else error_msg[:100]

    existing = ref_path.read_text()

    # Check if already known
    if error_key and error_key in existing:
        return
    if summary[:60] in existing:
        return

    # Append
    entry = f"- "
    if error_key:
        entry += f"[{error_key}] "
    entry += summary[:200] + "\n"

    with open(ref_path, "a") as f:
        f.write(entry)
    print(f"[+] Learned new constraint: {entry.strip()}")


def _run_sql_file(sql_file: Path, kind: str) -> tuple[bool, str]:
    """Run a SQL file via run_sql.py. Returns (success, error_msg)."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "data/py/run_sql.py", str(sql_file)],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode == 0:
        return True, ""
    return False, (r.stderr.strip() or r.stdout.strip())


def mode_provision_gen() -> None:
    """Provision generated functions and procedures to UC via data/py/run_sql.py.

    Self-heals on failure: captures Databricks error, sends SQL + error to LLM
    for correction, sanitizes, writes back, retries (max 2 attempts per file).
    Learned constraints are appended to the reference doc.
    """
    from lib.project_paths import gen_dir
    _gd = gen_dir()
    gen_func = _gd / "func"
    gen_proc = _gd / "proc"

    func_files = sorted(gen_func.glob("*.sql")) if gen_func.exists() else []
    proc_files = sorted(gen_proc.glob("*.sql")) if gen_proc.exists() else []
    all_files = func_files + proc_files

    if not all_files:
        print("[x] No generated function or procedure SQL files found")
        sys.exit(1)

    # Ensure catalog/schema exists first
    import subprocess
    print("[~] Ensuring catalog and schema exist...")
    sys.stdout.flush()
    r = subprocess.run(
        [sys.executable, "data/init/create_catalog_schema.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"[x] create_catalog_schema failed: {r.stderr.strip() or r.stdout.strip()}")
        sys.exit(1)
    print("[+] Catalog and schema ready")

    # Run each SQL file with self-healing
    total = len(all_files)
    func_count = 0
    proc_count = 0
    for i, sql_file in enumerate(all_files, 1):
        kind = "function" if sql_file.parent.name == "func" else "procedure"
        print(f"[~] ({i}/{total}) Creating {kind}: {sql_file.stem}...")
        sys.stdout.flush()

        ok, error_msg = _run_sql_file(sql_file, kind)

        # Self-healing loop
        attempts = 0
        original_error = error_msg
        while not ok and attempts < _MAX_HEAL_RETRIES:
            attempts += 1
            print(f"[~] Provision failed. Self-healing attempt {attempts}/{_MAX_HEAL_RETRIES}...")
            print(f"    Error: {error_msg[:200]}")
            sys.stdout.flush()

            fixed_sql = _self_heal(sql_file, error_msg, kind)
            if not fixed_sql:
                print(f"[x] Self-heal could not produce corrected SQL")
                break

            # Write corrected SQL and retry
            sql_file.write_text(fixed_sql)
            print(f"[~] Corrected SQL written. Retrying provision...")
            sys.stdout.flush()
            ok, error_msg = _run_sql_file(sql_file, kind)

        if not ok:
            print(f"[x] Failed after {attempts} self-heal attempt(s): {error_msg[:200]}")
            sys.exit(1)

        # Success -- learn from the original error that triggered healing
        if attempts > 0:
            _learn_constraint(original_error)
            print(f"[+] Self-healed and created {kind}: {sql_file.stem}")
        else:
            print(f"[+] Created {kind}: {sql_file.stem}")

        if kind == "function":
            func_count += 1
        else:
            proc_count += 1

    print(f"[+] Provisioned {func_count} function(s) + {proc_count} procedure(s)")

    # Auto-register provisioned functions in config
    provisioned_names = [f.stem for f in func_files + proc_files]
    if provisioned_names:
        config_file = os.environ.get("CONFIG_FILE", "")
        if config_file:
            try:
                from lib.config_json import read_config, write_config
                config = read_config()
                funcs = config.setdefault("tools", {}).setdefault("functions", [])
                for name in provisioned_names:
                    if name not in funcs:
                        funcs.append(name)
                write_config(config)
                os.environ["PROJECT_FUNCTIONS"] = ",".join(funcs)
                print(f"[+] functions = {funcs}")
            except Exception as e:
                print(f"[~] Could not update config.json: {e}")
        else:
            # Fallback: write to .env.local (legacy)
            existing = os.environ.get("PROJECT_FUNCTIONS", "").strip()
            existing_set = set(existing.split(",")) if existing else set()
            existing_set.update(provisioned_names)
            new_value = ",".join(sorted(existing_set - {""}))
            env_file = Path(os.environ.get("ENV_FILE", str(ROOT / ".env.local")))
            try:
                content = env_file.read_text() if env_file.exists() else ""
                import re
                if re.search(r'^PROJECT_FUNCTIONS=', content, re.MULTILINE):
                    content = re.sub(r'^PROJECT_FUNCTIONS=.*$', f'PROJECT_FUNCTIONS={new_value}', content, flags=re.MULTILINE)
                else:
                    content += f"\nPROJECT_FUNCTIONS={new_value}\n"
                env_file.write_text(content)
                os.environ["PROJECT_FUNCTIONS"] = new_value
                print(f"[+] PROJECT_FUNCTIONS = {new_value}")
            except Exception as e:
                print(f"[~] Could not update PROJECT_FUNCTIONS: {e}")

    _emit_result({"ok": True, "functions": func_count, "procedures": proc_count})


def main() -> None:
    parser = argparse.ArgumentParser(description="SQL function/procedure generation orchestrator")
    parser.add_argument("--mode", required=True, choices=["schema", "sql", "save", "provision-gen"])
    parser.add_argument("--domain", default="")
    parser.add_argument("--tables-json", default=None)
    args = parser.parse_args()

    if args.mode == "schema":
        if not args.domain:
            print("[x] --domain is required for schema mode")
            sys.exit(1)
        mode_schema(args.domain, args.tables_json)
    elif args.mode == "sql":
        mode_sql()
    elif args.mode == "save":
        mode_save()
    elif args.mode == "provision-gen":
        mode_provision_gen()


if __name__ == "__main__":
    main()
