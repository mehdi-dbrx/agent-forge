#!/usr/bin/env python3
"""
Create a Lakebase (database) instance if it doesn't already exist.

Default instance name: agent-forge-lakebase (override with LAKEBASE_INSTANCE_NAME env var).

Updates .env.local with LAKEBASE_INSTANCE_NAME on success.

Requires: DATABRICKS_HOST + auth (token or profile).
"""
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

DEFAULT_INSTANCE_NAME = "agent-forge-lakebase"


def _cli_args() -> list[str]:
    """Build databricks CLI auth args from env."""
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    if profile:
        return ["-p", profile]
    return []


def _instance_exists(name: str) -> bool:
    """Check if a Lakebase instance with the given name already exists."""
    args = ["databricks", "database", "get-database-instance", name, "--output", "json"] + _cli_args()
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode == 0


def _wait_for_instance(name: str, timeout: int = 600) -> bool:
    """Poll until the instance reaches AVAILABLE state (or timeout)."""
    args_base = ["databricks", "database", "get-database-instance", name, "--output", "json"] + _cli_args()
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(args_base, capture_output=True, text=True)
        if r.returncode == 0:
            import json
            try:
                data = json.loads(r.stdout)
                state = data.get("state", "").upper()
                if state == "AVAILABLE":
                    return True
                if state in ("FAILED", "DELETED"):
                    print(f"Instance entered {state} state", file=sys.stderr)
                    return False
            except json.JSONDecodeError:
                pass
        time.sleep(10)
    return False


def _update_env(key: str, value: str) -> None:
    """Write key=value to config.json (or .env.local fallback)."""
    config_file = os.environ.get("CONFIG_FILE", "")
    if config_file:
        from lib.config_json import read_config, write_config
        config = read_config()
        if key == "LAKEBASE_INSTANCE_NAME":
            config.setdefault("lakebase", {})["instance_name"] = value
        write_config(config)
        print(f"Updated {config_file} with {key}={value}", file=sys.stderr)
    else:
        env_path = Path(os.environ.get("ENV_FILE", str(ROOT / ".env.local")))
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        lines = [ln for ln in lines if not ln.strip().startswith(f"{key}=") and not ln.strip().startswith(f"#{key}=")]
        lines.append(f"{key}={value}")
        env_path.write_text("\n".join(lines) + "\n")
        print(f"Updated {env_path} with {key}={value}", file=sys.stderr)


def main():
    instance_name = os.environ.get("LAKEBASE_INSTANCE_NAME", "").strip() or DEFAULT_INSTANCE_NAME

    # Check if instance already exists
    if _instance_exists(instance_name):
        print(f"Lakebase instance '{instance_name}' already exists -- skipping creation")
        _update_env("LAKEBASE_INSTANCE_NAME", instance_name)
        return

    # Create the instance (--no-wait so we can poll ourselves with progress)
    print(f"Creating Lakebase instance '{instance_name}'...")
    args = [
        "databricks", "database", "create-database-instance", instance_name,
        "--capacity", "CU_1",
        "--no-wait",
    ] + _cli_args()

    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        err = r.stderr.strip() or r.stdout.strip()
        print(f"Failed to create Lakebase instance: {err}", file=sys.stderr)
        sys.exit(1)

    print(f"Instance creation initiated. Waiting for AVAILABLE state (up to 10 min)...")
    if not _wait_for_instance(instance_name):
        print("Timed out waiting for instance to become AVAILABLE", file=sys.stderr)
        sys.exit(1)

    print(f"Lakebase instance '{instance_name}' is AVAILABLE")
    _update_env("LAKEBASE_INSTANCE_NAME", instance_name)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
