"""Graph builder: generates nodes/edges for the architecture DAG."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from brickforge import PACKAGE_ROOT


def _scan_dir(directory: Path, ext: str) -> list[str]:
    try:
        return sorted(f.stem for f in directory.iterdir() if f.suffix == ext)
    except FileNotFoundError:
        return []


def _read_app_yaml() -> dict:
    try:
        return yaml.safe_load((PACKAGE_ROOT / "app.yaml").read_text()) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}


def _extract_env_vars(app_yaml: dict) -> dict[str, str]:
    env_vars = {}
    for e in app_yaml.get("env", []):
        env_vars[e.get("name", "")] = e.get("value", "")
    return env_vars


def _parse_model_name(endpoint: str) -> str:
    m = re.search(r"serving-endpoints/([^/]+)/invocations", endpoint or "")
    return m.group(1) if m else (endpoint or "unknown")


def build_graph() -> dict:
    app_yaml = _read_app_yaml()
    env_vars = _extract_env_vars(app_yaml)
    endpoint = env_vars.get("AGENT_MODEL", "")
    model_name = _parse_model_name(endpoint)
    schema = env_vars.get("PROJECT_UNITY_CATALOG_SCHEMA", "")
    parts = schema.split(".", 1) if schema else ["", ""]
    catalog, schema_name = parts[0], parts[1] if len(parts) > 1 else ""

    FRAMEWORK_TOOLS = {"sql_executor", "ka_factory", "get_current_time", "__init__"}
    tools = [t for t in _scan_dir(PACKAGE_ROOT / "tools", ".py") if t not in FRAMEWORK_TOOLS]
    funcs = _scan_dir(PACKAGE_ROOT / "data" / "default" / "func", ".sql")
    procs = _scan_dir(PACKAGE_ROOT / "data" / "default" / "proc", ".sql")
    tables = _scan_dir(PACKAGE_ROOT / "data" / "default" / "csv", ".csv")

    nodes = []
    edges = []
    y = 60

    # Agent node
    nodes.append({
        "id": "agent", "type": "agent", "position": {"x": 80, "y": 300},
        "data": {"kind": "agent", "label": "Agent", "subtitle": "LangGraph ResponsesAgent",
                 "sourceFile": "agent/agent.py", "meta": {"framework": "LangGraph", "server": "MLflow GenAI", "port": "8000"}},
    })

    # LLM node
    nodes.append({
        "id": "llm", "type": "llm", "position": {"x": 380, "y": y},
        "data": {"kind": "llm", "label": model_name or "(not set)", "subtitle": "Model endpoint",
                 "sourceFile": "app.yaml", "meta": {"endpoint": endpoint or "(not set)"}},
    })
    edges.append({"id": "e-agent-llm", "source": "agent", "target": "llm", "label": "uses model"})
    y += 160

    # Genie node
    raw_genie = env_vars.get("PROJECT_GENIE_SPACES", "")
    genie_keys = [s.strip() for s in raw_genie.split(",") if s.strip()] if raw_genie else []
    if genie_keys:
        nodes.append({
            "id": "genie", "type": "genie", "position": {"x": 380, "y": y},
            "data": {"kind": "genie",
                     "label": f"Genie ({len(genie_keys)} space{'s' if len(genie_keys) > 1 else ''})",
                     "subtitle": "MCP-based Genie space", "sourceFile": "agent/agent.py",
                     "meta": {"spaces": ", ".join(genie_keys)}},
        })
        edges.append({"id": "e-agent-genie", "source": "agent", "target": "genie", "label": "has MCP tool"})
        y += 160

    # Tool nodes
    for i, tool in enumerate(tools):
        tid = f"tool-{i}"
        nodes.append({
            "id": tid, "type": "tool", "position": {"x": 380, "y": y + i * 80},
            "data": {"kind": "tool", "label": tool, "subtitle": "domain tool", "sourceFile": f"tools/{tool}.py"},
        })
        edges.append({"id": f"e-agent-{tid}", "source": "agent", "target": tid, "label": "has tool"})

    # Function nodes
    data_y = 60
    for i, fn in enumerate(funcs):
        nodes.append({
            "id": f"func-{i}", "type": "data", "position": {"x": 700, "y": data_y + i * 80},
            "data": {"kind": "data", "label": fn, "subtitle": "UC function", "dataVariant": "function",
                     "sourceFile": f"data/demo/func/{fn}.sql"},
        })

    # Procedure nodes
    proc_start = data_y + len(funcs) * 80 + 40
    for i, proc in enumerate(procs):
        nodes.append({
            "id": f"proc-{i}", "type": "data", "position": {"x": 700, "y": proc_start + i * 80},
            "data": {"kind": "data", "label": proc, "subtitle": "UC procedure", "dataVariant": "procedure",
                     "sourceFile": f"data/demo/proc/{proc}.sql"},
        })

    # Table nodes
    for i, table in enumerate(tables):
        tid = f"table-{i}"
        full_name = f"{catalog}.{schema_name}.{table}" if catalog and schema_name else table
        nodes.append({
            "id": tid, "type": "data", "position": {"x": 1020, "y": 200 + i * 120},
            "data": {"kind": "data", "label": table, "subtitle": full_name, "dataVariant": "table",
                     "meta": {"catalog": catalog, "schema": schema_name, "table": table}},
        })
        if genie_keys:
            edges.append({"id": f"e-genie-{tid}", "source": "genie", "target": tid, "label": "queries", "animated": True})

    # Empty state
    if not tools and not funcs and not tables:
        nodes.append({
            "id": "empty", "type": "data", "position": {"x": 500, "y": 300},
            "data": {"kind": "data", "label": "No domain loaded",
                     "subtitle": "Load a stash to populate the architecture", "dataVariant": "table"},
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "projectRoot": str(PACKAGE_ROOT),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        },
    }
