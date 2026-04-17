---
name: forge-add-data
description: Add a new synthetic dataset to agent-forge. Triggered when the user wants to add data, create a new table, add synthetic data, or extend the data layer with a new dataset.
---

# Agent Forge — Add Data

Generates synthetic CSV data and the full data layer (CSV + DDL SQL + Delta table) for a new dataset.

## Key Files & Conventions

- `data/csv/<table_name>.csv` — synthetic data source (≤100 rows)
- `data/init/create_<table_name>.sql` — DDL + INSERT (uses `__SCHEMA_QUALIFIED__` placeholder)
- `data/py/csv_to_delta.py` — uploads CSV to UC Volume and creates Delta table via `read_files()`
- `data/py/run_sql.py <sql_path>` — runs a SQL file with schema substitution
- `data/init/create_all_assets.py` — orchestrator: auto-discovers CSVs → runs matching SQL → verifies

**Auto-discovery rule**: `create_all_assets.py` scans `data/csv/*.csv` and looks for `data/init/create_{stem}.sql` for each one. Adding both files is all that's needed — no script modifications required.

**SQL placeholder**: `__SCHEMA_QUALIFIED__` → replaced at runtime with `catalog.schema` from `PROJECT_UNITY_CATALOG_SCHEMA`.

## Reference: `create_flights.sql`

```sql
CREATE OR REPLACE TABLE __SCHEMA_QUALIFIED__.<table_name> (
    col1 STRING,
    col2 TIMESTAMP_NTZ,
    col3 STRING,
    ...
)
USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO __SCHEMA_QUALIFIED__.<table_name> VALUES
('val1', CAST('2026-01-01 08:00:00' AS TIMESTAMP_NTZ), 'val3'),
...;
```

## Workflow

### Step 1 — Gather requirements

Ask the user:
1. **Dataset name** (will become table name and CSV filename, e.g. `staff_duties` → `data/csv/staff_duties.csv`)
2. **Description**: what does this data represent? (domain, entity, relationships to existing tables)
3. **Columns**: what fields should it have? (or derive sensible ones from the description)
4. **Row count**: how many rows? (max 100, default 20)
5. **Realism constraints**: any specific value ranges, status enums, foreign keys to existing tables (e.g. flight_number matching flights table)?

### Step 2 — Generate synthetic CSV

Generate realistic, coherent synthetic data matching the domain:
- Use plausible values (real airport codes, realistic timestamps, sensible enums)
- If the table relates to `flights`, reuse the same flight numbers (BA312, BA418, AF134, AF178) for referential consistency
- Timestamps: use `YYYY-MM-DD HH:MM:SS` format
- Keep row count ≤ 100
- Save to `data/csv/<table_name>.csv`

CSV format:
```
col1,col2,col3,...
val1,val2,val3,...
```

### Step 3 — Generate `data/init/create_<table_name>.sql`

Write the DDL matching the CSV schema exactly:
- Map CSV column types: text → `STRING`, numbers → `INT`/`DOUBLE`, dates → `TIMESTAMP_NTZ`
- Always include `USING DELTA` and `TBLPROPERTIES (delta.enableChangeDataFeed = true)`
- Use `__SCHEMA_QUALIFIED__` (not hardcoded catalog/schema)
- Include INSERT statements with all generated rows

Template:
```sql
CREATE OR REPLACE TABLE __SCHEMA_QUALIFIED__.<table_name> (
    <col1> <TYPE>,
    <col2> <TYPE>,
    ...
)
USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO __SCHEMA_QUALIFIED__.<table_name> VALUES
(<row1>),
(<row2>),
...;
```

### Step 4 — Load the data

Run one of these (both achieve the same result):

**Option A — SQL file (recommended, matches create_all_assets flow):**
```bash
uv run python data/py/run_sql.py data/init/create_<table_name>.sql
```

**Option B — CSV upload to volume + read_files:**
```bash
uv run python data/py/csv_to_delta.py data/csv/<table_name>.csv
```

### Step 5 — Verify

```bash
# Quick verify: table exists and has rows
uv run python -c "
from databricks.sdk import WorkspaceClient
import os
from dotenv import load_dotenv
load_dotenv('.env.local', override=True)
w = WorkspaceClient()
spec = os.environ['PROJECT_UNITY_CATALOG_SCHEMA']
t = w.tables.get(f'{spec}.<table_name>')
print(t.name, t.table_type)
"
```

Or run the full asset verification:
```bash
uv run python data/init/create_all_assets.py
```

## Notes

- `create_all_assets.py` is NOT modified — it discovers new tables automatically via CSV scan
- If the table needs a UC function (for agent queries), also create `data/func/<fn_name>.sql` — see `/forge-add-tool`
- If data changes, re-run `run_sql.py` or `csv_to_delta.py` — both use `CREATE OR REPLACE`
- Genie space will pick up new tables automatically on next `create_genie_space.py` run (or full `create_all_assets.py`)
- `delta.enableChangeDataFeed = true` is required for Genie space compatibility
