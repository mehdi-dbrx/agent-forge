---
name: dbx-ka
description: Create and deploy a new Databricks Knowledge Assistant agent. Triggered when the user wants to add a KA, create a knowledge assistant, or add a new KA agent to agent-forge.
---

# Databricks Knowledge Assistant (KA) Creator

Guides through creating a new KA agent: write the YAML config, deploy it, and verify it's active.

## Key Files

- `config/ka/ka_<name>.yml` — per-KA definition (display_name, description, instructions, knowledge_sources)
- `config/ka/output_format.yml` — shared output format prepended to every KA's instructions automatically
- `config/ka/ka_passengers.yml` — reference example
- `scripts/ka/create_kas_from_yml.py` — creates KAs in Databricks from YAML configs
- `scripts/ka/list_ka_states.py` — lists all KAs with state (ACTIVE / FAILED / CREATING)
- `scripts/ka/ka_instructions_merger.py` — merges shared output_format + per-KA instructions

## YAML Schema

File must be named `ka_<slug>.yml` and placed in `config/ka/`.

```yaml
knowledge_assistant:
  display_name: "agent-forge-<slug>"          # unique name in workspace
  description: "One-sentence description."    # shown in Databricks UI

  instructions: |
    You are an expert on <topic>. When responding:
    - Cite specific document sections by name and page
    - ...domain-specific rules...
    - If information isn't in the documents, clearly state that

knowledge_sources:
  - display_name: "<Source Label>"
    description: "What these documents contain."
    source_type: "files"
    files:
      path: "{volume_path}"                   # always use {volume_path} — resolved at runtime

examples:
  - question: "Sample question?"
    guideline: "How the KA should answer it"
```

**Rules:**
- `{volume_path}` is the only supported placeholder — maps to `/Volumes/<catalog>/<schema>/doc`
- `display_name` must be unique in the workspace; convention is `agent-forge-<slug>`
- `instructions` block is optional but recommended; merged with `output_format.yml` automatically
- `knowledge_sources` must have exactly one `source_type: "files"` entry
- `examples` block is informational only (not sent to Databricks)

## Env Var Mapping

After a KA becomes ACTIVE, its endpoint is written to `.env.local`:
- Display name containing "passenger" → `PROJECT_KA_PASSENGERS`
- Any other name → `PROJECT_KA_<DISPLAY_NAME_UPPER>` (slug of display_name)

## Workflow

### Step 1 — Create the YAML config

Ask the user for:
1. Topic / domain of the KA
2. Display name (suggest `agent-forge-<topic>`)
3. What documents will be indexed (they must already be in the UC Volume at `{volume_path}`)
4. Key instructions (how to cite, what to cover, limitations)

Then write `config/ka/ka_<slug>.yml` following the schema above. Use `config/ka/ka_passengers.yml` as a style reference.

### Step 2 — Dry-run validate

```bash
uv run python scripts/ka/create_kas_from_yml.py config/ka/ka_<slug>.yml --dry-run
```

Confirm: config loaded, volume path resolved, env key shown. Fix any errors before proceeding.

### Step 3 — Create the KA

```bash
uv run python scripts/ka/create_kas_from_yml.py config/ka/ka_<slug>.yml
```

- Waits for ACTIVE state (up to 10 min). Press ESC to detach and check later.
- On ACTIVE: saves `PROJECT_KA_<SLUG>=<endpoint>` to `.env.local` automatically.

### Step 4 — Verify

```bash
uv run python scripts/ka/list_ka_states.py
```

Confirm the new KA shows ACTIVE. If FAILED, read the error line — usually a bad volume path or missing PDF.

### Step 5 — Check .env.local

Confirm the env key was written:
```bash
grep PROJECT_KA .env.local
```

### Step 6 — Register in setup script (optional)

If the new KA needs a setup menu entry, look for `run_resource_ka_*` functions in `scripts/setup_dbx_env.py` and add a corresponding one following the existing pattern.

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `FAILED` state | Bad volume path or no PDFs uploaded | Upload PDFs first: `uv run python scripts/ka/upload_pdfs.py` |
| `PROJECT_UNITY_CATALOG_SCHEMA not set` | Missing env var | Run `./run setup` and configure schema |
| Duplicate display_name | KA already exists | Use `--skip-existing` or delete old KA first |
| `{volume_path}` in output | Placeholder not resolved | Ensure `PROJECT_UNITY_CATALOG_SCHEMA` is set in `.env.local` |

## Useful Commands

```bash
# List all KAs and their states
uv run python scripts/ka/list_ka_states.py

# Delete KAs by display name
uv run python scripts/ka/delete_kas_by_display_name.py "agent-forge-<slug>"

# Upload PDFs to the volume before creating a KA
uv run python scripts/ka/upload_pdfs.py

# Re-run creation skipping already-existing KAs
uv run python scripts/ka/create_kas_from_yml.py --skip-existing

# Create without waiting for ACTIVE
uv run python scripts/ka/create_kas_from_yml.py config/ka/ka_<slug>.yml --no-wait
```
