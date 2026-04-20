#!/usr/bin/env python3
"""Create Databricks Knowledge Assistants from config/ka/*.yml files.

Volume path is derived at runtime from PROJECT_UNITY_CATALOG_SCHEMA in .env.local.
The {volume_path} placeholder in YAML configs is substituted before parsing.

After a KA reaches ACTIVE, its endpoint name is written to PROJECT_KA_PASSENGERS
(or PROJECT_KA_<DISPLAY_NAME_UPPER>) in .env.local for use by other scripts.

Usage:
  uv run python scripts/py/ka/create_kas_from_yml.py
  uv run python scripts/py/ka/create_kas_from_yml.py --dry-run
  uv run python scripts/py/ka/create_kas_from_yml.py --skip-existing
  uv run python scripts/py/ka/create_kas_from_yml.py --no-wait
"""
from __future__ import annotations

import os
import re
import sys
import termios
import threading
import time
import tty
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ka_instructions_merger import load_shared_output_format, merge_instructions

CONFIG_DIR = ROOT / "config" / "ka"
ENV_FILE = ROOT / ".env.local"

# ANSI colors
R = "\033[31m"
G = "\033[32m"
Y = "\033[33m"
B = "\033[34m"
M = "\033[35m"
C = "\033[36m"
W = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"

OK = f"{G}✓{W}"
FAIL = f"{R}✗{W}"
WARN = f"{Y}⚠{W}"
INFO = f"{C}→{W}"
STEP = f"{B}●{W}"


def _header(text: str) -> None:
    print(f"\n{BOLD}{B}{'═' * 60}{W}")
    print(f"{BOLD}{B}  {text}{W}")
    print(f"{BOLD}{B}{'═' * 60}{W}\n")


def _step(n: int, total: int, text: str) -> None:
    print(f"  {STEP} {DIM}[{n}/{total}]{W} {text}")


def _success(text: str) -> None:
    print(f"       {OK} {text}")


def _error(text: str) -> None:
    print(f"       {FAIL} {R}{text}{W}")


def _warn(text: str) -> None:
    print(f"       {WARN} {Y}{text}{W}")


def _info(text: str) -> None:
    print(f"       {INFO} {text}")


def _derive_volume_path() -> str | None:
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if not spec or "." not in spec:
        return None
    catalog, schema = spec.split(".", 1)
    return f"/Volumes/{catalog.strip()}/{schema.strip()}/doc"


def _write_env_entry(key: str, value: str) -> None:
    """Write or update key=value in .env.local."""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
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
    ENV_FILE.write_text("\n".join(new_lines) + "\n")


def _env_key_for_display_name(display_name: str) -> str:
    """Map KA display name to env key. Passengers KA → PROJECT_KA_PASSENGERS."""
    if "passenger" in display_name.lower():
        return "PROJECT_KA_PASSENGERS"
    slug = re.sub(r"[^a-z0-9]+", "_", display_name.lower()).strip("_").upper()
    return f"PROJECT_KA_{slug}"


BAR_FILL, BAR_EMPTY = "█", "░"
_bar_stop = threading.Event()
_detach_flag = threading.Event()


def _bar_loop(display_name: str, width: int = 24) -> None:
    """Animate indeterminate progress bar. Stops when _bar_stop is set."""
    i = 0
    while not _bar_stop.is_set():
        pos = i % (width + 2) - 1
        chars = [BAR_EMPTY] * width
        if 0 <= pos < width:
            chars[pos] = BAR_FILL
        bar = "".join(chars)
        elapsed = int(time.monotonic() - _bar_start)
        hint = f"  {DIM}(ESC to detach){W}"
        print(
            f"\r  {DIM}[{W}{G}{bar}{W}{DIM}]{W} {BOLD}{display_name}{W} "
            f"{DIM}{elapsed}s{W}{hint}",
            end="", flush=True,
        )
        i += 1
        _bar_stop.wait(0.06)
    print("\r\033[K", end="", flush=True)  # clear bar line


def _escape_listener() -> None:
    """Read raw stdin; set _detach_flag if ESC is pressed."""
    if not sys.stdin.isatty():
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while not _bar_stop.is_set():
            import select
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if r:
                ch = sys.stdin.read(1)
                if ch == "\x1b":  # ESC
                    _detach_flag.set()
                    return
    except Exception:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


_bar_start: float = 0.0


def wait_for_ka_ready(w, ka_name: str, timeout_sec: int = 600, poll_interval: int = 15) -> str | None:
    """Poll until KA state is ACTIVE or FAILED.

    Shows an animated progress bar while waiting.
    Press ESC at any time to detach — provisioning continues in Databricks;
    check status later with: uv run python scripts/py/ka/list_ka_states.py
    """
    global _bar_start
    _bar_start = time.monotonic()
    _bar_stop.clear()
    _detach_flag.clear()

    bar_thread = threading.Thread(target=_bar_loop, args=(ka_name.split("/")[-1],), daemon=True)
    esc_thread = threading.Thread(target=_escape_listener, daemon=True)
    bar_thread.start()
    esc_thread.start()

    last_state = "CREATING"
    try:
        start = time.monotonic()
        while (time.monotonic() - start) < timeout_sec:
            if _detach_flag.is_set():
                return "DETACHED"
            try:
                ka = w.knowledge_assistants.get_knowledge_assistant(ka_name)
                state = ka.state
                if state:
                    s = state.value if hasattr(state, "value") else str(state)
                    last_state = s
                    if s == "ACTIVE":
                        return "ACTIVE"
                    if s == "FAILED":
                        return "FAILED"
            except Exception:
                pass
            # sleep in small increments so ESC is detected quickly
            for _ in range(poll_interval * 10):
                if _detach_flag.is_set():
                    return "DETACHED"
                time.sleep(0.1)
    finally:
        _bar_stop.set()
        bar_thread.join(timeout=0.5)
        esc_thread.join(timeout=0.5)

    return last_state or "TIMEOUT"


def load_ka_config(path: Path, volume_path: str) -> dict | None:
    """Load KA config, substituting {volume_path} placeholder before parsing."""
    raw = path.read_text(encoding="utf-8")
    raw = raw.replace("{volume_path}", volume_path)

    # Try full YAML parse first
    try:
        import yaml
        data = yaml.safe_load(raw)
        if data and data.get("knowledge_assistant"):
            return data
    except Exception:
        pass

    # Fallback: regex extraction
    ka_section = re.search(
        r"knowledge_assistant:\s*\n(.*?)(?=\nknowledge_sources:|\n# ---)",
        raw,
        re.DOTALL,
    )
    if not ka_section:
        return None

    ka_block = ka_section.group(1)
    ka_display = re.search(r'display_name:\s*"([^"]+)"', ka_block)
    ka_display = (ka_display.group(1).strip() if ka_display else "").strip()
    if not ka_display or ka_display.startswith("<"):
        return None
    ka_desc = re.search(r'description:\s*"([^"]+)"', ka_block)
    ka_desc = (ka_desc.group(1).strip() if ka_desc else "").strip()
    if not ka_desc or ka_desc.startswith("<"):
        return None
    ka_instr = re.search(r"instructions:\s*\|\s*\n([\s\S]*?)(?=\n  # ---|\n  [a-z])", ka_block)
    ka_instr = (ka_instr.group(1).replace("\n    ", "\n").strip() if ka_instr else "") or None
    if ka_instr and ka_instr.startswith("<"):
        ka_instr = None

    files_match = re.search(r"source_type:\s*\"files\"[\s\S]*?path:\s*\"([^\"]+)\"", raw)
    if not files_match:
        return None
    path_val = files_match.group(1).strip()

    return {
        "knowledge_assistant": {
            "display_name": ka_display,
            "description": ka_desc,
            "instructions": ka_instr,
        },
        "knowledge_sources": [
            {
                "display_name": "Documents",
                "description": "",
                "source_type": "files",
                "files": {"path": path_val},
            }
        ],
    }


def extract_ka_payload(config: dict) -> tuple[dict, dict | None]:
    """Extract create_knowledge_assistant payload and first knowledge_source from config."""
    ka_block = config.get("knowledge_assistant") or {}
    display_name = (ka_block.get("display_name") or "").strip()
    description = (ka_block.get("description") or "").strip()
    instructions_raw = (ka_block.get("instructions") or "").strip()
    merged = merge_instructions(load_shared_output_format(), instructions_raw)

    if not display_name or not description:
        return {}, None

    ka_payload = {"display_name": display_name, "description": description}
    if merged:
        ka_payload["instructions"] = merged

    sources = config.get("knowledge_sources") or []
    for src in sources:
        if src.get("source_type") == "files" and src.get("files", {}).get("path"):
            path = src["files"]["path"]
            if path and not path.startswith("<"):
                src_payload = {
                    "display_name": (src.get("display_name") or "Documents").strip(),
                    "description": (src.get("description") or "").strip(),
                    "source_type": "files",
                    "files": {"path": path},
                }
                return ka_payload, src_payload
    return ka_payload, None


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Create Databricks KAs from YAML configs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python scripts/py/ka/create_kas_from_yml.py
  uv run python scripts/py/ka/create_kas_from_yml.py config/ka/ka_passengers.yml --no-wait
  uv run python scripts/py/ka/create_kas_from_yml.py --dry-run
  uv run python scripts/py/ka/create_kas_from_yml.py --skip-existing
        """,
    )
    parser.add_argument("configs", nargs="*", metavar="CONFIG", help="Specific YAML file(s). If omitted, all ka_*.yml in config/ka/.")
    parser.add_argument("--config-dir", default=str(CONFIG_DIR), help="Directory containing ka_*.yml files")
    parser.add_argument("--dry-run", action="store_true", help="Load configs and validate only; do not create")
    parser.add_argument("--skip-existing", action="store_true", help="Skip KAs that already exist (by display_name)")
    parser.add_argument("--limit", "-n", type=int, default=0, help="Process only first N configs (0 = all)")
    parser.add_argument("--no-wait", action="store_true", help="Do not wait for each KA to reach ACTIVE")
    parser.add_argument("--wait-timeout", type=int, default=600, help="Seconds to wait per KA before failing (default: 600)")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local", override=True)

    vol_path = _derive_volume_path()
    if not vol_path:
        print(f"{FAIL} PROJECT_UNITY_CATALOG_SCHEMA not set or invalid (expected catalog.schema){W}", file=sys.stderr)
        return 1

    config_dir = Path(args.config_dir)
    if not config_dir.exists() and not args.configs:
        print(f"{FAIL} Config directory not found: {config_dir}{W}", file=sys.stderr)
        return 1

    _header("Create Knowledge Assistants from YAML")

    if args.configs:
        yaml_files = [Path(p).resolve() for p in args.configs]
        for p in yaml_files:
            if not p.exists():
                print(f"{FAIL} Config not found: {p}{W}", file=sys.stderr)
                return 1
        print(f"  {INFO} Processing {len(yaml_files)} config(s): {', '.join(p.name for p in yaml_files)}{W}\n")
    else:
        yaml_files = sorted(config_dir.glob("ka_*.yml"))
        if not yaml_files:
            print(f"  {WARN} No ka_*.yml files in {config_dir}{W}")
            return 0
        if args.limit:
            yaml_files = yaml_files[: args.limit]

    # ─── Load and validate configs ───────────────────────────────────────────
    _step(1, 3, f"Loading and validating YAML configs (volume: {vol_path})")
    configs: list[tuple[Path, dict, dict, dict | None]] = []
    for p in yaml_files:
        cfg = load_ka_config(p, vol_path)
        if not cfg:
            continue
        ka, src = extract_ka_payload(cfg)
        if not ka.get("display_name") or not ka.get("description"):
            _error(f"{p.name}: missing display_name or description")
            continue
        if not src:
            _warn(f"{p.name}: no files-type knowledge source (skipped)")
            continue
        configs.append((p, cfg, ka, src))
    _success(f"{len(configs)} config(s) ready")

    if not configs:
        _error("No valid configs to process")
        return 1

    if args.dry_run:
        print(f"\n  {INFO} Dry run: would create {len(configs)} KA(s){W}")
        for p, _, ka, src in configs:
            env_key = _env_key_for_display_name(ka["display_name"])
            print(f"    {BOLD}•{W} {ka['display_name']}")
            print(f"      {DIM}volume: {src['files']['path']}{W}")
            print(f"      {DIM}env key: {env_key}{W}")
        return 0

    # ─── Connect to Databricks ───────────────────────────────────────────────
    _step(2, 3, "Connecting to Databricks workspace")

    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.knowledgeassistants import FilesSpec, KnowledgeAssistant, KnowledgeSource

        token = os.environ.get("DATABRICKS_TOKEN")
        if token:
            w = WorkspaceClient(host=os.environ.get("DATABRICKS_HOST"), token=token)
        else:
            w = WorkspaceClient()

        _success("Connected")
    except Exception as e:
        _error(f"Connection failed: {e}")
        return 1

    # ─── Create KAs ─────────────────────────────────────────────────────────
    _step(3, 3, "Creating Knowledge Assistants")

    created = 0
    skipped = 0
    failed = 0

    for i, (path, _cfg, ka_payload, src_payload) in enumerate(configs, 1):
        display_name = ka_payload["display_name"]
        env_key = _env_key_for_display_name(display_name)
        print(f"\n  {DIM}[{i}/{len(configs)}]{W} {BOLD}{display_name}{W}")
        print(f"       {DIM}volume: {src_payload['files']['path']}{W}")

        found_existing = False
        if args.skip_existing:
            try:
                for existing in w.knowledge_assistants.list_knowledge_assistants():
                    if (existing.display_name or "").lower() == display_name.lower():
                        _warn("Already exists (name match); skipping")
                        skipped += 1
                        found_existing = True
                        break
            except Exception:
                pass

        if found_existing:
            continue

        try:
            ka = w.knowledge_assistants.create_knowledge_assistant(
                knowledge_assistant=KnowledgeAssistant(
                    display_name=ka_payload["display_name"],
                    description=ka_payload["description"],
                    instructions=ka_payload.get("instructions") or None,
                )
            )
            parent = ka.name or f"knowledge-assistants/{ka.id}"
            _info(f"KA created: {ka.id}")

            w.knowledge_assistants.create_knowledge_source(
                parent=parent,
                knowledge_source=KnowledgeSource(
                    display_name=src_payload["display_name"],
                    description=src_payload["description"],
                    source_type="files",
                    files=FilesSpec(path=src_payload["files"]["path"]),
                ),
            )
            _info("Knowledge source added; waiting for endpoint to provision...")
            print(f"       {DIM}Press ESC at any time to detach — provisioning continues in Databricks.{W}")
            print(f"       {DIM}Check status later: uv run python scripts/py/ka/list_ka_states.py{W}\n")

            if args.no_wait:
                _success("Created (skipping wait)")
                created += 1
            else:
                final_state = wait_for_ka_ready(w, parent, timeout_sec=args.wait_timeout)
                if final_state == "DETACHED":
                    print()
                    _warn("Detached — provisioning continues in Databricks.")
                    _info(f"Check status: uv run python scripts/py/ka/list_ka_states.py")
                    _info(f"When ACTIVE, run: uv run python scripts/py/ka/create_kas_from_yml.py --skip-existing")
                    _info(f"  (re-run will save {env_key} to .env.local once endpoint is up)")
                    created += 1  # count as created since KA was submitted
                elif final_state == "ACTIVE":
                    # Fetch endpoint name and save to .env.local
                    try:
                        ka_detail = w.knowledge_assistants.get_knowledge_assistant(parent)
                        endpoint_name = ka_detail.endpoint_name or ""
                        if endpoint_name:
                            _write_env_entry(env_key, endpoint_name)
                            _success(f"ACTIVE — endpoint: {endpoint_name}")
                            _info(f"Saved {env_key}={endpoint_name} to .env.local")
                        else:
                            _success("ACTIVE — ready to query (endpoint name unavailable)")
                    except Exception:
                        _success("ACTIVE — ready to query")
                    created += 1
                elif final_state == "FAILED":
                    ka_get = w.knowledge_assistants.get_knowledge_assistant(parent)
                    err = getattr(ka_get, "error_info", None) or "unknown"
                    _error(f"KA reached FAILED state: {err}")
                    failed += 1
                else:
                    _error(f"Timeout after {args.wait_timeout}s (state: {final_state})")
                    failed += 1

        except Exception as e:
            _error(str(e))
            failed += 1

    # ─── Summary ─────────────────────────────────────────────────────────────
    _header("Summary")
    print(f"  {OK} Created:  {G}{created}{W}")
    if skipped:
        print(f"  {WARN} Skipped:  {Y}{skipped}{W}")
    if failed:
        print(f"  {FAIL} Failed:   {R}{failed}{W}")
    print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
