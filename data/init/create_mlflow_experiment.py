#!/usr/bin/env python3
"""
Create an MLflow experiment and update .env.local with MLFLOW_EXPERIMENT_ID.

Requires: DATABRICKS_HOST, DATABRICKS_TOKEN or DATABRICKS_CONFIG_PROFILE.
"""
import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
load_dotenv(ROOT / ".env.local", override=True)


def main() -> None:
    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        current_user = w.current_user.me()
        username = getattr(current_user, "user_name", "unknown") or "unknown"
    except Exception as e:
        print(f"Failed to connect: {e}", file=sys.stderr)
        sys.exit(1)

    experiment_name = f"/Users/{username}/agent-forge"
    experiment_id = ""

    try:
        exp = w.experiments.create_experiment(name=experiment_name)
        experiment_id = str(getattr(exp, "experiment_id", ""))
    except Exception as e:
        if "RESOURCE_ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
            experiment_name = f"/Users/{username}/agent-forge-{secrets.token_hex(4)}"
            try:
                exp = w.experiments.create_experiment(name=experiment_name)
                experiment_id = str(getattr(exp, "experiment_id", ""))
            except Exception as e2:
                print(f"Failed to create experiment with suffix: {e2}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Failed to create experiment: {e}", file=sys.stderr)
            sys.exit(1)

    if not experiment_id:
        print("Created experiment but no ID returned", file=sys.stderr)
        sys.exit(1)

    env_path = ROOT / ".env.local"
    key = "MLFLOW_EXPERIMENT_ID"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    new_lines = []
    replaced = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={experiment_id}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}={experiment_id}")
    env_path.write_text("\n".join(new_lines) + "\n")

    print(experiment_id)
    print(f"Updated {env_path} with {key}={experiment_id}", file=sys.stderr)


if __name__ == "__main__":
    main()
