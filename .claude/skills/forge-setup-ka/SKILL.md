---
name: forge-setup-ka
description: Configure Knowledge Assistant endpoints interactively. Claude checks existing KAs, shows PDFs, presents options to use/provision, writes PROJECT_KA_* to .env.local. No terminal needed.
---

# Agent Forge — Setup: ka

Configures `PROJECT_KA_PASSENGERS` (and other KA vars) in `.env.local`.

## Flow

### 1. Read current state (run in parallel)

```bash
grep "^PROJECT_KA_" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null || echo "NOT_SET"
```
```bash
ls /Users/mehdi.lamrani/code/code/agent-forge/data/pdf/*.pdf 2>/dev/null | xargs -I{} basename {}
```
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
for ka in w.knowledge_assistants.list_knowledge_assistants():
    if ka.endpoint_name:
        st = ka.state
        raw = (st.value if hasattr(st,'value') else str(st)) if st else 'UNKNOWN'
        print(ka.endpoint_name + '|' + (ka.display_name or '') + '|' + raw)
" 2>/dev/null || echo "CANNOT_LIST"
```

### 2. Present choices

```
forge-setup — Step 9: Knowledge Assistants

PDFs in data/pdf/:
  [+]  EU_Passenger_Rights.pdf
  [+]  Flight_Compensation_Rules.pdf

Current : PROJECT_KA_PASSENGERS = ka-087003b9-endpoint  [ACTIVE]

Existing KAs in workspace:
  [+]  ka-087003b9-endpoint  "Passengers"  ACTIVE   ← current
  [-]  ka-aabbccdd-endpoint  "Other KA"    INACTIVE

[1]  keep current
[2]  use: ka-aabbccdd-endpoint (Other KA - INACTIVE)
[3]  provision new KA from data/pdf/ (create volume, upload PDFs, deploy)
[4]  recreate current KA
```

### 3. Handle choices

**keep** → skip

**use existing** → write chosen endpoint name to .env.local as `PROJECT_KA_PASSENGERS`

**provision / recreate** → run provisioning steps:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python scripts/py/ka/create_volume.py 2>&1
```
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python scripts/py/ka/upload_pdfs.py 2>&1
```
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python scripts/py/ka/create_kas_from_yml.py --skip-existing 2>&1
```
Run sequentially, show output, stop on first failure.

After provisioning, read the new value from .env.local:
```bash
grep "^PROJECT_KA_" /Users/mehdi.lamrani/code/code/agent-forge/.env.local
```

### 4. Write to .env.local (when selecting existing)

```bash
python3 -c "
import re; from pathlib import Path
f = Path('/Users/mehdi.lamrani/code/code/agent-forge/.env.local')
key, val = 'PROJECT_KA_PASSENGERS', '<CHOSEN_ENDPOINT>'
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
ep = os.environ.get('PROJECT_KA_PASSENGERS','').strip()
w = WorkspaceClient()
for ka in w.knowledge_assistants.list_knowledge_assistants():
    if ka.endpoint_name == ep:
        st = ka.state; raw = (st.value if hasattr(st,'value') else str(st)) if st else '?'
        print('[+] KA:', ep, raw)
        break
else:
    print('[x] KA endpoint not found:', ep)
" 2>&1
```

### 6. Confirm + next step

```
[+] PROJECT_KA_PASSENGERS = ka-087003b9-endpoint  (ACTIVE)

Next: /forge-setup-mlflow
```

## Error cases

- No PDFs in data/pdf/ → warn before provisioning: "No PDFs found — KA will have no content"
- Provisioning scripts fail → show error, check UC permissions and workspace quotas
- KA stays INACTIVE → explain it may take a few minutes to activate
