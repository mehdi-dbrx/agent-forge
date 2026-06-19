#!/usr/bin/env python3
"""Push Agent App project to GitHub via Databricks Git Folders.

Uses Databricks-stored git credentials (no PAT needed from the user).
Flow:
1. Create Git Folder linked to user's repo
2. Write project files into it via workspace API
3. Submit one-shot job to git add + commit + push

Usage:
    python deploy/git_push.py --repo-url https://github.com/user/repo.git --config config.json
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import zipfile
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat

ROOT = Path(__file__).resolve().parents[1]


def check_git_credentials(w: WorkspaceClient) -> bool:
    """Check if the user has git credentials configured in Databricks."""
    try:
        creds = list(w.git_credentials.list())
        return len(creds) > 0
    except Exception:
        return False


def create_git_folder(w: WorkspaceClient, repo_url: str, provider: str = "github") -> str:
    """Create a Databricks Git Folder linked to the repo. Returns the workspace path."""
    me = w.current_user.me()
    # Derive repo name from URL
    repo_name = repo_url.rstrip("/").rstrip(".git").rsplit("/", 1)[-1]
    git_folder_path = f"/Repos/{me.user_name}/{repo_name}"

    try:
        # Check if already exists
        existing = w.workspace.get_status(git_folder_path)
        print(f"[+] Git Folder already exists: {git_folder_path}")
        return git_folder_path
    except Exception:
        pass

    # Detect provider from URL
    if "gitlab" in repo_url.lower():
        provider = "gitlab"
    elif "bitbucket" in repo_url.lower():
        provider = "bitbucket"

    print(f"[~] Creating Git Folder: {git_folder_path} -> {repo_url}")
    repo = w.repos.create(url=repo_url, provider=provider, path=git_folder_path)
    print(f"[+] Git Folder created (repo_id: {repo.id})")
    return git_folder_path


def upload_files_to_git_folder(
    w: WorkspaceClient,
    git_folder_path: str,
    bundle_zip: bytes,
) -> int:
    """Extract files from bundle zip and upload to Git Folder via workspace API."""
    zf = zipfile.ZipFile(io.BytesIO(bundle_zip))
    names = [n for n in zf.namelist() if not n.endswith("/")]

    # Create directories
    dirs_needed = set()
    for name in names:
        parts = name.split("/")
        for i in range(1, len(parts)):
            dirs_needed.add("/".join(parts[:i]))

    print(f"[~] Creating {len(dirs_needed)} directories...")
    for d in sorted(dirs_needed):
        try:
            w.workspace.mkdirs(f"{git_folder_path}/{d}")
        except Exception:
            pass

    # Upload files
    uploaded = 0
    for name in names:
        content = zf.read(name)
        b64 = base64.b64encode(content).decode()
        dest = f"{git_folder_path}/{name}"
        try:
            w.workspace.import_(
                path=dest,
                content=b64,
                format=ImportFormat.AUTO,
                overwrite=True,
            )
            uploaded += 1
            if uploaded % 50 == 0:
                print(f"[~] {uploaded}/{len(names)} files...")
        except Exception as e:
            print(f"[!] {name}: {str(e)[:80]}")

    print(f"[+] {uploaded}/{len(names)} files uploaded to {git_folder_path}")
    return uploaded


def commit_and_push(w: WorkspaceClient, git_folder_path: str, message: str) -> bool:
    """Submit a one-shot job to git add + commit + push inside the Git Folder."""
    import time

    commit_script = f"""\
import subprocess, sys
repo = "{git_folder_path.replace('/Repos/', '/Workspace/Repos/')}"
r1 = subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, text=True)
if r1.returncode != 0:
    print(f"git add failed: {{r1.stderr}}", file=sys.stderr)
    sys.exit(1)
r2 = subprocess.run(["git", "commit", "-m", "{message}"], cwd=repo, capture_output=True, text=True)
if r2.returncode != 0:
    if "nothing to commit" in r2.stdout:
        print("[+] Nothing to commit (already up to date)")
        sys.exit(0)
    print(f"git commit failed: {{r2.stderr}}", file=sys.stderr)
    sys.exit(1)
r3 = subprocess.run(["git", "push"], cwd=repo, capture_output=True, text=True)
if r3.returncode != 0:
    print(f"git push failed: {{r3.stderr}}", file=sys.stderr)
    sys.exit(1)
print("[+] Committed and pushed successfully")
"""

    print(f"[~] Submitting commit+push job...")
    try:
        # Use the SDK to run a one-shot task
        from databricks.sdk.service.jobs import (
            SubmitTask,
            SparkPythonTask,
            NotebookTask,
        )

        # Create a temporary notebook-style task that runs the git commands
        # Actually, use a Python script task on serverless
        run = w.jobs.submit(
            run_name="brickforge-git-push",
            tasks=[
                SubmitTask(
                    task_key="git_push",
                    spark_python_task=SparkPythonTask(
                        python_file="dbfs:/tmp/brickforge_git_push.py",
                    ),
                ),
            ],
        )
        print(f"[~] Job submitted: {run.run_id}")

        # Wait for completion
        for _ in range(60):
            status = w.jobs.get_run(run.run_id)
            state = status.state.life_cycle_state.value if status.state else "UNKNOWN"
            if state in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"):
                result = status.state.result_state.value if status.state.result_state else "UNKNOWN"
                print(f"[{'+'  if result == 'SUCCESS' else 'x'}] Job {state}: {result}")
                return result == "SUCCESS"
            time.sleep(5)

        print("[x] Job timed out")
        return False

    except Exception as e:
        print(f"[x] Job submission failed: {e}")
        print(f"[~] Files are in Git Folder. Commit manually from Databricks UI.")
        return False


def git_push(config: dict, repo_url: str) -> dict:
    """Full git push flow: create folder, upload files, commit+push."""
    from deploy.deploy_agent_app import build_agent_bundle

    w = WorkspaceClient()

    # Check git credentials
    if not check_git_credentials(w):
        print("[x] No git credentials configured in Databricks.")
        print("    Go to Settings > Developer > Git integration to connect GitHub.")
        return {"ok": False, "error": "no_git_credentials"}

    # Build bundle (strip tokens -- never commit secrets to git)
    import copy
    clean_config = copy.deepcopy(config)
    for section in ("workspace", "model"):
        if section in clean_config:
            clean_config[section].pop("token", None)
    print("[~] Building agent bundle...")
    bundle = build_agent_bundle(clean_config)
    print(f"[+] Bundle: {len(bundle)/1024/1024:.1f} MB")

    # Create Git Folder
    git_folder_path = create_git_folder(w, repo_url)

    # Upload files
    upload_files_to_git_folder(w, git_folder_path, bundle)

    # Commit and push
    ok = commit_and_push(w, git_folder_path, "BrickForge: project update")

    return {
        "ok": ok,
        "repo_url": repo_url,
        "git_folder_path": git_folder_path,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push Agent App to GitHub")
    parser.add_argument("--repo-url", required=True, help="GitHub/GitLab repo URL")
    parser.add_argument("--config", required=True, help="Config JSON path")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    result = git_push(config, args.repo_url)
    print(json.dumps(result, indent=2))
