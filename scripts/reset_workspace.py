#!/usr/bin/env python3
"""Delete all agent-forge workspace resources, keeping Unity Catalog and Knowledge Assistants.

Deletes:
  - Databricks App (DBX_APP_NAME)
  - MLflow experiment (MLFLOW_EXPERIMENT_ID)
  - Genie space (PROJECT_GENIE_CHECKIN)
  - UC Volume (derived from PROJECT_UNITY_CATALOG_SCHEMA)
  - UC functions from data/func/*.sql
  - UC procedures from data/proc/*.sql
  - DAB bundle state (.databricks/bundle/)
  - Clears PROJECT_GENIE_CHECKIN + MLFLOW_EXPERIMENT_ID from .env.local

Keeps:
  - Unity Catalog
  - Knowledge Assistants

Usage:
  uv run python scripts/reset_workspace.py
  uv run python scripts/reset_workspace.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local", override=True)

# ── ANSI ──────────────────────────────────────────────────────────────────────
R, G, Y, B, M, C, W = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m", "\033[0m"
BOLD, DIM = "\033[1m", "\033[2m"
OK   = f"{G}[+]{W}"
FAIL = f"{R}[x]{W}"
WARN = f"{Y}[!]{W}"
SKIP = f"{DIM}[-]{W}"


def section(title: str) -> None:
    print(f"\n{BOLD}{B}═══ {title} ═══{W}")


def _comment_key(env_path: Path, key: str) -> None:
    """Comment out all active occurrences of key in .env.local."""
    text = env_path.read_text(encoding="utf-8")
    text = re.sub(rf"^({re.escape(key)}=)", r"#\1", text, flags=re.MULTILINE)
    env_path.write_text(text, encoding="utf-8")


def _parse_sql_object_names(sql_dir: Path, kind: str) -> list[str]:
    """Extract bare object names from CREATE FUNCTION/PROCEDURE SQL files."""
    names: list[str] = []
    if not sql_dir.exists():
        return names
    pattern = re.compile(
        rf"CREATE\s+(?:OR\s+REPLACE\s+)?{kind}\s+(?:\w+\.)*(\w+)\s*\(",
        re.IGNORECASE,
    )
    for sql_file in sorted(sql_dir.glob("*.sql")):
        text = sql_file.read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            names.append(m.group(1))
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset agent-forge workspace resources")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    args = parser.parse_args()

    dry = args.dry_run

    print(f"\n{BOLD}{R}╔══════════════════════════════════════════╗{W}")
    print(f"{BOLD}{R}║  Agent Forge  —  Reset Workspace         ║{W}")
    print(f"{BOLD}{R}╚══════════════════════════════════════════╝{W}")

    if dry:
        print(f"\n  {WARN} {BOLD}--dry-run: nothing will be deleted{W}")

    # ── Collect resource IDs from env ──────────────────────────────────────────
    app_name   = os.environ.get("DBX_APP_NAME", "").strip()
    exp_id     = os.environ.get("MLFLOW_EXPERIMENT_ID", "").strip()
    genie_id   = os.environ.get("PROJECT_GENIE_CHECKIN", "").strip()
    schema_spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    catalog, schema = schema_spec.split(".", 1) if "." in schema_spec else ("", "")
    volume_name = "doc"  # convention from create_volume.py

    func_names = _parse_sql_object_names(ROOT / "data" / "func", "FUNCTION")
    proc_names = _parse_sql_object_names(ROOT / "data" / "proc", "PROCEDURE")
    bundle_dir = ROOT / ".databricks" / "bundle"

    # ── Preview ───────────────────────────────────────────────────────────────
    print(f"\n  {BOLD}Resources to delete:{W}")
    print(f"    {'App':30s} {C}{app_name or '(not set)'}{W}")
    print(f"    {'MLflow experiment':30s} {C}{exp_id or '(not set)'}{W}")
    print(f"    {'Genie space':30s} {C}{genie_id or '(not set)'}{W}")
    if catalog and schema:
        print(f"    {'UC Volume':30s} {C}/Volumes/{catalog}/{schema}/{volume_name}{W}")
    for fn in func_names:
        print(f"    {'UC function':30s} {C}{catalog}.{schema}.{fn}{W}")
    for pn in proc_names:
        print(f"    {'UC procedure':30s} {C}{catalog}.{schema}.{pn}{W}")
    if bundle_dir.exists():
        print(f"    {'DAB bundle state':30s} {C}{bundle_dir.relative_to(ROOT)}{W}")
    print(f"\n  {BOLD}Keeping:{W} Unity Catalog, Knowledge Assistants")

    if not dry:
        try:
            confirm = input(f"\n  {R}{BOLD}Confirm deletion? [yes/N]: {W}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {SKIP} Cancelled")
            return 0
        if confirm not in ("yes", "y"):
            print(f"  {SKIP} Aborted")
            return 0

    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()

    # ── Databricks App ─────────────────────────────────────────────────────────
    section("Databricks App")
    if app_name:
        if dry:
            print(f"  {SKIP} Would delete app: {app_name}")
        else:
            try:
                w.apps.delete(name=app_name)
                print(f"  {OK} Deleted app: {C}{app_name}{W}")
            except Exception as e:
                print(f"  {FAIL} App delete failed: {e}")
    else:
        print(f"  {SKIP} DBX_APP_NAME not set — skipped")

    # ── MLflow Experiment ──────────────────────────────────────────────────────
    section("MLflow Experiment")
    if exp_id:
        if dry:
            print(f"  {SKIP} Would delete experiment: {exp_id}")
        else:
            try:
                import mlflow
                mlflow.set_tracking_uri("databricks")
                mlflow.delete_experiment(exp_id)
                print(f"  {OK} Deleted experiment: {C}{exp_id}{W}")
            except Exception as e:
                print(f"  {FAIL} Experiment delete failed: {e}")
    else:
        print(f"  {SKIP} MLFLOW_EXPERIMENT_ID not set — skipped")

    # ── Genie Space ────────────────────────────────────────────────────────────
    section("Genie Space")
    if genie_id:
        if dry:
            print(f"  {SKIP} Would delete Genie space: {genie_id}")
        else:
            try:
                w.genie.trash_space(space_id=genie_id)
                print(f"  {OK} Deleted Genie space: {C}{genie_id}{W}")
            except Exception as e:
                print(f"  {FAIL} Genie space delete failed: {e}")
    else:
        print(f"  {SKIP} PROJECT_GENIE_CHECKIN not set — skipped")

    # ── UC Volume ──────────────────────────────────────────────────────────────
    section("UC Volume")
    if catalog and schema:
        full_volume = f"{catalog}.{schema}.{volume_name}"
        if dry:
            print(f"  {SKIP} Would delete volume: {full_volume}")
        else:
            try:
                w.volumes.delete(name=full_volume)
                print(f"  {OK} Deleted volume: {C}{full_volume}{W}")
            except Exception as e:
                print(f"  {FAIL} Volume delete failed: {e}")
    else:
        print(f"  {SKIP} PROJECT_UNITY_CATALOG_SCHEMA not set — skipped")

    # ── UC Functions ───────────────────────────────────────────────────────────
    section("UC Functions")
    if func_names and catalog and schema:
        wh_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
        if not wh_id:
            print(f"  {WARN} DATABRICKS_WAREHOUSE_ID not set — cannot drop functions")
        else:
            for fn in func_names:
                full = f"{catalog}.{schema}.{fn}"
                if dry:
                    print(f"  {SKIP} Would drop function: {full}")
                else:
                    try:
                        w.statement_execution.execute_statement(
                            warehouse_id=wh_id,
                            statement=f"DROP FUNCTION IF EXISTS {full}",
                            wait_timeout="30s",
                        )
                        print(f"  {OK} Dropped function: {C}{full}{W}")
                    except Exception as e:
                        print(f"  {FAIL} Drop function {full} failed: {e}")
    else:
        print(f"  {SKIP} No functions found in data/func/" if not func_names else f"  {SKIP} Schema not set")

    # ── UC Procedures ──────────────────────────────────────────────────────────
    section("UC Procedures")
    if proc_names and catalog and schema:
        wh_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
        if not wh_id:
            print(f"  {WARN} DATABRICKS_WAREHOUSE_ID not set — cannot drop procedures")
        else:
            for pn in proc_names:
                full = f"{catalog}.{schema}.{pn}"
                if dry:
                    print(f"  {SKIP} Would drop procedure: {full}")
                else:
                    try:
                        w.statement_execution.execute_statement(
                            warehouse_id=wh_id,
                            statement=f"DROP PROCEDURE IF EXISTS {full}",
                            wait_timeout="30s",
                        )
                        print(f"  {OK} Dropped procedure: {C}{full}{W}")
                    except Exception as e:
                        print(f"  {FAIL} Drop procedure {full} failed: {e}")
    else:
        print(f"  {SKIP} No procedures found in data/proc/" if not proc_names else f"  {SKIP} Schema not set")

    # ── DAB Bundle State ───────────────────────────────────────────────────────
    section("DAB Bundle State")
    if bundle_dir.exists():
        if dry:
            print(f"  {SKIP} Would delete: {bundle_dir.relative_to(ROOT)}")
        else:
            shutil.rmtree(bundle_dir)
            print(f"  {OK} Deleted: {C}{bundle_dir.relative_to(ROOT)}{W}")
    else:
        print(f"  {SKIP} .databricks/bundle/ not found — skipped")

    # ── Clear .env.local ───────────────────────────────────────────────────────
    section(".env.local cleanup")
    env_path = ROOT / ".env.local"
    for key in ("PROJECT_GENIE_CHECKIN", "MLFLOW_EXPERIMENT_ID"):
        val = os.environ.get(key, "").strip()
        if val:
            if dry:
                print(f"  {SKIP} Would comment out {key}")
            else:
                _comment_key(env_path, key)
                print(f"  {OK} Commented out {C}{key}{W}")
        else:
            print(f"  {SKIP} {key} not set — skipped")

    print(f"\n  {OK} {G}{BOLD}Reset complete.{W}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n  {SKIP} Interrupted")
        sys.exit(130)
