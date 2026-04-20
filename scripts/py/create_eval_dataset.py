#!/usr/bin/env python3
"""Create and push the EC 261/2004 eval dataset to Databricks MLflow.

Reads eval/data/ec261_eval_dataset.jsonl (local source of truth),
creates an MLflow GenAI EvaluationDataset in the agent-forge MLflow experiment,
and uploads all 13 records.

All configuration from .env.local — no hardcoded workspace paths or profile names.

Usage:
  uv run python scripts/py/create_eval_dataset.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local", override=True)

import os
import mlflow
from mlflow.genai.datasets import create_dataset, get_dataset
import databricks.rag_eval.clients.managedevals.managed_evals_client as _mc

_EXPERIMENT_ID = os.environ.get("MLFLOW_EXPERIMENT_ID", "").strip()
if not _EXPERIMENT_ID:
    raise EnvironmentError("MLFLOW_EXPERIMENT_ID must be set in .env.local")

_UC_SCHEMA = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
DATASET_NAME = f"{_UC_SCHEMA}.ec261_passenger_rights_eval" if _UC_SCHEMA else "ec261_passenger_rights_eval"
JSONL_PATH   = ROOT / "eval" / "data" / "ec261_eval_dataset.jsonl"

G    = "\033[32m"
R    = "\033[31m"
Y    = "\033[33m"
W    = "\033[0m"
BOLD = "\033[1m"


def _load_records() -> list[dict]:
    records = []
    with open(JSONL_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main() -> int:
    # MLFLOW_TRACKING_URI is already in env from .env.local — mlflow picks it up automatically
    experiment = mlflow.set_experiment(experiment_id=_EXPERIMENT_ID)

    print(f"\n{BOLD}Creating MLflow eval dataset: {DATASET_NAME}{W}")
    print(f"  Experiment : {_EXPERIMENT_ID}")
    print(f"  Source     : {JSONL_PATH.relative_to(ROOT)}")

    records = _load_records()
    print(f"  Records    : {len(records)}")

    # Patch out UC sync — requires Java/Spark locally; records are still
    # written to the MLflow managed eval backend via REST.
    _mc.ManagedEvalsClient.sync_dataset_to_uc = lambda *a, **kw: None

    try:
        dataset = create_dataset(
            name=DATASET_NAME,
            experiment_id=experiment.experiment_id,
        )
        print(f"  Status     : created")
    except Exception as e:
        if "already exists" in str(e).lower() or "TABLE_ALREADY_EXISTS" in str(e):
            print(f"  Status     : already exists, fetching...")
            dataset = get_dataset(name=DATASET_NAME)
        else:
            raise
    dataset.merge_records(records)

    print(f"\n{G}[+] Dataset '{DATASET_NAME}' pushed to Databricks{W}")
    print(f"  Dataset ID : {dataset.dataset_id}")
    print(f"  View in UI : Experiments → agent-forge → Datasets\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
