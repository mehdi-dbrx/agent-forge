"""Project-scoped artifact path resolution.

All generated artifacts (prompts, SQL, CSVs) are scoped per project.
PROJECT_DIR env var points to the active project's artifact directory.
Falls back to package-level dirs when not set.
"""
import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def get_project_dir() -> Path | None:
    """Return the active project artifact directory, or None."""
    pd = os.environ.get("PROJECT_DIR", "").strip()
    return Path(pd) if pd else None


def prompt_dir() -> Path:
    """Prompt directory: project-scoped if active, else package-level.
    When a project is active, always uses the project dir (no fallback to shared)."""
    pd = get_project_dir()
    if pd:
        d = pd / "prompt"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return PACKAGE_ROOT / "conf" / "prompt"


def gen_dir() -> Path:
    """Gen artifact directory: project-scoped if active, else package-level.
    When a project is active, always uses the project dir (no fallback to shared)."""
    pd = get_project_dir()
    if pd:
        d = pd / "gen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return PACKAGE_ROOT / "data" / "gen"


def init_artifact_dirs(artifact_dir: Path) -> None:
    """Create the standard artifact subdirs for a project."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "prompt").mkdir(exist_ok=True)
    (artifact_dir / "gen").mkdir(exist_ok=True)
    (artifact_dir / "conf").mkdir(exist_ok=True)
