"""Dynamic Knowledge Assistant tool factory.

Discovers all PROJECT_KA_* env vars and creates a @tool function for each.
Each tool calls the corresponding KA serving endpoint via the Databricks SDK.
"""

import json
import logging
import os

from databricks.sdk import WorkspaceClient
from langchain_core.tools import tool

_log = logging.getLogger(__name__)

_ws = None


def _get_ws() -> WorkspaceClient:
    global _ws
    if _ws is None:
        _ws = WorkspaceClient()
    return _ws


def _call_ka(env_key: str, query: str) -> str:
    endpoint = os.environ.get(env_key, "").strip()
    if not endpoint:
        raise ValueError(f"{env_key} is not configured")
    ws = _get_ws()
    path = f"/serving-endpoints/{endpoint}/invocations"
    payload = {"input": [{"role": "user", "content": query}]}
    resp = ws.api_client.do("POST", path, body=payload)
    try:
        raw = resp["output"][0]["content"][0]["text"]
        parsed = json.loads(raw)
        return parsed.get("answer", raw)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return str(resp)


def create_ka_tool(slug: str, env_key: str):
    """Create a @tool function for a KA endpoint identified by env_key."""
    display = slug.replace("_", " ").title()

    @tool
    def ka_query(query: str) -> str:
        """Placeholder docstring — replaced below."""
        try:
            return _call_ka(env_key, query)
        except Exception as e:
            return f"Error querying {display} KA: {e}"

    # LangChain reads __name__ and __doc__ to build tool metadata
    tool_name = f"query_{slug.lower()}_ka"
    ka_query.__name__ = tool_name
    ka_query.name = tool_name
    ka_query.__doc__ = f"Query the {display} Knowledge Assistant for domain-specific questions. Use when the user asks about {display.lower()} topics."
    return ka_query


def discover_ka_tools() -> list:
    """Find all active PROJECT_KA_* env vars and create tool functions."""
    tools = []
    for key in sorted(os.environ):
        if key.startswith("PROJECT_KA_") and os.environ[key].strip():
            slug = key[len("PROJECT_KA_"):]
            t = create_ka_tool(slug, key)
            _log.info("KA tool registered: %s -> %s", t.name, os.environ[key])
            tools.append(t)
    return tools
