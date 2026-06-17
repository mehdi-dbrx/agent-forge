# Plan: SQL Template Engine - LLM Designs, Code Writes

> Status: PLANNED
> Created: 2026-06-17

## Problem

The LLM generates raw Databricks SQL for UC functions and procedures. It consistently produces:
- Unqualified parameter references (fails at call time)
- Hallucinated column names (`order_date` when the table has `placed_at`)
- Truncated SQL (complex procedures exceed token limits)
- Missing `LANGUAGE SQL`, `SQL SECURITY INVOKER` clauses

Three layers of band-aids (prompt hints, sanitizer, self-healing) partially compensate. 4 of 5 functions needed self-healing in the pizza delivery build. This is not sustainable.

## Root Cause

The LLM doesn't know Databricks SQL syntax natively. It writes SQL by pattern matching against its training data, which includes PostgreSQL, MySQL, standard SQL - not Databricks-specific rules. Every prompt instruction we add is fighting the LLM's default behavior.

## Solution

**Separate reasoning from syntax.** The LLM decides WHAT the query should do (which tables, which joins, which filters). Code writes the actual SQL.

### LLM outputs query structure as JSON:

```json
{
  "name": "get_order_status",
  "type": "function",
  "params": [
    {"name": "p_order_id", "type": "STRING"}
  ],
  "returns": [
    {"name": "order_id", "source": "o.order_id"},
    {"name": "order_status", "source": "o.order_status"},
    {"name": "placed_at", "source": "o.placed_at"},
    {"name": "courier_name", "source": "dt.courier_name"},
    {"name": "current_coordinates", "source": "dt.current_coordinates"}
  ],
  "from": {"table": "orders", "alias": "o"},
  "joins": [
    {"table": "delivery_tracking", "alias": "dt", "on": "dt.order_id = o.order_id", "type": "LEFT"}
  ],
  "where": "o.order_id = {p_order_id}",
  "order_by": "dt.event_time DESC"
}
```

### Code generates SQL from JSON:

```sql
CREATE OR REPLACE FUNCTION __SCHEMA_QUALIFIED__.get_order_status(p_order_id STRING)
RETURNS TABLE (
  order_id STRING,
  order_status STRING,
  placed_at TIMESTAMP_NTZ,
  courier_name STRING,
  current_coordinates STRING
)
LANGUAGE SQL
RETURN
SELECT
  o.order_id,
  o.order_status,
  o.placed_at,
  dt.courier_name,
  dt.current_coordinates
FROM __SCHEMA_QUALIFIED__.orders o
LEFT JOIN __SCHEMA_QUALIFIED__.delivery_tracking dt ON dt.order_id = o.order_id
WHERE o.order_id = get_order_status.p_order_id
ORDER BY dt.event_time DESC
```

The template engine handles:
- `__SCHEMA_QUALIFIED__` prefix on all table names
- `LANGUAGE SQL` clause
- `RETURNS TABLE` with column types looked up from the table schema
- Parameter references always qualified with function name
- `SQL SECURITY INVOKER` for procedures
- `BEGIN...END` blocks for procedures
- Proper `CAST()` for STRING params in procedures

### Procedure JSON:

```json
{
  "name": "place_order",
  "type": "procedure",
  "params": [
    {"name": "p_customer_id", "type": "STRING"},
    {"name": "p_item_id", "type": "STRING"},
    {"name": "p_location_id", "type": "STRING"},
    {"name": "p_special_instructions", "type": "STRING"}
  ],
  "statements": [
    {
      "type": "insert",
      "table": "orders",
      "columns": ["order_id", "customer_id", "location_id", "order_status", "placed_at", "special_instructions"],
      "values": ["'ORD-' || LPAD(CAST(FLOOR(RAND()*99999) AS STRING), 5, '0')", "{p_customer_id}", "{p_location_id}", "'Pending'", "current_timestamp()", "{p_special_instructions}"]
    }
  ]
}
```

### What the LLM still does:
- Decides which tables to join and how
- Decides which columns to return
- Decides which WHERE conditions apply
- Decides the INSERT column mapping for procedures
- Provides the query logic as structured JSON

### What the LLM no longer does:
- Write raw SQL syntax
- Remember Databricks-specific keywords
- Qualify parameter references
- Add LANGUAGE SQL / SQL SECURITY INVOKER
- Handle BEGIN...END blocks

## Column type resolution

The template engine needs to know column types for RETURNS TABLE. Two sources:
1. **Generated manifest** - `gen/manifest.json` has table schemas with types
2. **UC metadata** - `w.tables.get()` returns column types from the workspace

The template engine reads the manifest first (available at gen time), falls back to UC metadata (available at runtime).

## Validation before generation

The JSON spec references table names and column names. The template engine validates:
- Every table in `from` and `joins` exists in the schema
- Every column in `returns`, `where`, `order_by` exists in its table
- Every param reference maps to a declared param
- No hallucinated column names pass through

If validation fails, return the error to the LLM for correction. This is faster than generating SQL, provisioning, failing, and self-healing.

## Files to create

| File | Purpose |
|------|---------|
| `brickforge/data/gen/sql_template_engine.py` | JSON -> SQL generator with validation |

## Files to modify

| File | Change |
|------|--------|
| `brickforge/data/gen/routine_sql_generator.py` | LLM outputs query JSON instead of raw SQL. Template engine generates SQL. |
| `brickforge/data/gen/generate_routines.py` | Pass table schemas to template engine for column type resolution. |

## What stays the same

- `routine_schema_generator.py` - still generates routine specs (what functions/procedures to create)
- Self-healing loop - still catches edge cases the template engine misses
- Sanitizer - reduced role but still catches anything the template missed
- The generated SQL files look the same to provisioning (CREATE FUNCTION/PROCEDURE)

## Implementation order

1. Build `sql_template_engine.py` - JSON -> SQL for functions (RETURNS TABLE)
2. Add procedure template (BEGIN...END, INSERT, UPDATE)
3. Add column type resolution from manifest
4. Add validation (table/column existence check)
5. Update `routine_sql_generator.py` - change LLM prompt to output JSON, pipe through template engine
6. Test: pizza domain - all functions generated without self-healing
7. Test: hotel domain - same
8. Test: edge case - function with subquery, multiple joins

## Review findings

### Where clause can contain raw SQL
Simple cases: `o.order_id = {p_order_id}`. Complex cases: subqueries, NOT IN, EXISTS. The template engine doesn't parse the where clause - it replaces `{param}` references with qualified names and passes the rest through. LLM writes the logic, template handles the wrapping.

### Aggregate functions supported
`returns` can have SQL expressions like `COUNT(*)`, `SUM(o.total)`. Template places them in SELECT as-is. `group_by` field added to JSON spec.

### Procedure values still raw SQL
INSERT values like `RAND()` expressions are LLM-written. The template wraps BEGIN/END, LANGUAGE SQL, SECURITY INVOKER, CAST - where the errors happen. Value expressions are standard SQL the LLM gets right.

### Graceful fallback
```python
try:
    sql = template_engine.generate(json_spec, schema_lookup)
except TemplateError:
    sql = call_llm(raw_sql_prompt, ...)  # old path
    sql = _sanitize_sql(sql)
```
Old and new coexist. No big bang cutover.

### Manifest format confirmed
`gen/manifest.json` has `{"tables": [{"name": "x", "columns": [{"name": "y", "type": "STRING"}]}]}`. Template engine builds lookup from this.

## Gates

1. **Template generates correct SQL for 3 function patterns** (simple, join, no-params) - MUST pass before touching pipeline
2. **Template generates correct SQL for 2 procedure patterns** (INSERT, UPDATE) - MUST pass before wiring
3. **LLM produces valid JSON specs for 3 domains** (pizza, hotel, healthcare) - MUST pass before replacing old prompt
4. **Full pipeline: pizza domain, zero self-healing on functions** - MUST pass before done

## Verification

- Zero self-healing needed for standard functions (SELECT with JOINs and WHERE)
- All params always qualified with function name
- All column names validated against actual schema - no hallucinated names
- LANGUAGE SQL and SQL SECURITY INVOKER always present
- Complex procedures (INSERT with computed values) generate correctly
- Fallback: if template engine can't handle a case, falls back to LLM raw SQL + sanitizer + self-healing
- 3 domains tested: pizza, hotel, healthcare
