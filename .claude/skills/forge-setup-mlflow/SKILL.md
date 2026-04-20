---
name: forge-setup-mlflow
description: Configure MLFLOW_EXPERIMENT_ID interactively. Claude checks current experiment, offers to create a new one or enter an ID, writes to .env.local and verifies. No terminal needed.
---

# Agent Forge — Setup: mlflow

Configures `MLFLOW_EXPERIMENT_ID` in `.env.local`.

## Flow

### 1. Read current state

```bash
grep "^MLFLOW_EXPERIMENT_ID" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null || echo "NOT_SET"
```

Verify if set:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from databricks.sdk import WorkspaceClient; import os
eid = os.environ.get('MLFLOW_EXPERIMENT_ID','').strip()
if not eid: print('NOT_SET'); exit()
w = WorkspaceClient()
exp = w.experiments.get_experiment(experiment_id=eid)
print('[+]', getattr(exp,'name',eid), '(id:', eid + ')')
" 2>&1
```

### 2. Present choices

**If already set and valid:**
```
forge-setup — Step 10: MLFLOW_EXPERIMENT_ID

Current : 3688767017703470  [+]  "/Users/mehdi.lamrani/agent-forge-eval"

[1]  keep current
[2]  enter different experiment ID
[3]  create new MLflow experiment
```

**If not set or invalid:**
```
forge-setup — Step 10: MLFLOW_EXPERIMENT_ID

Current : not set

[1]  create new MLflow experiment
[2]  enter experiment ID manually
```

### 3. Handle choices

**keep** → skip

**create new experiment** → run:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python data/init/create_mlflow_experiment.py 2>&1
```
After success, read new ID from .env.local:
```bash
grep "^MLFLOW_EXPERIMENT_ID" /Users/mehdi.lamrani/code/code/agent-forge/.env.local
```

**enter ID manually** → ask: "Paste MLflow experiment ID:"
Write to .env.local.

### 4. Write to .env.local

```bash
python3 -c "
import re; from pathlib import Path
f = Path('/Users/mehdi.lamrani/code/code/agent-forge/.env.local')
key, val = 'MLFLOW_EXPERIMENT_ID', '<ID>'
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

### 5. Confirm + next step

```
[+] MLFLOW_EXPERIMENT_ID = 3688767017703470

Next: /forge-setup-model
```

## Error cases

- Experiment not found on verify: show error, offer to create new one
- create_mlflow_experiment.py fails: show error output
