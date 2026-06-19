#!/usr/bin/env python3
"""UC Volume operations for Knowledge Assistant documents.

Modes:
  --mode=list                    List files in the KA volume
  --mode=upload --file=<path>    Upload a single file to the KA volume
  --mode=delete --name=<name>    Delete a file from the KA volume

Volume path derived from PROJECT_UNITY_CATALOG_SCHEMA: catalog.schema -> /Volumes/catalog/schema/doc
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent

sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(os.environ.get("ENV_FILE", str(ROOT / ".env.local")), override=True)


def _volume_path() -> str | None:
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if not spec or "." not in spec:
        return None
    catalog, schema = spec.split(".", 1)
    return f"/Volumes/{catalog.strip()}/{schema.strip()}/doc"


def _client():
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.config import Config
    token = os.environ.get("DATABRICKS_TOKEN")
    if token:
        config = Config(host=os.environ.get("DATABRICKS_HOST"), token=token)
    else:
        config = Config()
    config.http_timeout_seconds = 30
    return WorkspaceClient(config=config)


def _ensure_volume(w, vol_path: str) -> str | None:
    """Create the UC volume if it doesn't exist. Returns error message or None on success."""
    # vol_path = /Volumes/catalog/schema/doc
    parts = vol_path.strip("/").split("/")  # ['Volumes', catalog, schema, vol_name]
    if len(parts) < 4:
        return f"Invalid volume path: {vol_path}"
    catalog, schema, vol_name = parts[1], parts[2], parts[3]

    # Check if volume already exists
    full_name = f"{catalog}.{schema}.{vol_name}"
    try:
        w.volumes.read(name=full_name)
        return None  # already exists
    except Exception:
        pass  # doesn't exist yet, create it

    try:
        from databricks.sdk.service.catalog import VolumeType
        w.volumes.create(catalog_name=catalog, schema_name=schema, name=vol_name, volume_type=VolumeType.MANAGED)
        return None
    except Exception as e:
        err = str(e)
        if "already exists" in err.lower() or "ALREADY_EXISTS" in err:
            return None
        return f"Failed to create volume {full_name}: {err[:200]}"


def mode_list() -> None:
    vol = _volume_path()
    if not vol:
        print(json.dumps({"files": [], "error": "PROJECT_UNITY_CATALOG_SCHEMA not set"}))
        return

    w = _client()

    # Auto-create volume if it doesn't exist
    vol_err = _ensure_volume(w, vol)
    if vol_err:
        print(json.dumps({"files": [], "volumePath": vol, "error": vol_err}))
        return

    files = []
    try:
        for fi in w.files.list_directory_contents(vol):
            if fi.is_directory:
                continue
            files.append({
                "name": fi.name,
                "path": fi.path or f"{vol}/{fi.name}",
                "size": fi.file_size or 0,
                "modified": str(fi.last_modified) if fi.last_modified else None,
            })
    except Exception as e:
        print(json.dumps({"files": [], "volumePath": vol, "error": str(e)[:200]}))
        return

    print(json.dumps({"files": files, "volumePath": vol}))


def mode_upload(file_path: str) -> None:
    vol = _volume_path()
    if not vol:
        print(json.dumps({"ok": False, "error": "PROJECT_UNITY_CATALOG_SCHEMA not set"}))
        return

    p = Path(file_path)
    if not p.exists():
        print(json.dumps({"ok": False, "error": f"File not found: {file_path}"}))
        return

    dest = f"{vol}/{p.name}"
    w = _client()

    # Ensure volume exists before uploading
    vol_err = _ensure_volume(w, vol)
    if vol_err:
        print(json.dumps({"ok": False, "name": p.name, "error": vol_err}))
        return

    try:
        with open(p, "rb") as f:
            w.files.upload(dest, f, overwrite=True)
        print(json.dumps({"ok": True, "name": p.name, "path": dest, "size": p.stat().st_size}))
    except Exception as e:
        print(json.dumps({"ok": False, "name": p.name, "error": str(e)[:200]}))
        return


def mode_delete(name: str) -> None:
    vol = _volume_path()
    if not vol:
        print(json.dumps({"ok": False, "error": "PROJECT_UNITY_CATALOG_SCHEMA not set"}))
        return

    path = f"{vol}/{name}"
    w = _client()
    try:
        w.files.delete(path)
        print(json.dumps({"ok": True, "deleted": name}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:200]}))
        return


def mode_upload_url(url: str) -> None:
    """Download a file from a URL and upload it to the KA volume."""
    import tempfile
    import time
    import urllib.request
    from urllib.parse import urlparse, unquote

    steps: list[str] = []

    vol = _volume_path()
    if not vol:
        print(json.dumps({"ok": False, "error": "PROJECT_UNITY_CATALOG_SCHEMA not set", "steps": []}))
        return

    # Filename: prefer UPLOAD_FILENAME env var, fall back to URL-derived
    ALLOWED_EXTS = {'.md', '.pdf', '.docx', '.txt', '.html', '.csv', '.json'}
    filename = os.environ.get("UPLOAD_FILENAME", "").strip()
    if not filename:
        parsed = urlparse(url)
        url_path = unquote(parsed.path)
        filename = url_path.split("/")[-1] if "/" in url_path else "downloaded_file"
        if not filename or filename == "/":
            filename = "downloaded_file.pdf"

    # Validate extension
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        print(json.dumps({"ok": False, "name": filename, "error": f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTS))}", "steps": []}))
        return

    steps.append(f"[~] downloading {filename}...")
    sys.stderr.write(steps[-1] + "\n")
    sys.stderr.flush()

    # Download to temp file
    try:
        t0 = time.time()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}")
        tmp_path = tmp.name
        urllib.request.urlretrieve(url, tmp_path)
        dl_size = Path(tmp_path).stat().st_size
        dl_time = time.time() - t0
        steps.append(f"[+] downloaded {dl_size:,} bytes in {dl_time:.1f}s")
    except Exception as e:
        steps.append(f"[x] download failed: {str(e)[:150]}")
        print(json.dumps({"ok": False, "name": filename, "error": f"Download failed: {str(e)[:150]}", "steps": steps}))
        return

    # Ensure volume exists + upload
    dest = f"{vol}/{filename}"
    w = _client()
    vol_err = _ensure_volume(w, vol)
    if vol_err:
        steps.append(f"[x] {vol_err}")
        print(json.dumps({"ok": False, "name": filename, "error": vol_err, "steps": steps}), flush=True)
        try: Path(tmp_path).unlink()
        except OSError: pass
        return

    steps.append(f"[~] uploading to {dest}...")
    sys.stderr.write(steps[-1] + "\n")
    sys.stderr.flush()
    try:
        t0 = time.time()
        with open(tmp_path, "rb") as f:
            w.files.upload(dest, f, overwrite=True)
        up_time = time.time() - t0
        size = Path(tmp_path).stat().st_size
        steps.append(f"[+] uploaded in {up_time:.1f}s")
        print(json.dumps({"ok": True, "name": filename, "path": dest, "size": size, "steps": steps}), flush=True)
    except Exception as e:
        steps.append(f"[x] upload failed: {str(e)[:150]}")
        print(json.dumps({"ok": False, "name": filename, "error": str(e)[:200], "steps": steps}), flush=True)
        return
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="UC Volume operations for KA documents")
    parser.add_argument("--mode", required=True, choices=["list", "upload", "delete", "upload-url"])
    parser.add_argument("--file", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("--url", default="")
    args = parser.parse_args()

    if args.mode == "list":
        mode_list()
    elif args.mode == "upload":
        if not args.file:
            print(json.dumps({"ok": False, "error": "--file is required for upload mode"}))
            return
        mode_upload(args.file)
    elif args.mode == "upload-url":
        url = args.url or os.environ.get("UPLOAD_URL", "").strip() or sys.stdin.read().strip()
        if not url:
            print(json.dumps({"ok": False, "error": "URL required (--url, UPLOAD_URL env, or stdin)"}))
            return
        mode_upload_url(url)
    elif args.mode == "delete":
        if not args.name:
            print(json.dumps({"ok": False, "error": "--name is required for delete mode"}))
            return
        mode_delete(args.name)


if __name__ == "__main__":
    main()
