---
name: forge-setup-schema
description: Configure PROJECT_UNITY_CATALOG_SCHEMA interactively. Claude lists available UC catalogs, asks for schema name, writes to .env.local, and verifies. No terminal needed.
---

# Agent Forge — Setup: schema

Configures `PROJECT_UNITY_CATALOG_SCHEMA` (format: `catalog.schema`) in `.env.local`.

## Flow

### 1. Read current state (run in parallel)

```bash
grep "^PROJECT_UNITY_CATALOG_SCHEMA" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null || echo "NOT_SET"
```
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
for c in w.catalogs.list():
    if c.name: print(c.name)
" 2>/dev/null || echo "CANNOT_LIST"
```

### 2. Present choices

```
forge-setup — Step 4: PROJECT_UNITY_CATALOG_SCHEMA

Current : agent_forge_catalog.main  [+]  (or "not set")

Available catalogs:
[1]  agent_forge_catalog  ← (matches current)
[2]  hive_metastore
[3]  main
[4]  enter catalog.schema manually

Pick a catalog, or enter the full schema:
```

### 3. Take input

- User picks catalog number → ask: "Schema name within this catalog? [main]:" (default: main)
  → compose: `catalog.schema`
- User picks "enter manually" → ask: "Enter catalog.schema (e.g. agent_forge_catalog.main):"
- "keep" / number matching current → skip write

Validate: must contain exactly one `.` dot.

### 4. Write to .env.local

```bash
python3 -c "
import re; from pathlib import Path
f = Path('/Users/mehdi.lamrani/code/code/agent-forge/.env.local')
key, val = 'PROJECT_UNITY_CATALOG_SCHEMA', '<CHOSEN_VALUE>'
lines = f.read_text().splitlines() if f.exists() else []
new = []; found = False
for line in lines:
    m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
    if m and m.group(1) == key: new.append(f'{key}={val}'); found = True
    else: new.append(line)
if not found: new.append(f'{key}={val}')
f.write_text('\n'.join(new) + '\n')
print('[+]', key, '=', val)
"
```

### 5. Verify schema and offer to create if missing

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import os
spec = os.environ.get('PROJECT_UNITY_CATALOG_SCHEMA','').strip()
catalog, schema = spec.split('.',1) if '.' in spec else (spec,'')
w = WorkspaceClient()
try:
    w.schemas.get(full_name=spec)
    print('SCHEMA_OK')
except:
    try:
        w.catalogs.get(name=catalog)
        print('CATALOG_OK_SCHEMA_MISSING')
    except:
        print('CATALOG_MISSING')
" 2>&1
```

**If `SCHEMA_OK`** → proceed.

**If `CATALOG_OK_SCHEMA_MISSING`** → the catalog exists but schema doesn't. Offer:
```
Catalog exists but schema '<schema>' not found.

[1]  Create schema only  (catalog.<schema> — fast, no tables yet)
[2]  Create catalog + schema + all assets  (tables, volume, Genie — full setup)
[3]  Enter a different catalog.schema
```

If [1]:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import os
spec = os.environ.get('PROJECT_UNITY_CATALOG_SCHEMA','').strip()
catalog, schema = spec.split('.',1)
w = WorkspaceClient()
w.schemas.create(name=schema, catalog_name=catalog)
print('[+] Schema created:', spec)
" 2>&1
```

If [2]: run `create_all_assets.py` (see below).

**If `CATALOG_MISSING`** → the catalog doesn't exist at all. Offer:
```
Catalog '<catalog>' does not exist on this workspace.

[1]  Create catalog + schema + all assets  (full setup: tables, volume, Genie)
[2]  Create catalog + schema only  (no tables yet)
[3]  Enter a different catalog.schema  (use an existing catalog)
```

If [1]:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python data/init/create_all_assets.py 2>&1
```

If [2]:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import os
spec = os.environ.get('PROJECT_UNITY_CATALOG_SCHEMA','').strip()
catalog, schema = spec.split('.',1)
w = WorkspaceClient()
w.catalogs.create(name=catalog)
print('[+] Catalog created:', catalog)
w.schemas.create(name=schema, catalog_name=catalog)
print('[+] Schema created:', spec)
" 2>&1
```

If [3]: go back to step 3 and ask for a new value.

### 6. Confirm + next step

```
[+] PROJECT_UNITY_CATALOG_SCHEMA = agent_forge_catalog.main

Next: /forge-setup-tables
```

## Error cases

- Cannot list catalogs: show only manual entry option
- Schema value missing dot: reject, ask again
- Catalog creation fails (permissions): show error — user may need `CREATE CATALOG` privilege on metastore
- create_all_assets.py fails: show full error output
