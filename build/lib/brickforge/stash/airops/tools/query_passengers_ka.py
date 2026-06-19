"""Agent tool to query the Passenger Rights Knowledge Assistant."""

import json
import os

from databricks.sdk import WorkspaceClient
from langchain_core.tools import tool

_workspace_client = WorkspaceClient()


def _ka_url() -> str:
    endpoint = os.environ.get("PROJECT_KA_PASSENGERS", "").strip()
    if not endpoint:
        raise ValueError("PROJECT_KA_PASSENGERS is not configured")
    return f"/serving-endpoints/{endpoint}/invocations"


def _call_ka(query: str):
    path = _ka_url()
    payload = {"input": [{"role": "user", "content": query}]}
    return _workspace_client.api_client.do("POST", path, body=payload)


def _extract_answer(response: dict) -> str:
    try:
        raw = response["output"][0]["content"][0]["text"]
        parsed = json.loads(raw)
        return parsed.get("answer", raw)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return str(response)


@tool
def query_passengers_ka(query: str) -> str:
    """Query the Passenger Rights Knowledge Assistant for EU flight delay/cancellation compensation rules, passenger entitlements, and airline obligations. Use when a passenger asks about their rights, eligibility for compensation, or what assistance they are entitled to."""
    try:
        response = _call_ka(query)
        return _extract_answer(response)
    except Exception as e:
        return f"Error querying Passenger Rights KA: {e}"
