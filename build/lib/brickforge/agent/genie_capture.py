"""
Genie SQL capture: intercept Genie MCP tool calls, extract generated SQL,
and write to data/genie-capture-sql/.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import BaseTool, StructuredTool

logger = logging.getLogger(__name__)

CAPTURE_DIR = Path(__file__).resolve().parents[1] / "data" / "genie-capture-sql"


def _extract_query_from_args(args: Any) -> Optional[str]:
    if not args:
        return None
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return args.strip() or None
    if isinstance(args, dict):
        val = args.get("query") or args.get("message")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _sanitize_filename(query: str) -> str:
    s = re.sub(r"\s+", "_", query)
    s = re.sub(r"[^\w\-]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:60].rstrip("_") or "unnamed"


def _extract_sql_from_output(output: Any) -> list[str]:
    sql_list: list[str] = []

    def add(s: str) -> None:
        s = s.strip()
        if s and s.upper().startswith(("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")):
            sql_list.append(s)

    def extract_from(data: dict) -> None:
        for key in ("query", "sql", "statement"):
            v = data.get(key)
            if isinstance(v, str):
                add(v)
        for key in ("attachments", "queryAttachments"):
            for a in (data.get(key) or []) + (data.get("content", {}).get(key) or []):
                if isinstance(a, dict) and "query" in a:
                    add(str(a["query"]))
        # structured_content from MCP artifact
        for sc in (data.get("structured_content"), data.get("content", {}).get("structured_content")):
            if isinstance(sc, dict):
                for a in sc.get("queryAttachments") or sc.get("attachments") or []:
                    if isinstance(a, dict) and "query" in a:
                        add(str(a["query"]))

    # MCP tools return (content, artifact) tuple when response_format is content_and_artifact
    if isinstance(output, tuple) and len(output) >= 2:
        content, artifact = output[0], output[1]
        if artifact and isinstance(artifact, dict):
            sc = artifact.get("structured_content")
            if isinstance(sc, dict):
                extract_from(sc)
            else:
                extract_from(artifact)
        output = content

    # LangChain Message with .content
    if hasattr(output, "content"):
        output = output.content

    if isinstance(output, str):
        try:
            parsed = json.loads(output)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "text" in item:
                        try:
                            inner = json.loads(item["text"])
                            if isinstance(inner, dict):
                                extract_from(inner)
                        except (json.JSONDecodeError, TypeError):
                            pass
            elif isinstance(parsed, dict):
                extract_from(parsed)
        except json.JSONDecodeError:
            pass
        if not sql_list:
            for m in re.finditer(r"```(?:sql)?\s*\n(.*?)```", output, re.DOTALL | re.IGNORECASE):
                add(m.group(1))
        if not sql_list:
            add(output)
        return sql_list

    if isinstance(output, dict):
        extract_from(output)
    elif isinstance(output, list):
        for item in output:
            if isinstance(item, dict) and "text" in item:
                try:
                    inner = json.loads(item["text"])
                    if isinstance(inner, dict):
                        extract_from(inner)
                except (json.JSONDecodeError, TypeError):
                    pass
    return sql_list


def _write_sql_files(base_name: str, sql_list: list[str]) -> None:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    for i, sql in enumerate(sql_list):
        fn = f"{base_name}_{i + 1}" if i > 0 else base_name
        path = CAPTURE_DIR / f"{fn}.sql"
        try:
            path.write_text(sql, encoding="utf-8")
            logger.info("Captured Genie SQL: %s", path.name)
        except OSError as e:
            logger.warning("Failed to write Genie SQL: %s", e)


def _is_genie_tool(tool: BaseTool) -> bool:
    name = getattr(tool, "name", None) or getattr(tool, "get_name", lambda: "")()
    n = str(name).lower()
    return "genie" in n or "query_space" in n or "poll_response" in n


def wrap_for_genie_capture(tool: BaseTool) -> BaseTool:
    if not _is_genie_tool(tool):
        return tool

    def _try_capture(tool_input: Any, output: Any) -> None:
        try:
            query = _extract_query_from_args(tool_input)
            sql_list = _extract_sql_from_output(output)
            if not sql_list and logger.isEnabledFor(logging.DEBUG):
                logger.debug("Genie capture: no SQL found in output type=%s", type(output).__name__)
            if sql_list:
                base_name = _sanitize_filename(query) if query else _sanitize_filename(sql_list[0][:50])
                _write_sql_files(base_name, sql_list)
                logger.info("Genie SQL captured: %s (%d stmt(s))", base_name, len(sql_list))
        except Exception as e:
            logger.warning("Genie SQL capture failed: %s", e)

    def _run(**kwargs: Any) -> Any:
        result = tool.invoke(kwargs)
        _try_capture(kwargs, result)
        return result

    async def _arun(**kwargs: Any) -> Any:
        result = await tool.ainvoke(kwargs)
        _try_capture(kwargs, result)
        return result

    return StructuredTool.from_function(
        func=_run,
        coroutine=_arun,
        name=tool.name,
        description=tool.description,
        args_schema=getattr(tool, "args_schema", None),
    )
