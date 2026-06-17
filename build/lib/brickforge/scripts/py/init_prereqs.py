#!/usr/bin/env python3
"""Check and install local environment prerequisites for agent-forge.

Checks: uv, Python venv (.venv), node.js, npm,
        visual/backend node_modules, visual/frontend node_modules.

Usage:
  uv run python scripts/py/init_prereqs.py         # check + auto-fix
  uv run python scripts/py/init_prereqs.py --check # check only, no changes
"""
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT   = Path(__file__).resolve().parents[2]
VISUAL = ROOT / "visual"

os.chdir(ROOT)

# ── ANSI ─────────────────────────────────────────────────────────────────────
R, G, Y, B, C, W = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[36m", "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
ORANGE = "\033[38;5;214m"
CONF   = f"{BOLD}{ORANGE}"
OK     = f"{G}✓{W}"
FAIL   = f"{R}✗{W}"
WARN   = f"{Y}⚠{W}"
ARROW  = f"{B}→{W}"

CHECK_ONLY = "--check" in sys.argv


# ── Helpers ───────────────────────────────────────────────────────────────────

def section(title: str) -> None:
    print(f"\n{BOLD}{B}═══ {title} ═══{W}")


def cmd_version(cmd: str, flag: str = "--version") -> str | None:
    if not shutil.which(cmd):
        return None
    try:
        r = subprocess.run([cmd, flag], capture_output=True, text=True)
        return (r.stdout or r.stderr).strip().split("\n")[0]
    except Exception:
        return "?"


class Spinner:
    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, msg: str):
        self._msg  = msg
        self._stop = threading.Event()
        self._t    = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._t.join()
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _run(self):
        i = 0
        while not self._stop.is_set():
            sys.stdout.write(f"\r  {C}{self._FRAMES[i % len(self._FRAMES)]}{W} {self._msg}")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1


# ── Check functions ───────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str) -> bool:
    symbol = OK if ok else FAIL
    print(f"  {symbol}  {label:<32} {DIM}{detail}{W}")
    _results.append((label, ok, detail))
    return ok


def check_uv() -> bool:
    ver = cmd_version("uv")
    if ver:
        return check("uv", True, ver)
    return check("uv", False, "not found")


def check_venv() -> bool:
    venv       = ROOT / ".venv"
    pyproject  = ROOT / "pyproject.toml"
    cfg        = venv / "pyvenv.cfg"
    if not venv.exists():
        return check("Python venv  (.venv)", False, "missing — uv sync required")
    if pyproject.exists() and cfg.exists():
        if pyproject.stat().st_mtime > cfg.stat().st_mtime:
            return check("Python venv  (.venv)", False, "stale (pyproject.toml changed) — uv sync required")
    return check("Python venv  (.venv)", True, str(venv.relative_to(ROOT)))


def check_node() -> bool:
    ver = cmd_version("node")
    if ver:
        return check("node.js", True, ver)
    return check("node.js", False, "not found — install: https://nodejs.org (v18+)")


def check_npm() -> bool:
    ver = cmd_version("npm")
    if ver:
        return check("npm", True, ver)
    return check("npm", False, "not found (ships with node.js)")


def check_node_modules(label: str, dir_: Path) -> bool:
    sentinel = dir_ / "node_modules" / ".package-lock.json"
    lock     = dir_ / "package-lock.json"
    rel      = dir_.relative_to(ROOT)
    if not sentinel.exists():
        return check(f"node_modules  ({label})", False, f"missing — npm ci in {rel}/")
    if lock.exists() and lock.stat().st_mtime > sentinel.stat().st_mtime:
        return check(f"node_modules  ({label})", False, f"stale (package-lock.json updated)")
    return check(f"node_modules  ({label})", True, str(rel / "node_modules"))


# ── Install actions ───────────────────────────────────────────────────────────

def do_uv_sync() -> bool:
    print(f"\n  {ARROW} Running uv sync ...")
    with Spinner("Syncing Python dependencies..."):
        r = subprocess.run(["uv", "sync"], capture_output=True, text=True, cwd=ROOT)
    if r.returncode == 0:
        print(f"  {OK} uv sync complete")
        return True
    print(f"  {FAIL} uv sync failed:\n{r.stderr.strip()}")
    return False


def do_npm_ci(label: str, dir_: Path) -> bool:
    print(f"\n  {ARROW} npm ci — {label} ...")
    with Spinner(f"Installing {label} node dependencies..."):
        r = subprocess.run(["npm", "ci"], capture_output=True, text=True, cwd=dir_)
    if r.returncode == 0:
        print(f"  {OK} {label} node deps installed")
        return True
    print(f"  {FAIL} npm ci failed for {label}:\n{r.stderr.strip()[-500:]}")
    return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    section("Checking Prerequisites")

    uv_ok    = check_uv()
    venv_ok  = check_venv()
    node_ok  = check_node()
    npm_ok   = check_npm()
    back_ok  = check_node_modules("visual/backend",  VISUAL / "backend")
    front_ok = check_node_modules("visual/frontend", VISUAL / "frontend")

    all_ok = all([uv_ok, venv_ok, node_ok, npm_ok, back_ok, front_ok])

    # ── check-only mode ──
    if CHECK_ONLY:
        section("Summary")
        if all_ok:
            print(f"  {OK} {CONF}All prerequisites met.{W}\n")
        else:
            missing = [lbl for lbl, ok, _ in _results if not ok]
            print(f"  {FAIL} {len(missing)} issue(s): {C}{', '.join(missing)}{W}")
            print(f"\n  {DIM}Run without --check to fix automatically.{W}\n")
            sys.exit(1)
        return

    if all_ok:
        section("Summary")
        print(f"  {OK} {CONF}All prerequisites already satisfied — nothing to do.{W}\n")
        return

    # ── auto-fix ──
    section("Installing Missing Prerequisites")

    if not uv_ok:
        print(f"  {WARN} uv must be installed first.")
        print(f"  {DIM}Run:  pip install uv   or   curl -Ls https://astral.sh/uv/install.sh | sh{W}\n")
        sys.exit(1)

    if not venv_ok:
        if not do_uv_sync():
            sys.exit(1)

    if not node_ok:
        print(f"  {WARN} node.js not found.")
        print(f"  {DIM}Install from https://nodejs.org (v18+) then re-run this script.{W}\n")
        sys.exit(1)

    if not npm_ok:
        print(f"  {WARN} npm not found — it ships with node.js.")
        print(f"  {DIM}Re-install node.js from https://nodejs.org then re-run this script.{W}\n")
        sys.exit(1)

    if not back_ok:
        if not do_npm_ci("visual/backend", VISUAL / "backend"):
            sys.exit(1)

    if not front_ok:
        if not do_npm_ci("visual/frontend", VISUAL / "frontend"):
            sys.exit(1)

    section("Summary")
    print(f"  {OK} {CONF}All prerequisites installed successfully.{W}\n")
    print(f"  {DIM}Next: configure your environment →  ./scripts/sh/setup_dbx_env.sh{W}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {DIM}Interrupted.{W}\n")
        sys.exit(130)
