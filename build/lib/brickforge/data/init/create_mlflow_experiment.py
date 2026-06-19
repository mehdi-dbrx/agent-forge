#!/usr/bin/env python3
"""
Create an MLflow experiment and update .env.local with MLFLOW_EXPERIMENT_ID.

Requires: DATABRICKS_HOST, DATABRICKS_TOKEN or DATABRICKS_CONFIG_PROFILE.
"""
import os
import sys
from pathlib import Path

from coolname import generate_slug


ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main() -> None:
    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        current_user = w.current_user.me()
        username = getattr(current_user, "user_name", "unknown") or "unknown"
    except Exception as e:
        print(f"Failed to connect: {e}", file=sys.stderr)
        sys.exit(1)

    slug = generate_slug(2)
    experiment_name = f"/Users/{username}/brick-forge-{slug}"
    experiment_id = ""

    try:
        exp = w.experiments.create_experiment(name=experiment_name)
        experiment_id = str(getattr(exp, "experiment_id", ""))
    except Exception as e:
        if "RESOURCE_ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
            slug = generate_slug(3)
            experiment_name = f"/Users/{username}/brick-forge-{slug}"
            try:
                exp = w.experiments.create_experiment(name=experiment_name)
                experiment_id = str(getattr(exp, "experiment_id", ""))
            except Exception as e2:
                print(f"Failed to create experiment: {e2}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Failed to create experiment: {e}", file=sys.stderr)
            sys.exit(1)

    if not experiment_id:
        print("Created experiment but no ID returned", file=sys.stderr)
        sys.exit(1)

    config_file = os.environ.get("CONFIG_FILE", "")
    if config_file:
        from lib.config_json import read_config, write_config
        config = read_config()
        config.setdefault("app", {})["mlflow_experiment_id"] = experiment_id
        write_config(config)
        print(experiment_id)
        print(f"Updated {config_file} with mlflow_experiment_id={experiment_id}", file=sys.stderr)
    else:
        env_path = Path(os.environ.get("ENV_FILE", str(ROOT / ".env.local")))
        lines = env_path.read_text().splitlines() if env_path.exists() else []

        def _upsert(lines: list[str], key: str, value: str) -> list[str]:
            new_lines = []
            replaced = False
            for line in lines:
                if line.strip().startswith(f"{key}="):
                    new_lines.append(f"{key}={value}")
                    replaced = True
                else:
                    new_lines.append(line)
            if not replaced:
                new_lines.append(f"{key}={value}")
            return new_lines

        lines = _upsert(lines, "MLFLOW_EXPERIMENT_ID", experiment_id)
        lines = _upsert(lines, "MLFLOW_TRACKING_URI", "databricks")
        lines = _upsert(lines, "MLFLOW_REGISTRY_URI", "databricks-uc")
        env_path.write_text("\n".join(lines) + "\n")
        print(experiment_id)
        print(f"Updated {env_path} with MLFLOW_EXPERIMENT_ID", file=sys.stderr)


if __name__ == "__main__":
    main()
