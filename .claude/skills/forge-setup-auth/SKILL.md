---
name: forge-setup-auth
description: Configure Databricks authentication interactively. Claude checks current token/profile, presents options, takes the user's choice, writes to .env.local, verifies connection. No terminal needed.
---

# Agent Forge — Setup: auth

Configures `DATABRICKS_TOKEN` (or auto-detected CLI profile) in `.env.local`.

## Flow

### 1. Read current state (run in parallel)

```bash
grep "^DATABRICKS_HOST\|^DATABRICKS_TOKEN" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null
```
```bash
databricks auth profiles 2>/dev/null
```

### 2. Assess

- Extract `DATABRICKS_HOST` and `DATABRICKS_TOKEN` from .env.local
- From profiles output, check if any valid (`YES`) profile has a host matching `DATABRICKS_HOST`
- This tells you: has token? has matching profile?

### 3. Present choices

**Case A — token already set:**
```
forge-setup — Step 2: Auth

Current : DATABRICKS_TOKEN = dapi6f***...***3d9a  [already set]

[1]  keep current token
[2]  replace with new token
[3]  generate new 7-day PAT (via CLI profile)
```

**Case B — no token, but matching profile found:**
```
forge-setup — Step 2: Auth

Current : no token set
Auto-detected profile: fevm-agent-forge → https://fevm-agent-forge.cloud.databricks.com

[1]  use CLI profile (no token needed — auto-detected at runtime)
[2]  enter token manually
[3]  generate 7-day PAT using profile
```

**Case C — no token, no matching profile:**
```
forge-setup — Step 2: Auth

Current : no token, no matching CLI profile for this host

[1]  enter DATABRICKS_TOKEN manually
[2]  run CLI login (opens browser — requires terminal)
```

### 4. Handle each choice

**keep** → skip, go to next step

**enter token manually** → ask: "Paste your DATABRICKS_TOKEN (dapi...):"
- Write token to .env.local

**generate 7-day PAT** → run:
```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from scripts.py.setup_dbx_env import _profile_for_host, _redact, write_env_entry, ENV_FILE
import os; from databricks.sdk import WorkspaceClient
host = os.environ.get('DATABRICKS_HOST','').strip()
profile = _profile_for_host(host)
if not profile: print('[x] No matching CLI profile found'); exit(1)
from scripts.py.setup_dbx_env import _isolated_client
w = _isolated_client(profile)
t = w.tokens.create(comment='agent-forge-init', lifetime_seconds=604800)
write_env_entry(ENV_FILE, 'DATABRICKS_TOKEN', t.token_value)
print('[+] PAT generated (7d):', _redact(t.token_value))
"
```

**use CLI profile** → no write needed. Confirm: "Profile auto-detected at runtime — no token required."

**Write token** (when manually entered):
```bash
python3 -c "
import re; from pathlib import Path
f = Path('/Users/mehdi.lamrani/code/code/agent-forge/.env.local')
key, val = 'DATABRICKS_TOKEN', '<TOKEN>'
lines = f.read_text().splitlines() if f.exists() else []
new = []; found = False
for line in lines:
    m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
    if m and m.group(1) == key: new.append(f'{key}={val}'); found = True
    else: new.append(line)
if not found: new.append(f'{key}={val}')
f.write_text('\n'.join(new) + '\n')
print('[+] token written')
"
```

### 5. Verify connection

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
import os, json, urllib.request
host = os.environ.get('DATABRICKS_HOST','').strip().rstrip('/')
token = os.environ.get('DATABRICKS_TOKEN','').strip()
if token:
    req = urllib.request.Request(f'{host}/api/2.0/preview/scim/v2/Me', headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r: d = json.loads(r.read())
        print('[+] Connected as', d.get('userName','?'), 'on', host)
    except Exception as e: print('[x]', e)
else:
    print('[~] Using CLI profile — connection will be verified at runtime')
"
```

### 6. Confirm + next step

```
[+] Auth configured

Next: /forge-setup-warehouse
```

## Error cases

- Token invalid (HTTP 403/401): show error, ask if they want to enter a different one
- CLI login needed (Case C [2]): tell user "Run `! databricks auth login --host <host>` in the prompt below, then come back and run `/forge-setup-auth` again"
