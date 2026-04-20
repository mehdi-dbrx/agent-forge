---
name: forge-setup-warehouse
description: Configure DATABRICKS_WAREHOUSE_ID interactively. Claude lists available SQL warehouses from the workspace, presents numbered choices, takes the user's pick, writes to .env.local, and verifies. No terminal needed.
---

# Agent Forge — Setup: warehouse

Configures `DATABRICKS_WAREHOUSE_ID` in `.env.local`.

## Flow

### 1. Read current state (run in parallel)

```bash
grep "^DATABRICKS_WAREHOUSE_ID" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null || echo "NOT_SET"
```
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
for wh in w.warehouses.list():
    print(wh.id, '|', wh.name, '|', wh.state)
" 2>/dev/null || echo "CANNOT_LIST"
```

### 2. Parse and present

Build numbered list from warehouse output (format: `id | name | state`).

```
forge-setup — Step 3: DATABRICKS_WAREHOUSE_ID

Current : 8ba51d8cad2a3d9a  [+]  (or "not set")

Available warehouses:
[1]  Starter Warehouse        8ba51d8cad2a3d9a  ← current
[2]  My Shared Endpoint       abc123def456
[3]  enter ID manually

Pick a warehouse:
```

### 3. Take user input

- Number → use that warehouse ID
- "keep" or number matching current → skip write
- "enter ID manually" → ask: "Paste warehouse ID:"

### 4. Write to .env.local

```bash
python3 -c "
import re; from pathlib import Path
f = Path('/Users/mehdi.lamrani/code/code/agent-forge/.env.local')
key, val = 'DATABRICKS_WAREHOUSE_ID', '<CHOSEN_ID>'
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

### 5. Verify

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import os
wh_id = os.environ.get('DATABRICKS_WAREHOUSE_ID','').strip()
w = WorkspaceClient()
wh = w.warehouses.get(wh_id)
print('[+] Warehouse:', wh.name, '(' + str(wh.state) + ')')
" 2>&1
```

### 6. Confirm + next step

```
[+] DATABRICKS_WAREHOUSE_ID = 8ba51d8cad2a3d9a  (Starter Warehouse)

Next: /forge-setup-schema
```

## Error cases

- Cannot list warehouses (auth not set yet): show only "enter ID manually" option
- Warehouse not found on verify: show error, ask if they want to enter a different ID
