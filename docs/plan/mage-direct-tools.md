# Plan: Mage Direct Tools - Eliminate the Double-LLM Pipeline

> Status: PLANNED
> Created: 2026-06-17

## Problem

Mage builds agents through a Rube Goldberg machine:

```
Mage LLM -> httpx -> gen endpoint -> subprocess -> SECOND LLM -> sanitize -> self-heal
```

Two LLMs, one HTTP hop, one subprocess, three band-aid layers. For every single gen step.

The Mage LLM already has all the context (spec, tables, actions). It passes vague instructions to a gen endpoint. A second LLM guesses what to generate. Errors get patched after the fact.

## Solution

Replace `exec_generate` with direct Mage tools. One LLM, one tool call, one output.

```
Mage LLM (has spec, tables, context)
    |
    | calls Mage tool directly
    |
    v
Tool does the work (template engine / file I/O / SQL execution)
    |
    v
Result returned to Mage LLM
```

No httpx. No gen endpoint. No subprocess. No second LLM (except where creativity is genuinely needed).

## New Mage Tools (build phase)

### Deterministic tools (no LLM needed)

| Tool | What it does | Replaces |
|------|-------------|----------|
| `create_tables_sql` | Takes spec entities -> generates CREATE TABLE SQL from column names + types | gen/schema + gen/save (schema part) |
| `generate_routine` | Takes query JSON -> template engine -> SQL file | gen/routine-sql (the whole SQL template engine plan) |
| `save_files` | Writes CSV/SQL/manifest to project dir | gen/save |
| `provision_tables` | Executes CREATE TABLE SQL against warehouse | gen/provision |
| `provision_routines` | Executes CREATE FUNCTION/PROCEDURE SQL against warehouse | gen/routine-provision |
| `create_genie_space` | Creates Genie space via SDK | exec-genie |
| `create_mlflow_experiment` | Creates MLflow experiment via SDK | exec-mlflow |

### LLM-powered tools (creativity genuinely needed)

| Tool | What it does | Why LLM needed |
|------|-------------|---------------|
| `generate_data` | Takes table schema -> synthetic CSV rows | Creative: realistic names, addresses, dates, domain-specific content |
| `generate_prompt` | Takes spec -> system prompt + knowledge base | Creative: agent personality, tone, domain knowledge |

These two still call the LLM, but the Mage LLM calls them directly as tool functions - no httpx, no subprocess, no gen endpoint.

### Tools that stay (already working fine)

| Tool | Why keep |
|------|---------|
| `read_status`, `read_config`, etc. | Read tools - no change needed |
| `save_config` | Config saves work fine via httpx |
| `exec_deploy` | Deploy is complex (bundle + upload + SDK), keep as httpx |
| `present_spec` | Just built, works well |

## How each step changes

### Table creation (was: 4 gen steps)

**Before:**
```
exec_generate("/api/gen/schema", {domain})     -> subprocess -> LLM invents tables
exec_generate("/api/gen/data", {table})         -> subprocess -> LLM generates rows (per table)
exec_generate("/api/gen/save", {table, rows})   -> subprocess -> writes CSV + SQL
exec_generate("/api/gen/provision", {})          -> subprocess -> runs CREATE TABLE SQL
```

**After:**
```
create_tables_sql(spec.entities)                 -> deterministic SQL from spec
generate_data(table_schema, row_count)           -> LLM generates rows (still needs creativity)
save_files(table, rows)                          -> direct file write, no subprocess
provision_tables()                               -> direct SQL execution via SDK
```

Three gen endpoints eliminated. Data gen keeps LLM but goes direct (no subprocess).

### Routine creation (was: 4 gen steps + self-healing)

**Before:**
```
exec_generate("/api/gen/routine-schema", {domain, tables}) -> subprocess -> LLM designs routines
exec_generate("/api/gen/routine-sql", {routine})           -> subprocess -> LLM writes SQL
exec_generate("/api/gen/routine-save", {routine, sql})     -> subprocess -> writes SQL file
exec_generate("/api/gen/routine-provision", {})             -> subprocess -> runs CREATE in UC
```

**After:**
```
# routine-schema eliminated - spec already has actions
generate_routine(query_json)                               -> template engine -> SQL string
save_files(routine_name, sql)                              -> direct file write
provision_routines()                                       -> direct SQL execution
```

Four gen endpoints eliminated. Zero LLM for SQL. Template engine is deterministic.

### Prompt generation (was: 2 gen steps)

**Before:**
```
exec_generate("/api/gen/prompt-generate", {domain, tables}) -> subprocess -> LLM writes prompt
exec_generate("/api/gen/prompt-save", {})                   -> subprocess -> writes files
```

**After:**
```
generate_prompt(spec, tables)                              -> LLM writes prompt (direct call, no subprocess)
save_files("prompt", prompt_files)                         -> direct file write
```

Two gen endpoints eliminated. LLM still writes prompt (creativity) but no subprocess.

## Implementation approach

### Phase 1: Template engine + generate_routine tool
- Build `sql_template_engine.py` (from sql-template-engine plan)
- Add `generate_routine(query_json)` tool to Mage build-phase tools
- Test: Mage generates routines without gen endpoint
- Gate: pizza domain, zero self-healing

### Phase 2: Table creation tools
- Add `create_tables_sql(entities)` - generates CREATE TABLE from spec
- Add `save_files(name, content)` - writes to project dir
- Add `provision_tables()` - executes SQL via SDK
- Test: Mage creates tables without gen/schema endpoint
- Gate: tables provisioned from spec entities

### Phase 3: Data generation tool
- Add `generate_data(table_schema, row_count)` - calls LLM directly for rows
- No subprocess, no gen endpoint. Direct `call_llm_json` inside the tool.
- Test: synthetic data generated and saved
- Gate: CSVs written, data loaded into tables

### Phase 4: Prompt generation tool
- Add `generate_prompt(spec, tables)` - calls LLM directly
- Writes prompt files directly to project dir
- Test: prompt generated and saved
- Gate: main.prompt + knowledge.base exist

### Phase 5: Genie + MLflow tools
- Add `create_genie_space(name)` - SDK call
- Add `create_mlflow_experiment(name)` - SDK call
- Replace exec_provision calls for these
- Gate: Genie space and MLflow experiment created

### Phase 6: Update Mage system prompt
- Remove gen protocol (the 30+ lines of endpoint instructions)
- Replace with direct tool descriptions
- The LLM calls `generate_routine(query_json)` not `exec_generate(endpoint, body)`

## What happens to the gen endpoints?

They stay. The visual UI wizard still uses them. Mage just doesn't.

Two paths to the same result:
- Visual UI: user clicks through wizard -> gen endpoints -> subprocesses
- Mage: LLM calls tools -> direct execution

Same output (SQL files, CSVs, prompts). Different pipelines.

## Files to create

| File | Purpose |
|------|---------|
| `brickforge/data/gen/sql_template_engine.py` | JSON -> SQL generator |
| New tools in `brickforge/lib/mage_tools.py` | 7 deterministic + 2 LLM-powered build tools |

## Files to modify

| File | Change |
|------|--------|
| `brickforge/lib/mage_tools.py` | Add new build-phase tools |
| `brickforge/lib/mage_agent.py` | Update system prompt - direct tools instead of gen protocol |

## Files NOT modified

| File | Why |
|------|-----|
| `brickforge/routes/gen.py` | Stays for visual UI wizard |
| `brickforge/data/gen/generate_tables.py` | Stays for visual UI |
| `brickforge/data/gen/generate_routines.py` | Stays for visual UI |
| `brickforge/data/gen/schema_generator.py` | Stays for visual UI |

## Verification

- Pizza domain: Mage builds end-to-end without calling any gen endpoint
- Hotel domain: same
- Zero self-healing on routine generation
- All table SQL valid (no hallucinated columns)
- All function params qualified
- All procedure SQL has LANGUAGE SQL + SQL SECURITY INVOKER
- Synthetic data is realistic (LLM creativity preserved)
- Prompts have personality and domain knowledge
- Visual UI wizard still works (gen endpoints untouched)
