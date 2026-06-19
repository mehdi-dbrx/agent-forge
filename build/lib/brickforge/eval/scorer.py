"""Custom MLflow scorer: cites_regulation_precisely.

Uses the Databricks SDK to call the model endpoint as LLM judge.
Reads model name from AGENT_MODEL env var.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(os.environ.get("ENV_FILE", str(ROOT / ".env.local")), override=True)

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
from mlflow.genai.scorers import scorer

# ── Model — resolved once at import ──────────────────────────────────────────
_MODEL = os.environ.get("AGENT_MODEL", "").strip() or "databricks-claude-sonnet-4-6"
# Extract endpoint name from URL if needed
if _MODEL.startswith("http://") or _MODEL.startswith("https://"):
    _m = re.search(r"/serving-endpoints/([^/]+)/invocations", _MODEL)
    if _m:
        _MODEL = _m.group(1)

_ws: WorkspaceClient | None = None


def _get_client() -> WorkspaceClient:
    global _ws
    if _ws is None:
        _ws = WorkspaceClient()
    return _ws


def _call_judge(prompt: str) -> tuple[float, str]:
    """Call model endpoint as LLM judge via SDK. Returns (score, justification)."""
    try:
        w = _get_client()
        resp = w.serving_endpoints.query(
            name=_MODEL,
            messages=[ChatMessage(role=ChatMessageRole.USER, content=prompt)],
            max_tokens=1024,
        )
        text = (resp.choices[0].message.content or "").strip()  # type: ignore[union-attr]
        lines = text.split("\n", 1)
        verdict = lines[0].strip().upper()
        justification = lines[1].strip() if len(lines) > 1 else text
        score = 1.0 if "PASS" in verdict else 0.0
        return score, justification
    except Exception as e:
        return 0.0, f"scorer error: {e}"


def _extract_response_text(outputs: dict) -> str:
    """Pull the answer string from the KA output dict."""
    try:
        raw_text = outputs["output"][0]["content"][0]["text"]
        parsed = json.loads(raw_text)
        return parsed.get("answer", raw_text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return str(outputs)


@scorer(name="cites_regulation_precisely")
def cites_regulation_precisely(inputs: dict, outputs: dict) -> float:
    """Score 1.0 if the response cites a specific article, amount in euros, or named standard."""
    question = inputs.get("query", "")
    response_text = _extract_response_text(outputs)

    if not response_text:
        print("  [scorer] empty response → 0.0")
        return 0.0

    prompt = _JUDGE_PROMPT.format(question=question, response=response_text[:3000])
    score, justification = _call_judge(prompt)
    print(f"  [scorer] score={score} | {justification[:80]}")
    return score
