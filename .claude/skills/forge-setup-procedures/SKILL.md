---
name: forge-setup-procedures
description: Create or replace UC stored procedures interactively. Claude lists SQL files from data/proc/, asks for confirmation, runs create_all_procedures.py. No terminal needed.
---

# Agent Forge — Setup: procedures

Creates or replaces Unity Catalog stored procedures from `data/proc/*.sql`.

## Flow

### 1. List procedure SQL files

```bash
ls /Users/mehdi.lamrani/code/code/agent-forge/data/proc/*.sql 2>/dev/null | xargs -I{} basename {}
```

### 2. Present to user

```
forge-setup — Step 7: UC Procedures

Will CREATE OR REPLACE:
  [+]  checkin_summary
  [+]  flight_stats

[1]  create/replace all UC procedures
[2]  skip
```

If no `.sql` files found → say "No procedure files in data/proc/ — nothing to do." and move on.

### 3. If user picks [1]

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python data/init/create_all_procedures.py 2>&1
```

Show output. Success = exit code 0.

### 4. Confirm + next step

```
[+] UC procedures created/replaced

Next: /forge-setup-genie
```

## Error cases

- create_all_procedures.py fails → show error, check PROJECT_UNITY_CATALOG_SCHEMA is set
- No SQL files → skip silently and move to next step
