"""Agent tool to query the Passenger Rights Knowledge Assistant."""

import json
import os
import time

import requests
from databricks.sdk import WorkspaceClient
from langchain_core.tools import tool

_MAX_RETRIES = 3
_RETRY_BACKOFF = 15

_workspace_client = WorkspaceClient()


def _ka_url() -> str:
    host = _workspace_client.config.host.rstrip("/")
    endpoint = os.environ.get("PROJECT_KA_PASSENGERS", "").strip()
    if not host or not endpoint:
        raise ValueError("PROJECT_KA_PASSENGERS is not configured")
    return f"{host}/serving-endpoints/{endpoint}/invocations"


def _auth_header() -> str:
    return f"Bearer {_workspace_client.config.token}"


def _call_ka(query: str) -> dict:
    url = _ka_url()
    headers = {"Authorization": _auth_header(), "Content-Type": "application/json"}
    payload = {"input": [{"role": "user", "content": query}]}
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    for _ in range(1, _MAX_RETRIES):
        if resp.status_code != 500:
            break
        time.sleep(_RETRY_BACKOFF)
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()


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
