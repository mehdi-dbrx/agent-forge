# Plan: Separate Code from Data (issue #45)

> Status: DEFERRED — intentionally not scheduled. Documented for later.
> Slug: separate-code-from-data · Relates to GitHub issue #45
> Author context: written on branch `forge-SDK-refactor`, target base = `main`.
>
> **Decision (2026-07-20):** Deferred. Risk of breaking existing critical code is
> too high to justify the payoff right now. The move touches ~40 sites across two
> import spellings, and the highest-risk piece (`data/py/sql_utils.py`) is on the
> deployed agent's per-request path where breakage is silent until a real deploy.
> The gain is organizational legibility only — not worth risking a working
> pipeline at this time. Revisit if/when the `data/` area is being reworked
> anyway (e.g. alongside the SDK refactor's deploy-bundle changes), so the churn
> is shared rather than incurred standalone.

## Goal

Get executable Python **code** out of `brickforge/data/`, which currently mixes
code and data in the same tree. `data/` should mean *data only*.

## Tree: before → after

**Before**
```
brickforge/data/
├── demo/     # DATA — seed CSV/SQL/func/proc (stays)
├── pdf/      # DATA — example PDF (stays)
├── gen/      # CODE — LLM generators (schema, data, prompt, routine) + llm_client
├── init/     # CODE — provisioners (create_all_assets, catalog, functions, procedures, genie, lakebase, mlflow)
└── py/       # CODE — runtime utils (run_sql, csv_to_delta, sql_utils)
```

**After**
```
brickforge/
├── data/
│   ├── demo/
│   └── pdf/
├── generators/    # ← was data/gen
└── provisioners/  # ← was data/init + data/py
```

Optional finer sub-structure inside `generators/` (from the original branch's
intent): `tables/`, `routines/`, `prompts/`, plus shared `llm_client.py`.

## The idea (intent worth keeping)

1. **Code ≠ data.** A directory should mean one thing. `data/` = artifacts;
   code that acts on data lives elsewhere. This is the core of #45 and is still
   unaddressed on `main`.
2. **`generate` vs `provision` vocabulary.** Two verbs / two risk profiles:
   - *Generators* — author artifacts locally (safe, no workspace mutation).
   - *Provisioners* — push to Databricks (side-effectful, mutate the workspace).
   This boundary maps to the user journey (author → deploy) and is currently invisible.
3. **Group by domain, not file type** (tables/routines/prompts).

## Why this must be REDONE FRESH (not merged)

There is a prior attempt on branch `fix/issue-45-refactor-data-code-separation`
(4 commits, June 4 2026) and a squash-merge commit `e89fbeb` (PR #47). **Do not
merge or cherry-pick either.** Verified findings:

- The `fix/issue-45` branch is 6 weeks stale, 46 commits behind `main`, and its
  file *contents* are obsolete — 10 of its files still carry dead `.env.local` /
  `load_dotenv` code that `main` has since purged (config.json migration).
- It also bundles issue #49 (project auto-save / management) commits, which
  `main` already implemented differently (the `_project_file` mirror is already
  in `config_provider.py`). Replaying = regression.
- `e89fbeb` is a squash-merge onto a **May-13 base** (`1acb510`), parented 3 weeks
  stale. Merging it would revert ~140K lines. No branch contains it. It is dead.

**Conclusion:** use the old branch only as a *blueprint for where files go*.
Redo the move against today's `main`.

## Collision check (verified)

- **SDK refactor** (`docs/plan/sdk-refactor-*.md`) does **not** collide. It adds
  pluggable agent runtimes (LangGraph / OpenAI Agents SDK / Claude Agent SDK) in
  `brickforge/agent/`. Its only `data/` touch is *reading* `data/py/sql_utils.py`.
  All three docs are PLANNING/SPIKE with zero commits. Orthogonal.
- Other in-flight streams (CardMaker, Mage, table-schemas-in-config,
  sql-template-engine) touch `data/gen` *contents* but not its structure — they
  affect *what* to move, not *whether* the move conflicts.

## Critical constraint: TWO import spellings + name == path

`data` is both a directory segment AND a top-level import package name. Two
runtimes resolve imports differently and BOTH must keep working:

- **Setup App** (local): `from brickforge.data.gen.X import ...`
  (e.g. `lib/mage_tools.py:201,312,354`).
- **Deployed agent** (Databricks App): bundle is unzipped flat with
  `PYTHONPATH=$(pwd)`, so imports are top-level: `from data.py.sql_utils import ...`
  (`tools/tool_factory.py:20`, stash tool templates).

A rename therefore breaks string subprocess paths, bare imports, and qualified
imports simultaneously.

## Risk map (three phases)

| Code | Used at | Risk |
|---|---|---|
| `data/gen/` (generators) | Setup App / Mage only — no deployed-runtime import | **Low** — breaks loudly at setup time |
| `data/init/` (provisioners) | Setup App provisioning only | **Low-med** — subprocess string paths + cross-script calls |
| `data/py/sql_utils.py` | **Deployed agent, every request** + stash templates | **High** — live serving path, both import spellings |

## Full reference inventory (what must change) — exclude `build/` (stale artifact)

### A. String subprocess paths / path builds
- `routes/gen.py` — `data/gen/*.py` at lines 285, 295, 306, 316, 333, 339, 377,
  387, 395, 401, and **409, 415, 421** (`test_generator.py` — 3 new sites the
  June branch never saw).
- `routes/setup.py` — `data/init/*` and `data/py/*` at ~1595, 1613, 1729, 1741,
  1747, 1753, 1763, 1773, 1797, 1798; inline scripts at 1944, 1969, 1983, 1997,
  2008, 2016-2017.
- `scripts/py/setup_dbx_env.py` — `data/init/*` at ~510, 1466, 1722, 1740, 1765,
  1778, 1838, 2278, 2366, 2399, 2424.
- `deploy/deploy_agent_app.py:37-39` — `AGENT_APP_DIRS` (`data/init`, `data/gen`,
  `data/py`). Must add `generators`, `provisioners`.

### B. Cross-script subprocess calls INSIDE the moved files
- `generate_tables.py:98,112` and `generate_routines.py:170,203` call
  `create_catalog_schema.py` / `run_sql.py` by string path.
- `create_all_assets.py:253,260,264,268,272,276`, `create_all_functions.py:137`,
  `create_all_procedures.py:123` call each other / `run_sql.py` by string path.

### C. Python imports
- Bare (deployed-flat + PYTHONPATH): `data/gen/*` internal imports
  (`from data.gen.X`), `data/py/run_sql.py:15-16`, **`tools/tool_factory.py:20`
  (`from data.py.sql_utils`)**, and **stash templates**
  `stash/airops/tools/{back_to_normal,create_border_incident,create_checkin_incident,update_checkin_agent}.py`.
- Qualified: `lib/mage_tools.py:201,312,354` (`from brickforge.data.gen.*`).

### D. Deploy overlay (DECISION, not a blind rename)
- `deploy/deploy_agent_app.py:249-250` overlays user project `PROJECT_DIR/gen`
  → bundle path `data/gen`. This bundle path is an **output-data sink**, not code.
  Decide: keep bundle output at `data/gen` (pure data, fine) OR rename. Do NOT
  conflate with the code move. Provisioner fallback reads `ROOT/data/gen/func`
  (`create_all_functions.py:112`, `create_all_procedures.py:103`) — same call.

### E. ROOT depth inside moved scripts
- Each entry script computes `ROOT = Path(__file__).resolve().parent.parent.parent`
  (3 levels → `brickforge/`). If nesting depth changes, adjust the `.parent` count.
  Scripts that `os.chdir(ROOT)`: all `data/init/*` and `data/py/*`; the `data/gen/*`
  orchestrators do NOT chdir (they rely on caller `cwd=PACKAGE_ROOT`).

## New files on `main` the old branch never handled (must include in the move)
- `data/gen/sql_template_engine.py` (274 lines) — imported by `mage_tools.py:201`
- `data/gen/test_generator.py` (309 lines) — 3 subprocess sites in `routes/gen.py`
- `data/gen/.gitignore`

## Explicit non-goals
- Do NOT bring issue #49 (project management) — already on `main`.
- Do NOT resurrect `.env.local` / `load_dotenv` — purged on `main`.
- Do NOT commit built frontend assets — rebuild via `vite build` after.

## Suggested execution order (when implemented)
1. Fresh branch off current `main`.
2. Move `data/gen/*` → `generators/` (optionally tables/routines/prompts subdirs)
   with `git mv`; fix internal `data.gen.*` imports + ROOT depth.
3. Move `data/init/*` + `data/py/*` → `provisioners/`; fix cross-script string
   paths + imports.
4. Update all external callers (section A/B/C above).
5. Update `AGENT_APP_DIRS` (add `generators`, `provisioners`; drop moved `data/*`).
6. Update stash templates (`stash/airops/tools/*`).
7. Decide + handle the bundle overlay path (section D).
8. Verify with a real provision + deploy run (not just imports/tests) — the
   string paths and bundle manifest fail silently, not at edit time.

## Verification note
The dangerous failure mode is **silent runtime breakage** (string paths, bundle
manifest, deployed-agent `data.py` import). A unit test / typecheck will NOT catch
these. Only a full local provision + a deploy to Databricks Apps proves it.

## Latent pre-existing issue found nearby (NOT part of #45)
`PROJECT_DIR` is not propagated to the deployed runtime, so `prompt_dir()` /
`gen_dir()` (`lib/project_paths.py:19-36`) would raise if reached at runtime,
while the deploy overlay writes prompts to `conf/prompt`. Tangential to #45,
logged here so it isn't lost.
