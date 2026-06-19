"""MLflow eval runner for agent-forge passenger-rights KA.

Run 1 (baseline) and Run 2 (after guideline) comparison.
Uses external FE workspace endpoint as LLM judge (no personal tokens).

All configuration from .env.local — no hardcoded workspace paths or profile names.

Usage:
  uv run python eval/run_eval.py           # run 1 (baseline)
  uv run python eval/run_eval.py --run2    # run 2 (after adding guideline to KA)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(os.environ.get("ENV_FILE", str(ROOT / ".env.local")), override=True)

import os
os.environ["MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION"] = "True"

import mlflow

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))

from eval_dataset import eval_dataset
from predict import predict
from scorer import cites_regulation_precisely

# ── MLflow setup ─────────────────────────────────────────────────────────────
# MLFLOW_TRACKING_URI and MLFLOW_EXPERIMENT_ID are loaded from .env.local
_EXPERIMENT_ID = os.environ.get("MLFLOW_EXPERIMENT_ID", "").strip()
if not _EXPERIMENT_ID:
    raise EnvironmentError("MLFLOW_EXPERIMENT_ID must be set in .env.local")

mlflow.set_experiment(experiment_id=_EXPERIMENT_ID)


def _short(q: str, max_len: int = 40) -> str:
    return q[:max_len] + "…" if len(q) > max_len else q


def _print_results(results, run_label: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {run_label}")
    print(f"{'═' * 60}")
    df = results.result_df
    score_col = "cites_regulation_precisely/value"
    if score_col in df.columns:
        questions = [d["inputs"]["query"] for d in eval_dataset]
        scores = df[score_col].tolist()
        for q, s in zip(questions, scores):
            mark = "✓" if s and s >= 1.0 else "✗"
            print(f"  {mark} [{s}]  {_short(q)}")
        avg = sum(s or 0 for s in scores) / len(scores)
        print(f"\n  avg cites_regulation_precisely: {avg:.2f}")
    else:
        print("  (score column not found — check MLflow UI)")
        print("  columns:", list(df.columns))


def run1() -> None:
    """Baseline — loose instructions, no citation guidance."""
    print("\n▶ RUN 1 — loose instructions (no citation guidance)")
    with mlflow.start_run(run_name="run1_loose"):
        results = mlflow.genai.evaluate(
            data=eval_dataset,
            predict_fn=predict,
            scorers=[cites_regulation_precisely],
        )
    _print_results(results, "RUN 1 — loose")

    score_col = "cites_regulation_precisely/value"
    df = results.result_df
    if score_col in df.columns:
        questions = [d["inputs"]["query"] for d in eval_dataset]
        scores = df[score_col].tolist()
        failed = [(q, s) for q, s in zip(questions, scores) if not s or s < 1.0]
        if failed:
            print(f"\n  {len(failed)} question(s) scored 0 — review responses in MLflow UI")

    print("\n  Run 1 complete. Review scores above, then add the guideline and re-run with --run2")


def run2() -> None:
    """After adding citation guideline to KA."""
    print("\n▶ RUN 2 — strict instructions (explicit citation requirements)")
    with mlflow.start_run(run_name="run2_strict"):
        results = mlflow.genai.evaluate(
            data=eval_dataset,
            predict_fn=predict,
            scorers=[cites_regulation_precisely],
        )
    _print_results(results, "RUN 2 — with guideline")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--run2" in args:
        run2()
    else:
        run1()
