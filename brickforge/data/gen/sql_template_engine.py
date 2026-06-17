"""SQL Template Engine - generates Databricks SQL from structured JSON specs.

LLM designs the query (tables, joins, filters). This engine writes the SQL.
No LLM writes raw SQL. Deterministic output. Always correct syntax.

Handles:
- RETURNS TABLE functions with qualified parameter references
- Stored procedures with BEGIN...END, LANGUAGE SQL, SQL SECURITY INVOKER
- Schema qualification (__SCHEMA_QUALIFIED__)
- Column type resolution from table manifests
"""

from __future__ import annotations

import re
from typing import Any


class TemplateError(Exception):
    """Raised when the JSON spec is invalid or can't produce valid SQL."""
    pass


def build_schema_lookup(tables: list[dict]) -> dict[str, dict[str, str]]:
    """Build {table_name: {column_name: type}} from manifest tables list."""
    return {
        t["name"]: {c["name"]: c["type"] for c in t.get("columns", [])}
        for t in tables
    }


def generate_sql(spec: dict, schema_lookup: dict) -> str:
    """Generate SQL from a structured JSON spec.

    Dispatches to function or procedure generator based on spec["type"].
    Returns the complete CREATE OR REPLACE statement with __SCHEMA_QUALIFIED__ placeholders.
    """
    routine_type = spec.get("type", "function")
    if routine_type == "function":
        return _generate_function(spec, schema_lookup)
    elif routine_type == "procedure":
        return _generate_procedure(spec, schema_lookup)
    else:
        raise TemplateError(f"Unknown routine type: {routine_type}")


def validate_spec(spec: dict, schema_lookup: dict) -> list[str]:
    """Validate a spec against the schema. Returns list of errors (empty = valid)."""
    errors = []

    if not spec.get("name"):
        errors.append("Missing 'name'")
    if not spec.get("type"):
        errors.append("Missing 'type' (function or procedure)")

    # Validate table references
    all_tables = set(schema_lookup.keys())

    from_table = spec.get("from", {})
    if from_table and from_table.get("table") not in all_tables:
        errors.append(f"Table '{from_table.get('table')}' not found. Available: {sorted(all_tables)}")

    for join in spec.get("joins", []):
        if join.get("table") not in all_tables:
            errors.append(f"Join table '{join.get('table')}' not found. Available: {sorted(all_tables)}")

    # Validate column references in returns (for functions)
    if spec.get("type") == "function" and spec.get("returns"):
        alias_map = _build_alias_map(spec)
        for ret in spec["returns"]:
            source = ret.get("source", "")
            if ret.get("type"):
                continue  # explicit type, skip validation
            m = re.match(r'^(\w+)\.(\w+)$', source)
            if m:
                alias, col = m.group(1), m.group(2)
                table = alias_map.get(alias)
                if table and table in schema_lookup:
                    if col not in schema_lookup[table]:
                        errors.append(f"Column '{col}' not found in table '{table}'. Available: {sorted(schema_lookup[table].keys())}")

    # Validate param references in where
    where = spec.get("where", "")
    if where:
        param_names = {p["name"] for p in spec.get("params", [])}
        referenced = set(re.findall(r'\{(\w+)\}', where))
        unknown = referenced - param_names
        if unknown:
            errors.append(f"Unknown param references in where: {unknown}. Declared params: {param_names}")

    return errors


def _build_alias_map(spec: dict) -> dict[str, str]:
    """Build {alias: table_name} from from + joins."""
    alias_map = {}
    from_table = spec.get("from", {})
    if from_table:
        alias_map[from_table.get("alias", from_table["table"])] = from_table["table"]
    for join in spec.get("joins", []):
        alias_map[join.get("alias", join["table"])] = join["table"]
    return alias_map


def _resolve_column_type(source: str, alias_map: dict, schema_lookup: dict) -> str:
    """Resolve a column's type from its source expression."""
    m = re.match(r'^(\w+)\.(\w+)$', source)
    if m:
        alias, col = m.group(1), m.group(2)
        table = alias_map.get(alias)
        if table and table in schema_lookup and col in schema_lookup[table]:
            return schema_lookup[table][col]
    # Can't resolve - default to STRING
    return "STRING"


def _qualify_params(text: str, func_name: str, params: list[dict]) -> str:
    """Replace {param_name} with func_name.param_name in text."""
    for p in params:
        text = text.replace(f"{{{p['name']}}}", f"{func_name}.{p['name']}")
    return text


def _generate_function(spec: dict, schema_lookup: dict) -> str:
    """Generate a RETURNS TABLE function from spec."""
    name = spec["name"]
    params = spec.get("params", [])
    returns = spec.get("returns", [])
    from_table = spec.get("from", {})
    joins = spec.get("joins", [])
    where = spec.get("where")
    order_by = spec.get("order_by")
    group_by = spec.get("group_by")
    limit = spec.get("limit")

    alias_map = _build_alias_map(spec)

    # Param list
    param_str = ", ".join(f"{p['name']} {p.get('type', 'STRING')}" for p in params)

    # RETURNS TABLE columns
    returns_lines = []
    for ret in returns:
        col_type = ret.get("type") or _resolve_column_type(ret["source"], alias_map, schema_lookup)
        returns_lines.append(f"  {ret['name']} {col_type}")
    returns_str = ",\n".join(returns_lines)

    # SELECT columns
    select_lines = [f"  {ret['source']}" for ret in returns]
    select_str = ",\n".join(select_lines)

    # FROM
    from_alias = from_table.get("alias", "")
    from_str = f"__SCHEMA_QUALIFIED__.{from_table['table']}"
    if from_alias:
        from_str += f" {from_alias}"

    # JOINs
    join_lines = []
    for j in joins:
        jtype = j.get("type", "INNER").upper()
        jalias = j.get("alias", "")
        jstr = f"{jtype} JOIN __SCHEMA_QUALIFIED__.{j['table']}"
        if jalias:
            jstr += f" {jalias}"
        jstr += f" ON {j['on']}"
        join_lines.append(jstr)

    # WHERE with qualified params
    where_str = ""
    if where:
        qualified_where = _qualify_params(where, name, params)
        where_str = f"WHERE {qualified_where}"

    # GROUP BY
    group_str = f"GROUP BY {group_by}" if group_by else ""

    # ORDER BY
    order_str = f"ORDER BY {order_by}" if order_by else ""

    # LIMIT
    limit_str = f"LIMIT {limit}" if limit else ""

    # Assemble
    parts = [
        f"CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.{name}({param_str})",
        f"RETURNS TABLE (\n{returns_str}\n)",
        "LANGUAGE SQL",
        "RETURN",
        f"SELECT\n{select_str}",
        f"FROM {from_str}",
    ]
    for jl in join_lines:
        parts.append(jl)
    if where_str:
        parts.append(where_str)
    if group_str:
        parts.append(group_str)
    if order_str:
        parts.append(order_str)
    if limit_str:
        parts.append(limit_str)

    return "\n".join(parts) + "\n"


def _generate_procedure(spec: dict, schema_lookup: dict) -> str:
    """Generate a stored procedure from spec."""
    name = spec["name"]
    params = spec.get("params", [])
    statements = spec.get("statements", [])

    # All procedure params are STRING (convention)
    param_str = ", ".join(f"{p['name']} STRING" for p in params)

    # Build statement lines
    body_lines = []
    for stmt in statements:
        stype = stmt.get("type", "").upper()

        if stype == "INSERT":
            table = stmt["table"]
            columns = stmt["columns"]
            values = stmt["values"]
            # Substitute params (bare, not qualified - procedures don't need it)
            sub_values = []
            for v in values:
                sv = v
                for p in params:
                    sv = sv.replace(f"{{{p['name']}}}", p["name"])
                sub_values.append(sv)
            cols_str = ", ".join(columns)
            vals_str = ",\n    ".join(sub_values)
            body_lines.append(f"  INSERT INTO __SCHEMA_QUALIFIED__.{table} ({cols_str})")
            body_lines.append(f"  VALUES ({vals_str});")

        elif stype == "UPDATE":
            table = stmt["table"]
            sets = stmt.get("set", {})
            where = stmt.get("where", "")
            set_parts = []
            for col, val in sets.items():
                sv = val
                for p in params:
                    sv = sv.replace(f"{{{p['name']}}}", p["name"])
                set_parts.append(f"{col} = {sv}")
            set_str = ", ".join(set_parts)
            body_lines.append(f"  UPDATE __SCHEMA_QUALIFIED__.{table}")
            body_lines.append(f"  SET {set_str}")
            if where:
                sw = where
                for p in params:
                    sw = sw.replace(f"{{{p['name']}}}", p["name"])
                body_lines.append(f"  WHERE {sw};")
            else:
                body_lines[-1] += ";"

        elif stype == "RAW":
            # Escape hatch: raw SQL line
            line = stmt.get("sql", "")
            for p in params:
                line = line.replace(f"{{{p['name']}}}", p["name"])
            body_lines.append(f"  {line}")

    body_str = "\n".join(body_lines)

    return (
        f"CREATE OR REPLACE PROCEDURE __SCHEMA_QUALIFIED__.{name}({param_str})\n"
        f"LANGUAGE SQL\n"
        f"SQL SECURITY INVOKER\n"
        f"BEGIN\n"
        f"{body_str}\n"
        f"END\n"
    )
