---
name: forge-setup-host
description: Configure DATABRICKS_HOST interactively. Claude discovers available workspaces, presents numbered choices, takes the user's answer, writes to .env.local, and validates. No terminal needed.
---

# Agent Forge — Setup: host

Configures `DATABRICKS_HOST` in `.env.local`. Claude does all the work — discovers workspaces, presents choices, writes the value.

## Flow

### 1. Read current state (run in parallel)

```bash
grep "^DATABRICKS_HOST" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null || echo "NOT_SET"
```
```bash
databricks auth profiles 2>/dev/null
```

### 2. Parse and present

From `databricks auth profiles` output (skip header line), extract rows with `YES` in last column.
Each row: `Name  Host  ...  YES/NO`. Deduplicate by host. Mark current host with `← current`.

Show the user:
```
forge-setup — Step 1: DATABRICKS_HOST

Current : https://...  [+]     (or "not set" if missing)

Valid workspaces from your CLI profiles:
[1]  fevm-agent-forge    https://fevm-agent-forge.cloud.databricks.com  ← current
[2]  fevm-agent-ops      https://fevm-agent-ops.cloud.databricks.com
[3]  azure               https://adb-984752964297111.11.azuredatabricks.net
...
[N]  enter custom URL

Keep current [1] or pick another?
```

If no valid profiles found: show only the "enter custom URL" option.

### 3. Take user input

Wait for the user's reply. Interpret:
- A number → use that host
- "keep" or the number matching current → keep and skip write
- A URL (https://...) → use as-is
- "enter custom URL" or `N` → ask "Paste workspace URL:"

Validate: must start with `https://`. If missing scheme, prepend it.

### 4. Write to .env.local

If keeping current: skip write. Otherwise run:

```bash
python3 -c "
import re; from pathlib import Path
f = Path('/Users/mehdi.lamrani/code/code/agent-forge/.env.local')
key, val = 'DATABRICKS_HOST', '<CHOSEN_URL>'
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

Note: if the host changed, warn: "Workspace changed — delete `.databricks/bundle/` if you get Terraform state errors on next deploy."

### 5. Validate

```bash
grep "^DATABRICKS_HOST" /Users/mehdi.lamrani/code/code/agent-forge/.env.local
```

### 6. Confirm + next step

```
[+] DATABRICKS_HOST = https://...

Next: /forge-setup-auth
```

## Error cases

- No valid profiles → only offer custom URL input
- URL missing scheme → prepend `https://` silently
- .env.local missing → Python one-liner creates it
