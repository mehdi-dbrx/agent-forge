"""BrickForge Setup App - FastAPI backend."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from brickforge import PROJECT_ROOT, PACKAGE_ROOT, USER_DIR
from brickforge.lib.config_provider import LocalConfigProvider, ForgeConfigProvider, ConfigProvider
from brickforge.routes.setup import router as setup_router
from brickforge.routes.auth import router as auth_router
from brickforge.routes.gen import router as gen_router
from brickforge.routes.ka import router as ka_router
from brickforge.routes.cleanup import router as cleanup_router
from brickforge.routes.projects import router as projects_router
from brickforge.lib.graph_builder import build_graph

DIST_DIR = Path(__file__).resolve().parent / "static"
# Config file: ~/.brickforge/config.json (pip install) or repo/config.json (editable)
if (PROJECT_ROOT / "pyproject.toml").exists():
    CONFIG_FILE = PROJECT_ROOT / "config.json"  # editable install: repo root
else:
    CONFIG_FILE = USER_DIR / "config.json"  # pip install: ~/.brickforge/
PORT = int(os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("VISUAL_PORT") or 9000)
FORGE_MODE = os.environ.get("FORGE_MODE") == "true" or os.environ.get("DATABRICKS_APP_PORT") is not None

# Config provider -- default to local, overridden in lifespan for FORGE mode
config: ConfigProvider = LocalConfigProvider(CONFIG_FILE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global config
    # Startup
    if FORGE_MODE:
        config = ForgeConfigProvider()
        await config.init()
        schema = config.get("workspace.unity_catalog_schema")
        print(f"[forge] ForgeConfigProvider initialized" + (f" (schema: {schema})" if schema else " (bootstrap phase)"))
    else:
        config = LocalConfigProvider(CONFIG_FILE)
        # Restore project auto-save mirror if a current project exists
        from brickforge.routes.projects import _read_current, _set_project_mirror, PROJECTS_DIR
        from brickforge.lib.project_paths import init_artifact_dirs
        current = _read_current()
        if current:
            _set_project_mirror(current)
            config._save()  # sync config.json -> project mirror
            artifact_dir = PROJECTS_DIR / current
            init_artifact_dirs(artifact_dir)
            os.environ["PROJECT_DIR"] = str(artifact_dir)
            print(f"[project] active: {current}")

    # Restore token from token store (keyring or secrets scope)
    if not FORGE_MODE:
        from brickforge.lib.token_store import get_token_store
        _token_store = get_token_store()
        _host = config.get("workspace.host") or ""
        if _host:
            _token = _token_store.get(_host)
            if _token:
                os.environ["DATABRICKS_TOKEN"] = _token
                config._data.setdefault("workspace", {})["token"] = _token
                print(f"[token] restored from {_token_store.__class__.__name__} for {_host}")
            else:
                print(f"[token] not found in {_token_store.__class__.__name__} for {_host}")

    mode = "FORGE (SaaS)" if FORGE_MODE else f"LOCAL ({CONFIG_FILE})"
    print(f"[config] mode: {mode}")
    print(f"[visual] http://localhost:{PORT}")
    yield
    # Shutdown
    print("[visual] shutting down")


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "PUT", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"ok": True}


# ── Environment Config ────────────────────────────────────────────────────────

LAYOUT_FILE = PROJECT_ROOT / "visual" / "graph-layout.json"


@app.get("/api/graph")
async def get_graph():
    try:
        graph = build_graph()
        # Merge saved positions
        try:
            import json
            positions = json.loads(LAYOUT_FILE.read_text())
            for node in graph["nodes"]:
                if node["id"] in positions:
                    node["position"] = positions[node["id"]]
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return graph
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.put("/api/layout")
async def save_layout(request: Request):
    try:
        import json
        positions = await request.json()
        LAYOUT_FILE.write_text(json.dumps(positions, indent=2))
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/assets")
async def project_assets():
    """Return current project's on-disk assets (prompts, SQL, CSVs, manifests)."""
    from brickforge.lib.project_paths import prompt_dir as _prompt_dir, gen_dir as _gen_dir
    assets: dict[str, list[dict]] = {}

    prompt_dir = _prompt_dir()
    gen_dir = _gen_dir()

    # Prompts
    prompts = []
    if prompt_dir.exists():
        for f in sorted(prompt_dir.iterdir()):
            if f.is_file() and f.suffix in (".prompt", ".base"):
                prompts.append({"name": f.name, "size": f.stat().st_size})
    assets["prompts"] = prompts

    # Generated data
    for category, subdir in [("tables", "init"), ("csv", "csv"), ("functions", "func"), ("procedures", "proc")]:
        items = []
        d = gen_dir / subdir
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.is_file() and not f.name.startswith("."):
                    items.append({"name": f.name, "size": f.stat().st_size})
        assets[category] = items

    # Demo data
    demo_dir = PACKAGE_ROOT / "data" / "demo"
    demo = []
    if demo_dir.exists():
        for subdir in ["init", "csv", "func", "proc"]:
            d = demo_dir / subdir
            if d.exists():
                for f in sorted(d.iterdir()):
                    if f.is_file() and not f.name.startswith("."):
                        demo.append({"name": f"{subdir}/{f.name}", "size": f.stat().st_size})
    assets["demo"] = demo

    # Manifests
    manifests = []
    for mf in ["manifest.json", "routine_manifest.json"]:
        p = gen_dir / mf
        if p.exists():
            manifests.append({"name": mf, "size": p.stat().st_size})
    assets["manifests"] = manifests

    total = sum(len(v) for v in assets.values())
    return {"assets": assets, "total": total}


@app.get("/api/env")
async def get_env():
    return config.list()


@app.put("/api/env")
async def put_env(request: Request):
    try:
        updates = await request.json()
        if "DATABRICKS_HOST" in updates:
            h = updates["DATABRICKS_HOST"].strip().rstrip("/")
            if h and not h.startswith("http"):
                h = "https://" + h
            updates["DATABRICKS_HOST"] = h
        config.set_many(updates)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Setup routes ──────────────────────────────────────────────────────────────
app.include_router(setup_router)
app.include_router(auth_router)
app.include_router(gen_router)
app.include_router(ka_router)
app.include_router(cleanup_router)
app.include_router(projects_router)


# ── Static files + SPA fallback ──────────────────────────────────────────────

# Mount static assets (JS, CSS, images) at /assets/
assets_dir = DIST_DIR / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

# SPA fallback: serve index.html for all non-API, non-asset routes
index_html = DIST_DIR / "index.html"


@app.get("/{path:path}")
async def spa_fallback(request: Request, path: str):
    # Don't catch /api/* routes (they'll 404 naturally if not implemented)
    if path.startswith("api/"):
        return JSONResponse({"error": "not found"}, status_code=404)
    if index_html.exists():
        return FileResponse(str(index_html))
    return JSONResponse({"error": "frontend not built"}, status_code=404)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import socket
    import uvicorn

    port = PORT
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("0.0.0.0", port))
        sock.close()
    except OSError:
        sock.close()
        print(f"\n  Port {port} is already in use.")
        try:
            choice = input(f"  [K]ill it and reuse {port}, or [N]ext available port? (k/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "n"
        if choice == "k":
            import subprocess
            pids = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True).stdout.strip()
            if pids:
                for pid in pids.split("\n"):
                    try:
                        import os
                        os.kill(int(pid), 9)
                    except (ValueError, ProcessLookupError):
                        pass
                print(f"  [+] Killed process on port {port}")
                import time
                time.sleep(1)
        else:
            for _ in range(10):
                port += 1
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.bind(("0.0.0.0", port))
                    s.close()
                    break
                except OSError:
                    s.close()
            else:
                print(f"  [x] No available port found ({PORT}-{PORT + 10})")
                return

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
