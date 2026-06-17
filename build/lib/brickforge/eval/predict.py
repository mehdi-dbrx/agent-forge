"""Call the passenger-rights KA endpoint via raw HTTP (Responses API format).

KA response schema:
  {
    "model": "kbqa_agent",
    "object": "response",
    "output": [
      {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "<answer with <cite> tags>"}]
      }
    ]
  }
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(os.environ.get("ENV_FILE", str(ROOT / ".env.local")), override=True)

import os
import time
import requests
import mlflow

_MAX_RETRIES = 3
_RETRY_BACKOFF = 15  # seconds


def _token() -> str:
    """Get Databricks PAT from env — same workspace as the KA endpoint."""
    tok = os.environ.get("DATABRICKS_TOKEN", "").strip()
    if not tok:
        raise EnvironmentError("DATABRICKS_TOKEN must be set in .env.local")
    return tok


def _ka_url() -> str:
    host = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
    endpoint = os.environ.get("PROJECT_KA_PASSENGERS", "").strip()
    if not endpoint:
        raise EnvironmentError("PROJECT_KA_PASSENGERS must be set in .env.local")
    return f"{host}/serving-endpoints/{endpoint}/invocations"


def extract_text(response: dict) -> str:
    """Extract the answer string from a KA Responses API response dict.

    The KA returns output_format JSON: {"answer": "...", "source_documents": [...]}
    embedded inside output[0].content[0].text.
    """
    try:
        raw_text = response["output"][0]["content"][0]["text"]
        parsed = json.loads(raw_text)
        return parsed.get("answer", raw_text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return ""


@mlflow.trace
def predict(query: str) -> dict:
    """Call the KA endpoint; return full response dict."""
    last_resp = None
    for attempt in range(_MAX_RETRIES):
        last_resp = requests.post(
            _ka_url(),
            headers={
                "Authorization": f"Bearer {_token()}",
                "Content-Type": "application/json",
            },
            json={"input": [{"role": "user", "content": query}]},
            timeout=90,
        )
        if last_resp.status_code != 500:
            break
        if attempt < _MAX_RETRIES - 1:
            print(f"  [predict] 500 error, retrying in {_RETRY_BACKOFF}s ({attempt + 1}/{_MAX_RETRIES})")
            time.sleep(_RETRY_BACKOFF)
    last_resp.raise_for_status()  # type: ignore[union-attr]
    return last_resp.json()  # type: ignore[union-attr]


if __name__ == "__main__":
    question = "What compensation is a passenger entitled to for a 4-hour delay on a flight from Paris to New York?"
    print(f"\nQuery: {question}\n")
    raw = predict(question)
    text = extract_text(raw)
    print("Response text:")
    print(text[:800])
    print("\nFull schema keys:", list(raw.keys()))
    if raw.get("output"):
        print("output[0] keys:", list(raw["output"][0].keys()))
        if raw["output"][0].get("content"):
            print("content[0] keys:", list(raw["output"][0]["content"][0].keys()))
