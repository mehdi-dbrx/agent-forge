"""Dynamic external API tool factory.

Discovers PROJECT_API_<SLUG>_* env vars and creates @tool functions for each API.

Supports two modes:
  - UC Connection (Option A): set PROJECT_API_<SLUG>_CONN=<connection_name>
    Calls via WorkspaceClient().serving_endpoints.http_request(conn=...)
  - Direct HTTP (Option B): set PROJECT_API_<SLUG>_URL=<base_url>
    Calls via requests.get/post with optional auth header

Env var pattern per API:
  PROJECT_API_<SLUG>_CONN    UC connection name (Option A)
  PROJECT_API_<SLUG>_URL     Base URL (Option B, used if no _CONN)
  PROJECT_API_<SLUG>_METHOD  HTTP method: GET, POST, PUT, DELETE (default: GET)
  PROJECT_API_<SLUG>_PATH    API path appended to base (default: /)
  PROJECT_API_<SLUG>_DESC    Tool description for the LLM
  PROJECT_API_<SLUG>_PARAMS  Comma-separated param:type pairs (e.g. city:str,days:int)
  PROJECT_API_<SLUG>_HEADER  Auth header as Name:Value (Option B only)
"""

import json
import logging
import os
from typing import Optional

import requests
from langchain_core.tools import tool

_log = logging.getLogger(__name__)

_ws_client = None


def _get_ws():
    global _ws_client
    if _ws_client is None:
        from databricks.sdk import WorkspaceClient
        _ws_client = WorkspaceClient()
    return _ws_client


def _call_uc_api(conn: str, method: str, path: str, params: Optional[dict] = None, body: Optional[dict] = None) -> str:
    """Call an external API via UC Connection."""
    from databricks.sdk.service.serving import ExternalFunctionRequestHttpMethod
    method_enum = ExternalFunctionRequestHttpMethod(method.upper())
    ws = _get_ws()
    resp = ws.serving_endpoints.http_request(
        conn=conn,
        method=method_enum,
        path=path,
        params=params,
        json=body,
    )
    try:
        return json.dumps(resp.json(), indent=2)
    except (ValueError, AttributeError):
        return resp.text


def _call_direct_api(url: str, method: str, path: str, headers: Optional[dict] = None,
                     params: Optional[dict] = None, body: Optional[dict] = None) -> str:
    """Call an external API via direct HTTP."""
    full_url = url.rstrip("/") + "/" + path.lstrip("/") if path and path != "/" else url
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    resp = requests.request(
        method=method.upper(),
        url=full_url,
        headers=req_headers,
        params=params,
        json=body,
        timeout=30,
    )
    try:
        return json.dumps(resp.json(), indent=2)
    except (ValueError, AttributeError):
        return resp.text


def _parse_params(params_str: str) -> list[tuple[str, str]]:
    """Parse 'city:str,days:int' into [('city', 'str'), ('days', 'int')]."""
    if not params_str.strip():
        return []
    result = []
    for p in params_str.split(","):
        p = p.strip()
        if ":" in p:
            name, typ = p.split(":", 1)
            result.append((name.strip(), typ.strip()))
        elif p:
            result.append((p, "str"))
    return result


def _discover_api_slugs() -> list[str]:
    """Find all unique API slugs from PROJECT_API_<SLUG>_* env vars."""
    slugs = set()
    for key in os.environ:
        if not key.startswith("PROJECT_API_"):
            continue
        # Strip prefix and find the slug (everything before the last _SUFFIX)
        rest = key[len("PROJECT_API_"):]
        # Known suffixes to strip
        for suffix in ("_CONN", "_URL", "_METHOD", "_PATH", "_DESC", "_PARAMS", "_HEADER"):
            if rest.endswith(suffix):
                slug = rest[: -len(suffix)]
                if slug:
                    slugs.add(slug)
                break
    return sorted(slugs)


def create_api_tool(slug: str):
    """Create a @tool function for an external API identified by PROJECT_API_<SLUG>_* env vars."""
    prefix = f"PROJECT_API_{slug}_"
    conn = os.environ.get(f"{prefix}CONN", "").strip()
    url = os.environ.get(f"{prefix}URL", "").strip()
    method = os.environ.get(f"{prefix}METHOD", "GET").strip().upper()
    path = os.environ.get(f"{prefix}PATH", "/").strip()
    desc = os.environ.get(f"{prefix}DESC", "").strip()
    params_str = os.environ.get(f"{prefix}PARAMS", "").strip()
    header_val = os.environ.get(f"{prefix}HEADER", "").strip()

    if not conn and not url:
        _log.warning("API '%s': neither _CONN nor _URL set, skipping", slug)
        return None

    display = slug.replace("_", " ").title()
    param_defs = _parse_params(params_str)
    use_uc = bool(conn)

    # Parse auth header for direct mode
    auth_headers = None
    if not use_uc and header_val and ":" in header_val:
        hname, hval = header_val.split(":", 1)
        auth_headers = {hname.strip(): hval.strip()}

    if not param_defs:
        # No-param tool
        @tool
        def api_call() -> str:
            """Placeholder."""
            try:
                if use_uc:
                    return _call_uc_api(conn, method, path)
                else:
                    return _call_direct_api(url, method, path, headers=auth_headers)
            except Exception as e:
                return f"Error calling {display} API: {e}"
    else:
        # Tool with query string parameter (most common: single param)
        @tool
        def api_call(query: str) -> str:
            """Placeholder."""
            try:
                # Build params dict from the query string
                # For single-param APIs, the query IS the param value
                params = {}
                if len(param_defs) == 1:
                    params[param_defs[0][0]] = query
                else:
                    # Try to parse as key=value pairs
                    for part in query.split(","):
                        if "=" in part:
                            k, v = part.split("=", 1)
                            params[k.strip()] = v.strip()

                if use_uc:
                    return _call_uc_api(conn, method, path, params=params)
                else:
                    return _call_direct_api(url, method, path, headers=auth_headers, params=params)
            except Exception as e:
                return f"Error calling {display} API: {e}"

    tool_name = f"call_{slug.lower()}_api"
    api_call.__name__ = tool_name
    api_call.name = tool_name
    api_call.__doc__ = desc or f"Call the {display} external API ({method} {path})."
    return api_call


def discover_api_tools() -> list:
    """Find all PROJECT_API_<SLUG>_* env vars and create tool functions."""
    slugs = _discover_api_slugs()
    tools = []
    for slug in slugs:
        t = create_api_tool(slug)
        if t is not None:
            _log.info("API tool registered: %s", t.name)
            tools.append(t)
    return tools
