#!/usr/bin/env python3
"""Verify a Databricks Vector Search index: check status and run a test query.

Usage:
  uv run python scripts/py/vs/verify_vs_index.py
  uv run python scripts/py/vs/verify_vs_index.py --query "my test query"
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(os.environ.get("ENV_FILE", str(ROOT / ".env.local")), override=True)

# ANSI
R, G, Y, B, C, W = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[36m", "\033[0m"
DIM, BOLD = "\033[2m", "\033[1m"
OK = f"{G}[+]{W}"
FAIL = f"{R}[-]{W}"
WARN = f"{Y}[!]{W}"
INFO = f"{C}[*]{W}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify VS index")
    parser.add_argument("--query", default="test query", help="Test query")
    parser.add_argument("--num-results", type=int, default=3)
    args = parser.parse_args()

    index_name = os.environ.get("PROJECT_VS_INDEX", "").strip()
    endpoint_name = os.environ.get("PROJECT_VS_ENDPOINT", "").strip()

    if not index_name:
        print(f"{FAIL} PROJECT_VS_INDEX not set in .env.local")
        return 1
    if not endpoint_name:
        print(f"{FAIL} PROJECT_VS_ENDPOINT not set in .env.local")
        return 1

    print(f"\n{BOLD}Vector Search Verification{W}")
    print(f"  Index:    {C}{index_name}{W}")
    print(f"  Endpoint: {C}{endpoint_name}{W}")
    print(f"  Query:    {C}{args.query}{W}")

    # 1. Check endpoint
    print(f"\n{BOLD}1. Endpoint status{W}")
    w = WorkspaceClient()
    try:
        ep = w.vector_search_endpoints.get_endpoint(endpoint_name)
        status = getattr(ep, "endpoint_status", None)
        state = ""
        if status:
            state = getattr(status, "state", "")
            if hasattr(state, "value"):
                state = state.value
        print(f"  {OK} Endpoint exists (state: {state or 'unknown'})")
        if state != "ONLINE":
            print(f"  {WARN} Endpoint not ONLINE — queries may fail")
    except Exception as e:
        print(f"  {FAIL} Endpoint check failed: {e}")
        return 1

    # 2. Check index
    print(f"\n{BOLD}2. Index status{W}")
    try:
        from databricks.vector_search.client import VectorSearchClient
        # Use SP auth (WorkspaceClient default) -- lab workspaces have broken
        # VS permissions, so the SP that created the endpoint must query it.
        ws_host = w.config.host.rstrip("/")
        ws_token = w.config.authenticate().get("Authorization", "").replace("Bearer ", "")
        if ws_host and ws_token:
            vs_client = VectorSearchClient(workspace_url=ws_host, personal_access_token=ws_token, disable_notice=True)
        else:
            vs_client = VectorSearchClient(disable_notice=True)
        idx = vs_client.get_index(index_name=index_name, endpoint_name=endpoint_name)
        desc = idx.describe()

        status_info = desc.get("status", {})
        ready = status_info.get("ready", False)
        row_count = status_info.get("indexed_row_count", "?")
        message = status_info.get("message", "")

        print(f"  {OK if ready else WARN} ready={ready}, rows={row_count}")
        if message:
            print(f"  {DIM}{message[:120]}{W}")

        # Print index config
        delta_sync = desc.get("delta_sync_index_spec", {})
        embed_cols = delta_sync.get("embedding_source_columns", [])
        embed_model = ""
        if embed_cols:
            embed_model = embed_cols[0].get("embedding_model_endpoint_name", "")
        pipeline = delta_sync.get("pipeline_type", "")
        source = delta_sync.get("source_table", "")
        print(f"  Source:    {C}{source}{W}")
        print(f"  Embedding: {C}{embed_model}{W}")
        print(f"  Pipeline:  {C}{pipeline}{W}")

        if not ready:
            print(f"\n  {WARN} Index not ready — cannot run query yet")
            return 1

    except Exception as e:
        print(f"  {FAIL} Index check failed: {e}")
        return 1

    # 3. Query
    print(f"\n{BOLD}3. Similarity search{W}")
    try:
        results = idx.similarity_search(
            columns=["content", "source"],
            query_text=args.query,
            num_results=args.num_results,
        )
        rows = results.get("result", {}).get("data_array", [])
        if not rows:
            print(f"  {WARN} No results returned")
            return 1

        print(f"  {OK} {len(rows)} result(s):\n")
        for i, row in enumerate(rows, 1):
            content = row[0] if len(row) > 0 else ""
            source = row[1] if len(row) > 1 else ""
            score = row[2] if len(row) > 2 else ""
            preview = (content[:200] + "...") if len(content) > 200 else content
            print(f"  {BOLD}#{i}{W} [score={score}] {Y}source={source}{W}")
            print(f"     {DIM}{preview}{W}\n")

        print(f"{G}Verification passed.{W}")
        return 0

    except Exception as e:
        print(f"  {FAIL} Query failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
