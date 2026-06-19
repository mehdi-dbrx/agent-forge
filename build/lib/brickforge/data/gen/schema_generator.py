"""Generate table schemas from a domain description using the LLM."""
from __future__ import annotations

import re
from typing import Any

from data.gen.llm_client import call_llm_json

ALLOWED_TYPES = frozenset(
    ["STRING", "INT", "BIGINT", "DOUBLE", "FLOAT", "BOOLEAN", "DATE", "TIMESTAMP_NTZ"]
)

SYSTEM_PROMPT = """\
You are a data architect designing Delta tables for a Databricks Unity Catalog.

Given the user's domain description, design a relational data model.

Return ONLY a JSON object — no markdown, no explanation:
{
  "tables": [
    {
      "name": "snake_case_table_name",
      "columns": [
        {"name": "snake_case_column_name", "type": "SPARK_SQL_TYPE"}
      ],
      "row_count": 10,
      "instructions": "Description of what realistic data to generate for this table"
    }
  ]
}

Rules:
- Table and column names: lowercase snake_case, letters/digits/underscores only
- Column types must be one of: STRING, INT, BIGINT, DOUBLE, FLOAT, BOOLEAN, DATE, TIMESTAMP_NTZ
- Design 2-8 tables with 3-12 columns each
- Include primary key columns (typically <entity>_id as STRING)
- Design foreign key relationships via shared column names across tables
- row_count: 5-50, realistic for demo/seed data
- instructions: describe realistic value ranges, domain context, and relationships to other tables
- Make the model practical and useful for building demo applications"""


def _validate_name(name: str) -> str:
    """Ensure name is valid snake_case."""
    cleaned = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "t_" + cleaned
    return cleaned


def _validate_type(col_type: str) -> str:
    """Return a valid Spark SQL type, falling back to STRING."""
    upper = col_type.upper().strip()
    if upper in ALLOWED_TYPES:
        return upper
    return "STRING"


def _validate_table(table: dict[str, Any]) -> dict[str, Any]:
    """Validate and clean a single table definition."""
    name = _validate_name(table.get("name", "unnamed_table"))

    columns = []
    for col in table.get("columns", []):
        col_name = _validate_name(col.get("name", "unnamed_col"))
        col_type = _validate_type(col.get("type", "STRING"))
        columns.append({"name": col_name, "type": col_type})

    if not columns:
        columns = [{"name": "id", "type": "STRING"}]

    row_count = table.get("row_count", 10)
    if not isinstance(row_count, int) or row_count < 1:
        row_count = 10
    row_count = min(row_count, 100)

    instructions = table.get("instructions", "")
    if not isinstance(instructions, str):
        instructions = str(instructions)

    return {
        "name": name,
        "columns": columns,
        "row_count": row_count,
        "instructions": instructions,
    }


def generate_schema(domain_description: str) -> list[dict[str, Any]]:
    """Generate table schemas from a domain description.

    Returns a list of validated table definitions.
    """
    print(f"[+] Generating schema for domain: {domain_description[:80]}...")

    result = call_llm_json(SYSTEM_PROMPT, domain_description)

    tables_raw = result.get("tables", [])
    if not isinstance(tables_raw, list) or len(tables_raw) == 0:
        raise ValueError("LLM returned no tables in schema")

    tables = [_validate_table(t) for t in tables_raw]

    print(f"[+] Generated {len(tables)} table(s):")
    for t in tables:
        cols_str = ", ".join(f"{c['name']} {c['type']}" for c in t["columns"])
        print(f"    {t['name']} ({len(t['columns'])} cols, {t['row_count']} rows): {cols_str}")

    return tables
