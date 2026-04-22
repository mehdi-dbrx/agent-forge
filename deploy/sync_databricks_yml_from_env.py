#!/usr/bin/env python3
"""Sync databricks.yml and app.yaml from .env.local.
Creates databricks.yml and app.yaml from templates if they don't exist.

Updates:
  - databricks.yml: sql_warehouse.id, genie_space.space_id, serving_endpoint.name, ka_endpoint.name, app name
  - app.yaml: AGENT_MODEL_ENDPOINT, PROJECT_UNITY_CATALOG_SCHEMA, DATABRICKS_WAREHOUSE_ID, PROJECT_KA_PASSENGERS
  - Databricks Secrets: pushes AGENT_MODEL_TOKEN to scope 'agent-forge' (cross-workspace only)

Usage:
  uv run python deploy/sync_databricks_yml_from_env.py [--dry-run]
"""
import argparse
import json
import os
import re
import subprocess
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

SECRET_SCOPE = "agent-forge"

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
            name: 'agent-forge-checkin'
            space_id: 'PLACEHOLDER_GENIE_ID'
            permission: 'CAN_RUN'
        - name: 'serving_endpoint'
          serving_endpoint:
            name: 'PLACEHOLDER_ENDPOINT'
            permission: 'CAN_QUERY'
        - name: 'ka_endpoint'
          serving_endpoint:
            name: 'PLACEHOLDER_KA_ENDPOINT'
            permission: 'CAN_QUERY'
        - name: 'agent_model_token'
          secret:
            scope: 'agent-forge'
            key: 'AGENT_MODEL_TOKEN'
            permission: 'READ'

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
command: ["uv", "run", "python", "-c", "from agent.start_server import main; main()"]
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
  - name: PROJECT_UNITY_CATALOG_SCHEMA
    value: "PLACEHOLDER_SCHEMA"
  - name: DATABRICKS_WAREHOUSE_ID
    value: "PLACEHOLDER_WAREHOUSE_ID"
  - name: PROJECT_KA_PASSENGERS
    value: "PLACEHOLDER_KA_ENDPOINT"
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


def ensure_secret(token: str, dry_run: bool) -> None:
    """Push AGENT_MODEL_TOKEN to Databricks Secrets, creating the scope if needed."""
    result = subprocess.run(
        ["databricks", "secrets", "list-scopes", "--output", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  {WARN} Could not list secret scopes: {result.stderr.strip()}")
        return

    try:
        existing = {s["name"] for s in json.loads(result.stdout)}
    except (json.JSONDecodeError, KeyError):
        existing = set()

    if SECRET_SCOPE not in existing:
        print(f"  {ARR} Creating secret scope {C}{SECRET_SCOPE}{W}")
        if not dry_run:
            r = subprocess.run(
                ["databricks", "secrets", "create-scope", SECRET_SCOPE],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                print(f"  {FAIL} Failed to create scope: {r.stderr.strip()}")
                return
            print(f"  {OK} Scope {C}{SECRET_SCOPE}{W} created")
    else:
        print(f"  {OK} Scope {C}{SECRET_SCOPE}{W} already exists")

    if dry_run:
        print(f"  {WARN} {DIM}--dry-run: secret not pushed{W}")
        return

    r = subprocess.run(
        ["databricks", "secrets", "put-secret", SECRET_SCOPE, "AGENT_MODEL_TOKEN", "--string-value", token],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  {FAIL} Failed to push secret: {r.stderr.strip()}")
        return
    print(f"  {OK} Secret {C}AGENT_MODEL_TOKEN{W} pushed to scope {C}{SECRET_SCOPE}{W}")


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

    # genie_space.space_id + name <- PROJECT_GENIE_CHECKIN
    genie_id = os.environ.get("PROJECT_GENIE_CHECKIN", "").strip()
    if genie_id:
        m = re.search(r"genie_space:.*?space_id: '([^']*)'", content, re.DOTALL)
        if m and m.group(1) != genie_id:
            content = re.sub(r"space_id: '[^']*'", f"space_id: '{genie_id}'", content, count=1)
            changes.append(("genie_space.space_id", "PROJECT_GENIE_CHECKIN", genie_id))
        # Replace placeholder name with a fixed DAB label (name is a bundle ref, not workspace-specific)
        if "PLACEHOLDER_GENIE_NAME" in content:
            content = content.replace("PLACEHOLDER_GENIE_NAME", "agent-forge-checkin", 1)
            changes.append(("genie_space.name", None, "agent-forge-checkin"))

    # serving_endpoint <- AGENT_MODEL_ENDPOINT
    # Cross-workspace URL: remove serving_endpoint resource (can't grant on external workspace),
    #   push AGENT_MODEL_TOKEN to Databricks Secrets.
    # Same-workspace (not set or same-host URL): keep serving_endpoint with FM_MODEL name
    #   so the app SP gets CAN_QUERY; remove agent_model_token secret (not needed).
    # Local name: update serving_endpoint.name as usual.
    endpoint = os.environ.get("AGENT_MODEL_ENDPOINT", "").strip()
    databricks_host = os.environ.get("DATABRICKS_HOST", "").strip().rstrip("/")
    fm_model = "databricks-claude-sonnet-4-6"

    # Determine if endpoint is cross-workspace
    _is_cross_workspace = False
    _ep_name_from_url: str | None = None
    if endpoint:
        ep_url = re.search(r"/serving-endpoints/([^/]+)/invocations", endpoint)
        if ep_url:
            _ep_name_from_url = ep_url.group(1)
            ep_host = endpoint[:ep_url.start()].rstrip("/")
            _is_cross_workspace = ep_host != databricks_host

    if not endpoint or (endpoint and _ep_name_from_url and not _is_cross_workspace):
        # Same-workspace mode: ensure serving_endpoint resource uses the FM model name
        # so the app service principal gets CAN_QUERY permission.
        ep_name = _ep_name_from_url or fm_model
        m = re.search(r"(- name: 'serving_endpoint'\s*\n\s+serving_endpoint:\s*\n\s+)name: '([^']*)'", content)
        if m:
            if m.group(2) != ep_name:
                content = re.sub(
                    r"(- name: 'serving_endpoint'\s*\n\s+serving_endpoint:\s*\n\s+)name: '[^']*'",
                    r"\g<1>name: '" + ep_name + "'",
                    content,
                    count=1,
                )
                changes.append(("serving_endpoint.name", None, f"{ep_name} (same-workspace — app SP needs CAN_QUERY)"))
        else:
            # serving_endpoint resource was removed previously — re-add it
            # Insert before ka_endpoint or agent_model_token if they exist, else at end of resources
            se_block = (
                f"\n        - name: 'serving_endpoint'\n"
                f"          serving_endpoint:\n"
                f"            name: '{ep_name}'\n"
                f"            permission: 'CAN_QUERY'"
            )
            # Try to insert before ka_endpoint
            if "- name: 'ka_endpoint'" in content:
                content = content.replace("        - name: 'ka_endpoint'", se_block + "\n        - name: 'ka_endpoint'", 1)
            elif "- name: 'agent_model_token'" in content:
                content = content.replace("        - name: 'agent_model_token'", se_block + "\n        - name: 'agent_model_token'", 1)
            else:
                # Append after last resource block (before targets:)
                content = content.replace("\ntargets:", se_block + "\n\ntargets:", 1)
            changes.append(("serving_endpoint resource", None, f"added ({ep_name} — app SP needs CAN_QUERY)"))

        # Remove agent_model_token secret resource (not needed in same-workspace)
        new_content = re.sub(
            r"\s*- name: 'agent_model_token'\s*\n\s+secret:\s*\n\s+scope: '[^']*'\s*\n\s+key: '[^']*'\s*\n\s+permission: '[^']*'",
            "",
            content,
        )
        if new_content != content:
            content = new_content
            changes.append(("agent_model_token resource", "AGENT_MODEL_ENDPOINT", "removed (same-workspace mode)"))

    elif endpoint and _is_cross_workspace:
        # Cross-workspace: remove serving_endpoint resource (can't grant on external workspace)
        new_content = re.sub(
            r"\s*- name: 'serving_endpoint'\s*\n\s+serving_endpoint:\s*\n\s+name: '[^']*'\s*\n\s+permission: '[^']*'",
            "",
            content,
        )
        if new_content != content:
            content = new_content
            changes.append(("serving_endpoint resource", "AGENT_MODEL_ENDPOINT", "removed (cross-workspace URL)"))

        # Push AGENT_MODEL_TOKEN to Databricks Secrets
        model_token = os.environ.get("AGENT_MODEL_TOKEN", "").strip()
        if model_token:
            print(f"\n{BOLD}Databricks Secrets:{W}")
            ensure_secret(model_token, args.dry_run)
        else:
            print(f"  {WARN} AGENT_MODEL_TOKEN not set in .env.local — secret not pushed")

    elif endpoint and not _ep_name_from_url:
        # Local endpoint name (not a URL) — update serving_endpoint.name
        m = re.search(r"serving_endpoint:\s*\n\s+name: '([^']*)'", content)
        if m and m.group(1) != endpoint:
            content = re.sub(
                r"(serving_endpoint:\s*\n\s+)name: '[^']*'",
                r"\g<1>name: '" + endpoint + "'",
                content,
                count=1,
            )
            changes.append(("serving_endpoint.name", "AGENT_MODEL_ENDPOINT", endpoint))

    # ka_endpoint.name <- PROJECT_KA_PASSENGERS
    ka_endpoint = os.environ.get("PROJECT_KA_PASSENGERS", "").strip()
    if ka_endpoint:
        m = re.search(r"ka_endpoint.*?serving_endpoint:.*?name: '([^']*)'", content, re.DOTALL)
        if m and m.group(1) != ka_endpoint:
            content = re.sub(
                r"(name: 'ka_endpoint'\s*\n\s+serving_endpoint:\s*\n\s+)name: '[^']*'",
                r"\g<1>name: '" + ka_endpoint + "'",
                content,
                count=1,
            )
            changes.append(("ka_endpoint.name", "PROJECT_KA_PASSENGERS", ka_endpoint))
    else:
        # Remove ka_endpoint resource block so PLACEHOLDER check doesn't abort
        new_content = re.sub(
            r"\s*- name: 'ka_endpoint'\s*\n\s+serving_endpoint:\s*\n\s+name: '[^']*'\s*\n\s+permission: '[^']*'",
            "",
            content,
        )
        if new_content != content:
            content = new_content
            changes.append(("ka_endpoint resource", "PROJECT_KA_PASSENGERS", "removed (not configured)"))

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

    schema_spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()

    # app.yaml env var sync
    # AGENT_MODEL_ENDPOINT + AGENT_MODEL_TOKEN: only present when cross-workspace endpoint is set.
    # All others: always present, value updated from .env.local.
    if app_yml.exists():
        app_content = app_yml.read_text()
        app_changed = False

        def _app_has(name: str) -> bool:
            return bool(re.search(rf"- name: {name}\b", app_content))

        def _app_remove(content: str, name: str) -> str:
            """Remove a full env entry block (- name: KEY\n    value/valueFrom: ...\n)."""
            # Remove optional preceding comment line too
            content = re.sub(rf"  #[^\n]*\n(?=  - name: {name}\b)", "", content)
            return re.sub(rf"  - name: {name}\b[^\n]*\n(?:    [^\n]*\n)*", "", content)

        def _app_set(content: str, name: str, value: str, use_value_from: bool = False) -> str:
            """Update existing entry value, or append if missing."""
            key = "valueFrom" if use_value_from else "value"
            pattern = rf"({name}\s*\n\s+{key}:\s*)[\"']([^\"']*)[\"']"
            if re.search(pattern, content):
                return re.sub(pattern, r'\g<1>"' + value + '"', content, count=1)
            # Append before PROJECT_UNITY_CATALOG_SCHEMA as anchor
            entry = f'  - name: {name}\n    {key}: "{value}"\n'
            return content.replace("  - name: PROJECT_UNITY_CATALOG_SCHEMA", entry + "  - name: PROJECT_UNITY_CATALOG_SCHEMA", 1)

        # AGENT_MODEL_ENDPOINT: always set explicitly in app.yaml.
        # In same-workspace mode, use just the model name (not a full URL) so
        # agent.py takes the local-name path with default WorkspaceClient auth,
        # avoiding host-comparison mismatches at runtime.
        # AGENT_MODEL_TOKEN: only inject for cross-workspace (via Databricks Secrets).
        effective_endpoint = endpoint or fm_model
        if effective_endpoint:
            new = _app_set(app_content, "AGENT_MODEL_ENDPOINT", effective_endpoint)
            if _is_cross_workspace and not _app_has("AGENT_MODEL_TOKEN"):
                new += '  # Secret injected via DAB resource agent_model_token (scope: agent-forge, key: AGENT_MODEL_TOKEN).\n'
                new += '  - name: AGENT_MODEL_TOKEN\n    valueFrom: "agent_model_token"\n'
            elif not _is_cross_workspace and _app_has("AGENT_MODEL_TOKEN"):
                new = _app_remove(new, "AGENT_MODEL_TOKEN")
            if new != app_content:
                app_content = new; app_changed = True
                label = "cross-workspace" if _is_cross_workspace else "same-workspace (explicit)"
                changes.append(("app.yaml  AGENT_MODEL_ENDPOINT", None, f"{effective_endpoint} ({label})"))

        # Standard value fields
        for env_name, value in [
            ("PROJECT_UNITY_CATALOG_SCHEMA", schema_spec),
            ("DATABRICKS_WAREHOUSE_ID", wh_id),
            ("PROJECT_KA_PASSENGERS", ka_endpoint),
        ]:
            if not value:
                # Remove if present (not configured)
                if _app_has(env_name):
                    app_content = _app_remove(app_content, env_name)
                    app_changed = True
                    changes.append((f"app.yaml  {env_name}", None, "(removed — not configured)"))
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

    # Always print current config summary
    host = os.environ.get("DATABRICKS_HOST", "").strip()
    genie_id_display = os.environ.get("PROJECT_GENIE_CHECKIN", "").strip()
    print(f"\n{BOLD}Current config:{W}")
    for label, val in [
        ("DATABRICKS_HOST              ", host),
        ("DATABRICKS_WAREHOUSE_ID      ", wh_id),
        ("PROJECT_UNITY_CATALOG_SCHEMA ", schema_spec),
        ("PROJECT_GENIE_CHECKIN        ", genie_id_display),
        ("PROJECT_KA_PASSENGERS        ", ka_endpoint),
        ("AGENT_MODEL_ENDPOINT         ", endpoint),
        ("DBX_APP_NAME                 ", app_name),
    ]:
        marker = OK if val else WARN
        display = val if val else f"{DIM}not set{W}"
        print(f"  {marker}  {label}{C}{display}{W}")

    if not changes:
        print(f"\n  {OK} {G}databricks.yml{W} and {G}app.yaml{W} already in sync with {C}.env.local{W}")
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
