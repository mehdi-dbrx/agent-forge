---
name: forge-setup-genie
description: Configure PROJECT_GENIE_CHECKIN interactively. Claude lists Genie spaces from the workspace, presents numbered choices, takes the user's pick or creates a new room, writes to .env.local. No terminal needed.
---

# Agent Forge — Setup: genie

Configures `PROJECT_GENIE_CHECKIN` (Genie space ID) in `.env.local`.

## Flow

### 1. Read current state (run in parallel)

```bash
grep "^PROJECT_GENIE_CHECKIN" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null || echo "NOT_SET"
```
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
r = w.genie.list_spaces()
spaces = getattr(r, 'spaces', []) or []
for s in spaces:
    sid = str(getattr(s,'space_id',None) or getattr(s,'id',''))
    title = getattr(s,'title','?')
    print(sid + '|' + title)
" 2>/dev/null || echo "CANNOT_LIST"
```

### 2. Present choices

```
forge-setup — Step 8: PROJECT_GENIE_CHECKIN

Current : 01f139de15a5156fb140cf83b40ed88f  [+]  (or "not set")

Available Genie spaces:
[1]  01f139de15a5156fb140cf83b40ed88f  "Checkin Metrics"  ← current
[2]  02abc123def456789012345678901234  "Flight Analytics"
[3]  create a new Genie room
[4]  enter space ID manually

Pick a space:
```

### 3. Handle choices

**keep / [1] current** → skip write

**pick a space [N]** → write that space ID to .env.local

**create a new Genie room** → ask: "Name for the new Genie room:"
Then run:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && GENIE_ROOM_NAME="<NAME>" uv run python data/init/create_genie_space.py 2>&1
```
After success, read the new ID from .env.local:
```bash
grep "^PROJECT_GENIE_CHECKIN" /Users/mehdi.lamrani/code/code/agent-forge/.env.local
```

**enter manually** → ask: "Paste Genie space ID:"

### 4. Write to .env.local (if not creating via script)

```bash
python3 -c "
import re; from pathlib import Path
f = Path('/Users/mehdi.lamrani/code/code/agent-forge/.env.local')
key, val = 'PROJECT_GENIE_CHECKIN', '<CHOSEN_ID>'
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
sid = os.environ.get('PROJECT_GENIE_CHECKIN','').strip()
w = WorkspaceClient()
sp = w.genie.get_space(space_id=sid)
print('[+] Genie space:', getattr(sp,'title',sid))
" 2>&1
```

### 6. Confirm + next step

```
[+] PROJECT_GENIE_CHECKIN = 01f139de...  ("Checkin Metrics")

Next: /forge-setup-ka
```

## Error cases

- Cannot list spaces (permissions): show only manual entry + create options
- Space not found on verify: show error, confirm the ID is correct
- create_genie_space.py fails: show error output
