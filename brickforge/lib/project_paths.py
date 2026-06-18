"""Project-scoped artifact path resolution.

All generated artifacts (prompts, SQL, CSVs) are scoped per project.
PROJECT_DIR env var points to the active project's artifact directory.
No fallback to package-level dirs — if no project is active, fail loud.
"""
import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def get_project_dir() -> Path | None:
    """Return the active project artifact directory, or None."""
    pd = os.environ.get("PROJECT_DIR", "").strip()
    return Path(pd) if pd else None


def prompt_dir() -> Path:
    """Prompt directory: project-scoped only. Raises if no project active."""
    pd = get_project_dir()
    if pd:
        d = pd / "prompt"
        d.mkdir(parents=True, exist_ok=True)
        return d
    raise RuntimeError("No active project. PROJECT_DIR not set. Create or load a project first.")


def gen_dir() -> Path:
    """Gen artifact directory: project-scoped only. Raises if no project active."""
    pd = get_project_dir()
    if pd:
        d = pd / "gen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    raise RuntimeError("No active project. PROJECT_DIR not set. Create or load a project first.")


def init_artifact_dirs(artifact_dir: Path) -> None:
    """Create the standard artifact subdirs for a project."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "prompt").mkdir(exist_ok=True)
    (artifact_dir / "gen").mkdir(exist_ok=True)
    (artifact_dir / "conf").mkdir(exist_ok=True)
