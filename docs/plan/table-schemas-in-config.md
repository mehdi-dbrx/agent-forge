# Plan: Table Schemas in Config

> Status: EXECUTING
> Created: 2026-06-17

## Problem

Table schemas stored in separate `manifest.json` — doesn't travel with config, doesn't travel with bundles, forces fragile regex parsing.

## Solution

Store in `data.table_schemas` in config.json. Clean slate — no backward compat with old manifests.

## Config Shape

```json
"data": {
  "table_schemas": [
    {"name": "orders", "columns": [{"name": "order_id", "type": "BIGINT"}], "row_count": 15}
  ]
}
```

## Changes

### 1. `config_provider.py` — add default
Add `"table_schemas": []` to DEFAULT_CONFIG["data"].

### 2. `mage_tools.py` — writers use config only
- `create_tables_sql`: `config.set("data.table_schemas", manifest_tables)`. Remove manifest.json write.
- `generate_data`: update config. Remove manifest.json read/write.
- `generate_routine`: read from config. Remove manifest.json read.

### 3. `gen.py` — readers use config only
- `gen_status`: read from config, not manifest.json.
- `gen_tables`: config for gen tables, regex only for demo.
- `routine_status`: read from config, UC fallback for non-Mage projects.
- `gen_save`: sync allTables from request body to config before subprocess.
- `clear_gen`: clear config. Stop deleting manifest.json.

### 4. `server.py` — assets endpoint
Read table count from config, not manifest files.

## NOT changing
- `writer.py` — subprocess, will be dead code for Mage path. Leave for old gen wizard.
- `generate_tables.py` — subprocess. `gen_save` route syncs to config.
- Routine/prompt generators — receive table_schemas as params from endpoints. No change.
- Import/export — config travels with bundle. No migration needed.
