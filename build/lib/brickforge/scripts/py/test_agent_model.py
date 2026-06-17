#!/usr/bin/env python3
"""Test AGENT_MODEL by sending a simple message via the Databricks SDK.

Usage:
  python scripts/py/test_agent_model.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


import re
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

R, G, Y, W = "\033[31m", "\033[32m", "\033[33m", "\033[0m"
BOLD = "\033[1m"

model = os.environ.get("AGENT_MODEL", "").strip()

if not model:
    model = "databricks-claude-sonnet-4-6"
    print(f"{BOLD}{Y}INFO{W} AGENT_MODEL not set — using default: {model}")

# If someone stored a full URL, extract the endpoint name
if model.startswith("http://") or model.startswith("https://"):
    m = re.search(r"/serving-endpoints/([^/]+)/invocations", model)
    if m:
        model = m.group(1)

print(f"  Model    : {model}")
print(f"  Sending  : Hi\n")

try:
    w = WorkspaceClient()
    resp = w.serving_endpoints.query(
        name=model,
        messages=[ChatMessage(role=ChatMessageRole.USER, content="Hi")],
        max_tokens=50,
    )
    reply = resp.choices[0].message.content or str(resp)[:200]  # type: ignore[union-attr]
    print(f"{BOLD}{G}OK{W}  Model replied: {reply[:120]}")
    sys.exit(0)
except Exception as e:
    err = str(e)
    print(f"{BOLD}{R}FAIL{W} {err[:300]}")
    if "429" in err:
        print(f"  -> Rate limit hit. This workspace has zero quota for foundation models.")
        print(f"  -> Use a field-eng workspace endpoint (set AGENT_MODEL).")
    elif "401" in err or "403" in err:
        print(f"  -> Auth failed. Check DATABRICKS_TOKEN.")
    elif "404" in err:
        print(f"  -> Endpoint not found. Check the model name in AGENT_MODEL.")
    sys.exit(1)
