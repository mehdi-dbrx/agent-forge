#!/usr/bin/env python3
"""Test AGENT_MODEL_ENDPOINT by sending a simple message and confirming the model responds.

Usage:
  uv run python scripts/test_agent_model.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local", override=True)

import requests

R, G, Y, W = "\033[31m", "\033[32m", "\033[33m", "\033[0m"
BOLD = "\033[1m"

endpoint = os.environ.get("AGENT_MODEL_ENDPOINT", "").strip()
token = (
    os.environ.get("AGENT_MODEL_TOKEN", "").strip()
    or os.environ.get("DATABRICKS_TOKEN", "").strip()
)

if not endpoint:
    print(f"{BOLD}{R}FAIL{W} AGENT_MODEL_ENDPOINT is not set.")
    print(f"  → Run the init script and configure the model endpoint.")
    sys.exit(1)

if not token:
    print(f"{BOLD}{Y}WARN{W} No token found (AGENT_MODEL_TOKEN or DATABRICKS_TOKEN).")
    print(f"  → Proceeding without auth — will likely get 401.")

print(f"  Endpoint : {endpoint}")
print(f"  Auth     : {'token set (' + token[:6] + '...)' if token else 'none'}")
print(f"  Sending  : Hi\n")

headers = {"Content-Type": "application/json"}
if token:
    headers["Authorization"] = f"Bearer {token}"

payload = {
    "messages": [{"role": "user", "content": "Hi"}],
    "max_tokens": 50,
}

try:
    resp = requests.post(endpoint, json=payload, headers=headers, timeout=30)
except requests.exceptions.ConnectionError as e:
    print(f"{BOLD}{R}FAIL{W} Cannot reach endpoint.")
    print(f"  → Check AGENT_MODEL_ENDPOINT URL is correct and reachable.")
    print(f"  → Detail: {e}")
    sys.exit(1)
except requests.exceptions.Timeout:
    print(f"{BOLD}{R}FAIL{W} Request timed out (30s).")
    print(f"  → Endpoint may be cold-starting or unreachable.")
    sys.exit(1)

if resp.status_code == 200:
    try:
        data = resp.json()
        reply = (
            (data.get("choices") or [{}])[0].get("message", {}).get("content")
            or (data.get("content") or [{}])[0].get("text")
            or str(data)[:200]
        )
        print(f"{BOLD}{G}OK{W}  Model replied: {reply[:120]}")
        sys.exit(0)
    except Exception:
        print(f"{BOLD}{G}OK{W}  HTTP 200 — response: {resp.text[:200]}")
        sys.exit(0)

# Error cases
body = resp.text[:300]
print(f"{BOLD}{R}FAIL{W} HTTP {resp.status_code}")
print(f"  Body: {body}")

if resp.status_code == 429:
    print(f"  → Rate limit hit. This workspace has zero quota for foundation models.")
    print(f"  → Use a field-eng workspace endpoint (see AGENT_MODEL_ENDPOINT setup).")
elif resp.status_code in (401, 403):
    print(f"  → Auth failed. Check AGENT_MODEL_TOKEN (for cross-workspace) or DATABRICKS_TOKEN.")
elif resp.status_code == 404:
    print(f"  → Endpoint not found. Check the model name in AGENT_MODEL_ENDPOINT URL.")
elif resp.status_code >= 500:
    print(f"  → Server error. The endpoint may be down or still starting up.")

sys.exit(1)
