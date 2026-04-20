---
name: forge-setup-app-name
description: Configure DBX_APP_NAME interactively. Claude shows current value, asks for app name, writes to .env.local. No terminal needed.
---

# Agent Forge — Setup: app-name

Configures `DBX_APP_NAME` in `.env.local`. This is the Databricks Apps deployment name used by the deploy pipeline.

## Flow

### 1. Read current state

```bash
grep "^DBX_APP_NAME" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null || echo "NOT_SET"
```

### 2. Present

```
forge-setup — Step 13: DBX_APP_NAME

Current : agent-vibe-app-no-dist  (or "not set")

[1]  keep current
[2]  enter new app name
```

### 3. Take input

- keep → skip
- [2] → ask: "Enter app name (e.g. my-agent-app, lowercase, hyphens ok):"

Validate: lowercase letters, numbers, hyphens only. No spaces.

### 4. Write to .env.local

```bash
python3 -c "
import re; from pathlib import Path
f = Path('/Users/mehdi.lamrani/code/code/agent-forge/.env.local')
key, val = 'DBX_APP_NAME', '<APP_NAME>'
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
[+] DBX_APP_NAME = agent-vibe-app-no-dist

Next: /forge-setup-env-store
```

## Error cases

- Name contains spaces or uppercase: normalize (lowercase, replace spaces with hyphens) and confirm with user before writing
