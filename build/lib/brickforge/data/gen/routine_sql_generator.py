"""Generate SQL code for a single function or procedure using the LLM.

Uses a Databricks SQL reference doc + working examples to guide the LLM,
plus a sanitizer to catch/fix known constraint violations, plus a self-healing
loop at provision time (see generate_routines.py).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from data.gen.llm_client import call_llm

_REFERENCE_PATH = Path(__file__).parent / "databricks_sql_reference.md"


def _load_reference() -> str:
    """Load the Databricks SQL reference doc (constraints + working examples)."""
    try:
        return _REFERENCE_PATH.read_text()
    except FileNotFoundError:
        return ""


FUNCTION_SYSTEM_PROMPT = """\
You write Databricks SQL. Not standard SQL. Not PostgreSQL. Databricks SQL only.

Generate a CREATE OR REPLACE FUNCTION for Databricks Unity Catalog.
Return ONLY the raw SQL. No markdown fences. No explanation. No comments.

CRITICAL: Use __SCHEMA_QUALIFIED__ as prefix for ALL table and routine names.
Example: CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.my_func(...)
Example: SELECT * FROM __SCHEMA_QUALIFIED__.my_table

Be minimalist. Write the simplest SQL that works.
- Only the parameters the user asked for. Nothing extra.
- Only the columns needed. Nothing extra.
- No optional clauses. No clever tricks. No exotic features.
- If in doubt, leave it out."""

PROCEDURE_SYSTEM_PROMPT = """\
You write Databricks SQL. Not standard SQL. Not PostgreSQL. Databricks SQL only.

Generate a CREATE OR REPLACE PROCEDURE for Databricks Unity Catalog.
Return ONLY the raw SQL. No markdown fences. No explanation. No comments.

CRITICAL: Use __SCHEMA_QUALIFIED__ as prefix for ALL table and routine names.
Example: CREATE OR REPLACE PROCEDURE __SCHEMA_QUALIFIED__.my_proc(...)
Example: INSERT INTO __SCHEMA_QUALIFIED__.my_table VALUES (...)

CRITICAL: ALL procedure parameters MUST be declared as STRING type.
- The calling tool always passes arguments as quoted strings.
- Prefix every parameter with p_ to avoid column name conflicts.
- Use CAST() in the procedure body to convert to the target column type.
- Example: parameter p_check_in_date STRING, then CAST(p_check_in_date AS DATE) in the INSERT.
- Example: parameter p_total_amount STRING, then CAST(p_total_amount AS DOUBLE) in the INSERT.
- NEVER use DATE, DOUBLE, TIMESTAMP, INT, BIGINT, DECIMAL, or FLOAT as parameter types.

Be minimalist. Write the simplest SQL that works.
- Only the parameters the user asked for. Nothing extra.
- No optional clauses. No clever tricks.
- Do NOT end with SELECT 'status' -- just do the INSERT/UPDATE and end."""


def _build_user_prompt(
    routine: dict[str, Any],
    table_schemas: list[dict[str, Any]] | None = None,
) -> str:
    """Build the user prompt with routine definition and table context."""
    params_desc = "\n".join(
        f"  - {p['name']}: {p['sql_type']}" for p in routine.get("parameters", [])
    )
    prompt = f"""Routine: {routine['name']}
Type: {routine['type']}
Description: {routine.get('description', '')}

Parameters:
{params_desc or '  (none)'}

Tables referenced: {', '.join(routine.get('tables_referenced', []))}

Instructions: {routine.get('instructions', 'Generate appropriate SQL')}"""

    if table_schemas:
        prompt += "\n\nFull table schemas:"
        for t in table_schemas:
            cols = "\n".join(f"    {c['name']} {c['type']}" for c in t.get("columns", []))
            prompt += f"\n  {t['name']}:\n{cols}"

    return prompt


def _strip_fences(raw: str) -> str:
    """Strip markdown code fences if present."""
    cleaned = re.sub(r"^```(?:sql)?\s*\n?", "", raw.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


def _sanitize_sql(sql: str, routine_type: str) -> str:
    """Validate and auto-fix generated SQL for Databricks UC compatibility.

    Auto-fixes what it can (logs each fix), raises ValueError for what it can't.
    """
    fixes: list[str] = []
    upper = sql.upper()

    # ── Common: auto-add schema qualifier if missing ──
    if "__SCHEMA_QUALIFIED__" not in sql:
        # Qualify the routine name in CREATE statement
        if routine_type == "procedure":
            sql = re.sub(r'(CREATE\s+OR\s+REPLACE\s+PROCEDURE\s+)`?(\w+)`?', r'\1__SCHEMA_QUALIFIED__.\2', sql, count=1, flags=re.IGNORECASE)
        else:
            sql = re.sub(r'(CREATE\s+OR\s+REPLACE\s+FUNCTION\s+)`?(\w+)`?', r'\1__SCHEMA_QUALIFIED__.\2', sql, count=1, flags=re.IGNORECASE)
        # Qualify table names in FROM, INTO, UPDATE, JOIN clauses (bare backtick-quoted or unquoted)
        for kw in ('FROM', 'INTO', 'UPDATE', 'JOIN'):
            sql = re.sub(rf'({kw}\s+)`?(\w+)`?', rf'\1__SCHEMA_QUALIFIED__.\2', sql, flags=re.IGNORECASE)
        fixes.append("auto-added __SCHEMA_QUALIFIED__ to routine and table names")

    # ── Common: strip SQL SECURITY INVOKER from functions ──
    if routine_type == "function" and re.search(r'\bSQL\s+SECURITY\s+INVOKER\b', sql):
        sql = re.sub(r'\n\s*SQL\s+SECURITY\s+INVOKER\b', '', sql)
        fixes.append("removed SQL SECURITY INVOKER (not supported for functions)")

    # ── Common: LIMIT must be a constant, not a parameter ──
    m = re.search(r'\bLIMIT\s+(p_\w+)\b', sql, re.IGNORECASE)
    if m:
        sql = re.sub(r'\bLIMIT\s+p_\w+\b', 'LIMIT 100', sql, flags=re.IGNORECASE)
        fixes.append(f"replaced LIMIT {m.group(1)} with LIMIT 100 (must be constant)")

    # ── Common: ensure LANGUAGE SQL present ──
    if "LANGUAGE SQL" not in sql.upper():
        if routine_type == "function":
            sql = re.sub(r'(\n)(RETURN\b)', r'\1LANGUAGE SQL\n\2', sql, count=1)
        else:
            sql = re.sub(r'(\n)(AS\b)', r'\1LANGUAGE SQL\n\2', sql, count=1)
        if "LANGUAGE SQL" in sql.upper():
            fixes.append("added missing LANGUAGE SQL")

    # ── Function-specific checks ──
    if routine_type == "function":
        upper = sql.upper()
        if "CREATE" not in upper or "FUNCTION" not in upper:
            raise ValueError("Function SQL missing CREATE FUNCTION statement")
        if "RETURNS TABLE" not in upper:
            raise ValueError("Function SQL missing RETURNS TABLE clause")
        # Check RETURN keyword exists (but not just inside RETURNS TABLE)
        if not re.search(r'\bRETURN\s', sql):
            raise ValueError("Function SQL missing RETURN keyword (use RETURN SELECT ..., not BEGIN...END)")
        # Functions cannot use BEGIN...END
        if re.search(r'\bBEGIN\b', upper) and re.search(r'\bEND\s*;', upper):
            raise ValueError("Functions must use RETURN SELECT, not BEGIN...END blocks — rewrite as a single RETURN query")
        # Functions cannot contain write operations
        for kw in ("UPDATE ", "INSERT ", "DELETE "):
            # Only flag if it's a statement keyword, not inside a column name
            if re.search(rf'^\s*{kw}', sql, re.MULTILINE | re.IGNORECASE):
                raise ValueError(f"Functions are read-only — cannot contain {kw.strip()} statements")

        # ── DEFAULT parameter ordering ──
        param_match = re.search(
            r'CREATE\s+OR\s+REPLACE\s+FUNCTION\s+\S+\s*\((.*?)\)\s*\n\s*RETURNS',
            sql, re.DOTALL | re.IGNORECASE,
        )
        if param_match:
            params_block = param_match.group(1)
            params = [p.strip() for p in params_block.split(',') if p.strip()]
            if len(params) > 1:
                seen_default = False
                needs_reorder = False
                for p in params:
                    has_default = 'DEFAULT' in p.upper()
                    if seen_default and not has_default:
                        needs_reorder = True
                        break
                    if has_default:
                        seen_default = True
                if needs_reorder:
                    non_default = [x for x in params if 'DEFAULT' not in x.upper()]
                    with_default = [x for x in params if 'DEFAULT' in x.upper()]
                    new_block = ',\n    '.join(non_default + with_default)
                    sql = sql[:param_match.start(1)] + '\n    ' + new_block + '\n' + sql[param_match.end(1):]
                    fixes.append("reordered parameters (non-DEFAULT before DEFAULT)")

    # ── Procedure-specific checks ──
    if routine_type == "procedure":
        upper = sql.upper()
        if "CREATE" not in upper:
            raise ValueError("Procedure SQL missing CREATE statement")
        if "BEGIN" not in upper or "END" not in upper:
            raise ValueError("Procedure SQL missing BEGIN...END block")

        # ── Procedure params must be STRING -- auto-fix non-STRING types ──
        param_match = re.search(
            r'CREATE\s+OR\s+REPLACE\s+PROCEDURE\s+\S+\s*\((.*?)\)\s*\n',
            sql, re.DOTALL | re.IGNORECASE,
        )
        if param_match:
            params_block = param_match.group(1)
            params = [p.strip() for p in params_block.split(',') if p.strip()]
            non_string_types = re.compile(r'\b(DATE|DOUBLE|FLOAT|INT|BIGINT|DECIMAL|TIMESTAMP_NTZ|TIMESTAMP|BOOLEAN)\b', re.IGNORECASE)
            new_params = []
            fixed_any = False
            for p in params:
                if non_string_types.search(p):
                    original_type = non_string_types.search(p).group(1)
                    p = non_string_types.sub('STRING', p)
                    fixed_any = True
                new_params.append(p)
            if fixed_any:
                new_block = ',\n  '.join(new_params)
                sql = sql[:param_match.start(1)] + '\n  ' + new_block + '\n' + sql[param_match.end(1):]
                fixes.append("auto-fixed procedure params to STRING (tool_factory passes quoted strings)")

    for fix in fixes:
        print(f"[~] Auto-fixed: {fix}")

    return sql


def generate_routine_sql(
    routine: dict[str, Any],
    table_schemas: list[dict[str, Any]] | None = None,
) -> str:
    """Generate SQL code for a single routine.

    Returns the raw SQL string.
    """
    print(f"[+] Generating SQL for {routine['type']}: {routine['name']}...")

    base_prompt = PROCEDURE_SYSTEM_PROMPT if routine["type"] == "procedure" else FUNCTION_SYSTEM_PROMPT
    ref = _load_reference()
    system = f"{base_prompt}\n\n{ref}" if ref else base_prompt
    user = _build_user_prompt(routine, table_schemas)

    raw = call_llm(system, user, max_tokens=4096)
    sql = _strip_fences(raw)

    try:
        sql = _sanitize_sql(sql, routine["type"])
    except ValueError as e:
        print(f"[~] Validation warning: {e} — retrying...")
        correction = (
            f"Your SQL was invalid: {e}. "
            "Return ONLY the corrected raw SQL, no markdown fences."
        )
        raw2 = call_llm(system, f"{user}\n\n{correction}", max_tokens=4096)
        sql = _strip_fences(raw2)
        sql = _sanitize_sql(sql, routine["type"])

    line_count = len(sql.splitlines())
    print(f"[+] Generated {line_count} lines for {routine['name']}")
    return sql
