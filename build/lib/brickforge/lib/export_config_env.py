#!/usr/bin/env python3
"""Flatten config.json to /tmp/_env_exports.sh for shell sourcing.

Called by start.sh at boot to inject config into the shell environment
before the agent starts. This ensures ALL processes (Python, Node.js,
uvicorn workers) inherit the config as env vars.
"""
import json
import os
import sys

sys.path.insert(0, os.environ.get("PYTHONPATH", "."))

from lib.config_provider import flatten

config_file = os.environ.get("CONFIG_FILE", "config.json")
if not os.path.exists(config_file):
    print(f"[x] config.json not found at {config_file}")
    sys.exit(1)

cfg = json.loads(open(config_file).read())
flat = flatten(cfg)

# On deployed apps, SP OAuth (CLIENT_ID) is injected by runtime -- don't override with PAT
if os.environ.get("DATABRICKS_CLIENT_ID"):
    flat.pop("DATABRICKS_TOKEN", None)
    flat.pop("DATABRICKS_CONFIG_PROFILE", None)

with open("/tmp/_env_exports.sh", "w") as f:
    for k, v in flat.items():
        # Shell-safe: escape single quotes
        v_safe = v.replace("'", "'\\''")
        f.write(f"export {k}='{v_safe}'\n")

print(f"[+] Loaded {len(flat)} env vars from config.json")
