#!/usr/bin/env python3
"""Sync databricks.yml and app.yaml from .env.local.
Creates databricks.yml and app.yaml from templates if they don't exist.

Updates:
  - databricks.yml: sql_warehouse.id, genie_space.space_id, serving_endpoint.name, app name
  - app.yaml: AGENT_MODEL_ENDPOINT, PROJECT_UNITY_CATALOG_SCHEMA, DATABRICKS_WAREHOUSE_ID

Usage:
  uv run python deploy/sync_databricks_yml_from_env.py [--dry-run]
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local")

# ANSI
R, G, Y, B, C, W = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[36m", "\033[0m"
BOLD, DIM = "\033[1m", "\033[2m"
OK  = f"{G}✓{W}"
WARN = f"{Y}⚠{W}"
FAIL = f"{R}✗{W}"
ARR = f"{C}←{W}"

DATABRICKS_YML_TEMPLATE = """\
bundle:
  name: agent-forge

resources:
  experiments:
    agent_experiment:
      name: /Users/${workspace.current_user.userName}/${bundle.name}-${bundle.target}

  apps:
    agent_app:
      name: "${bundle.target}-agent"
      description: "LangGraph agent application"
      source_code_path: ./

      resources:
        - name: 'experiment'
          experiment:
            experiment_id: "${resources.experiments.agent_experiment.id}"
            permission: 'CAN_MANAGE'
        - name: 'sql_warehouse'
          sql_warehouse:
            id: 'PLACEHOLDER_WAREHOUSE_ID'
            permission: 'CAN_USE'
        - name: 'genie_space'
          genie_space:
            name: 'PLACEHOLDER_GENIE_NAME'
            space_id: 'PLACEHOLDER_GENIE_ID'
            permission: 'CAN_RUN'
        - name: 'serving_endpoint'
          serving_endpoint:
            name: 'PLACEHOLDER_ENDPOINT'
            permission: 'CAN_QUERY'

targets:
  dev:
    mode: development

  default:
    mode: production
    default: true
    workspace:
      root_path: /Workspace/Users/${workspace.current_user.userName}/.bundle/${bundle.name}/default
    resources:
      apps:
        agent_app:
          name: 'PLACEHOLDER_APP_NAME'
"""

APP_YAML_TEMPLATE = """\
command: ["uv", "run", "start-app"]
# Databricks Apps listens by default on port 8000

env:
  - name: MLFLOW_TRACKING_URI
    value: "databricks"
  - name: MLFLOW_REGISTRY_URI
    value: "databricks-uc"
  - name: API_PROXY
    value: "http://localhost:8000/invocations"
  - name: CHAT_APP_PORT
    value: "3000"
  - name: TASK_EVENTS_URL
    value: "http://127.0.0.1:3000"
  - name: CHAT_PROXY_TIMEOUT_SECONDS
    value: "300"
  - name: MLFLOW_EXPERIMENT_ID
    valueFrom: "experiment"
  - name: AGENT_MODEL_ENDPOINT
    value: "PLACEHOLDER_ENDPOINT"
  - name: PROJECT_UNITY_CATALOG_SCHEMA
    value: "PLACEHOLDER_SCHEMA"
  - name: DATABRICKS_WAREHOUSE_ID
    value: "PLACEHOLDER_WAREHOUSE_ID"
"""


def init_databricks_yml(yml_path: Path, dry_run: bool) -> None:
    if yml_path.exists():
        return
    print(f"  {WARN} {BOLD}databricks.yml{W} not found — creating from template")
    if not dry_run:
        yml_path.write_text(DATABRICKS_YML_TEMPLATE)
        print(f"  {OK} Created {C}{yml_path}{W}")


def init_app_yaml(app_yml: Path, dry_run: bool) -> None:
    if app_yml.exists():
        return
    print(f"  {WARN} {BOLD}app.yaml{W} not found — creating from template")
    if not dry_run:
        app_yml.write_text(APP_YAML_TEMPLATE)
        print(f"  {OK} Created {C}{app_yml}{W}")


def _find_production_target(content: str) -> str | None:
    """Find the first production target name in databricks.yml."""
    m = re.search(r"^(\s{2})(\S+):\s*\n\s+mode: production", content, re.MULTILINE)
    return m.group(2).strip() if m else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync databricks.yml from .env.local")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    print(f"\n{BOLD}{B}╔══════════════════════════════════════════╗{W}")
    print(f"{BOLD}{B}║  Sync databricks.yml / app.yaml          ║{W}")
    print(f"{BOLD}{B}╚══════════════════════════════════════════╝{W}")

    yml_path = ROOT / "databricks.yml"
    app_yml = ROOT / "app.yaml"

    init_databricks_yml(yml_path, args.dry_run)
    init_app_yaml(app_yml, args.dry_run)

    if not yml_path.exists():
        print(f"Error: {yml_path} not found", file=sys.stderr)
        return 1

    content = yml_path.read_text()
    changes = []

    # sql_warehouse.id <- DATABRICKS_WAREHOUSE_ID
    wh_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
    if wh_id:
        m = re.search(r"sql_warehouse:\s*\n\s+id: '([^']*)'", content)
        if m and m.group(1) != wh_id:
            content = re.sub(
                r"(sql_warehouse:\s*\n\s+)id: '[^']*'",
                r"\g<1>id: '" + wh_id + "'",
                content,
                count=1,
            )
            changes.append(("sql_warehouse.id", "DATABRICKS_WAREHOUSE_ID", wh_id))

    # genie_space.space_id <- PROJECT_GENIE_CHECKIN
    genie_id = os.environ.get("PROJECT_GENIE_CHECKIN", "").strip()
    if genie_id:
        m = re.search(r"genie_space:.*?space_id: '([^']*)'", content, re.DOTALL)
        if m and m.group(1) != genie_id:
            content = re.sub(r"space_id: '[^']*'", f"space_id: '{genie_id}'", content, count=1)
            changes.append(("genie_space.space_id", "PROJECT_GENIE_CHECKIN", genie_id))

    # serving_endpoint.name <- AGENT_MODEL_ENDPOINT
    endpoint = os.environ.get("AGENT_MODEL_ENDPOINT", "").strip()
    if endpoint:
        m = re.search(r"serving_endpoint:\s*\n\s+name: '([^']*)'", content)
        if m and m.group(1) != endpoint:
            content = re.sub(
                r"(serving_endpoint:\s*\n\s+)name: '[^']*'",
                r"\g<1>name: '" + endpoint + "'",
                content,
                count=1,
            )
            changes.append(("serving_endpoint.name", "AGENT_MODEL_ENDPOINT", endpoint))

    # production target app name <- DBX_APP_NAME
    app_name = os.environ.get("DBX_APP_NAME", "").strip()
    if app_name:
        target = _find_production_target(content)
        if target:
            pattern = rf"({re.escape(target)}:.*?agent_app:\s*\n\s+name: )[^\n]+"
            m = re.search(pattern, content, re.DOTALL)
            current = m.group(0).split("name: ")[-1].strip().strip("'\"") if m else ""
            if current != app_name:
                content = re.sub(
                    pattern,
                    r"\g<1>" + f"'{app_name}'",
                    content,
                    count=1,
                    flags=re.DOTALL,
                )
                changes.append((f"targets.{target} app name", "DBX_APP_NAME", app_name))

    # app.yaml: AGENT_MODEL_ENDPOINT, PROJECT_UNITY_CATALOG_SCHEMA, DATABRICKS_WAREHOUSE_ID
    if app_yml.exists():
        app_content = app_yml.read_text()
        app_changed = False
        schema_spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()

        for env_name, value in [
            ("AGENT_MODEL_ENDPOINT", endpoint),
            ("PROJECT_UNITY_CATALOG_SCHEMA", schema_spec),
            ("DATABRICKS_WAREHOUSE_ID", wh_id),
        ]:
            if not value:
                continue
            m = re.search(rf"{env_name}\s*\n\s+value:\s*[\"']([^\"']*)[\"']", app_content)
            if m and m.group(1) != value:
                app_content = re.sub(
                    rf"({env_name}\s*\n\s+value:\s*)[\"'][^\"']*[\"']",
                    r'\g<1>"' + value + '"',
                    app_content,
                    count=1,
                )
                app_changed = True
                changes.append((f"app.yaml  {env_name}", None, value))

        if app_changed and not args.dry_run:
            app_yml.write_text(app_content)

    if not changes:
        print(f"  {OK} {G}databricks.yml{W} and {G}app.yaml{W} already in sync with {C}.env.local{W}")
        return 0

    print(f"\n{BOLD}Syncing from {C}.env.local{W}{BOLD}:{W}\n")
    for key, env_var, val in changes:
        display_val = val if len(val) <= 60 else val[:57] + "..."
        if env_var:
            print(f"  {OK}  {BOLD}{key}{W}  {ARR}  {DIM}{env_var}{W}={C}{display_val}{W}")
        else:
            print(f"  {OK}  {BOLD}{key}{W}  {ARR}  {C}{display_val}{W}")

    if args.dry_run:
        print(f"\n  {WARN} {DIM}--dry-run: files not written{W}")
        return 0

    yml_path.write_text(content)
    print(f"\n  {OK} {G}Written:{W} {C}{yml_path.relative_to(ROOT)}{W}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
