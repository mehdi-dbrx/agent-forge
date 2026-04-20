---
name: forge-setup-functions
description: Create or replace UC functions interactively. Claude lists SQL files from data/func/, asks for confirmation, runs create_all_functions.py. No terminal needed.
---

# Agent Forge — Setup: functions

Creates or replaces Unity Catalog functions from `data/func/*.sql`.

## Flow

### 1. List function SQL files

```bash
ls /Users/mehdi.lamrani/code/code/agent-forge/data/func/*.sql 2>/dev/null | xargs -I{} basename {} .sql
```

Also check which files contain `CREATE` (only those are executed):
```bash
grep -li "CREATE" /Users/mehdi.lamrani/code/code/agent-forge/data/func/*.sql 2>/dev/null | xargs -I{} basename {}
```

### 2. Present to user

```
forge-setup — Step 6: UC Functions

Will CREATE OR REPLACE:
  [+]  get_passenger_rights
  [+]  calculate_compensation
  [~]  query_template.sql  (no CREATE — skipped)

[1]  create/replace all UC functions
[2]  skip
```

If no `.sql` files found → say "No function files in data/func/ — nothing to do." and move to next step.

### 3. If user picks [1]

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python data/init/create_all_functions.py 2>&1
```

Show output. Success = exit code 0.

### 4. Confirm + next step

```
[+] UC functions created/replaced

Next: /forge-setup-procedures
```

## Error cases

- create_all_functions.py fails → show error, check that PROJECT_UNITY_CATALOG_SCHEMA is set
- No SQL files → skip silently and move to next step
