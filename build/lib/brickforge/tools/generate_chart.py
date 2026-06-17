"""Agent tool to generate inline chart visualizations in the chat UI."""

import json

from langchain_core.tools import tool

VALID_TYPES = {"bar", "line", "area", "pie"}


@tool
def generate_chart(
    chart_type: str,
    title: str,
    headers: str,
    rows: str,
    x_column: str,
    y_column: str,
) -> str:
    """Generate an interactive chart rendered inline in the chat.

    Use this tool when the user asks for a visualization, graph, or chart of data.
    The chart appears directly in the conversation.

    Args:
        chart_type: One of "bar", "line", "area", or "pie".
        title: Chart title displayed above the chart.
        headers: Comma-separated column names, e.g. "terminal,count".
        rows: JSON array of arrays, e.g. '[["T1",42],["T2",38]]'.
        x_column: Column name for the X axis (must be in headers).
        y_column: Column name for the Y axis (must be in headers).
    """
    # Validate chart type
    ct = chart_type.strip().lower()
    if ct not in VALID_TYPES:
        return f"Error: chart_type must be one of {VALID_TYPES}, got '{chart_type}'"

    # Parse headers
    hdr_list = [h.strip() for h in headers.split(",") if h.strip()]
    if len(hdr_list) < 2:
        return "Error: headers must have at least 2 comma-separated column names"

    # Parse rows
    try:
        row_list = json.loads(rows)
        if not isinstance(row_list, list):
            raise ValueError("rows must be a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        return f"Error parsing rows: {e}"

    # Resolve column indices
    x_col = x_column.strip()
    y_col = y_column.strip()
    if x_col not in hdr_list:
        return f"Error: x_column '{x_col}' not found in headers {hdr_list}"
    if y_col not in hdr_list:
        return f"Error: y_column '{y_col}' not found in headers {hdr_list}"

    config = {
        "type": ct,
        "title": title.strip(),
        "headers": hdr_list,
        "rows": row_list,
        "x_column": hdr_list.index(x_col),
        "y_column": hdr_list.index(y_col),
    }

    return f"```chart\n{json.dumps(config)}\n```"
