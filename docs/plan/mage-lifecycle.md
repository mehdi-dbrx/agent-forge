# Plan: Mage Lifecycle Fixes

> Status: REVIEWED — ready to implement
> Created: 2026-06-18

## Context

Deep-think + unravel revealed 6 gaps in the Mage project lifecycle. These aren't edge cases — they're the core paths: create, resume, switch, reset.

## Gaps

| # | Gap | Severity |
|---|-----|----------|
| 1 | Step 0 writes `mage.domain` to CURRENT project config before new project is created — corrupts existing project | **High** |
| 2 | No "New project" path in Mage UI — must go to Setup tab | **Medium** |
| 3 | Reset clears mage state on current project — destructive, no way to resume | **Medium** |
| 4 | Mage header doesn't show active project name | **Medium** |
| 5 | Mage doesn't detect project already built via Setup UI | **Low — defer** |
| 6 | No build state persistence for interrupted builds | **Low — defer** |

## Fixes

### Fix 1: Step 0 must NOT write to config (HIGH)

**Root cause:** `mage.py:88-90` — step 0 calls `config.set("mage.domain", ...)` and `config.set("mage.mode", ...)` on the CURRENTLY ACTIVE project. The new project doesn't exist until step 1.

**Fix:** Module-level local vars `_startup_domain` and `_startup_mode`. Step 0 stores there. Step 1 writes to config AFTER project creation switches the active config.

```python
# Module level (alongside _startup_step, _agent, _model)
_startup_domain: str = ""
_startup_mode: str | None = None
```

**Step 0 changes (mage.py:86-90):**
```python
# Before: config.set("mage.domain", user_message) — WRONG, writes to current project
# After: _startup_domain = user_message — local only
```

**Step 1 changes (mage.py:149-155), AFTER project creation + config switch:**
```python
config = _get_config()  # now points to new project
config.set("mage.domain", _startup_domain)
if _startup_mode:
    config.set("mage.mode", _startup_mode)
```

**Step 2 changes:** None needed. By step 2, the new project is active. `config.set("mage.mode", ...)` at line 164/166 writes to the correct config.

**Also remove:** mage carryover in `projects.py:144-148` — dead code after this fix.

**Files:** `brickforge/routes/mage.py`, `brickforge/routes/projects.py`

### Fix 2: Mage header shows project name (MEDIUM)

**Current:** Header shows "Mage" + mode badge + reset button. No project context.

**Fix:** Read `project` from `/api/mage/status` response. Show in header between "Mage" and mode badge.

**Files:** `visual/frontend/src/components/MageView.tsx`

### Fix 3: Reset = New Project (MEDIUM)

**Current:** Reset clears `mage.mode` + `mage.domain` on current config. Destructive — can't resume.

**Fix:** Reset does NOT touch config. Only clears in-memory state:
- `_agent = None`
- `_model = None`
- `_startup_step = 0`
- `_force_startup = True`

`_force_startup` flag: `_get_phase` checks it first. If true, returns `"startup"` regardless of config. Step 1 (project creation) sets it back to `False`.

This way:
- Current project's mage state stays intact
- Hero screen appears (new project flow)
- If user refreshes before creating a new project, `_force_startup` is true → hero still shows
- After new project is created, `_force_startup` clears → normal phase detection

**Reset endpoint (mage.py:293-305):**
```python
# Before: config.set("mage.mode", None) / config.set("mage.domain", "") — DESTRUCTIVE
# After: only clear in-memory state + set _force_startup
```

**Frontend `handleReset` (MageView.tsx:210-215):** No change needed — already clears messages and sets phase to startup.

**Files:** `brickforge/routes/mage.py`

### Fix 4: Status returns project name (MEDIUM)

**Current:** `/api/mage/status` returns phase, mode, domain, model, prereqs.

**Fix:** Add `project` field:
```python
from brickforge.routes.projects import _read_current
# In status response:
"project": _read_current(),
```

**Files:** `brickforge/routes/mage.py`

## Implementation Order

1. Fix 1 — local vars for step 0 + remove carryover (prevents config corruption)
2. Fix 3 — non-destructive reset with `_force_startup` flag
3. Fix 4 — project name in status response
4. Fix 2 — project name in Mage header

## Verification

- Create space-pizza via Mage → config has `mage.domain` + `mage.mode` on space-pizza project
- Verify: the PREVIOUS project's config does NOT have space-pizza's domain (Fix 1)
- Reset → hero screen appears, space-pizza's config unchanged (Fix 3)
- Create pet-hotel → new project, space-pizza intact
- Switch to space-pizza in Setup → Mage shows "Session resumed" (Fix 1 + 3)
- Header shows project name in both resumed and fresh states (Fix 2 + 4)
- Page refresh after reset (before new project) → hero still shows, not "Session resumed" (Fix 3 — `_force_startup`)
