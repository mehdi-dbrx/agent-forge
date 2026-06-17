"""LLM client for synthetic data generation.

Uses the Databricks SDK to call serving endpoints by name —
no URL construction needed. Reads model name from AGENT_MODEL env var,
falls back to databricks-claude-sonnet-4-6.
"""
from __future__ import annotations

import json
import os
import re

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole


_ws: WorkspaceClient | None = None


def _get_client() -> WorkspaceClient:
    global _ws
    if _ws is None:
        _ws = WorkspaceClient()
    return _ws


def _get_model_name() -> str:
    name = os.environ.get("AGENT_MODEL", "").strip()
    if not name:
        name = "databricks-claude-sonnet-4-6"
    # If someone stored a full URL, extract the endpoint name from it
    if name.startswith("http://") or name.startswith("https://"):
        m = re.search(r"/serving-endpoints/([^/]+)/invocations", name)
        if m:
            name = m.group(1)
    return name


def call_llm(system: str, user: str, max_tokens: int = 4096) -> str:
    """Call the model endpoint and return the assistant's text reply."""
    w = _get_client()
    model = _get_model_name()
    resp = w.serving_endpoints.query(
        name=model,
        messages=[
            ChatMessage(role=ChatMessageRole.SYSTEM, content=system),
            ChatMessage(role=ChatMessageRole.USER, content=user),
        ],
        max_tokens=max_tokens,
    )
    content = resp.choices[0].message.content  # type: ignore[union-attr]
    if not content:
        raise ValueError(f"Model {model} returned empty content")
    return content.strip()


def call_llm_json(system: str, user: str, max_tokens: int = 4096) -> dict:
    """Call the model and parse the response as JSON.

    Retries once with a correction prompt on parse failure.
    """
    raw = call_llm(system, user, max_tokens)

    # Strip markdown fences if the model wraps output
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Retry once with correction
    print("[~] LLM returned invalid JSON — retrying with correction prompt")
    correction = (
        "Your previous response was not valid JSON. "
        "Return ONLY the raw JSON object, no markdown fences, no explanation."
    )
    raw2 = call_llm(system, f"{user}\n\n{correction}", max_tokens)
    cleaned2 = re.sub(r"^```(?:json)?\s*", "", raw2)
    cleaned2 = re.sub(r"\s*```$", "", cleaned2)

    try:
        return json.loads(cleaned2)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON after retry: {e}\nRaw: {cleaned2[:500]}"
        ) from e
