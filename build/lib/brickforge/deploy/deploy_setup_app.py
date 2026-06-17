#!/usr/bin/env python3
"""
Deploy the BrickForge Setup App to Databricks Apps.

Uses the Databricks SDK (not CLI binary) to create/update the app
and deploy the source code. The Setup App is the visual wizard that
helps users configure and deploy agent projects.

Usage:
    uv run python deploy/deploy_setup_app.py [--app-name NAME] [--dry-run]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Directories to include in the Setup App bundle
INCLUDE_DIRS = [
    "visual/backend",
    "visual/frontend/dist",
    "agent",
    "conf",
    "data",
    "deploy",
    "scripts",
    "stash",
    "tools",
]

INCLUDE_FILES = [
    "app.yaml",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".env.local",
]

EXCLUDE_PATTERNS = {
    "__pycache__", ".mypy_cache", ".pytest_cache",
    "node_modules", ".git", ".DS_Store",
}


def log(msg: str, level: str = "info"):
    prefix = {"info": "[+]", "warn": "[!]", "error": "[x]", "step": "[>]"}
    print(f"{prefix.get(level, '[+]')} {msg}")


def check_prerequisites():
    """Verify Databricks CLI is available and authenticated."""
    try:
        result = subprocess.run(
            ["databricks", "auth", "describe"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            log("Databricks CLI not authenticated. Run: databricks auth login", "error")
            sys.exit(1)
        log("Databricks CLI authenticated")
    except FileNotFoundError:
        log("Databricks CLI not found. Install: pip install databricks-cli", "error")
        sys.exit(1)


def check_frontend_built():
    """Verify frontend dist exists (pre-built)."""
    dist = PROJECT_ROOT / "visual" / "frontend" / "dist" / "index.html"
    if not dist.exists():
        log("Frontend not built. Run: cd visual/frontend && npm run build", "error")
        sys.exit(1)
    log("Frontend dist found")


def check_app_yaml():
    """Verify app.yaml exists."""
    app_yaml = PROJECT_ROOT / "app.yaml"
    if not app_yaml.exists():
        log("app.yaml not found at project root", "error")
        sys.exit(1)
    log(f"app.yaml: {app_yaml.read_text().strip()[:80]}...")


def deploy_via_cli(app_name: str, dry_run: bool = False):
    """Deploy using 'databricks apps deploy' CLI command."""
    log(f"Deploying Setup App as '{app_name}'...", "step")

    if dry_run:
        log("DRY RUN — would run: databricks apps deploy " + app_name)
        # Validate bundle structure
        cmd = ["databricks", "apps", "get", app_name]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            log(f"App '{app_name}' already exists — deploy would update")
        else:
            log(f"App '{app_name}' does not exist — deploy would create")
        return

    # Create app if it doesn't exist
    check_cmd = ["databricks", "apps", "get", app_name]
    result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        log(f"Creating app '{app_name}'...", "step")
        create_cmd = ["databricks", "apps", "create", app_name]
        result = subprocess.run(
            create_cmd, capture_output=True, text=True, timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            log(f"Failed to create app: {result.stderr}", "error")
            sys.exit(1)
        log(f"App '{app_name}' created")

    # Deploy source code
    deploy_cmd = ["databricks", "apps", "deploy", app_name, "--source-code-path", str(PROJECT_ROOT)]
    log(f"Running: {' '.join(deploy_cmd)}", "step")
    result = subprocess.run(
        deploy_cmd,
        capture_output=False,  # stream output
        timeout=300,
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        log("Deploy failed", "error")
        sys.exit(1)

    log(f"Setup App deployed as '{app_name}'")

    # Get app URL
    get_cmd = ["databricks", "apps", "get", app_name, "--output", "json"]
    result = subprocess.run(get_cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            url = data.get("url", "")
            if url:
                log(f"App URL: {url}")
        except json.JSONDecodeError:
            pass


def main():
    parser = argparse.ArgumentParser(description="Deploy BrickForge Setup App")
    parser.add_argument("--app-name", default="brickforge-setup", help="Databricks App name")
    parser.add_argument("--dry-run", action="store_true", help="Validate without deploying")
    args = parser.parse_args()

    log(f"BrickForge Setup App Deployment", "step")
    log(f"App name: {args.app_name}")
    log(f"Project root: {PROJECT_ROOT}")

    check_prerequisites()
    check_frontend_built()
    check_app_yaml()
    deploy_via_cli(args.app_name, args.dry_run)

    if not args.dry_run:
        log("Done. Open the app URL in your browser to start the Setup Wizard.")


if __name__ == "__main__":
    main()
