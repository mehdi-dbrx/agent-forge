#!/usr/bin/env python3
"""Save/load .env.local to/from a Databricks Unity Catalog Volume.

Auth: ENV_STORE_HOST + ENV_STORE_TOKEN (or SDK credential chain for the host).
Config: ENV_STORE_CATALOG_VOLUME_PATH in .env.local (set via init_env_store.sh (scripts/sh/init_env_store.sh))

File naming convention (derived from DATABRICKS_HOST):
  Current  : {host-prefix}-latest.env           e.g. fevm-agent-forge-latest.env
  Backups  : {host-prefix}-1.env, -2.env, ...   (previous latest, never deleted automatically)

  On each save, the existing -latest.env is archived as -{n+1}.env before the new
  content is written to -latest.env (overwrite).

Usage:
  uv run python scripts/py/env_store.py save
  uv run python scripts/py/env_store.py load
  uv run python scripts/py/env_store.py save --dry-run
  uv run python scripts/py/env_store.py load --dry-run
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ── ANSI ──────────────────────────────────────────────────────────────────────
R, G, Y, B, M, C, W = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m", "\033[0m"
BOLD, DIM = "\033[1m", "\033[2m"
ORG = "\033[38;5;208m"
OK   = f"{G}[+]{W}"
FAIL = f"{R}[x]{W}"
WARN = f"{Y}[!]{W}"
SKIP = f"{DIM}[-]{W}"

_SECRET_KEYS = {"DATABRICKS_TOKEN", "AGENT_MODEL_TOKEN"}


def section(title: str) -> None:
    print(f"\n{BOLD}{B}═══ {title} ═══{W}")


def _setup_interrupt_handler() -> None:
    """Erase the ^C echo and exit cleanly on Ctrl+C."""
    import signal as _signal
    def _handler(*_):
        print(f"\033[2K\r\n  {DIM}Cancelled.{W}\n", flush=True)
        sys.exit(130)
    _signal.signal(_signal.SIGINT, _handler)


def _redact(val: str) -> str:
    if len(val) > 10:
        return val[:6] + "*" * (len(val) - 10) + val[-4:]
    return "*" * len(val)


def _hostname_prefix() -> str | None:
    """Extract subdomain prefix from DATABRICKS_HOST.

    https://fevm-agent-forge.cloud.databricks.com  →  fevm-agent-forge
    """
    host = os.environ.get("DATABRICKS_HOST", "").strip().rstrip("/")
    if not host:
        return None
    hostname = host.replace("https://", "").replace("http://", "")
    return hostname.split(".")[0]


def _parse_numbered_index(basename: str, prefix: str) -> int:
    """Return N for '{prefix}-N.env', or -1 if not a match."""
    m = re.match(rf"^{re.escape(prefix)}-(\d+)\.env$", basename)
    return int(m.group(1)) if m else -1


def _list_store_files(w, base_path: str, prefix: str) -> list[dict]:
    """Return files sorted: latest first, then numbered descending.

    Each entry: {path, name, index, ts, is_latest}
    """
    latest_name = f"{prefix}-latest.env"
    results: list[dict] = []
    try:
        dir_path = base_path.lstrip("/")
        resp = w.api_client.do("GET", f"/api/2.0/fs/directories/{dir_path}")
        for entry in resp.get("contents", []):
            if entry.get("is_directory"):
                continue
            path = entry.get("path", "")
            basename = path.rstrip("/").split("/")[-1]
            last_modified = entry.get("last_modified")
            ts = (
                datetime.fromtimestamp(last_modified / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                if last_modified
                else "unknown"
            )
            if basename == latest_name:
                results.append({"path": path, "name": basename, "index": 10**9, "ts": ts, "is_latest": True})
            else:
                idx = _parse_numbered_index(basename, prefix)
                if idx >= 0:
                    results.append({"path": path, "name": basename, "index": idx, "ts": ts, "is_latest": False})
    except Exception as e:
        print(f"  {WARN} Could not list {base_path}: {e}", file=sys.stderr)
    # latest (10^9) first, then highest numbered first
    return sorted(results, key=lambda x: x["index"], reverse=True)


def _next_backup_n(files: list[dict]) -> int:
    """Next numbered index for archiving current latest."""
    numbered = [f for f in files if not f["is_latest"]]
    if not numbered:
        return 1
    return max(f["index"] for f in numbered) + 1


def _profile_for_host(host: str) -> str | None:
    """Find a valid CLI profile whose host matches. Returns profile name or None."""
    host = host.rstrip("/")
    try:
        result = subprocess.run(
            ["databricks", "auth", "profiles"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 3 and parts[-1].upper() == "YES":
                if parts[1].rstrip("/") == host:
                    return parts[0]
    except Exception:
        pass
    return None


def _connect():
    """Connect to the store workspace using ENV_STORE_HOST + ENV_STORE_TOKEN or auto-discovered profile."""
    from databricks.sdk import WorkspaceClient
    host  = os.environ.get("ENV_STORE_HOST", "").strip()
    token = os.environ.get("ENV_STORE_TOKEN", "").strip()
    if not host:
        raise RuntimeError("ENV_STORE_HOST not set — run ./scripts/sh/init_env_store.sh first.")
    if token:
        return WorkspaceClient(host=host, token=token)
    profile = _profile_for_host(host)
    if profile:
        return WorkspaceClient(host=host, profile=profile)
    raise RuntimeError(f"No auth found for {host} — set ENV_STORE_TOKEN or add a CLI profile for this host.")


def cmd_save(args) -> int:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local", override=True)

    base_path = os.environ.get("ENV_STORE_CATALOG_VOLUME_PATH", "").strip().rstrip("/")
    if not base_path:
        print(f"\n  {FAIL} ENV_STORE_CATALOG_VOLUME_PATH not set — run ./scripts/sh/init_env_store.sh first.")
        return 1

    env_local = ROOT / ".env.local"
    if not env_local.exists():
        print(f"\n  {FAIL} .env.local not found — nothing to save.")
        return 1

    prefix = _hostname_prefix()
    if not prefix:
        print(f"\n  {FAIL} DATABRICKS_HOST not set in .env.local.")
        return 1

    store_host_display = os.environ.get("ENV_STORE_HOST", "").strip()
    print(f"\n{BOLD}{B}╔══════════════════════════════════════════╗{W}")
    print(f"{BOLD}{B}║  Agent Forge  —  Env Store Save          ║{W}")
    print(f"{BOLD}{B}╚══════════════════════════════════════════╝{W}")
    print(f"\n  Workspace : {C}{store_host_display}{W}")
    print(f"  Store     : {C}{base_path}{W}")
    print(f"  Prefix    : {C}{prefix}{W}")

    if args.dry_run:
        print(f"\n  {WARN} {BOLD}--dry-run: nothing uploaded{W}\n")
        return 0

    section("Connecting")
    try:
        w = _connect()
        me = w.current_user.me()
        print(f"  {OK} Connected as {C}{me.user_name}{W} on {C}{store_host_display}{W}")
    except Exception as e:
        print(f"  {FAIL} Connection failed: {e}")
        return 1

    section("Archiving Previous Snapshot")
    existing = _list_store_files(w, base_path, prefix)
    latest_file = next((f for f in existing if f["is_latest"]), None)

    if latest_file:
        backup_n = _next_backup_n(existing)
        backup_name = f"{prefix}-{backup_n}.env"
        backup_path = f"{base_path}/{backup_name}"
        try:
            # Download current latest
            resp = w.files.download(latest_file["path"])
            data = resp.contents
            if data is None:
                raise RuntimeError("Download returned empty response")
            archived = data.read()
            # Re-upload as numbered backup
            w.files.upload(backup_path, io.BytesIO(archived), overwrite=False)
            print(f"  {OK} Archived {C}{latest_file['name']}{W} → {C}{backup_name}{W}")
        except Exception as e:
            print(f"  {FAIL} Archive failed: {e}")
            return 1
    else:
        print(f"  {SKIP} No previous snapshot to archive")

    section("Uploading")
    latest_path = f"{base_path}/{prefix}-latest.env"
    try:
        contents = env_local.read_bytes()
        w.files.upload(latest_path, io.BytesIO(contents), overwrite=True)
        print(f"  {OK} Saved .env.local → {C}{latest_path}{W}")
    except Exception as e:
        print(f"  {FAIL} Upload failed: {e}")
        return 1

    print(f"\n  {OK} {G}{BOLD}Save complete.{W}\n")
    return 0


def cmd_load(args) -> int:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local", override=True)

    base_path = os.environ.get("ENV_STORE_CATALOG_VOLUME_PATH", "").strip().rstrip("/")
    if not base_path:
        print(f"\n  {FAIL} ENV_STORE_CATALOG_VOLUME_PATH not set — run ./scripts/sh/init_env_store.sh first.")
        return 1

    prefix = _hostname_prefix()
    if not prefix:
        print(f"\n  {FAIL} DATABRICKS_HOST not set in .env.local.")
        return 1

    store_host_display = os.environ.get("ENV_STORE_HOST", "").strip()
    print(f"\n{BOLD}{B}╔══════════════════════════════════════════╗{W}")
    print(f"{BOLD}{B}║  Agent Forge  —  Env Store Load          ║{W}")
    print(f"{BOLD}{B}╚══════════════════════════════════════════╝{W}")
    print(f"\n  Workspace : {C}{store_host_display}{W}")
    print(f"  Store     : {C}{base_path}{W}")
    print(f"  Prefix    : {C}{prefix}{W}")

    if args.dry_run:
        print(f"\n  {WARN} {BOLD}--dry-run: nothing downloaded{W}\n")
        return 0

    section("Connecting")
    try:
        w = _connect()
        me = w.current_user.me()
        print(f"  {OK} Connected as {C}{me.user_name}{W} on {C}{store_host_display}{W}")
    except Exception as e:
        print(f"  {FAIL} Connection failed: {e}")
        return 1

    section(f"Available Snapshots for '{prefix}'")
    files = _list_store_files(w, base_path, prefix)
    if not files:
        print(f"  {WARN} No snapshots found for prefix '{prefix}' in {C}{base_path}{W}")
        print(f"  {ORG}Run './scripts/sh/env_store.sh save' to store your first snapshot.{W}")
        return 1

    for i, f in enumerate(files, 1):
        label = f" {G}[latest]{W}" if f["is_latest"] else ""
        print(f"  [{i}] {C}{f['name']:<40}{W}{label} {DIM}{f['ts']}{W}")

    backups = [f for f in files if not f["is_latest"]]
    n_options = len(files)
    clear_option = n_options + 1
    if backups:
        print(f"  [{clear_option}] {Y}keep only latest, clear {len(backups)} backup(s){W}")

    try:
        limit = clear_option if backups else n_options
        raw = input(f"\n  Select [1-{limit}] (or Enter to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n  {SKIP} Cancelled")
        return 0

    if not raw:
        print(f"  {SKIP} Cancelled")
        return 0

    try:
        idx = int(raw)
        if not 1 <= idx <= (clear_option if backups else n_options):
            raise ValueError
    except ValueError:
        print(f"  {FAIL} Invalid selection.")
        return 1

    # ── Clear backups ─────────────────────────────────────────────────────────
    if backups and idx == clear_option:
        section("Clearing Backups")
        errors = 0
        for f in backups:
            try:
                w.files.delete(f["path"])
                print(f"  {OK} Deleted {C}{f['name']}{W}")
            except Exception as e:
                print(f"  {FAIL} Could not delete {f['name']}: {e}")
                errors += 1
        if errors:
            print(f"\n  {WARN} {errors} deletion(s) failed.")
        else:
            print(f"\n  {OK} {G}{BOLD}Backups cleared.{W}\n")
        return 0

    selected = files[idx - 1]

    # ── Download for peek ─────────────────────────────────────────────────────
    try:
        response = w.files.download(selected["path"])
        contents = response.contents
        if contents is None:
            print(f"  {FAIL} Download returned empty response.")
            return 1
        downloaded = contents.read()
    except Exception as e:
        print(f"  {FAIL} Download failed: {e}")
        return 1

    # ── Preview with masked secrets ───────────────────────────────────────────
    section(f"Preview: {selected['name']}")
    for line in downloaded.decode("utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", stripped)
        if m:
            key, val = m.group(1), m.group(2).strip().strip("'\"")
            display = _redact(val) if key in _SECRET_KEYS and val else (val or f"{DIM}(empty){W}")
            print(f"  {C}{key:<38}{W} {display}")

    # ── Confirm ───────────────────────────────────────────────────────────────
    try:
        confirm = input(f"\n  Load this file? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(f"\n  {SKIP} Cancelled")
        return 0

    if confirm not in ("y", "yes"):
        print(f"  {SKIP} Aborted")
        return 0

    # ── Write .env.local ──────────────────────────────────────────────────────
    section("Writing .env.local")
    env_local = ROOT / ".env.local"
    if env_local.exists():
        shutil.copy2(env_local, ROOT / ".env.local.bak")
        print(f"  {OK} Backed up existing .env.local → {C}.env.local.bak{W}")

    env_local.write_bytes(downloaded)
    print(f"  {OK} {C}{selected['name']}{W} → {BOLD}.env.local{W}")

    print(f"\n  {OK} {G}{BOLD}Load complete.{W}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Save/load .env.local to/from a Databricks Unity Catalog Volume"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    save_p = sub.add_parser("save", help="Upload .env.local to the UC Volume store")
    save_p.add_argument("--dry-run", action="store_true", help="Preview without uploading")

    load_p = sub.add_parser("load", help="Download .env.local from the UC Volume store")
    load_p.add_argument("--dry-run", action="store_true", help="Preview without downloading")

    args = parser.parse_args()
    _setup_interrupt_handler()
    return cmd_save(args) if args.cmd == "save" else cmd_load(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n  {DIM}Cancelled.{W}\n")
        sys.exit(130)
