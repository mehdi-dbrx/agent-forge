"""Shared helpers for reading/writing config.json from subprocesses.

Init scripts (create_genie_space.py, generate_routines.py, etc.) run as
subprocesses and need to read/update/write config.json. This module provides
the minimal interface for that.

Usage in a subprocess:
    from lib.config_json import read_config, write_config
    config = read_config()  # reads from CONFIG_FILE env var
    config["tools"]["genie_spaces"].append("new-space-id")
    write_config(config)
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def _config_path() -> Path:
    """Get config.json path from CONFIG_FILE env var."""
    path = os.environ.get("CONFIG_FILE", "")
    if not path:
        raise ValueError("CONFIG_FILE env var not set -- cannot read/write config.json")
    return Path(path)


def read_config() -> dict:
    """Read config.json from the path specified by CONFIG_FILE env var."""
    p = _config_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def write_config(config: dict) -> None:
    """Write config.json to the path specified by CONFIG_FILE env var."""
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(config, indent=2) + "\n")
