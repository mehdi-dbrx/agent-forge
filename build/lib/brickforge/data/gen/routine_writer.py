"""Write generated SQL files for functions and procedures."""
from __future__ import annotations

from pathlib import Path

from lib.project_paths import gen_dir as _resolve_gen_dir

GEN_DIR = _resolve_gen_dir()
FUNC_DIR = GEN_DIR / "func"
PROC_DIR = GEN_DIR / "proc"


def write_function_sql(name: str, sql: str) -> Path:
    """Write a function query template to data/gen/func/<name>.sql."""
    FUNC_DIR.mkdir(parents=True, exist_ok=True)
    path = FUNC_DIR / f"{name}.sql"
    with open(path, "w", encoding="utf-8") as f:
        f.write(sql + "\n")
    print(f"[+] Wrote {path.name}")
    return path


def write_procedure_sql(name: str, sql: str) -> Path:
    """Write a procedure DDL to data/gen/proc/<name>.sql."""
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    path = PROC_DIR / f"{name}.sql"
    with open(path, "w", encoding="utf-8") as f:
        f.write(sql + "\n")
    print(f"[+] Wrote {path.name}")
    return path


def clear_all_generated_routines() -> None:
    """Remove all generated function/procedure SQL files."""
    count = 0
    for d in (FUNC_DIR, PROC_DIR):
        if d.exists():
            for f in d.iterdir():
                if f.is_file():
                    f.unlink()
                    count += 1
    print(f"[+] Cleared {count} generated routine file(s)")
