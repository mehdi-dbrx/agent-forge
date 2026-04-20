---
name: forge-setup-tables
description: Check and create Delta tables interactively. Claude checks which tables exist in UC, shows [+]/[x] per table, and offers to run create_all_assets.py to provision missing ones. No terminal needed.
---

# Agent Forge — Setup: tables

Checks Delta tables derived from `data/csv/*.csv` and offers to create missing ones.

## Flow

### 1. Read current state (run in parallel)

```bash
grep "^PROJECT_UNITY_CATALOG_SCHEMA" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null
```
```bash
ls /Users/mehdi.lamrani/code/code/agent-forge/data/csv/*.csv 2>/dev/null | xargs -I{} basename {} .csv | tr '-' '_'
```

### 2. Check each table in UC

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
import os; from databricks.sdk import WorkspaceClient
spec = os.environ.get('PROJECT_UNITY_CATALOG_SCHEMA','').strip()
if '.' not in spec: print('[x] PROJECT_UNITY_CATALOG_SCHEMA not set'); exit(1)
w = WorkspaceClient()
import re, glob
tables = sorted(re.sub(r'-','_', p.split('/')[-1].replace('.csv','')) for p in glob.glob('data/csv/*.csv'))
for t in tables:
    try:
        w.tables.get(f'{spec}.{t}')
        print('[+]', t)
    except Exception as e:
        print('[x]', t, '-', str(e)[:60])
" 2>&1
```

### 3. Present to user

```
forge-setup — Step 5: Delta Tables

Schema : agent_forge_catalog.main

[+]  checkin_metrics
[+]  border_officers
[x]  flights          (table not found)
[x]  checkin_agents   (table not found)

2 tables missing.

[1]  create all missing tables (run create_all_assets.py)
[2]  skip for now
```

If all tables exist → show all [+] and say "All tables present." Then suggest next step.

### 4. If user picks [1] — create assets

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python data/init/create_all_assets.py 2>&1
```

Stream the output. After completion, re-run the check from step 2 to confirm all [+].

### 5. Confirm + next step

```
[+] All tables present in agent_forge_catalog.main

Next: /forge-setup-functions
```

## Error cases

- PROJECT_UNITY_CATALOG_SCHEMA not set → say "Run /forge-setup-schema first"
- create_all_assets.py fails → show the error output and suggest checking UC permissions
