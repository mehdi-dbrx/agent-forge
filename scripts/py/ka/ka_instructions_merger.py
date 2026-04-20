"""Load shared `output.format` from config/ka/output_format.yml and merge with per-agent instructions."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SHARED_OUTPUT_FORMAT_PATH = ROOT / "config" / "ka" / "output_format.yml"


def load_shared_output_format() -> str:
    """Return `output.format` text from YAML, or empty string if missing/invalid."""
    if not SHARED_OUTPUT_FORMAT_PATH.exists():
        return ""
    try:
        import yaml

        data = yaml.safe_load(SHARED_OUTPUT_FORMAT_PATH.read_text(encoding="utf-8"))
        if not data:
            return ""
        out = data.get("output") or {}
        fmt = out.get("format")
        if fmt is None:
            return ""
        return str(fmt).strip()
    except Exception:
        return ""


def merge_instructions(shared_format: str, per_ka_instructions: str) -> str:
    """Prepend shared output.format, then per-KA instructions, separated by a rule line."""
    shared = (shared_format or "").strip()
    per_ka = (per_ka_instructions or "").strip()
    if shared and per_ka:
        return f"{per_ka}\n\n---\n\n{shared}"
    if shared:
        return shared
    return per_ka
