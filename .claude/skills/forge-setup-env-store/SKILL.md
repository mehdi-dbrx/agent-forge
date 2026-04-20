---
name: forge-setup-env-store
description: Configure env store (optional) interactively. Claude checks current state, asks if the user wants to set up UC Volume backup, guides through workspace+volume path selection. No terminal needed.
---

# Agent Forge — Setup: env-store (optional)

Optionally configures `ENV_STORE_HOST` and `ENV_STORE_CATALOG_VOLUME_PATH` — saves/restores `.env.local` to a Databricks Unity Catalog Volume.

## Flow

### 1. Read current state

```bash
grep "^ENV_STORE_HOST\|^ENV_STORE_CATALOG_VOLUME_PATH" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null || echo "NOT_SET"
```

### 2. Present

**If already configured:**
```
forge-setup — Step 14: Env Store (optional)

Current :
  ENV_STORE_HOST              = https://adb-984752964297111.11.azuredatabricks.net
  ENV_STORE_CATALOG_VOLUME_PATH = /Volumes/agent_forge_catalog/main/store

[1]  keep current
[2]  reconfigure
[3]  skip (disable env store)
```

**If not configured:**
```
forge-setup — Step 14: Env Store (optional)

Not configured. The env store lets you save/restore .env.local to a UC Volume
(useful for team sharing or backup across sessions).

[1]  set up env store
[2]  skip (not needed)
```

### 3. If setting up

Ask:
1. "Which workspace hosts the UC Volume? (Enter URL or pick from profiles):"
   - Run `databricks auth profiles` and show valid profiles as options
2. "UC Volume path? (format: /Volumes/catalog/schema/volume):"
   - Default suggestion: `/Volumes/<current-catalog>/<current-schema>/store`

Write both to .env.local:
```bash
python3 -c "
import re; from pathlib import Path
f = Path('/Users/mehdi.lamrani/code/code/agent-forge/.env.local')
vals = {'ENV_STORE_HOST': '<HOST>', 'ENV_STORE_CATALOG_VOLUME_PATH': '<PATH>'}
lines = f.read_text().splitlines() if f.exists() else []
new = []; found = set()
for line in lines:
    m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
    if m and m.group(1) in vals:
        new.append(f'{m.group(1)}={vals[m.group(1)]}'); found.add(m.group(1))
    else: new.append(line)
for k, v in vals.items():
    if k not in found: new.append(f'{k}={v}')
f.write_text('\n'.join(new) + '\n')
for k, v in vals.items(): print('[+]', k, '=', v)
"
```

### 4. Confirm + final step

```
[+] Env store configured:
    ENV_STORE_HOST              = https://...
    ENV_STORE_CATALOG_VOLUME_PATH = /Volumes/.../store

Use `! ./scripts/sh/env_store.sh save` to snapshot your current .env.local.

Next: /forge-setup-check  (final verification pass)
```

## Error cases

- Volume path doesn't start with `/Volumes/`: warn, ask to confirm or fix
- Skip chosen: "Env store skipped — you can set it up later by running /forge-setup-env-store"
