#!/usr/bin/env python3
"""Grant CAN_QUERY on serving endpoints to the app's service principal.

Grants on all serving_endpoint resources declared in databricks.yml.
Resolves endpoint IDs via SDK (the permissions API requires IDs, not names).
Foundation model endpoints (system-managed, id=None) are skipped — they are
accessible to all workspace users by default.

Usage:
  uv run python deploy/grant/authorize_endpoint_for_app.py [APP_NAME]

  APP_NAME: Databricks app name (default: DBX_APP_NAME from .env.local)
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local")

import requests
from databricks.sdk import WorkspaceClient


def _endpoint_names_from_yml() -> list[str]:
    """Extract all serving_endpoint names from databricks.yml resources."""
    yml = ROOT / "databricks.yml"
    if not yml.exists():
        return []
    content = yml.read_text()
    return re.findall(
        r"serving_endpoint:\s*\n\s+name:\s*'([^']+)'",
        content,
    )


def _resolve_endpoint_id(w: WorkspaceClient, name: str) -> str | None:
    """Resolve endpoint name to ID via SDK. Returns None for FM endpoints (id=None)."""
    try:
        ep = w.serving_endpoints.get(name)
        return ep.id
    except Exception as e:
        print(f"    Could not resolve endpoint '{name}': {e}", file=sys.stderr)
        return None


def _grant_can_query(host: str, token: str, endpoint_id: str, sp_name: str) -> bool:
    """Grant CAN_QUERY on a serving endpoint to a service principal via REST API."""
    url = f"{host}/api/2.0/permissions/serving-endpoints/{endpoint_id}"
    resp = requests.patch(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "access_control_list": [
                {
                    "service_principal_name": sp_name,
                    "permission_level": "CAN_QUERY",
                }
            ]
        },
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"    {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
    return resp.status_code == 200


def main() -> int:
    default_app = os.environ.get("DBX_APP_NAME", "").strip()

    parser = argparse.ArgumentParser(
        description="Grant CAN_QUERY on serving endpoints to app service principal",
    )
    parser.add_argument("app_name", nargs="?", default=default_app, help="Databricks app name")
    args = parser.parse_args()

    if not args.app_name:
        print("Error: app name required. Pass as argument or set DBX_APP_NAME in .env.local", file=sys.stderr)
        return 1

    w = WorkspaceClient()
    host = w.config.host.rstrip("/")
    token = w.config.token

    try:
        app = w.apps.get(name=args.app_name)
    except Exception as e:
        print(f"Error: Could not get app '{args.app_name}': {e}", file=sys.stderr)
        return 1

    sp_id = getattr(app, "service_principal_client_id", None)
    if not sp_id:
        print(f"Error: App '{args.app_name}' has no service_principal_client_id", file=sys.stderr)
        return 1
    sp_display = getattr(app, "service_principal_name", sp_id)

    endpoints = _endpoint_names_from_yml()
    if not endpoints:
        print("No serving_endpoint resources found in databricks.yml")
        return 0

    errors = 0
    for ep_name in endpoints:
        ep_id = _resolve_endpoint_id(w, ep_name)
        if not ep_id:
            print(f"  [~] {ep_name} — skipped (FM endpoint or not found, no grantable ID)")
            continue
        print(f"Granting CAN_QUERY on {ep_name} ({ep_id}) to {sp_display}")
        if _grant_can_query(host, token, ep_id, sp_id):
            print(f"  [+] {ep_name}")
        else:
            print(f"  [-] {ep_name} — grant failed", file=sys.stderr)
            errors += 1

    if errors:
        print(f"Warning: {errors} endpoint grant(s) failed", file=sys.stderr)
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
