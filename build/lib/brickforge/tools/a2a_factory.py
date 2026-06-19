"""Dynamic Agent-to-Agent (A2A) tool factory.

Discovers all PROJECT_A2A_* env vars and creates a @tool function for each.
Each tool sends messages to the remote A2A agent via JSON-RPC 2.0 over HTTP.
The Agent Card is fetched at startup to get the agent's name and skills.
"""

import json
import logging
import os
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from langchain_core.tools import tool

_log = logging.getLogger(__name__)


def _fetch_agent_card(base_url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> dict | None:
    """Fetch the A2A Agent Card from /.well-known/agent.json."""
    url = base_url.rstrip("/") + "/.well-known/agent.json"
    req = Request(url, method="GET")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        resp = urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _log.warning("Failed to fetch A2A agent card from %s: %s", url, e)
        return None


def _call_a2a(base_url: str, message: str, headers: dict[str, str] | None = None, timeout: int = 30) -> str:
    """Send a message to an A2A agent via JSON-RPC 2.0."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [{"kind": "text", "text": message}],
            }
        },
    }).encode("utf-8")

    req = Request(base_url.rstrip("/"), data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        resp = urlopen(req, timeout=timeout)
        body = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return f"A2A HTTP error {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}"
    except URLError as e:
        return f"A2A connection error: {e.reason}"
    except Exception as e:
        return f"A2A error: {e}"

    # Extract text parts from the JSON-RPC response
    result = body.get("result", {})
    parts = result.get("parts", [])
    texts = [p.get("text", "") for p in parts if p.get("kind") == "text"]
    if texts:
        return "\n".join(texts)

    # Fallback: check for error
    error = body.get("error")
    if error:
        return f"A2A error: {error.get('message', str(error))}"

    return str(body)


def create_a2a_tool(slug: str, base_url: str, headers: dict[str, str] | None = None):
    """Create a @tool function for a remote A2A agent."""
    # Fetch agent card for metadata
    card = _fetch_agent_card(base_url, headers)
    agent_name = card.get("name", slug.replace("_", " ").title()) if card else slug.replace("_", " ").title()
    agent_desc = card.get("description", "") if card else ""
    skills = card.get("skills", []) if card else []
    skill_names = ", ".join(s.get("name", s.get("id", "")) for s in skills[:5])

    @tool
    def a2a_query(message: str) -> str:
        """Placeholder -- replaced below."""
        return _call_a2a(base_url, message, headers)

    tool_name = f"a2a_{slug.lower()}"
    a2a_query.__name__ = tool_name
    a2a_query.name = tool_name

    desc_parts = [f"Send a message to the {agent_name} A2A agent."]
    if agent_desc:
        desc_parts.append(agent_desc)
    if skill_names:
        desc_parts.append(f"Skills: {skill_names}.")
    a2a_query.__doc__ = " ".join(desc_parts)

    return a2a_query


def discover_a2a_tools() -> list:
    """Find all active PROJECT_A2A_* env vars and create tool functions."""
    tools = []
    for key in sorted(os.environ):
        if key.startswith("PROJECT_A2A_") and not key.endswith("_HEADER") and os.environ[key].strip():
            url = os.environ[key].strip()
            slug = key[len("PROJECT_A2A_"):]
            # Optional auth header
            headers = None
            header_val = os.environ.get(f"{key}_HEADER", "").strip()
            if header_val and ":" in header_val:
                hname, hval = header_val.split(":", 1)
                headers = {hname.strip(): hval.strip()}
            t = create_a2a_tool(slug, url, headers)
            _log.info("A2A tool registered: %s -> %s", t.name, url)
            tools.append(t)
    return tools
