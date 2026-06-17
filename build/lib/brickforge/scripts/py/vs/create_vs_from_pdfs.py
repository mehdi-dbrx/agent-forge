#!/usr/bin/env python3
"""Provision a Databricks Vector Search index from PDFs in data/pdf/.

Steps:
  1. Extract text from PDFs and chunk it
  2. Write chunks to a Delta table in Unity Catalog
  3. Create a Vector Search endpoint (if it doesn't exist)
  4. Create a Delta Sync index with managed embeddings
  5. Wait for the index to become ONLINE
  6. Write PROJECT_VS_INDEX to .env.local

Usage:
  uv run python scripts/py/vs/create_vs_from_pdfs.py
  uv run python scripts/py/vs/create_vs_from_pdfs.py --dry-run
  uv run python scripts/py/vs/create_vs_from_pdfs.py --config conf/vector-search/vs_config.yml
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import yaml
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState
from databricks.sdk.service.vectorsearch import EndpointType
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

load_dotenv(os.environ.get("ENV_FILE", str(ROOT / ".env.local")), override=True)

# ANSI
R, G, Y, B, C, W = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[36m", "\033[0m"
DIM, BOLD = "\033[2m", "\033[1m"
OK = f"{G}[+]{W}"
FAIL = f"{R}[-]{W}"
WARN = f"{Y}[!]{W}"
INFO = f"{C}[*]{W}"

ENV_FILE = ROOT / ".env.local"

# Defaults (overridden by YAML config)
DEFAULT_ENDPOINT = "agent-forge-vs"
DEFAULT_EMBEDDING_MODEL = "databricks-bge-large-en"
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
TABLE_SUFFIX = "pdf_chunks"
INDEX_SUFFIX = "pdf_chunks_index"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _vs_client():
    """Create a VectorSearchClient using the default WorkspaceClient's auth.

    On lab workspaces the VS permissions API is broken, so the client must
    authenticate as the same principal that owns the VS endpoint (typically
    the service principal from DATABRICKS_CONFIG_PROFILE).
    """
    from databricks.vector_search.client import VectorSearchClient
    w = WorkspaceClient()
    host = w.config.host.rstrip("/")
    token = w.config.authenticate().get("Authorization", "").replace("Bearer ", "")
    if host and token:
        return VectorSearchClient(workspace_url=host, personal_access_token=token, disable_notice=True)
    return VectorSearchClient(disable_notice=True)


def _schema_spec() -> tuple[str, str]:
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if not spec or "." not in spec:
        print(f"{FAIL} PROJECT_UNITY_CATALOG_SCHEMA not set")
        sys.exit(1)
    return spec.split(".", 1)


def _load_config(config_path: Path | None) -> dict:
    if config_path and config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    # Try default
    default = next((ROOT / "conf" / "vector-search").glob("vs_*.yml"), None)
    if default.exists():
        with open(default) as f:
            return yaml.safe_load(f) or {}
    return {}


def _write_env_entry(key: str, value: str) -> None:
    """Append key=value to .env.local, commenting out any existing active entry."""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.startswith(f"{key}="):
            new_lines.append(f"#{line}")
        else:
            new_lines.append(line)
    new_lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(new_lines) + "\n")


# ── PDF Chunking ─────────────────────────────────────────────────────────────


def extract_and_chunk_pdfs(
    pdf_dir: Path, chunk_size: int, chunk_overlap: int
) -> list[dict]:
    """Extract text from PDFs and split into overlapping chunks."""
    try:
        import pypdf
    except ImportError:
        print(f"{FAIL} pypdf not installed. Run: uv add pypdf")
        sys.exit(1)

    chunks = []
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        print(f"{WARN} No PDFs found in {pdf_dir}")
        return []

    for pdf_path in pdfs:
        print(f"  {INFO} Reading {pdf_path.name}...")
        reader = pypdf.PdfReader(str(pdf_path))
        full_text = ""
        for page in reader.pages:
            text = page.extract_text() or ""
            full_text += text + "\n"

        # Fixed-size chunking with overlap
        text = re.sub(r"\s+", " ", full_text).strip()
        start = 0
        chunk_idx = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end]
            if chunk_text.strip():
                chunk_id = hashlib.md5(
                    f"{pdf_path.name}:{chunk_idx}".encode()
                ).hexdigest()[:12]
                chunks.append(
                    {
                        "id": chunk_id,
                        "content": chunk_text,
                        "source": pdf_path.name,
                        "chunk_index": chunk_idx,
                    }
                )
                chunk_idx += 1
            start = end - chunk_overlap

    print(f"  {OK} Extracted {len(chunks)} chunks from {len(pdfs)} PDF(s)")
    return chunks


# ── Delta Table ──────────────────────────────────────────────────────────────


def create_chunks_table(
    w: WorkspaceClient, catalog: str, schema: str, chunks: list[dict], wh_id: str
) -> str:
    """Create or replace Delta table with PDF chunks. Returns full table name."""
    table_name = f"{catalog}.{schema}.{TABLE_SUFFIX}"
    print(f"\n{BOLD}Creating Delta table: {table_name}{W}")

    # Create table
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id STRING NOT NULL,
        content STRING,
        source STRING,
        chunk_index INT
    )
    USING DELTA
    TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
    """
    r = w.statement_execution.execute_statement(
        statement=create_sql, warehouse_id=wh_id, wait_timeout="30s"
    )
    if r.status.state != StatementState.SUCCEEDED:
        print(f"  {FAIL} Table creation failed: {r.status}")
        return ""
    print(f"  {OK} Table created/verified")

    # Truncate existing data
    w.statement_execution.execute_statement(
        statement=f"TRUNCATE TABLE {table_name}",
        warehouse_id=wh_id,
        wait_timeout="30s",
    )

    # Insert chunks in batches (async + poll — large batches can exceed 50s limit)
    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        values = []
        for c in batch:
            content = c["content"].replace("'", "''").replace("\\", "\\\\")
            source = c["source"].replace("'", "''")
            values.append(f"('{c['id']}', '{content}', '{source}', {c['chunk_index']})")
        insert_sql = f"INSERT INTO {table_name} VALUES {', '.join(values)}"
        r = w.statement_execution.execute_statement(
            statement=insert_sql, warehouse_id=wh_id, wait_timeout="0s"
        )
        stmt_id = r.statement_id
        # Poll until done
        for _ in range(60):
            time.sleep(5)
            r = w.statement_execution.get_statement(stmt_id)
            if r.status.state in (StatementState.SUCCEEDED, StatementState.FAILED, StatementState.CANCELED):
                break
        if r.status.state != StatementState.SUCCEEDED:
            print(f"  {FAIL} Insert batch {i // batch_size} failed: {r.status}")
            return ""

    print(f"  {OK} Inserted {len(chunks)} chunks")
    return table_name


# ── Vector Search Endpoint ───────────────────────────────────────────────────


def ensure_vs_endpoint(endpoint_name: str) -> bool:
    """Create VS endpoint if it doesn't exist. Returns True on success."""
    w = WorkspaceClient()
    print(f"\n{BOLD}Vector Search endpoint: {endpoint_name}{W}")
    try:
        ep = w.vector_search_endpoints.get_endpoint(endpoint_name)
        status = getattr(ep, "endpoint_status", None)
        state = ""
        if status:
            state = getattr(status, "state", "")
            if hasattr(state, "value"):
                state = state.value
        print(f"  {OK} Exists (state: {state or 'unknown'})")
        return True
    except Exception:
        pass

    print(f"  {INFO} Creating endpoint {endpoint_name}...")
    try:
        w.vector_search_endpoints.create_endpoint(
            name=endpoint_name,
            endpoint_type=EndpointType.STANDARD,
        )
        print(f"  {OK} Endpoint creation started")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"  {OK} Endpoint already exists")
            return True
        print(f"  {FAIL} Failed to create endpoint: {e}")
        return False

    # Wait for endpoint to be ready
    print(f"  {INFO} Waiting for endpoint to become ONLINE...")
    for i in range(60):
        time.sleep(10)
        try:
            ep = w.vector_search_endpoints.get_endpoint(endpoint_name)
            status = getattr(ep, "endpoint_status", None)
            state = ""
            if status:
                state = getattr(status, "state", "")
                if hasattr(state, "value"):
                    state = state.value
            if state == "ONLINE":
                print(f"\n  {OK} Endpoint ONLINE")
                return True
            print(f"\r  {DIM}[{i * 10}s] state={state}{W}    ", end="", flush=True)
        except Exception:
            pass
    print(f"\n  {WARN} Endpoint not ONLINE after 600s — may still be provisioning")
    return True


# ── Vector Search Index ──────────────────────────────────────────────────────


def create_vs_index(
    endpoint_name: str,
    table_name: str,
    catalog: str,
    schema: str,
    embedding_model: str,
) -> str | None:
    """Create a Delta Sync VS index with managed embeddings. Returns index name."""
    index_name = f"{catalog}.{schema}.{INDEX_SUFFIX}"
    print(f"\n{BOLD}Vector Search index: {index_name}{W}")

    # Check if index already exists
    try:
        vs_client = _vs_client()
        idx = vs_client.get_index(index_name=index_name, endpoint_name=endpoint_name)
        desc = idx.describe()
        status = desc.get("status", {}).get("ready", False)
        print(f"  {OK} Index exists (ready={status})")
        if not status:
            print(f"  {INFO} Syncing index...")
            idx.sync()
        return index_name
    except Exception:
        pass

    print(f"  {INFO} Creating Delta Sync index...")
    try:
        vs_client = _vs_client()
        vs_client.create_delta_sync_index(
            endpoint_name=endpoint_name,
            source_table_name=table_name,
            index_name=index_name,
            pipeline_type="TRIGGERED",
            primary_key="id",
            embedding_source_column="content",
            embedding_model_endpoint_name=embedding_model,
        )
        print(f"  {OK} Index creation started")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"  {OK} Index already exists")
            return index_name
        print(f"  {FAIL} Failed to create index: {e}")
        return None

    # Wait for index to be ready
    print(f"  {INFO} Waiting for index to become ONLINE (this may take a few minutes)...")
    for i in range(120):
        time.sleep(10)
        try:
            vs_client = _vs_client()
            idx = vs_client.get_index(index_name=index_name, endpoint_name=endpoint_name)
            desc = idx.describe()
            status = desc.get("status", {})
            ready = status.get("ready", False)
            state = status.get("indexed_row_count", "?")
            if ready:
                print(f"\n  {OK} Index ONLINE ({state} rows indexed)")
                return index_name
            msg = status.get("message", "")
            print(
                f"\r  {DIM}[{i * 10}s] ready={ready} rows={state} {msg[:60]}{W}    ",
                end="",
                flush=True,
            )
        except Exception:
            pass
    print(f"\n  {WARN} Index not ready after 1200s — check workspace UI")
    return index_name


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Create VS index from PDFs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    catalog, schema = _schema_spec()
    config = _load_config(args.config)
    vs_config = config.get("vector_search", {})
    endpoint_name = vs_config.get("endpoint_name", DEFAULT_ENDPOINT)
    embedding_model = vs_config.get("embedding_model", DEFAULT_EMBEDDING_MODEL)
    chunk_size = vs_config.get("chunk_size", DEFAULT_CHUNK_SIZE)
    chunk_overlap = vs_config.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP)

    wh_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
    if not wh_id:
        print(f"{FAIL} DATABRICKS_WAREHOUSE_ID not set")
        return 1

    pdf_dir = ROOT / "data" / "pdf"
    print(f"\n{BOLD}Vector Search Provisioning{W}")
    print(f"  Catalog/Schema: {catalog}.{schema}")
    print(f"  Endpoint:       {endpoint_name}")
    print(f"  Embedding:      {embedding_model}")
    print(f"  Chunk size:     {chunk_size} / overlap: {chunk_overlap}")
    print(f"  PDF dir:        {pdf_dir}")

    # 1. Extract and chunk PDFs
    chunks = extract_and_chunk_pdfs(pdf_dir, chunk_size, chunk_overlap)
    if not chunks:
        return 1

    if args.dry_run:
        print(f"\n{WARN} Dry run — would create table + index with {len(chunks)} chunks")
        return 0

    w = WorkspaceClient()

    # 2. Create Delta table with chunks
    table_name = create_chunks_table(w, catalog, schema, chunks, wh_id)
    if not table_name:
        return 1

    # 3. Ensure VS endpoint exists
    if not ensure_vs_endpoint(endpoint_name):
        return 1

    # 4. Create Delta Sync index
    index_name = create_vs_index(
        endpoint_name, table_name, catalog, schema, embedding_model
    )
    if not index_name:
        return 1

    # 5. Write to .env.local
    _write_env_entry("PROJECT_VS_INDEX", index_name)
    _write_env_entry("PROJECT_VS_ENDPOINT", endpoint_name)
    print(f"\n  {OK} PROJECT_VS_INDEX={index_name}")
    print(f"  {OK} PROJECT_VS_ENDPOINT={endpoint_name}")
    print(f"\n{G}Vector Search provisioning complete.{W}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
