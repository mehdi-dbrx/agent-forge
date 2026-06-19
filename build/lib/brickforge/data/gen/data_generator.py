"""Generate synthetic CSV rows for a single table using the LLM."""
from __future__ import annotations

import math
from typing import Any

from data.gen.llm_client import call_llm_json

BATCH_SIZE = 30

SYSTEM_PROMPT = """\
You are a synthetic data generator for Databricks Delta tables.

Generate realistic sample data matching the schema exactly.

Return ONLY a JSON object — no markdown, no explanation:
{{"rows": [{{"col1": "val1", "col2": 42}}, ...]}}

Rules:
- Generate exactly {row_count} rows
- Every row must have exactly these columns: {column_names}
- Match declared types strictly:
  - STRING: realistic text values
  - INT / BIGINT: integer numbers (no decimals)
  - DOUBLE / FLOAT: decimal numbers
  - BOOLEAN: true or false (lowercase, no quotes around the value)
  - DATE: "YYYY-MM-DD" format
  - TIMESTAMP_NTZ: "YYYY-MM-DDTHH:MM:SS.000" format
- Values must be realistic, varied, and domain-appropriate
- No null values unless the instructions explicitly mention optional fields
- If related tables are provided, maintain referential integrity (use matching IDs)
"""


def _build_user_prompt(table: dict[str, Any], context_tables: list[dict] | None) -> str:
    """Build the user prompt with table schema and optional context."""
    cols_desc = "\n".join(
        f"  - {c['name']}: {c['type']}" for c in table["columns"]
    )
    prompt = f"""Table: {table['name']}

Columns:
{cols_desc}

Number of rows to generate: {table['row_count']}

Instructions: {table.get('instructions', 'Generate realistic demo data')}"""

    if context_tables:
        prompt += "\n\nRelated tables for referential integrity:"
        for ct in context_tables:
            ct_cols = ", ".join(f"{c['name']}({c['type']})" for c in ct["columns"])
            prompt += f"\n  - {ct['name']}: [{ct_cols}]"
            if ct.get("sample_ids"):
                prompt += f" (existing IDs: {ct['sample_ids']})"

    return prompt


def _validate_rows(rows: list[dict], columns: list[dict]) -> list[dict]:
    """Validate and clean generated rows."""
    col_names = [c["name"] for c in columns]
    validated = []
    for row in rows:
        clean_row = {}
        for col in columns:
            val = row.get(col["name"])
            if val is None:
                # Provide a type-appropriate default
                if col["type"] in ("INT", "BIGINT"):
                    val = 0
                elif col["type"] in ("DOUBLE", "FLOAT"):
                    val = 0.0
                elif col["type"] == "BOOLEAN":
                    val = False
                elif col["type"] == "DATE":
                    val = "2026-01-01"
                elif col["type"] == "TIMESTAMP_NTZ":
                    val = "2026-01-01T00:00:00.000"
                else:
                    val = ""
            clean_row[col["name"]] = val
        validated.append(clean_row)
    return validated


def generate_data(
    table: dict[str, Any],
    context_tables: list[dict] | None = None,
) -> list[dict]:
    """Generate synthetic rows for a table.

    Chunks into batches of BATCH_SIZE for large row counts.
    Returns a list of row dicts.
    """
    row_count = table.get("row_count", 10)
    col_names = ", ".join(c["name"] for c in table["columns"])

    if row_count <= BATCH_SIZE:
        print(f"[+] Generating {row_count} rows for {table['name']}...")
        system = SYSTEM_PROMPT.format(
            row_count=row_count, column_names=col_names
        )
        user = _build_user_prompt(table, context_tables)
        result = call_llm_json(system, user)
        rows = result.get("rows", [])
        if not isinstance(rows, list):
            raise ValueError(f"LLM returned non-list rows for {table['name']}")
        validated = _validate_rows(rows, table["columns"])
        print(f"[+] Got {len(validated)} rows for {table['name']}")
        return validated

    # Chunked generation
    total_batches = math.ceil(row_count / BATCH_SIZE)
    all_rows: list[dict] = []

    for batch_idx in range(total_batches):
        remaining = row_count - len(all_rows)
        batch_count = min(BATCH_SIZE, remaining)
        print(f"[~] Generating batch {batch_idx + 1}/{total_batches} ({batch_count} rows) for {table['name']}...")

        batch_table = {**table, "row_count": batch_count}
        system = SYSTEM_PROMPT.format(
            row_count=batch_count, column_names=col_names
        )
        user = _build_user_prompt(batch_table, context_tables)
        if all_rows:
            user += f"\n\nContinuation: you already generated {len(all_rows)} rows. Generate the next {batch_count} unique rows."

        result = call_llm_json(system, user)
        rows = result.get("rows", [])
        if not isinstance(rows, list):
            raise ValueError(f"LLM returned non-list rows in batch {batch_idx + 1}")
        validated = _validate_rows(rows, table["columns"])
        all_rows.extend(validated)

    print(f"[+] Generated {len(all_rows)} total rows for {table['name']}")
    return all_rows[:row_count]
