---
name: dbx-eval
description: Run MLflow evaluation of the agent-forge Knowledge Assistant. Triggered when user says /dbx-eval, "run eval", "run the eval", "evaluate the KA", "run evaluation", or similar.
---

# DBX Eval

Runs MLflow GenAI evaluation of the passenger-rights Knowledge Assistant using a custom `cites_regulation_precisely` scorer (LLM judge via Claude Sonnet). Supports a two-run workflow: baseline → add citation guideline → compare.

## Eval Files

| File | Purpose |
|------|---------|
| `eval/run_eval.py` | Main orchestrator — run1 / run2 |
| `eval/predict.py` | Calls `PROJECT_KA_PASSENGERS` endpoint |
| `eval/scorer.py` | Claude judge via `AGENT_MODEL_ENDPOINT` |
| `eval/eval_dataset.py` | 13 EC 261/2004 test questions |
| `eval/data/ec261_eval_dataset.jsonl` | JSONL source of truth |
| `scripts/py/create_eval_dataset.py` | Push dataset to MLflow UI |

## Required Env Vars (`.env.local`)

- `DATABRICKS_HOST` — workspace URL
- `DATABRICKS_TOKEN` — PAT for KA endpoint auth
- `PROJECT_KA_PASSENGERS` — KA endpoint name (e.g. `ka-ff5f8b5a-endpoint`)
- `AGENT_MODEL_ENDPOINT` — Claude Sonnet judge endpoint URL
- `AGENT_MODEL_TOKEN` — Judge endpoint auth token
- `MLFLOW_EXPERIMENT_ID` — MLflow experiment to log runs into
- `MLFLOW_TRACKING_URI` — should be `databricks`

## Workflow

### Phase 1: Pre-flight checks
1. Read `.env.local` and verify all required env vars above are present and non-empty
2. If any are missing, tell the user which ones and stop
3. Optionally smoke-test the KA endpoint:
   ```bash
   uv run python eval/predict.py
   ```

### Phase 2: (Optional) Push dataset to MLflow
If the user wants to view the dataset in the MLflow UI:
```bash
uv run python scripts/py/create_eval_dataset.py
```

### Phase 3: Run 1 — Baseline
```bash
uv run python eval/run_eval.py
```
- Runs all 13 questions through the KA
- Scores each with `cites_regulation_precisely` (1.0 = PASS, 0.0 = FAIL)
- Prints per-question results with ✓/✗ and average score
- Logs run to MLflow under `run1_loose`

Interpret results:
- Score 1.0 = response cited a specific article, €amount, or named legal standard
- Score 0.0 = response was vague — no precise regulatory reference
- Average < 0.7 = guideline addition recommended

### Phase 4: (Optional) Add citation guideline to KA
If run1 scores are low, add a citation guideline to the KA instructions via Databricks SDK:

```python
from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv
import os

load_dotenv(".env.local", override=True)
w = WorkspaceClient()

ka_id = "<knowledge_assistant_id>"  # get from list_ka_states.py
w.knowledge_assistants.update_knowledge_assistant(
    knowledge_assistant_id=ka_id,
    # add explicit citation instructions to the KA's system prompt
)
```

To find the KA ID:
```bash
uv run python scripts/py/ka/list_ka_states.py
```

### Phase 5: Run 2 — After guideline
```bash
uv run python eval/run_eval.py --run2
```
- Same 13 questions, same scorer
- Logs under `run2_strict`
- Compare average scores: run1 vs run2

### Phase 6: View in MLflow UI
Results are logged to the experiment at `MLFLOW_EXPERIMENT_ID`.
Navigate: Databricks workspace → Experiments → agent-forge → compare run1_loose vs run2_strict.

## Scorer Details

`cites_regulation_precisely` judges each KA response for at least ONE of:
- Specific article number (e.g. "Article 7", "Article 9(1)(a)")
- Exact euro amount (e.g. "€600", "€400", "€250")
- Named legal standard (e.g. "Sturgeon judgment", "Montreal Convention")

Returns 1.0 (PASS) or 0.0 (FAIL). Judge output printed as:
```
[scorer] score=1.0 | Response cites Article 7 with €600 compensation threshold.
```

## Examples

### Example: Full eval run
User says: "/dbx-eval"
Result: Check env vars → run baseline → print scores → offer to add guideline and run2

### Example: Just run2
User says: "run eval run 2"
Result: Skip to Phase 5, run `eval/run_eval.py --run2`

### Example: Check setup only
User says: "check eval setup"
Result: Verify env vars and smoke-test predict endpoint only
