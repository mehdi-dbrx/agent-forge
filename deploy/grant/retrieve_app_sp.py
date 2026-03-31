#!/usr/bin/env python3
"""Retrieve app service principal info (name + application ID) from Databricks.

Usage:
  uv run python deploy/grant/retrieve_app_sp.py [APP_NAME]

  APP_NAME: Databricks app name (default: DBX_APP_NAME from .env.local)
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local")

from databricks.sdk import WorkspaceClient


def main() -> int:
    default_app = os.environ.get("DBX_APP_NAME", "").strip()
    parser = argparse.ArgumentParser(description="Retrieve app service principal info")
    parser.add_argument(
        "app_name",
        nargs="?",
        default=default_app,
        help="Databricks app name (default: DBX_APP_NAME from .env.local)",
    )
    args = parser.parse_args()

    if not args.app_name:
        print("Error: app name required. Pass as argument or set DBX_APP_NAME in .env.local", file=sys.stderr)
        return 1

    w = WorkspaceClient()
    try:
        app = w.apps.get(name=args.app_name)
    except Exception as e:
        print(f"Error: Could not get app '{args.app_name}': {e}", file=sys.stderr)
        return 1

    sp_name = getattr(app, "service_principal_name", None)
    sp_id = getattr(app, "service_principal_client_id", None) or getattr(app, "oauth2_app_client_id", None)

    print(json.dumps({
        "service_principal_name": sp_name,
        "service_principal_client_id": sp_id,
        "app_name": app.name,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
