---
name: forge-setup-model-test
description: Test the Foundation Model endpoint interactively. Claude runs test_agent_model.py, shows the response or error, reports pass/fail. No terminal needed.
---

# Agent Forge — Setup: model-test

Sends a test message to the configured Foundation Model endpoint and validates the response.

## Flow

### 1. Show what will be tested

```bash
grep "^AGENT_MODEL_ENDPOINT\|^DATABRICKS_HOST" /Users/mehdi.lamrani/code/code/agent-forge/.env.local 2>/dev/null
```

Show:
```
forge-setup — Step 12: Foundation Model Test

Endpoint : https://e2-demo-field-eng.../invocations  (cross-workspace)
           OR: same-workspace (derived from DATABRICKS_HOST at runtime)

Sending "Hi" to the endpoint...
```

### 2. Run the test

```bash
cd /Users/mehdi.lamrani/code/code/agent-forge && uv run python scripts/py/test_agent_model.py 2>&1
```

Show the full output.

### 3. Parse result

- If output contains a response message → `[+] Model responded OK`
- If output contains error like `401`, `403` → `[x] Auth error — check AGENT_MODEL_TOKEN`
- If output contains `404` or "not found" → `[x] Endpoint not found — check AGENT_MODEL_ENDPOINT`
- If output contains "rate limit" or `429` → `[x] Rate limited — try again in a moment`
- Non-zero exit code with other error → show full output and suggest `/forge-setup-model` to reconfigure

### 4. Confirm + next step

On success:
```
[+] Foundation Model is responding correctly

Next: /forge-setup-app-name
```

On failure:
```
[x] Model test failed — see above

Run /forge-setup-model to reconfigure the endpoint.
```

## Error cases

- AGENT_MODEL_ENDPOINT not set and DATABRICKS_HOST not set: "Run /forge-setup-host first"
- Persistent failures: offer to run `/forge-setup-model` to reconfigure
