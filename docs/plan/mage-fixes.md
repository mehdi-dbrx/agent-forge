# Mage Fixes - Outstanding Issues

> Status: ACTIVE
> Updated: 2026-06-17

## Issues to fix (in priority order)

### 1. Data generation KeyError: 'columns' / 'row_count'
**Symptom:** Mage calls `exec_generate("/api/gen/data")` which hits the old subprocess pipeline. The pipeline expects table objects with `columns` and `row_count` keys. Mage passes spec entities with `fields` and no `row_count`. KeyError every time.

**Root cause:** Two different data shapes. Spec uses `fields`, gen pipeline uses `columns`. The old subprocess endpoint was never designed for Mage's format.

**Fix:** Build `generate_data` as a direct Mage tool (Phase 3 of mage-direct-tools plan). Accepts spec-shaped table schema, defaults row_count to 15, calls `call_llm_json` inline. No subprocess, no format mismatch.

**Files:** `brickforge/lib/mage_tools.py` - add generate_data tool

---

### 2. Self-critique adds 30-40s of thinking dots after spec is shown
**Symptom:** User sees the spec summary, then 30-40s of thinking dots before they can type. The self-critique loop runs after `present_spec`.

**Root cause:** `mage_agent.py` runs `_self_critique()` after detecting the `present_spec` tool call. This was designed for the old heuristic detection path. With `present_spec` as a tool, discovery already happened properly - the critique is redundant.

**Fix:** Remove the self-critique block after `present_spec` detection in the agent loop. The LLM's own reasoning during discovery + the `present_spec` JSON validation is sufficient.

**Files:** `brickforge/lib/mage_agent.py` - remove self-critique after present_spec

---

### 3. Deployed agent has wrong system prompt (stale domain)
**Symptom:** Spec is pizza delivery. Tables are pizza. But the deployed agent says "I'm ARIA, the booking assistant for Orbital Haven" - a space hotel prompt.

**Root cause:** Prompt generated via `exec_generate("/api/gen/prompt-generate")` - old subprocess pipeline. The subprocess reads domain from gen directory or config, not from Mage's confirmed spec. Previous project was a hotel. Gen directory had stale hotel context. Prompt LLM generated hotel prompt from stale data.

**Fix:** Build `generate_prompt` as a direct Mage tool. Passes `spec.domain` + `spec.entities` + `spec.actions` directly to the LLM call. No subprocess reading stale files. Same root fix as issues #1 and #2 - direct tools eliminate the stale context problem.

**Files:** `brickforge/lib/mage_tools.py` - add generate_prompt tool

---

### 4. Duplicate spec summary message
**Symptom:** The spec summary shows twice in the chat - once from `present_spec` tool (via sse_queue), once from the LLM parroting it despite "do NOT repeat" instruction.

**Root cause:** The tool sends the summary directly to the user via sse_queue, then returns a message to the LLM. The LLM ignores "do NOT repeat" and rephrases the spec.

**Fix:** After `present_spec` tool call is detected in the agent loop, suppress the LLM's next text response if it looks like a spec repeat. Or: make the tool return an empty string so the LLM has nothing to parrot.

**Files:** `brickforge/lib/mage_tools.py` - present_spec return value, `brickforge/lib/mage_agent.py` - suppress post-spec LLM message

---

### 4. Project name too long (entire input slugified)
**Symptom:** User types "Intergalactic Pizza delivery assistant sci fi keep it simple" -> project name becomes `intergalactic-pizza-delivery-assistant-sci-fi-keep-it-simple`

**Root cause:** LLM suggests names via choice cards (fixed). But if user types custom name, the full input gets slugified.

**Status:** Partially fixed - LLM suggests 3 short names. User can still type a long custom name. Could cap at 3 words for custom input.

---

### 5. save-schema param mismatch (FIXED)
**Symptom:** save-schema failed 4 times because system prompt said `params={"schema": "catalog.schema"}` but endpoint expects `{"catalog": "x", "schema": "y"}`.

**Fix applied:** System prompt corrected for save-schema, save-model-endpoint, save-genie. All save actions audited against setup.py handlers.

---

### 6. Workspace lost on project creation (FIXED)
**Symptom:** Mage creates new project -> fresh DEFAULT_CONFIG -> workspace connection gone.

**Fix applied:** `routes/projects.py` now carries over workspace.host, workspace.token, workspace.warehouse_id, model.endpoint from active config to new project.

---

### 7. Prerequisites not checked before chat (FIXED)
**Symptom:** User types in Mage, workspace not connected, nothing happens.

**Fix applied:** Hero screen checks prereqs on load + window focus. Shows green/red dots for workspace + model. Input disabled until both OK. Links to Setup tab.

---

### 8. "y" not in confirmation keywords (FIXED)
**Symptom:** User types "y" to confirm spec, tools don't upgrade.

**Fix applied:** Added "y" to confirms list in mage_agent.py.

---

### 9. Keyword heuristic for spec detection (FIXED)
**Symptom:** Spec detection used 7 hotel-domain keywords. Failed for pizza, healthcare, fleet.

**Fix applied:** Replaced with `present_spec` tool. LLM calls it with structured JSON. No heuristics.
