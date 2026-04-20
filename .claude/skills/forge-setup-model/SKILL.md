---
name: forge-setup-model
description: Configure Foundation Model endpoint interactively. Claude asks same-workspace vs cross-workspace, handles both flows, writes AGENT_MODEL_ENDPOINT and AGENT_MODEL_TOKEN to .env.local. No terminal needed.
---

# Agent Forge — Setup: model

Configures `AGENT_MODEL_ENDPOINT` (and optionally `AGENT_MODEL_TOKEN`) in `.env.local`.

The default model is `databricks-claude-sonnet-4-6`.

## Flow

### 1. Read current state

```bash
grep "^AGENT_MODEL_ENDPOINT\|^AGENT_MODEL_TOKEN\|^DATABRICKS_HOST" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null
```

### 2. Ask same-workspace vs cross-workspace

Show:
```
forge-setup — Step 11: Foundation Model Endpoint

DATABRICKS_HOST : https://fevm-agent-forge.cloud.databricks.com

Is your Foundation Model hosted in this same workspace?

[1]  Yes — same workspace  (endpoint derived from DATABRICKS_HOST at runtime, no config needed)
[2]  No  — Foundation Model is on another workspace  (cross-workspace URL + token required)
```

**If [1] — same workspace:**
- If AGENT_MODEL_ENDPOINT or AGENT_MODEL_TOKEN are currently set in .env.local, comment them out:
  ```bash
  python3 -c "
  from pathlib import Path; import re
  f = Path('/Users/mehdi.lamrani/code/code/agent-forge/.env.local')
  lines = f.read_text().splitlines()
  new = []
  for line in lines:
      m = re.match(r'^(AGENT_MODEL_ENDPOINT|AGENT_MODEL_TOKEN)=', line)
      if m: new.append('#' + line)
      else: new.append(line)
  f.write_text('\n'.join(new) + '\n')
  print('[+] Same-workspace mode — AGENT_MODEL_ENDPOINT/TOKEN commented out')
  "
  ```
- Show: `[+] Same-workspace mode set. Endpoint at runtime: https://<host>/serving-endpoints/databricks-claude-sonnet-4-6/invocations`
- Move to next step.

**If [2] — cross-workspace:**

Continue with cross-workspace flow below.

### 3. Cross-workspace flow

**Important context to show:**
- fevm workspaces (fevm-*) have zero rate limits — they cannot use their own FM endpoints
- Recommended FM workspaces:
  - AWS field eng: `https://e2-demo-field-eng.cloud.databricks.com`
  - Azure field eng: `https://adb-984752964297111.11.azuredatabricks.net`
- Pick the one matching your fevm's cloud (AWS fevm → AWS field eng, Azure fevm → Azure field eng)

Run to find matching CLI profiles for FM workspaces:
```bash
databricks auth profiles 2>/dev/null | grep -E "e2-demo-field-eng|adb-984752964297111"
```

Show numbered choices:
```
[1]  use profile: e2-demo  →  https://e2-demo-field-eng.cloud.databricks.com  (auto-generate PAT)
[2]  use profile: azure    →  https://adb-984752964297111.11.azuredatabricks.net  (auto-generate PAT)
[3]  set up new profile for AWS field eng
[4]  set up new profile for Azure field eng
[5]  enter endpoint URL + token manually
```

**If user picks existing profile:**
- Run PAT generation:
  ```bash
  cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python -c "
  from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
  from scripts.py.setup_dbx_env import _isolated_client, _redact, write_env_entry, comment_active_for_key, ENV_FILE
  profile = '<PROFILE_NAME>'
  fm_host = '<FM_HOST>'
  w = _isolated_client(profile)
  t = w.tokens.create(comment='agent-forge-fm-endpoint', lifetime_seconds=604800)
  endpoint = fm_host.rstrip('/') + '/serving-endpoints/databricks-claude-sonnet-4-6/invocations'
  comment_active_for_key(ENV_FILE, 'AGENT_MODEL_ENDPOINT')
  write_env_entry(ENV_FILE, 'AGENT_MODEL_ENDPOINT', endpoint)
  comment_active_for_key(ENV_FILE, 'AGENT_MODEL_TOKEN')
  write_env_entry(ENV_FILE, 'AGENT_MODEL_TOKEN', t.token_value)
  print('[+] AGENT_MODEL_ENDPOINT =', endpoint)
  print('[+] AGENT_MODEL_TOKEN =', _redact(t.token_value))
  " 2>&1
  ```

**If user picks "enter manually":**
- Ask: "Paste endpoint URL (https://host/serving-endpoints/name/invocations):"
- Ask: "Paste PAT token for that workspace:"
- Write both to .env.local using python3 one-liner (same pattern as other steps)

**If user picks "set up new profile":**
- Inform: "Run this in your terminal to log in, then come back:\n`! databricks auth login --host <fm_host> --profile <name>`\nThen run `/forge-setup-model` again."

### 4. Confirm + next step

```
[+] AGENT_MODEL_ENDPOINT = https://e2-demo-field-eng.../invocations
[+] AGENT_MODEL_TOKEN    = dapi66****...****82f5

Next: /forge-setup-model-test
```

## Error cases

- PAT generation fails: show error, fall back to "enter manually"
- Flavor mismatch (Azure fevm + AWS FM): warn before proceeding
- User needs browser login: redirect to terminal with `!` command
