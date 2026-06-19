"""KA document management routes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import JSONResponse

from brickforge import PROJECT_ROOT, PACKAGE_ROOT
from brickforge.lib.env_utils import build_sub_env

router = APIRouter()


def _get_config():
    from brickforge.server import config
    return config


@router.get("/api/ka/documents")
async def list_documents():
    env = build_sub_env(_get_config())
    try:
        result = subprocess.run(
            [sys.executable, "scripts/py/ka/volume_ops.py", "--mode=list"],
            capture_output=True, text=True, timeout=30,
            cwd=str(PACKAGE_ROOT), env=env,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data
        from brickforge.lib.env_utils import parse_subprocess_error; return {"files": [], "error": parse_subprocess_error(result.stderr, result.stdout)}
    except Exception as e:
        return {"files": [], "error": str(e)}


@router.post("/api/ka/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    env = build_sub_env(_get_config())
    uploaded = []
    tmp_dir = PACKAGE_ROOT / "data" / ".tmp-uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        tmp_path = tmp_dir / f.filename
        try:
            content = await f.read()
            tmp_path.write_bytes(content)

            result = subprocess.run(
                [sys.executable, "scripts/py/ka/volume_ops.py", "--mode=upload", f"--file={tmp_path}"],
                capture_output=True, text=True, timeout=60,
                cwd=str(PACKAGE_ROOT), env=env,
            )
            uploaded.append({"name": f.filename, "ok": result.returncode == 0, "error": result.stderr if result.returncode != 0 else None})
        except Exception as e:
            uploaded.append({"name": f.filename, "ok": False, "error": str(e)})
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return {"ok": all(u["ok"] for u in uploaded), "uploaded": uploaded}


@router.post("/api/ka/upload-url")
async def upload_url(request: Request):
    body = await request.json()
    url = body.get("url", "")
    if not url:
        return JSONResponse({"error": "url required"}, status_code=400)

    filename = body.get("filename", "")

    env = build_sub_env(_get_config())
    env["UPLOAD_URL"] = url
    if filename:
        env["UPLOAD_FILENAME"] = filename
    try:
        result = subprocess.run(
            [sys.executable, "scripts/py/ka/volume_ops.py", "--mode=upload-url"],
            capture_output=True, text=True, timeout=60,
            cwd=str(PACKAGE_ROOT), env=env,
        )
        if result.returncode == 0:
            return json.loads(result.stdout.strip()) if result.stdout.strip() else {"ok": True}
        return {"ok": False, "error": result.stderr or result.stdout}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.delete("/api/ka/documents/{name}")
async def delete_document(name: str):
    env = build_sub_env(_get_config())
    try:
        result = subprocess.run(
            [sys.executable, "scripts/py/ka/volume_ops.py", "--mode=delete", f"--name={name}"],
            capture_output=True, text=True, timeout=30,
            cwd=str(PACKAGE_ROOT), env=env,
        )
        return {"ok": result.returncode == 0, "error": result.stderr if result.returncode != 0 else None}
    except Exception as e:
        return {"ok": False, "error": str(e)}
