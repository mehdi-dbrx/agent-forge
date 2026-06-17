#!/usr/bin/env python3
"""Grant Lakebase permissions to the app service principal.

Grants the SP the ability to connect, create schemas, and manage tables
in the Lakebase instance used for agent memory (checkpointing + user store).

Usage:
  uv run python deploy/grant/grant_lakebase_for_app.py [APP_NAME]

  APP_NAME: Databricks app name (default: DBX_APP_NAME from .env.local)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]



def _get_sp_client_id(app_name: str) -> str | None:
    """Retrieve service principal client ID from app."""
    try:
        r = subprocess.run(
            ["databricks", "apps", "get", app_name, "--output", "json"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return None
        import json
        data = json.loads(r.stdout)
        return data.get("service_principal_client_id") or data.get("oauth2_app_client_id")
    except Exception:
        return None


def main() -> int:
    default_app = os.environ.get("DBX_APP_NAME", "").strip()
    instance_name = os.environ.get("LAKEBASE_INSTANCE_NAME", "").strip()

    parser = argparse.ArgumentParser(description="Grant Lakebase permissions to app SP")
    parser.add_argument("app_name", nargs="?", default=default_app,
                        help="Databricks app name (default: DBX_APP_NAME)")
    args = parser.parse_args()

    if not args.app_name:
        print("[x] app name required -- pass as argument or set DBX_APP_NAME", file=sys.stderr)
        return 1

    if not instance_name:
        print("[~] LAKEBASE_INSTANCE_NAME not set -- skipping Lakebase grants")
        return 0

    sp_id = _get_sp_client_id(args.app_name)
    if not sp_id:
        print(f"[x] could not retrieve SP for app '{args.app_name}' -- deploy the app first", file=sys.stderr)
        return 1

    print(f"[~] granting Lakebase access to SP {sp_id} on instance {instance_name}...")

    from databricks_ai_bridge.lakebase import LakebaseClient

    try:
        client = LakebaseClient(instance_name=instance_name)

        # Grant role
        client.create_role(sp_id, "SERVICE_PRINCIPAL")
        print(f"  [+] role created for {sp_id}")

        # Grant schema-level permissions
        schemas = ["public"]
        client.grant_schema(grantee=sp_id, schemas=schemas,
                           privileges=["USAGE", "CREATE"])
        print(f"  [+] schema USAGE + CREATE on {schemas}")

        # Grant table-level permissions on all tables
        client.grant_all_tables_in_schema(grantee=sp_id, schemas=schemas,
                                          privileges=["SELECT", "INSERT", "UPDATE", "DELETE"])
        print(f"  [+] table SELECT/INSERT/UPDATE/DELETE on all tables in {schemas}")

        # Grant sequence permissions (needed for checkpoint IDs)
        client.grant_all_sequences_in_schema(grantee=sp_id, schemas=schemas,
                                             privileges=["USAGE", "SELECT", "UPDATE"])
        print(f"  [+] sequence USAGE/SELECT/UPDATE on {schemas}")

        print(f"[+] Lakebase grants applied for {args.app_name}")
        return 0

    except ImportError:
        print("[x] LakebaseClient not available -- install databricks-ai-bridge[memory]", file=sys.stderr)
        return 1
    except Exception as e:
        # Fallback: try SQL-based grants via databricks CLI
        print(f"  [~] LakebaseClient failed ({e}), trying SQL fallback...")
        try:
            sqls = [
                f"GRANT USAGE, CREATE ON SCHEMA public TO '{sp_id}'",
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO '{sp_id}'",
                f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO '{sp_id}'",
            ]
            for sql in sqls:
                r = subprocess.run(
                    ["databricks", "database", "execute-statement", instance_name,
                     "--statement", sql, "--output", "json"],
                    capture_output=True, text=True, timeout=30,
                )
                if r.returncode != 0:
                    print(f"  [x] SQL failed: {sql[:60]}... -- {r.stderr.strip()[:100]}", file=sys.stderr)
                else:
                    print(f"  [+] {sql[:60]}...")
            print(f"[+] Lakebase grants applied via SQL for {args.app_name}")
            return 0
        except Exception as e2:
            print(f"[x] SQL fallback failed: {e2}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
