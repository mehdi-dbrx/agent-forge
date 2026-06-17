#!/usr/bin/env python3
"""Initialize the env store: configure ENV_STORE_* keys in .env.local.

The env store workspace is independent from the project workspace — it can be
a shared catalog on a different Databricks workspace used across multiple projects.

Sets up:
  ENV_STORE_HOST                  Workspace hosting the store volume
  ENV_STORE_TOKEN                 PAT for that workspace (optional — profile auto-detected otherwise)
  ENV_STORE_CATALOG_VOLUME_PATH   UC volume base path

Can be run standalone or called from setup_dbx_env.sh.

Usage:
  uv run python scripts/py/init_env_store.py
"""
from __future__ import annotations

import io
import json
import os
import re
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

# ── ANSI ──────────────────────────────────────────────────────────────────────
R, G, Y, B, M, C, W = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m", "\033[0m"
BOLD, DIM = "\033[1m", "\033[2m"
ORG = "\033[38;5;208m"
OK   = f"{G}[+]{W}"
FAIL = f"{R}[x]{W}"
WARN = f"{Y}[!]{W}"
SKIP = f"{DIM}[-]{W}"

ENV_FILE = ROOT / ".env.local"


# ── Terminal helpers (mirrored from setup_dbx_env.py) ─────────────────────────

def _setup_interrupt_handler() -> None:
    """Erase the ^C echo and exit cleanly on Ctrl+C."""
    def _handler(*_):
        print(f"\033[2K\r\n  {DIM}Cancelled.{W}\n", flush=True)
        sys.exit(130)
    signal.signal(signal.SIGINT, _handler)


def _read_choice(prompt: str, n: int) -> int | None:
    """Single-keypress numbered menu. Returns 1-based index or None on ESC."""
    import termios
    import tty

    print(prompt, end="", flush=True)

    if not sys.stdin.isatty():
        try:
            raw = input("").strip()
            idx = int(raw)
            return idx if 1 <= idx <= n else None
        except (ValueError, EOFError):
            return None

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    buf = ""
    try:
        tty.setraw(fd)
        while True:
            ch = os.read(fd, 1).decode("utf-8", errors="ignore")
            if ch == "\x1b":
                sys.stdout.write(f" {DIM}(cancelled){W}\r\n")
                sys.stdout.flush()
                return None
            if ch in ("\r", "\n"):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                try:
                    idx = int(buf)
                    return idx if 1 <= idx <= n else None
                except ValueError:
                    return None
            if ch in ("\x7f", "\x08"):
                if buf:
                    buf = buf[:-1]
                    print("\b \b", end="", flush=True)
            elif ch.isdigit():
                buf += ch
                print(ch, end="", flush=True)
            elif ch == "\x03":
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                print(f"\n  {DIM}Cancelled.{W}\n")
                sys.exit(130)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_line(prompt: str) -> str | None:
    """Line input with ESC-to-cancel. Returns string or None on ESC."""
    import termios
    import tty

    sys.stdout.write(f"\n {prompt}")
    sys.stdout.flush()

    if not sys.stdin.isatty():
        try:
            return input("").strip()
        except EOFError:
            return None

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    buf = ""
    try:
        tty.setraw(fd)
        while True:
            ch = os.read(fd, 1).decode("utf-8", errors="ignore")
            if ch == "\x1b":
                sys.stdout.write(f" {DIM}(cancelled){W}\r\n")
                sys.stdout.flush()
                return None
            if ch in ("\r", "\n"):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return buf
            if ch in ("\x7f", "\x08"):
                if buf:
                    buf = buf[:-1]
                    print("\b \b", end="", flush=True)
            elif ch == "\x03":
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                print(f"\n  {DIM}Cancelled.{W}\n")
                sys.exit(130)
            elif ch >= " ":
                buf += ch
                print(ch, end="", flush=True)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def list_dbx_profiles_with_host() -> list[tuple[str, str, bool]]:
    """Return [(name, host, valid), ...] from `databricks auth profiles`."""
    try:
        result = subprocess.run(
            ["databricks", "auth", "profiles"],
            capture_output=True, text=True, timeout=10,
        )
        profiles = []
        for line in result.stdout.splitlines()[1:]:  # skip header
            parts = line.split()
            if len(parts) >= 3:
                name = parts[0]
                host = parts[1].rstrip("/")
                valid = parts[-1].upper() == "YES"
                profiles.append((name, host, valid))
        return profiles
    except Exception:
        return []


# ── Env helpers ───────────────────────────────────────────────────────────────

def section(title: str) -> None:
    print(f"\n{BOLD}{B}═══ {title} ═══{W}")


def _write_env_entry(path: Path, key: str, value: str) -> None:
    """Write key=value to .env.local, replacing existing active entry if present."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    new_lines: list[str] = []
    replaced = False
    for line in lines:
        m = re.match(r"^(\s*)(#?\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(3) == key and not line.strip().startswith("#"):
            new_lines.append(f"{key}={value}")
            replaced = True
            continue
        new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _redact(val: str) -> str:
    if len(val) > 10:
        return val[:6] + "*" * (len(val) - 10) + val[-4:]
    return "*" * len(val)


def _profile_for_host(host: str) -> str | None:
    """Find a valid CLI profile whose host matches. Returns profile name or None."""
    host = host.rstrip("/")
    for name, phost, valid in list_dbx_profiles_with_host():
        if valid and phost.rstrip("/") == host:
            return name
    return None


def _verify_connection(host: str, token: str | None, profile: str | None) -> tuple[bool, str]:
    """Test workspace connection. Returns (ok, message)."""
    host = host.rstrip("/")
    if token:
        try:
            req = urllib.request.Request(
                f"{host}/api/2.0/preview/scim/v2/Me",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return True, f"{host} ({data.get('userName', '?')})"
        except urllib.error.HTTPError as e:
            return False, f"HTTP {e.code} — token invalid or wrong workspace"
        except Exception as e:
            return False, str(e)
    # Auto-discover profile from ~/.databrickscfg if not explicitly provided
    resolved_profile = profile or _profile_for_host(host)
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient(host=host, profile=resolved_profile) if resolved_profile else WorkspaceClient(host=host)
        me = w.current_user.me()
        return True, f"{host} ({me.user_name})"
    except Exception as e:
        return False, str(e)


def _host_from_auth_env(profile_name: str) -> str:
    """Extract DATABRICKS_HOST from ``databricks auth env --profile <name>``.

    Handles both the current JSON format and the legacy KEY=value text format.
    """
    try:
        result = subprocess.run(
            ["databricks", "auth", "env", "--profile", profile_name],
            capture_output=True, text=True,
        )
        # Try JSON first (current CLI default)
        try:
            data = json.loads(result.stdout)
            return data.get("env", {}).get("DATABRICKS_HOST", "")
        except (json.JSONDecodeError, ValueError):
            pass
        # Fallback: legacy text format (KEY=value)
        for line in result.stdout.splitlines():
            if "DATABRICKS_HOST" in line and "=" in line:
                return line.split("=", 1)[-1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


# ── Store workspace configuration ─────────────────────────────────────────────

def _configure_store_workspace() -> bool:
    """Interactive workspace selection for the env store, mirroring setup_dbx_env.py UX.

    Writes ENV_STORE_HOST (and ENV_STORE_TOKEN if a PAT is provided) to .env.local.
    Profile is auto-detected at runtime by matching host against ~/.databrickscfg.
    Returns True when auth is confirmed.
    """
    load_dotenv(ENV_FILE, override=True)

    section("Store Workspace")
    print(f"  {DIM}The store workspace can be the same as the project or a different one.{W}")

    # ── Project workspace context ─────────────────────────────────────────────
    proj_host  = os.environ.get("DATABRICKS_HOST", "").strip().rstrip("/")
    proj_token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    proj_prof  = _profile_for_host(proj_host) if proj_host else ""
    if proj_host:
        ok, _ = _verify_connection(proj_host, proj_token or None, proj_prof or None)
        status = f"{G}[connected]{W}" if ok else f"{R}[unreachable]{W}"
        print(f"\n  Project workspace : {C}{proj_host}{W}  {status}")

    # ── Current store config ──────────────────────────────────────────────────
    cur_host  = os.environ.get("ENV_STORE_HOST", "").strip().rstrip("/")
    cur_token = os.environ.get("ENV_STORE_TOKEN", "").strip()

    # ── Available CLI profiles (used in submenus only) ────────────────────────
    profiles = list_dbx_profiles_with_host()

    # ── Build menu ────────────────────────────────────────────────────────────
    choices: list[str] = []
    if cur_host:
        print(f"\n  Store workspace   : {C}{cur_host}{W}")
        if cur_token:
            print(f"  ENV_STORE_TOKEN   : {C}{_redact(cur_token)}{W}")
        choices.append("keep")

    if profiles:
        choices.append("use profile workspace")
    choices.append("enter host URL manually")
    choices.append("set up a new workspace profile")

    # Build display labels (same order as choices)
    def _label(c: str) -> str:
        if c == "use profile workspace":
            n = len(profiles)
            return f"use profile workspace  {DIM}[{n} detected]{W}"
        return c

    while True:
        print(f"\n  {C}Action?{W}")
        for i, c in enumerate(choices, 1):
            print(f"    {B}[{i}]{W} {_label(c)}")
        idx = _read_choice(f"  Choice (1-{len(choices)}): ", len(choices))
        if idx is None or not (1 <= idx <= len(choices)):
            continue
        choice = choices[idx - 1]

        # ── Keep ──────────────────────────────────────────────────────────────
        if choice == "keep":
            ok, msg = _verify_connection(cur_host, cur_token or None, None)
            if ok:
                print(f"  {OK} Connected: {C}{msg}{W}")
                return True
            print(f"  {FAIL} Connection failed: {msg}")
            return False

        # ── Use profile workspace ─────────────────────────────────────────────
        if choice == "use profile workspace":
            print(f"\n  {C}Pick a profile:{W}")
            for i, (name, host, valid) in enumerate(profiles, 1):
                vstatus = f"{G}[valid]{W}" if valid else f"{DIM}[invalid]{W}"
                print(f"    {B}[{i}]{W} {name}  {DIM}{host}{W}  {vstatus}")
            pidx = _read_choice(f"  Choice (1-{len(profiles)}): ", len(profiles))
            if pidx is None or not (1 <= pidx <= len(profiles)):
                continue
            pname, phost, _ = profiles[pidx - 1]

            # Resolve host
            host = phost
            if not host:
                host = _host_from_auth_env(pname)
            if not host:
                val = _read_line("Enter workspace URL: ")
                if not val:
                    continue
                host = val

            # Verify connection using profile (transient — not written to .env.local)
            ok, msg = _verify_connection(host, None, pname)
            if not ok:
                print(f"  {FAIL} Connection failed: {msg}")
                return False

            _write_env_entry(ENV_FILE, "ENV_STORE_HOST", host)
            load_dotenv(ENV_FILE, override=True)
            print(f"  {OK} Host set  : {C}{host}{W}")
            print(f"  {OK} Connected : {C}{msg}{W}")
            return True

        # ── Set up new profile ────────────────────────────────────────────────
        if choice == "set up a new workspace profile":
            new_host = _read_line("Workspace URL (https://....databricks.com): ")
            if not new_host:
                continue
            if not new_host.startswith("http"):
                new_host = f"https://{new_host}"
            default_pname = new_host.split("//")[-1].split(".")[0]
            pname_input = _read_line(f"Profile name [{default_pname}]: ")
            if pname_input is None:
                continue
            pname = pname_input or default_pname
            print(f"\n  {C}Running: databricks auth login --host {new_host} --profile {pname}{W}")
            rc = subprocess.call(
                ["databricks", "auth", "login", "--host", new_host, "--profile", pname],
                cwd=ROOT,
            )
            if rc != 0:
                print(f"  {FAIL} databricks auth login failed (exit {rc})")
                continue
            _read_line("Press Enter once browser login is complete, or ESC to cancel: ")

            ok, msg = _verify_connection(new_host, None, pname)
            if not ok:
                print(f"  {FAIL} Connection failed: {msg}")
                return False

            _write_env_entry(ENV_FILE, "ENV_STORE_HOST", new_host)
            load_dotenv(ENV_FILE, override=True)
            print(f"  {OK} Host set  : {C}{new_host}{W}")
            print(f"  {OK} Connected : {C}{msg}{W}")
            return True

        # ── Enter manually ────────────────────────────────────────────────────
        val = _read_line("Enter store workspace URL (https://....databricks.com): ")
        if not val:
            continue
        if not val.startswith("http"):
            val = f"https://{val}"

        print(f"\n  Auth for {C}{val}{W}:")
        print(f"    {B}[1]{W} Personal access token  (stored as ENV_STORE_TOKEN)")
        print(f"    {B}[2]{W} SDK credential chain   (uses ~/.databrickscfg for this host)")
        aidx = _read_choice("  Choice (1-2): ", 2)
        if aidx == 1:
            token_val = _read_line("Enter token (dapi...): ")
            if not token_val:
                continue
            ok, msg = _verify_connection(val, token_val, None)
            if not ok:
                print(f"  {FAIL} Connection failed: {msg}")
                return False
            _write_env_entry(ENV_FILE, "ENV_STORE_HOST", val)
            _write_env_entry(ENV_FILE, "ENV_STORE_TOKEN", token_val)
        elif aidx == 2:
            ok, msg = _verify_connection(val, None, None)
            if not ok:
                print(f"  {FAIL} Connection failed: {msg}")
                return False
            _write_env_entry(ENV_FILE, "ENV_STORE_HOST", val)
        else:
            continue

        load_dotenv(ENV_FILE, override=True)
        print(f"  {OK} Connected: {C}{msg}{W}")
        return True


def main() -> int:
    _setup_interrupt_handler()
    load_dotenv(ENV_FILE, override=True)

    print(f"\n{BOLD}{B}╔══════════════════════════════════════════╗{W}")
    print(f"{BOLD}{B}║  Agent Forge  —  Init Env Store          ║{W}")
    print(f"{BOLD}{B}╚══════════════════════════════════════════╝{W}")

    # ── Store workspace auth ──────────────────────────────────────────────────
    if not _configure_store_workspace():
        return 1

    load_dotenv(ENV_FILE, override=True)

    # ── Suggest default volume path ───────────────────────────────────────────
    schema_spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    default_path: str | None = None
    if "." in schema_spec:
        cat, sch = schema_spec.split(".", 1)
        default_path = f"/Volumes/{cat.strip()}/{sch.strip()}/store"

    # ── Volume path ───────────────────────────────────────────────────────────
    existing = os.environ.get("ENV_STORE_CATALOG_VOLUME_PATH", "").strip()
    base_path: str = ""

    section("Store Volume Path")
    if existing:
        print(f"  Current: {C}{existing}{W}")
        raw = _read_line("Change? [y/N]: ") or ""
        if raw.strip().lower() not in ("y", "yes"):
            base_path = existing
        else:
            existing = ""

    if not existing:
        if default_path:
            print(f"  Suggested: {C}{default_path}{W}")
            raw = _read_line("Use suggested path? [Y/n]: ") or ""
            if raw.strip().lower() in ("", "y", "yes"):
                base_path = default_path
            else:
                val = _read_line("Enter base volume path: ")
                base_path = val.strip().rstrip("/") if val else ""
        else:
            print(f"  {WARN} PROJECT_UNITY_CATALOG_SCHEMA not set — enter path manually.")
            val = _read_line("Enter base volume path (e.g. /Volumes/catalog/schema/store): ")
            base_path = val.strip().rstrip("/") if val else ""

    if not base_path:
        print(f"  {FAIL} Volume path is required.")
        return 1

    if not base_path.startswith("/Volumes/"):
        print(f"  {FAIL} Path must start with /Volumes/")
        return 1

    parts = base_path.lstrip("/").split("/")
    if len(parts) < 4:
        print(f"  {FAIL} Path must be /Volumes/{{catalog}}/{{schema}}/{{volume_name}}")
        return 1
    _, catalog, schema, vol_name = parts[0], parts[1], parts[2], parts[3]

    # ── Connect to store workspace via SDK ────────────────────────────────────
    section("Connecting to Store Workspace")
    store_host  = os.environ.get("ENV_STORE_HOST", "").strip()
    store_token = os.environ.get("ENV_STORE_TOKEN", "").strip()
    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.catalog import VolumeType
        if store_token:
            w = WorkspaceClient(host=store_host, token=store_token)
        else:
            store_prof = _profile_for_host(store_host)
            w = WorkspaceClient(host=store_host, profile=store_prof) if store_prof else WorkspaceClient(host=store_host)
        me = w.current_user.me()
        print(f"  {OK} Connected as {C}{me.user_name}{W} on {C}{store_host}{W}")
    except Exception as e:
        print(f"  {FAIL} Connection failed: {e}")
        return 1

    # ── Validate catalog access — create catalog/schema if missing ────────────
    section("Validating Catalog Access")
    try:
        list(w.volumes.list(catalog_name=catalog, schema_name=schema))
        print(f"  {OK} {C}{catalog}.{schema}{W} is accessible")
    except Exception as e:
        err = str(e).lower()
        # Try to create catalog if it doesn't exist
        if "does not exist" in err or "not found" in err:
            print(f"  {WARN} {C}{catalog}.{schema}{W} not found — attempting to create...")
            try:
                # Create catalog if needed
                try:
                    w.catalogs.get(catalog)
                    print(f"  {SKIP} Catalog {C}{catalog}{W} already exists")
                except Exception:
                    w.catalogs.create(name=catalog)
                    print(f"  {OK} Catalog {C}{catalog}{W} created")
                # Create schema if needed
                try:
                    w.schemas.get(f"{catalog}.{schema}")
                    print(f"  {SKIP} Schema {C}{catalog}.{schema}{W} already exists")
                except Exception:
                    w.schemas.create(name=schema, catalog_name=catalog)
                    print(f"  {OK} Schema {C}{catalog}.{schema}{W} created")
            except Exception as create_err:
                print(f"  {FAIL} Could not create {catalog}.{schema}: {create_err}")
                print(f"  {WARN} Enter a different path or create the catalog/schema manually.")
                return 1
        else:
            print(f"  {FAIL} Cannot access {catalog}.{schema}: {e}")
            return 1

    # ── Create store volume (idempotent) ──────────────────────────────────────
    section("Creating Store Volume")
    try:
        existing_vols = [v.name for v in w.volumes.list(catalog_name=catalog, schema_name=schema)]
        if vol_name in existing_vols:
            print(f"  {SKIP} Volume {C}{base_path}{W} already exists")
        else:
            w.volumes.create(
                catalog_name=catalog,
                schema_name=schema,
                name=vol_name,
                volume_type=VolumeType.MANAGED,
            )
            print(f"  {OK} Volume {C}{base_path}{W} created")
    except Exception as e:
        err = str(e)
        if "already exists" in err.lower():
            print(f"  {SKIP} Volume {C}{base_path}{W} already exists")
        else:
            print(f"  {FAIL} Volume creation failed: {e}")
            return 1

    # ── Write test ────────────────────────────────────────────────────────────
    section("Write Test")
    probe_path = f"{base_path}/.probe"
    try:
        w.files.upload(probe_path, io.BytesIO(b"probe"), overwrite=True)
        w.files.delete(probe_path)
        print(f"  {OK} Write access confirmed")
    except Exception as e:
        print(f"  {FAIL} Write test failed: {e}")
        return 1

    # ── Save to .env.local ────────────────────────────────────────────────────
    section("Saving Configuration")
    _write_env_entry(ENV_FILE, "ENV_STORE_CATALOG_VOLUME_PATH", base_path)
    print(f"  {OK} ENV_STORE_CATALOG_VOLUME_PATH={C}{base_path}{W} → .env.local")

    # ── Verification: list existing snapshots ────────────────────────────────
    section("Verification")
    host_prefix = store_host.replace("https://", "").replace("http://", "").split(".")[0]
    proj_host = os.environ.get("DATABRICKS_HOST", "").strip().rstrip("/")
    snap_prefix = proj_host.replace("https://", "").replace("http://", "").split(".")[0] if proj_host else host_prefix
    try:
        snap_count = 0
        dir_path = base_path.lstrip("/")
        resp = w.api_client.do("GET", f"/api/2.0/fs/directories/{dir_path}")
        for entry in resp.get("contents", []):
            name = entry.get("path", "").rstrip("/").split("/")[-1]
            if name.endswith(".env") and (name == f"{snap_prefix}.env" or name.startswith(f"{snap_prefix}-")):
                snap_count += 1
        if snap_count:
            print(f"  {OK} {snap_count} existing snapshot(s) found for prefix {C}{snap_prefix}{W}")
        else:
            print(f"  {OK} Volume listing works — 0 snapshots yet (prefix: {C}{snap_prefix}{W})")
        print(f"  {OK} Full round-trip verified")
    except Exception as e:
        print(f"  {FAIL} Listing failed after setup — store may not be usable: {e}")
        return 1

    print(f"\n  {OK} {G}{BOLD}Env store ready.{W}")
    print(f"  {ORG}Run './scripts/sh/env_store.sh save' to store your first snapshot.{W}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
