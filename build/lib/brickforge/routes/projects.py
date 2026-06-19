"""Project management routes -- local + UC Volume projects."""
from __future__ import annotations

import json
import os
import shutil
import zipfile
import io
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import JSONResponse, Response

from brickforge import PACKAGE_ROOT, PROJECT_ROOT, USER_DIR
from brickforge.lib.project_paths import init_artifact_dirs, prompt_dir as _prompt_dir, gen_dir as _gen_dir

router = APIRouter()

# Local projects dir: ~/.brickforge/projects/ (pip) or PROJECT_ROOT/projects/ (editable)
if (PROJECT_ROOT / "pyproject.toml").exists():
    PROJECTS_DIR = PROJECT_ROOT / "projects"
else:
    PROJECTS_DIR = USER_DIR / "projects"

CURRENT_FILE = PROJECTS_DIR / ".current"


def _get_config():
    from brickforge.server import config
    return config


def _read_current() -> str | None:
    """Read the currently active project name."""
    if CURRENT_FILE.exists():
        name = CURRENT_FILE.read_text().strip()
        if name and (PROJECTS_DIR / f"{name}.json").exists():
            return name
    return None


def _write_current(name: str | None) -> None:
    """Write the currently active project name."""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    if name:
        CURRENT_FILE.write_text(name)
    elif CURRENT_FILE.exists():
        CURRENT_FILE.unlink()


def _set_project_mirror(name: str | None) -> None:
    """Point config auto-save at the named project file (or clear it)."""
    config = _get_config()
    if hasattr(config, "_project_file"):
        if name:
            config._project_file = PROJECTS_DIR / f"{name}.json"
        else:
            config._project_file = None


# ── List projects ────────────────────────────────────────────────────────────

@router.get("/api/projects")
async def list_projects():
    config = _get_config()
    projects = []

    # Local projects
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    for f in sorted(PROJECTS_DIR.glob("*.json")):
        name = f.stem
        projects.append({"name": name, "source": "local", "size": f.stat().st_size})

    # UC Volume projects (if schema + auth configured)
    schema = config.get("workspace.unity_catalog_schema") or ""
    host = config.get("workspace.host") or ""
    token = config.get("workspace.token") or ""

    if schema and "." in schema and host and token:
        catalog, schema_name = schema.split(".", 1)
        volume_base = f"/Volumes/{catalog}/{schema_name}/brickforge/stash"
        try:
            import urllib.request
            url = f"{host.rstrip('/')}/api/2.0/fs/directories{volume_base}"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            for entry in data.get("contents", []):
                name = entry.get("name", "")
                if name.endswith(".forge.zip"):
                    projects.append({
                        "name": name.replace(".forge.zip", ""),
                        "source": "volume",
                        "path": entry.get("path", ""),
                        "size": entry.get("file_size", 0),
                    })
        except Exception:
            pass  # Volume not accessible -- show local projects only

    current = _read_current()
    return {"projects": projects, "current": current}


# ── Create project ───────────────────────────────────────────────────────────

@router.post("/api/projects")
async def create_project(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)

    # Sanitize name
    safe_name = name.replace(" ", "-").replace("/", "-").replace("\\", "-")

    # Create local project config
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    project_file = PROJECTS_DIR / f"{safe_name}.json"
    if project_file.exists():
        return JSONResponse({"error": f"project '{safe_name}' already exists"}, status_code=409)

    # Fresh config from defaults
    import copy
    from brickforge.lib.config_provider import DEFAULT_CONFIG
    fresh = copy.deepcopy(DEFAULT_CONFIG)
    project_file.write_text(json.dumps(fresh, indent=2) + "\n")

    # Create artifact directory
    artifact_dir = PROJECTS_DIR / safe_name
    init_artifact_dirs(artifact_dir)

    # Switch mirror FIRST (so _save doesn't overwrite old project with defaults)
    _write_current(safe_name)
    _set_project_mirror(safe_name)

    # Replace active config with fresh defaults
    config = _get_config()
    config._data = fresh
    config._save()
    config._sync_env()
    # Set PROJECT_DIR for subprocess scripts
    os.environ["PROJECT_DIR"] = str(artifact_dir)

    return {"ok": True, "name": safe_name, "source": "local"}


# ── Load project ─────────────────────────────────────────────────────────────

@router.get("/api/projects/{name}")
async def load_project(name: str):
    # Try local first
    project_file = PROJECTS_DIR / f"{name}.json"
    if project_file.exists():
        project_config = json.loads(project_file.read_text())
        # Switch mirror FIRST (so _save doesn't overwrite old project)
        _write_current(name)
        _set_project_mirror(name)
        config = _get_config()
        from brickforge.lib.config_provider import _merge_defaults, DEFAULT_CONFIG
        config._data = _merge_defaults(project_config, DEFAULT_CONFIG)
        config._save()
        config._sync_env()
        # Restore token from token store for this project's workspace
        host = config.get("workspace.host") or ""
        if host:
            from brickforge.lib.token_store import get_token_store
            token = get_token_store().get(host)
            if token:
                os.environ["DATABRICKS_TOKEN"] = token
                config._data.setdefault("workspace", {})["token"] = token
        # Set PROJECT_DIR for subprocess scripts
        artifact_dir = PROJECTS_DIR / name
        init_artifact_dirs(artifact_dir)
        os.environ["PROJECT_DIR"] = str(artifact_dir)
        return {"ok": True, "name": name, "source": "local"}

    # Try UC Volume
    config = _get_config()
    schema = config.get("workspace.unity_catalog_schema") or ""
    host = config.get("workspace.host") or ""
    token = config.get("workspace.token") or ""

    if not schema or "." not in schema or not host or not token:
        return JSONResponse({"error": f"project '{name}' not found"}, status_code=404)

    catalog, schema_name = schema.split(".", 1)
    volume_path = f"/Volumes/{catalog}/{schema_name}/brickforge/stash/{name}.forge.zip"

    try:
        import urllib.request
        url = f"{host.rstrip('/')}/api/2.0/fs/files{volume_path}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
        # Extract config.json from zip
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if "config.json" in zf.namelist():
                project_config = json.loads(zf.read("config.json").decode())
                from brickforge.lib.config_provider import _merge_defaults, DEFAULT_CONFIG
                config._data = _merge_defaults(project_config, DEFAULT_CONFIG)
                config._save()
                config._sync_env()
                _write_current(name)
                _set_project_mirror(name)
                return {"ok": True, "name": name, "source": "volume"}
        return JSONResponse({"error": "invalid project zip"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=404)


# ── Download project config ──────────────────────────────────────────────────

@router.get("/api/projects/{name}/download")
async def download_project(name: str):
    """Return project config JSON as a downloadable file."""
    project_file = PROJECTS_DIR / f"{name}.json"
    if not project_file.exists():
        return JSONResponse({"error": f"project '{name}' not found"}, status_code=404)
    from fastapi.responses import Response
    content = project_file.read_text()
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}.forge.json"'},
    )


# ── Export project bundle ────────────────────────────────────────────────────

@router.get("/api/projects/{name}/export")
async def export_project(name: str):
    """Export project as .forge.zip (config + prompts + generated artifacts)."""
    project_file = PROJECTS_DIR / f"{name}.json"
    if not project_file.exists():
        return JSONResponse({"error": f"project '{name}' not found"}, status_code=404)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Config
        zf.write(str(project_file), "config.json")

        # Use project artifact dir if exists, fall back to package-level
        prompt_dir = _prompt_dir()
        gen_dir = _gen_dir()

        # Prompts
        if prompt_dir.exists():
            for f in sorted(prompt_dir.iterdir()):
                if f.is_file() and f.suffix in (".prompt", ".base"):
                    zf.write(str(f), f"prompt/{f.name}")

        # Generated artifacts
        for subdir in ["csv", "init", "func", "proc"]:
            d = gen_dir / subdir
            if d.exists():
                for f in sorted(d.iterdir()):
                    if f.is_file() and not f.name.startswith("."):
                        zf.write(str(f), f"gen/{subdir}/{f.name}")

        # Manifests
        for mf in ["manifest.json", "routine_manifest.json"]:
            p = gen_dir / mf
            if p.exists():
                zf.write(str(p), f"gen/{mf}")

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.forge.zip"'},
    )


# ── Import project bundle ───────────────────────────────────────────────────

CLEAR_ON_NEW_IMPORT = {
    "workspace.host": None,
    "workspace.token": None,
    "workspace.config_profile": None,
    "workspace.refresh_token": None,
    "workspace.token_endpoint": None,
    "workspace.client_id": None,
    "workspace.client_secret": None,
    "workspace.warehouse_id": None,
    "tools.genie_spaces": [],
    "app.mlflow_experiment_id": None,
    "model.token": None,
    "lakebase.instance_name": None,
    "lakebase.agent_memory_schema": None,
}


@router.post("/api/projects/import")
async def import_project(request: Request, file: UploadFile = File(...)):
    """Import a .forge.zip bundle. mode=load (as-is) or mode=new (sanitized)."""
    mode = request.query_params.get("mode", "load")
    if mode not in ("load", "new"):
        return JSONResponse({"error": "mode must be 'load' or 'new'"}, status_code=400)

    if not file.filename or not file.filename.endswith(".zip"):
        return JSONResponse({"error": "expected a .zip file"}, status_code=400)

    data = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return JSONResponse({"error": "invalid zip file"}, status_code=400)

    # Extract config
    if "config.json" not in zf.namelist():
        return JSONResponse({"error": "zip missing config.json"}, status_code=400)

    config_data = json.loads(zf.read("config.json").decode())

    # Sanitize for new project: clear workspace-specific values
    if mode == "new":
        for dot_path, default in CLEAR_ON_NEW_IMPORT.items():
            keys = dot_path.split(".")
            obj = config_data
            for k in keys[:-1]:
                obj = obj.setdefault(k, {})
            obj[keys[-1]] = default

        # Enable gen data if bundle has table data (csv or init SQL)
        has_table_data = any(
            (e.startswith("gen/csv/") or e.startswith("gen/init/")) and not e.endswith("/")
            for e in zf.namelist()
        )
        if has_table_data:
            config_data.setdefault("data", {})["use_gen_data"] = True

    # Derive project name from filename
    base = file.filename.replace(".forge.zip", "").replace(".zip", "")
    safe_name = base.replace(" ", "-").replace("/", "-").replace("\\", "-")

    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

    if mode == "load":
        # Load overwrites existing project with same name
        pass
    else:
        # New avoids collision
        candidate = safe_name
        counter = 2
        while (PROJECTS_DIR / f"{candidate}.json").exists():
            candidate = f"{safe_name}-{counter}"
            counter += 1
        safe_name = candidate

    project_file = PROJECTS_DIR / f"{safe_name}.json"
    project_file.write_text(json.dumps(config_data, indent=2) + "\n")

    # Create artifact directory for this project
    artifact_dir = PROJECTS_DIR / safe_name
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Extract prompts -> project artifact dir
    prompt_dir = artifact_dir / "prompt"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    for entry in zf.namelist():
        if entry.startswith("prompt/") and not entry.endswith("/"):
            fname = entry.split("/", 1)[1]
            (prompt_dir / fname).write_bytes(zf.read(entry))

    # Extract gen artifacts -> project artifact dir
    gen_dir = artifact_dir / "gen"
    for entry in zf.namelist():
        if entry.startswith("gen/") and not entry.endswith("/"):
            rel = entry.split("/", 1)[1]
            target = gen_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(entry))

    zf.close()

    # Load the imported project as active
    _write_current(safe_name)
    _set_project_mirror(safe_name)
    config = _get_config()
    from brickforge.lib.config_provider import _merge_defaults, DEFAULT_CONFIG
    config._data = _merge_defaults(config_data, DEFAULT_CONFIG)
    config._save()
    config._sync_env()
    os.environ["PROJECT_DIR"] = str(artifact_dir)

    return {"ok": True, "name": safe_name, "mode": mode}


# ── Delete project ───────────────────────────────────────────────────────────

@router.delete("/api/projects/{name}")
async def delete_project(name: str):
    # If deleting the current project, clear current + PROJECT_DIR
    if _read_current() == name:
        _write_current(None)
        _set_project_mirror(None)
        os.environ.pop("PROJECT_DIR", None)

    # Try local first
    project_file = PROJECTS_DIR / f"{name}.json"
    if project_file.exists():
        project_file.unlink()
        # Remove artifact directory
        artifact_dir = PROJECTS_DIR / name
        if artifact_dir.exists():
            shutil.rmtree(artifact_dir)
        return {"ok": True, "source": "local"}

    # Try UC Volume
    config = _get_config()
    schema = config.get("workspace.unity_catalog_schema") or ""
    host = config.get("workspace.host") or ""
    token = config.get("workspace.token") or ""

    if not schema or "." not in schema or not host or not token:
        return JSONResponse({"error": f"project '{name}' not found"}, status_code=404)

    catalog, schema_name = schema.split(".", 1)
    volume_path = f"/Volumes/{catalog}/{schema_name}/brickforge/stash/{name}.forge.zip"

    try:
        import urllib.request
        url = f"{host.rstrip('/')}/api/2.0/fs/files{volume_path}"
        req = urllib.request.Request(url, method="DELETE", headers={"Authorization": f"Bearer {token}"})
        urllib.request.urlopen(req, timeout=10)
        return {"ok": True, "source": "volume"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Rename project ───────────────────────────────────────────────────────────

@router.patch("/api/projects/{name}")
async def rename_project(name: str, request: Request):
    body = await request.json()
    new_name = body.get("name", "").strip().replace(" ", "-").replace("/", "-").replace("\\", "-")
    if not new_name:
        return JSONResponse({"error": "new name required"}, status_code=400)
    if new_name == name:
        return {"ok": True, "name": name}

    old_file = PROJECTS_DIR / f"{name}.json"
    new_file = PROJECTS_DIR / f"{new_name}.json"

    if not old_file.exists():
        return JSONResponse({"error": f"project '{name}' not found"}, status_code=404)
    if new_file.exists():
        return JSONResponse({"error": f"project '{new_name}' already exists"}, status_code=409)

    old_file.rename(new_file)

    # Rename artifact directory
    old_dir = PROJECTS_DIR / name
    new_dir = PROJECTS_DIR / new_name
    if old_dir.exists():
        old_dir.rename(new_dir)

    # Update current if renamed the active project
    if _read_current() == name:
        _write_current(new_name)
        _set_project_mirror(new_name)
        os.environ["PROJECT_DIR"] = str(new_dir)

    return {"ok": True, "name": new_name}
