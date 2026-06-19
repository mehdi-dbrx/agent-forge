"""Write generated data as CSV files and DDL SQL files."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.project_paths import gen_dir as _resolve_gen_dir

GEN_DIR = _resolve_gen_dir()
CSV_DIR = GEN_DIR / "csv"
INIT_DIR = GEN_DIR / "init"
MANIFEST_PATH = GEN_DIR / "manifest.json"


def _sql_value(val: Any, col_type: str) -> str:
    """Format a Python value as a SQL literal for INSERT."""
    if val is None:
        return "NULL"
    if col_type in ("INT", "BIGINT"):
        return str(int(val))
    if col_type in ("DOUBLE", "FLOAT"):
        return str(float(val))
    if col_type == "BOOLEAN":
        return "TRUE" if val else "FALSE"
    if col_type == "TIMESTAMP_NTZ":
        return f"CAST('{val}' AS TIMESTAMP_NTZ)"
    # STRING, DATE — quote as string
    escaped = str(val).replace("'", "''")
    return f"'{escaped}'"


def write_csv(table_name: str, columns: list[dict], rows: list[dict]) -> Path:
    """Write rows to data/gen/csv/<table_name>.csv. Returns the path."""
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = CSV_DIR / f"{table_name}.csv"

    col_names = [c["name"] for c in columns]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=col_names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"[+] Wrote {csv_path.name}")
    return csv_path


def write_create_sql(table_name: str, columns: list[dict], rows: list[dict]) -> Path:
    """Generate data/gen/init/create_<table_name>.sql with DDL + INSERT.

    Uses __SCHEMA_QUALIFIED__ placeholder (same pattern as existing SQL files).
    """
    INIT_DIR.mkdir(parents=True, exist_ok=True)
    sql_path = INIT_DIR / f"create_{table_name}.sql"

    col_defs = ",\n    ".join(f"{c['name']} {c['type']}" for c in columns)

    lines = [
        f"CREATE OR REPLACE TABLE __SCHEMA_QUALIFIED__.{table_name} (",
        f"    {col_defs}",
        ")",
        "USING DELTA",
        "TBLPROPERTIES (delta.enableChangeDataFeed = true);",
        "",
    ]

    # INSERT statement
    if rows:
        lines.append(f"INSERT INTO __SCHEMA_QUALIFIED__.{table_name} VALUES")
        row_strs = []
        for row in rows:
            vals = ", ".join(
                _sql_value(row.get(c["name"]), c["type"]) for c in columns
            )
            row_strs.append(f"({vals})")
        lines.append(",\n".join(row_strs) + ";")

    with open(sql_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[+] Wrote {sql_path.name}")
    return sql_path


def write_manifest(tables: list[dict]) -> Path:
    """Write data/gen/manifest.json with metadata about generated tables."""
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "tables": [
            {
                "name": t["name"],
                "columns": t["columns"],
                "row_count": t.get("row_count", len(t.get("rows", []))),
                "instructions": t.get("instructions", ""),
            }
            for t in tables
        ],
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[+] Wrote {MANIFEST_PATH.name}")
    return MANIFEST_PATH


def clear_all_generated() -> None:
    """Remove all generated CSVs, SQL files, and reset manifest."""
    count = 0
    for d in (CSV_DIR, INIT_DIR):
        if d.exists():
            for f in d.iterdir():
                if f.is_file():
                    f.unlink()
                    count += 1
    if MANIFEST_PATH.exists():
        MANIFEST_PATH.unlink()
    print(f"[+] Cleared {count} generated file(s)")
