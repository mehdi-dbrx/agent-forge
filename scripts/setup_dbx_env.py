#!/usr/bin/env python3
"""Interactive setup & check of Databricks resources in .env.local.

For each resource: if not configured, prompt to enter. If configured, verify and offer
to keep, add new, or activate an inactive entry. Inactive (commented) entries are
parsed and shown; user can activate [1], [2], etc.

Usage:
  uv run python scripts/setup_dbx_env.py         # interactive setup
  uv run python scripts/setup_dbx_env.py --check # quick check only
"""
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from databricks.sdk import WorkspaceClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

ENV_FILE = ROOT / ".env.local"

# ANSI
R, G, Y, B, M, C, W = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[35m", "\033[36m", "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ORANGE = "\033[38;5;214m"
CONF = f"{BOLD}{ORANGE}"
OK, FAIL, WARN = f"{G}✓{W}", f"{R}✗{W}", f"{Y}⚠{W}"

FIX_FIRST_MSG = f"\n  {WARN} This needs to be fixed first before moving forward with the other configurations.{W}\n"

FM_WORKSPACES = [
    ("AWS field eng",   "https://e2-demo-field-eng.cloud.databricks.com"),
    ("Azure field eng", "https://adb-984752964297111.11.azuredatabricks.net"),
]
FM_MODEL = "databricks-claude-sonnet-4-6"

_SECRET_KEYS = {"DATABRICKS_TOKEN", "AGENT_MODEL_TOKEN"}

def _redact(val: str) -> str:
    """Mask a secret value for display: show first 6 + stars + last 4 chars."""
    if len(val) > 10:
        return val[:6] + "*" * (len(val) - 10) + val[-4:]
    return "*" * len(val)


def abort_step() -> None:
    """Interrupt gracefully and exit."""
    print(FIX_FIRST_MSG)
    sys.exit(1)


def section(title: str) -> None:
    print(f"\n{BOLD}{B}═══ {title} ═══{W}")


def parse_env_file(path: Path) -> tuple[dict[str, str], dict[str, list[tuple[int, str]]], list[str]]:
    """Return (active, inactive, raw_lines). active[key]=value; inactive[key]=[(line_idx, value), ...]"""
    if not path.exists():
        return {}, {}, []
    lines = path.read_text().splitlines()
    active: dict[str, str] = {}
    inactive: dict[str, list[tuple[int, str]]] = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") and "=" not in stripped.lstrip("#"):
            continue
        m = re.match(r"^#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", stripped)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip().strip("'\"").strip()
        if stripped.startswith("#"):
            inactive.setdefault(key, []).append((i, val))
        else:
            active[key] = val
    return active, inactive, lines


def write_env_entry(path: Path, key: str, value: str) -> None:
    """Append key=value. Existing active lines for this key are left as-is (commented out first by the caller)."""
    lines = path.read_text().splitlines() if path.exists() else []
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
    path.write_text("\n".join(new_lines) + "\n")


def uncomment_line(path: Path, line_idx: int) -> None:
    """Uncomment the line at line_idx."""
    lines = path.read_text().splitlines()
    if 0 <= line_idx < len(lines) and lines[line_idx].strip().startswith("#"):
        lines[line_idx] = lines[line_idx].lstrip("#").lstrip()
        path.write_text("\n".join(lines) + "\n")


def comment_active_for_key(path: Path, key: str) -> None:
    """Comment the active line for key."""
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(#?\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(3) == key and not line.strip().startswith("#"):
            lines[i] = "#" + line.lstrip()
            path.write_text("\n".join(lines) + "\n")
            return


def _read_choice(prompt: str, n: int) -> int | None:
    """Read a numbered menu choice from terminal.

    Returns the 1-based index on Enter, or None if ESC is pressed.
    Falls back to line-buffered input when stdin is not a tty.
    """
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
            ch = os.read(fd, 1).decode("utf-8", errors="ignore")  # bypass Python IO buffer
            if ch == "\x1b":                    # ESC
                sys.stdout.write(f" {DIM}(cancelled){W}\r\n")
                sys.stdout.flush()
                return None
            if ch in ("\r", "\n"):              # Enter
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                try:
                    idx = int(buf)
                    return idx if 1 <= idx <= n else None
                except ValueError:
                    return None
            if ch in ("\x7f", "\x08"):          # Backspace
                if buf:
                    buf = buf[:-1]
                    print("\b \b", end="", flush=True)
            elif ch.isdigit():
                buf += ch
                print(ch, end="", flush=True)
            elif ch == "\x03":                  # Ctrl-C
                raise KeyboardInterrupt
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_line(prompt: str) -> str | None:
    """Read a line of text from terminal with ESC-to-cancel support.

    Returns the entered string, or None if ESC is pressed.
    Falls back to input() when stdin is not a tty.
    """
    import termios
    import tty

    sys.stdout.write(f"\n {prompt}")
    sys.stdout.flush()

    if not sys.stdin.isatty():
        try:
            return input("").strip()
        except (EOFError, KeyboardInterrupt):
            return None

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    buf = ""
    try:
        tty.setraw(fd)
        while True:
            ch = os.read(fd, 1).decode("utf-8", errors="ignore")
            if ch == "\x1b":                    # ESC
                sys.stdout.write(f" {DIM}(cancelled){W}\r\n")
                sys.stdout.flush()
                return None
            if ch in ("\r", "\n"):              # Enter
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return buf
            if ch in ("\x7f", "\x08"):          # Backspace
                if buf:
                    buf = buf[:-1]
                    print("\b \b", end="", flush=True)
            elif ch == "\x03":                  # Ctrl-C
                raise KeyboardInterrupt
            elif ch >= " ":                     # printable
                buf += ch
                print(ch, end="", flush=True)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def prompt_choice(prompt: str, choices: list[str]) -> str | None:
    """Return choice string, or None if ESC was pressed."""
    while True:
        print(f"\n  {C}{prompt}{W}")
        for i, c in enumerate(choices, 1):
            print(f"    {B}[{i}]{W} {c}")
        try:
            idx = _read_choice(f"  Choice (1-{len(choices)}): ", len(choices))
        except KeyboardInterrupt:
            print(f"\n\n  {WARN} Interrupted — exiting.{W}\n")
            sys.exit(130)
        if idx is None:
            return None
        if 1 <= idx <= len(choices):
            return choices[idx - 1]
        print(f"  {WARN} Invalid choice{W}")


def _print_inactive(inact: list[tuple[int, str]], secret: bool = False) -> None:
    """Print numbered inactive entries."""
    if not inact:
        return
    print(f"  {C}Inactive:{W}")
    for i, (_, val) in enumerate(inact, 1):
        display = _redact(val) if secret else f"{val[:50]}{'...' if len(val) > 50 else ''}"
        print(f"    {C}[{i}]{W} {DIM}{display}{W}")


def _activate_entry(
    key: str,
    inact: list[tuple[int, str]],
    num: int,
    verify_fn,
    on_ok=None,
) -> None:
    """Uncomment inactive entry num, verify, call on_ok() on success."""
    if not (1 <= num <= len(inact)):
        return
    line_idx, val = inact[num - 1]
    comment_active_for_key(ENV_FILE, key)
    uncomment_line(ENV_FILE, line_idx)
    load_dotenv(ENV_FILE, override=True)
    load_env_for_key(key, val)
    ok, msg = verify_fn()
    if ok:
        print(f"  {OK} Activated and verified: {msg}{W}")
        print(f"\n  {CONF}✓  Entry activated.{W}")
        if on_ok:
            on_ok()
    else:
        print(f"  {FAIL} Activated but verify failed: {msg}{W}")
        abort_step()


def run_resource_warehouse() -> bool:
    """Interactive config for DATABRICKS_WAREHOUSE_ID with workspace list as choices."""
    load_dotenv(ENV_FILE, override=True)

    key = "DATABRICKS_WAREHOUSE_ID"
    active, inactive, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()
    inact = inactive.get(key, [])

    section("DATABRICKS_WAREHOUSE_ID")

    whs = list_warehouses()
    if whs:
        for name, wh_id in whs:
            print(f"  {C}Available :{W} {name} {DIM}({wh_id}){W}")

    ok, msg = False, ""
    if cur:
        load_env_for_key(key, cur)
        ok, msg = verify_warehouse()
        if ok:
            print(f"  {OK} Active: {C}{cur}{W} {G}({msg}){W}")
        else:
            print(f"  {FAIL} Active: {C}{cur}{W} {R}({msg}){W}")
    else:
        print(f"  {WARN} Not configured{W}")

    _print_inactive(inact)

    choices: list[str] = []
    if cur and ok:
        choices.append("keep")
    elif cur:
        choices.append("add new")
    else:
        choices.append("enter new")
    if whs:
        for name, wh_id in whs:
            choices.append(f"Available : {name} ({wh_id})")
        choices.append("enter ID manually")
    for i in range(1, len(inact) + 1):
        choices.append(f"activate [{i}]")
    if not choices:
        choices = ["enter new"]

    wh_choices = [f"Available : {n} ({i})" for n, i in whs]
    while True:
        print(f"\n  {C}Action?{W}")
        for i, c in enumerate(choices, 1):
            print(f"    {B}[{i}]{W} {c}")
        idx = _read_choice(f"  Choice (1-{len(choices)}): ", len(choices))
        if idx is None:
            return True
        if not (1 <= idx <= len(choices)):
            print(f"  {WARN} Invalid choice{W}")
            continue
        choice = choices[idx - 1]

        if choice == "keep":
            return True
        if choice and choice.startswith("activate ["):
            num = int(choice.split("[")[1].rstrip("]"))
            _activate_entry(key, inact, num, verify_warehouse)
            return True

        # Pick from list or manual
        if choice in wh_choices:
            val = whs[wh_choices.index(choice)][1]
        else:
            val = _read_line(f"Enter {key}: ")
            if val is None:
                continue   # ESC → back to menu
        if not val:
            return True
        if cur:
            comment_active_for_key(ENV_FILE, key)
        write_env_entry(ENV_FILE, key, val)
        load_dotenv(ENV_FILE, override=True)
        load_env_for_key(key, val)
        ok, msg = verify_warehouse()
        if ok:
            print(f"  {OK} Set and verified: {msg}{W}")
            print(f"\n  {CONF}✓  Warehouse configured.{W}")
        else:
            print(f"  {FAIL} Set but verify failed: {msg}{W}")
            abort_step()
        break
    return True


def _offer_create_pat() -> None:
    """Offer to create a 7-day PAT for the current workspace and save as DATABRICKS_TOKEN."""
    raw = _read_line(f"\n  {C}Create a 7-day PAT for this workspace and save as DATABRICKS_TOKEN? [y/N]: {W}")
    if raw is None or raw.lower() not in ("y", "yes"):
        print(f"  {DIM}Skipped{W}")
        return
    try:
        w = WorkspaceClient()
        response = w.tokens.create(comment="agent-forge init (7-day)", lifetime_seconds=604800)
        token_value = response.token_value
        if not token_value:
            print(f"  {FAIL} No token value returned{W}")
            return
        comment_active_for_key(ENV_FILE, "DATABRICKS_TOKEN")
        write_env_entry(ENV_FILE, "DATABRICKS_TOKEN", token_value)
        load_dotenv(ENV_FILE, override=True)
        masked = _redact(token_value)
        print(f"  {OK} PAT created (7 days) and saved as DATABRICKS_TOKEN: {C}{masked}{W}")
        print(f"\n  {CONF}✓  Token saved.{W}")
    except Exception as e:
        print(f"  {FAIL} Failed to create PAT: {e}{W}")


def run_resource_profile() -> bool:
    """Interactive config for DATABRICKS_CONFIG_PROFILE with CLI profile list as choices."""
    load_dotenv(ENV_FILE, override=True)

    key = "DATABRICKS_CONFIG_PROFILE"
    active, inactive, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()
    inact = inactive.get(key, [])

    section("DATABRICKS_CONFIG_PROFILE")

    profiles = list_dbx_profiles()
    if profiles:
        for name, valid in profiles:
            status = f"{G}[valid]{W}" if valid else f"{DIM}[invalid]{W}"
            print(f"  {C}Available :{W} {name} {status}")
    else:
        print(f"  {DIM}No profiles found (databricks auth profiles){W}")

    ok, msg = False, ""
    if cur:
        load_env_for_key(key, cur)
        ok, msg = verify_host_token()
        if ok:
            print(f"  {OK} Active: {C}{cur}{W} {G}({msg}){W}")
        else:
            print(f"  {FAIL} Active: {C}{cur}{W} {R}({msg}){W}")
    else:
        print(f"  {WARN} Not configured{W}")

    _print_inactive(inact)

    choices: list[str] = []
    if cur and ok:
        choices.append("keep")
    valid_profiles = [(n, v) for n, v in profiles if v]
    invalid_profiles = [(n, v) for n, v in profiles if not v]
    for name, _ in valid_profiles:
        choices.append(f"[+] {name}")
    for name, _ in invalid_profiles:
        choices.append(f"[-] {name}")
    choices.append("enter manually")
    for i in range(1, len(inact) + 1):
        choices.append(f"activate [{i}]")
    if not choices:
        choices = ["enter manually"]

    profile_choices = [f"[+] {n}" for n, _ in valid_profiles] + [f"[-] {n}" for n, _ in invalid_profiles]
    while True:
        print(f"\n  {C}Action?{W}")
        for i, c in enumerate(choices, 1):
            print(f"    {B}[{i}]{W} {c}")
        idx = _read_choice(f"  Choice (1-{len(choices)}): ", len(choices))
        if idx is None:
            continue
        if not (1 <= idx <= len(choices)):
            print(f"  {WARN} Invalid choice{W}")
            continue
        choice = choices[idx - 1]

        if choice == "keep":
            return True
        if choice and choice.startswith("activate ["):
            num = int(choice.split("[")[1].rstrip("]"))
            _activate_entry(key, inact, num, verify_host_token, on_ok=_offer_create_pat)
            return True

        # Pick from profile list or enter manually
        if choice in profile_choices:
            val = choice.split("] ", 1)[1]
        else:
            val = _read_line(f"Enter profile name: ")
            if val is None:
                continue   # ESC → back to menu
        if not val:
            return True
        if cur:
            comment_active_for_key(ENV_FILE, key)
        write_env_entry(ENV_FILE, key, val)
        load_dotenv(ENV_FILE, override=True)
        load_env_for_key(key, val)
        ok, msg = verify_host_token()
        if ok:
            print(f"  {OK} Set and verified: {msg}{W}")
            _offer_create_pat()
            print(f"\n  {CONF}✓  Profile configured.{W}")
        else:
            print(f"  {FAIL} Set but verify failed: {msg}{W}")
            abort_step()
        break
    return True


def run_resource_genie() -> bool:
    """Interactive config for PROJECT_GENIE_CHECKIN with Genie space list as choices."""
    load_dotenv(ENV_FILE, override=True)

    key = "PROJECT_GENIE_CHECKIN"
    active, inactive, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()
    inact = inactive.get(key, [])

    section("PROJECT_GENIE_CHECKIN")

    spaces = list_genie_spaces()
    if spaces:
        for title, space_id in spaces:
            print(f"  {C}Available :{W} {title} {DIM}({space_id}){W}")

    ok, msg = False, ""
    if cur:
        load_env_for_key(key, cur)
        ok, msg = verify_genie()
        if ok:
            print(f"  {OK} Active: {C}{cur}{W} {G}({msg}){W}")
        else:
            print(f"  {FAIL} Active: {C}{cur}{W} {R}({msg}){W}")
    else:
        print(f"  {WARN} Not configured{W}")

    _print_inactive(inact)

    choices: list[str] = []
    if cur and ok:
        choices.append("keep")
    if spaces:
        for title, space_id in spaces:
            choices.append(f"Available : {title} ({space_id})")
    choices.append("enter space ID")
    choices.append("Create Genie Room")
    for i in range(1, len(inact) + 1):
        choices.append(f"activate [{i}]")

    # When no spaces from API: still show choices (enter space ID, Create Genie Room)
    # Don't block - list_spaces can return empty due to permissions/API behavior
    space_choices = [f"Available : {t} ({i})" for t, i in spaces]
    while True:
        choice = prompt_choice("Action?", choices)
        if choice is None:
            print(f"  {DIM}Skipped{W}")
            return True

        if choice == "keep":
            return True
        if choice == "Create Genie Room":
            room_name = _read_line(f"Genie room name: ")
            if room_name is None:
                continue   # ESC → back to menu
            if not room_name:
                print(f"  {WARN} No name entered. Skipped.{W}\n")
                return True
            env = {**os.environ, "GENIE_ROOM_NAME": room_name}
            print(f"  {B}Creating Genie space '{room_name}' ...{W}\n")
            rc = subprocess.call(
                ["uv", "run", "python", "data/init/create_genie_space.py"],
                cwd=ROOT,
                env=env,
            )
            if rc == 0:
                load_dotenv(ENV_FILE, override=True)
                new_id = os.environ.get(key, "").strip()
                if new_id:
                    print(f"\n  {OK} {G}Genie Room created: {new_id}{W}\n")
                    print(f"  {CONF}✓  Genie Room created.{W}")
                else:
                    print(f"\n  {OK} {G}Genie Room created. Re-run to verify.{W}\n")
                    print(f"  {CONF}✓  Genie Room created.{W}")
            else:
                print(f"\n  {FAIL} Genie creation exited with {rc}{W}\n")
                abort_step()
            return True
        if choice and choice.startswith("activate ["):
            num = int(choice.split("[")[1].rstrip("]"))
            _activate_entry(key, inact, num, verify_genie)
            return True

        # Pick from list or manual
        if choice in space_choices:
            val = spaces[space_choices.index(choice)][1]
        else:
            val = _read_line(f"Enter {key}: ")
            if val is None:
                continue   # ESC → back to menu
        if not val:
            return True
        if cur:
            comment_active_for_key(ENV_FILE, key)
        write_env_entry(ENV_FILE, key, val)
        load_dotenv(ENV_FILE, override=True)
        load_env_for_key(key, val)
        ok, msg = verify_genie()
        if ok:
            print(f"  {OK} Set and verified: {msg}{W}")
            print(f"\n  {CONF}✓  Genie space configured.{W}")
        else:
            print(f"  {FAIL} Set but verify failed: {msg}{W}")
            abort_step()
        break
    return True


def run_resource_host() -> bool:
    """Interactive config for DATABRICKS_HOST — lists available profiles as workspace options."""
    load_dotenv(ENV_FILE, override=True)

    key = "DATABRICKS_HOST"
    active, _, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()

    section("Connection: DATABRICKS_HOST")

    profiles = list_dbx_profiles()

    if cur:
        ok, msg = verify_host_only()
        if ok:
            print(f"  {OK} Active: {C}{cur}{W}")
        else:
            print(f"  {FAIL} Active: {C}{cur}{W} {R}({msg}){W}")
        choices = ["keep", "enter host URL manually"]
    else:
        print(f"  {WARN} Not configured{W}")
        choices = ["enter host URL manually"]

    if profiles:
        print(f"\n  {DIM}Available workspaces (from Databricks CLI profiles):{W}")
        for name, valid in profiles:
            status = f"{G}[valid]{W}" if valid else f"{DIM}[invalid]{W}"
            print(f"    {C}•{W} {name} {status}")
        # Insert "use profile workspace" after "keep" if keep is present, else prepend
        if "keep" in choices:
            choices.insert(1, "use profile workspace")
        else:
            choices.insert(0, "use profile workspace")

    choices.append("set up a new workspace profile")

    while True:
        print(f"\n  {C}Action?{W}")
        for i, c in enumerate(choices, 1):
            print(f"    {B}[{i}]{W} {c}")
        idx = _read_choice(f"  Choice (1-{len(choices)}): ", len(choices))
        if idx is None:
            continue
        if not (1 <= idx <= len(choices)):
            continue
        choice = choices[idx - 1]

        if choice == "keep":
            return True

        if choice == "use profile workspace":
            # Let user pick a specific profile → extract its host
            print(f"\n  {C}Pick a profile:{W}")
            for i, (name, valid) in enumerate(profiles, 1):
                status = f"{G}[valid]{W}" if valid else f"{DIM}[invalid]{W}"
                print(f"    {B}[{i}]{W} {name} {status}")
            pidx = _read_choice(f"  Choice (1-{len(profiles)}): ", len(profiles))
            if pidx is None or not (1 <= pidx <= len(profiles)):
                continue
            profile_name = profiles[pidx - 1][0]

            # Extract host from `databricks auth env --profile <name>`
            host = ""
            try:
                result = subprocess.run(
                    ["databricks", "auth", "env", "--profile", profile_name],
                    capture_output=True, text=True,
                )
                for line in result.stdout.splitlines():
                    if "DATABRICKS_HOST" in line:
                        host = line.split("=", 1)[-1].strip().strip('"').strip("'")
                        break
            except Exception:
                host = ""

            if not host:
                print(f"  {WARN} Could not extract host for profile {profile_name} — enter manually{W}")
                host = _read_line(f"Enter DATABRICKS_HOST: ")

            if not host:
                continue

            # Set DATABRICKS_HOST + pre-set DATABRICKS_CONFIG_PROFILE
            if cur:
                comment_active_for_key(ENV_FILE, key)
            write_env_entry(ENV_FILE, key, host)
            comment_active_for_key(ENV_FILE, "DATABRICKS_CONFIG_PROFILE")
            write_env_entry(ENV_FILE, "DATABRICKS_CONFIG_PROFILE", profile_name)
            load_dotenv(ENV_FILE, override=True)
            load_env_for_key(key, host)
            print(f"  {OK} Host set: {C}{host}{W}")
            print(f"  {OK} Profile pre-set: {C}{profile_name}{W}")
            print(f"\n  {CONF}✓  Workspace configured.{W}")
            return True

        if choice == "set up a new workspace profile":
            new_host = _read_line("Workspace URL (https://....databricks.com): ")
            if not new_host:
                continue
            if not new_host.startswith("http"):
                new_host = f"https://{new_host}"
            default_pname = new_host.split("//")[-1].split(".")[0]
            pname = _read_line(f"Profile name [{default_pname}]: ")
            if pname is None:
                continue
            if not pname:
                pname = default_pname
            print(f"\n  {C}Running: databricks auth login --host {new_host} --profile {pname}{W}")
            rc = subprocess.call(
                ["databricks", "auth", "login", "--host", new_host, "--profile", pname],
                cwd=ROOT,
            )
            if rc != 0:
                print(f"  {FAIL} databricks auth login failed (exit {rc}){W}")
                continue
            raw = _read_line("Press Enter once browser login is complete, or ESC to cancel: ")
            if raw is None:
                continue
            if cur:
                comment_active_for_key(ENV_FILE, key)
            write_env_entry(ENV_FILE, key, new_host)
            comment_active_for_key(ENV_FILE, "DATABRICKS_CONFIG_PROFILE")
            write_env_entry(ENV_FILE, "DATABRICKS_CONFIG_PROFILE", pname)
            load_dotenv(ENV_FILE, override=True)
            load_env_for_key(key, new_host)
            print(f"  {OK} Host set: {C}{new_host}{W}")
            print(f"  {OK} Profile set: {C}{pname}{W}")
            print(f"\n  {CONF}✓  Workspace configured.{W}")
            return True

        # Manual entry
        val = _read_line(f"Enter DATABRICKS_HOST (https://....databricks.com): ")
        if not val:
            continue
        if cur:
            comment_active_for_key(ENV_FILE, key)
        write_env_entry(ENV_FILE, key, val)
        load_dotenv(ENV_FILE, override=True)
        load_env_for_key(key, val)
        ok, msg = verify_host_only()
        if ok:
            print(f"  {OK} Set: {C}{val}{W}")
            print(f"\n  {CONF}✓  Host configured.{W}")
        else:
            print(f"  {FAIL} {msg}{W}")
            abort_step()
        return True


def verify_host_only() -> tuple[bool, str]:
    """Verify DATABRICKS_HOST is set and looks like a URL."""
    host = os.environ.get("DATABRICKS_HOST", "").strip()
    if not host:
        return False, "not set"
    if not host.startswith("https://") and not host.startswith("http://"):
        return False, "should be https://... or http://..."
    return True, host


def verify_host_token() -> tuple[bool, str]:
    """Verify DATABRICKS_HOST + token/profile work. Return (ok, msg)."""
    import json
    import urllib.error
    import urllib.request
    host = os.environ.get("DATABRICKS_HOST", "").strip().rstrip("/")
    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "").strip()
    if not host:
        return False, "DATABRICKS_HOST not set"
    if token:
        # Verify the PAT directly via raw HTTP — no SDK fallback chains
        try:
            req = urllib.request.Request(
                f"{host}/api/2.0/preview/scim/v2/Me",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return True, f"OK → {host} ({data.get('userName', '?')})"
        except urllib.error.HTTPError as e:
            return False, f"HTTP {e.code} — token invalid or wrong workspace"
        except Exception as e:
            return False, str(e)
    elif profile:
        # Profile auth — use SDK (no token to test directly)
        try:
            w = WorkspaceClient(host=host, profile=profile)
            me = w.current_user.me()
            return True, f"OK → {host} ({me.user_name})"
        except Exception as e:
            return False, str(e)
    else:
        return False, "Need DATABRICKS_TOKEN or DATABRICKS_CONFIG_PROFILE"


def verify_warehouse() -> tuple[bool, str]:
    wh = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
    if not wh:
        return False, "not set"
    try:
        w = WorkspaceClient()
        wh_obj = w.warehouses.get(wh)
        return True, getattr(wh_obj, "name", wh)
    except Exception as e:
        return False, str(e)


def list_warehouses() -> list[tuple[str, str]]:
    """Return [(name, id), ...] for warehouses in workspace."""
    try:
        w = WorkspaceClient()
        whs = list(w.warehouses.list())
        return [(getattr(wh, "name", "") or str(wh.id), str(wh.id)) for wh in whs]
    except Exception:
        return []


def list_dbx_profiles() -> list[tuple[str, bool]]:
    """Return [(name, valid), ...] from `databricks auth profiles`."""
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
                valid = parts[-1].upper() == "YES"
                profiles.append((name, valid))
        return profiles
    except Exception:
        return []


def _isolated_client(profile: str) -> "WorkspaceClient":
    """Create a WorkspaceClient using only profile credentials.

    Temporarily removes Databricks env vars so they don't override the
    profile's token in the SDK auth chain (env vars take priority over
    profile config, causing cross-workspace PAT creation to fail with 400).
    """
    _DBX_ENV_KEYS = [
        "DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_CONFIG_PROFILE",
        "DATABRICKS_AZURE_CLIENT_ID", "DATABRICKS_AZURE_CLIENT_SECRET",
        "DATABRICKS_AZURE_TENANT_ID", "DATABRICKS_USERNAME", "DATABRICKS_PASSWORD",
    ]
    saved = {k: os.environ.pop(k) for k in _DBX_ENV_KEYS if k in os.environ}
    try:
        return WorkspaceClient(profile=profile)
    finally:
        os.environ.update(saved)


def list_dbx_profiles_with_host() -> list[tuple[str, str, bool]]:
    """Return [(name, host, valid), ...] from `databricks auth profiles` (includes host column)."""
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


def list_genie_spaces() -> list[tuple[str, str]]:
    """Return [(title, space_id), ...] for Genie spaces in workspace."""
    try:
        w = WorkspaceClient()
        r = w.genie.list_spaces()
        spaces = getattr(r, "spaces", []) or []
        return [
            (getattr(s, "title", "") or "?", str(getattr(s, "space_id", None) or getattr(s, "id", "") or ""))
            for s in spaces
        ]
    except Exception:
        return []


def list_serving_endpoints() -> list[tuple[str, str]]:
    """Return [(name, ready_state), ...] for serving endpoints in workspace."""
    try:
        w = WorkspaceClient()
        endpoints = list(w.serving_endpoints.list())
        result = []
        for ep in endpoints:
            name = getattr(ep, "name", "") or ""
            state = getattr(ep, "state", None)
            ready = str(getattr(state, "ready", "") or "") if state else ""
            result.append((name, ready))
        return result
    except Exception:
        return []


def get_csv_tables() -> list[str]:
    """Return table names derived from data/csv/*.csv (stem, - replaced with _)."""
    csv_dir = ROOT / "data" / "csv"
    if not csv_dir.exists():
        return []
    return sorted(p.stem.replace("-", "_") for p in csv_dir.glob("*.csv"))


TABLES_TO_VERIFY = get_csv_tables()


def _infer_sql_type(col: str) -> str:
    low = col.lower()
    if any(k in low for k in ("time", "date", "timestamp", "at", "created", "updated")):
        return "TIMESTAMP_NTZ"
    if any(k in low for k in ("id",)):
        return "BIGINT"
    return "STRING"


def _generate_create_sql(table: str, csv_path: Path) -> str:
    """Generate a CREATE OR REPLACE TABLE stub from CSV header."""
    import csv as csv_mod
    from io import StringIO
    header = csv_path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    if header:
        row = next(csv_mod.reader(StringIO(header[0])))
        col_defs = ",\n".join(f"    {c} {_infer_sql_type(c)}" for c in row)
    else:
        col_defs = "    -- no columns detected"
    return (
        f"CREATE OR REPLACE TABLE __SCHEMA_QUALIFIED__.{table} (\n"
        f"{col_defs}\n"
        f")\n"
        f"USING DELTA\n"
        f"TBLPROPERTIES (delta.enableChangeDataFeed = true);\n"
    )


def ensure_init_sql_files() -> list[Path]:
    """Check data/csv/*.csv against data/init/create_<table>.sql. Generate stubs for missing ones.
    Returns list of all init SQL paths (existing + newly created)."""
    csv_dir = ROOT / "data" / "csv"
    init_dir = ROOT / "data" / "init"
    if not csv_dir.exists():
        return []
    csvs = sorted(csv_dir.glob("*.csv"))
    if not csvs:
        return []

    print(f"\n  {C}Checking SQL init files for {len(csvs)} CSV(s):{W}")
    sql_paths: list[Path] = []
    for csv_path in csvs:
        table = csv_path.stem.replace("-", "_")
        sql_path = init_dir / f"create_{table}.sql"
        if sql_path.exists():
            print(f"  [+] {sql_path.relative_to(ROOT)}  {DIM}(exists){W}")
        else:
            content = _generate_create_sql(table, csv_path)
            sql_path.write_text(content)
            print(f"  [+] {sql_path.relative_to(ROOT)}  {G}(generated){W}")
        sql_paths.append(sql_path)
    return sql_paths


def print_asset_checks() -> None:
    """Print catalog, schema, tables, volume checks (same as create_all_assets, excluding Genie)."""
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if "." not in spec:
        return
    catalog, schema_name = spec.split(".", 1)
    full_schema = f"{catalog}.{schema_name}"
    try:
        w = WorkspaceClient()
        try:
            w.catalogs.get(name=catalog)
            print(f"  {OK} catalog {C}({catalog}){W}")
        except Exception as e:
            print(f"  {FAIL} catalog {C}({e}){W}")
        try:
            w.schemas.get(full_name=full_schema)
            print(f"  {OK} schema {C}({full_schema}){W}")
        except Exception as e:
            print(f"  {FAIL} schema {C}({e}){W}")
        for name in TABLES_TO_VERIFY:
            full_name = f"{full_schema}.{name}"
            try:
                w.tables.get(full_name)
                print(f"  {OK} {name} {C}({full_name}){W}")
            except Exception as e:
                print(f"  {FAIL} {name} {C}({e}){W}")
    except Exception as e:
        print(f"  {FAIL} assets {C}({e}){W}")


def verify_schema() -> tuple[bool, str]:
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if "." not in spec:
        return False, "need catalog.schema"
    try:
        w = WorkspaceClient()
        w.schemas.get(full_name=spec)
        return True, spec
    except Exception as e:
        return False, str(e)


def verify_tables() -> tuple[bool, str]:
    """Verify checkin_metrics, flights, checkin_agents, border_officers, border_terminals exist. Return (ok, msg)."""
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if "." not in spec:
        return False, "PROJECT_UNITY_CATALOG_SCHEMA not set"
    catalog, schema_name = spec.split(".", 1)
    full_schema = f"{catalog}.{schema_name}"
    tables = TABLES_TO_VERIFY
    missing = []
    try:
        w = WorkspaceClient()
        for name in tables:
            try:
                w.tables.get(full_name=f"{full_schema}.{name}")
            except Exception:
                missing.append(name)
        if missing:
            return False, f"missing: {', '.join(missing)}"
        return True, full_schema
    except Exception as e:
        return False, str(e)


def verify_genie() -> tuple[bool, str]:
    sid = os.environ.get("PROJECT_GENIE_CHECKIN", "").strip()
    if not sid:
        return False, "not set"
    try:
        w = WorkspaceClient()
        sp = w.genie.get_space(space_id=sid)
        return True, getattr(sp, "title", sid)
    except Exception as e:
        return False, str(e)


def verify_model_endpoint() -> tuple[bool, str]:
    endpoint = os.environ.get("AGENT_MODEL_ENDPOINT", "").strip()
    if not endpoint:
        return False, "not set"
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        # Full URL — accept as-is, no SDK lookup possible
        return True, f"URL ({endpoint})"
    try:
        w = WorkspaceClient()
        ep = w.serving_endpoints.get(name=endpoint)
        state = getattr(ep, "state", None)
        ready = str(getattr(state, "ready", "") or "") if state else ""
        return True, f"{endpoint} ({ready or 'OK'})"
    except Exception as e:
        return False, str(e)


def _fm_invocations_url(base_host: str) -> str:
    """Build the full invocations URL for the foundation model on a given workspace host."""
    return f"{base_host.rstrip('/')}/serving-endpoints/{FM_MODEL}/invocations"


def _save_endpoint_and_token(key: str, cur: str, endpoint_url: str, token_val: str | None) -> None:
    """Save AGENT_MODEL_ENDPOINT and optionally AGENT_MODEL_TOKEN to .env.local."""
    if cur:
        comment_active_for_key(ENV_FILE, key)
    write_env_entry(ENV_FILE, key, endpoint_url)
    load_dotenv(ENV_FILE, override=True)
    load_env_for_key(key, endpoint_url)
    print(f"  {OK} AGENT_MODEL_ENDPOINT set: {C}{endpoint_url}{W}")
    if token_val:
        comment_active_for_key(ENV_FILE, "AGENT_MODEL_TOKEN")
        write_env_entry(ENV_FILE, "AGENT_MODEL_TOKEN", token_val)
        load_dotenv(ENV_FILE, override=True)
        load_env_for_key("AGENT_MODEL_TOKEN", token_val)
        masked = _redact(token_val)
        print(f"  {OK} AGENT_MODEL_TOKEN set:     {C}{masked}{W}")
        print(f"\n  {CONF}✓  Model endpoint and token configured.{W}")
    else:
        print(f"  {WARN} AGENT_MODEL_TOKEN not set — configure it in the next step{W}")
        print(f"\n  {CONF}✓  Model endpoint configured.{W}")


def run_resource_model_endpoint() -> bool:
    """Interactive config for AGENT_MODEL_ENDPOINT with serving endpoint list as choices."""
    load_dotenv(ENV_FILE, override=True)

    key = "AGENT_MODEL_ENDPOINT"
    active, inactive, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()
    inact = inactive.get(key, [])

    section("AGENT_MODEL_ENDPOINT")

    # fevm detection
    current_host = os.environ.get("DATABRICKS_HOST", "").strip()
    is_fevm = "fevm" in current_host.lower()
    if is_fevm:
        print(f"\n  {BOLD}{R}⚠  Current workspace ({current_host}) applies zero rate limits{W}")
        print(f"  {BOLD}{R}   to foundation models — its endpoints cannot be used here.{W}")

    # FM workspace guidance — always shown
    print(f"\n  {C}Foundation model endpoints require one of these workspaces:{W}")
    for label, fmhost in FM_WORKSPACES:
        print(f"    {DIM}• {label}: {fmhost}{W}")

    # Find matching CLI profiles
    all_profiles = list_dbx_profiles_with_host()
    fm_profiles: list[tuple[str, str, bool]] = []  # (name, host, valid)
    for pname, phost, pvalid in all_profiles:
        for _, fmhost in FM_WORKSPACES:
            if fmhost.split("//")[1].rstrip("/") in phost.rstrip("/"):
                fm_profiles.append((pname, phost, pvalid))
                break
    if fm_profiles:
        print(f"\n  {G}Matching CLI profiles found:{W}")
        for pname, phost, pvalid in fm_profiles:
            status = f"{G}[valid]{W}" if pvalid else f"{DIM}[invalid]{W}"
            print(f"    {C}[+]{W} {pname} → {DIM}{phost}{W} {status}")
    else:
        print(f"\n  {DIM}No matching CLI profiles — you can create one below.{W}")

    endpoints: list[tuple[str, str]] = []
    if not is_fevm:
        endpoints = list_serving_endpoints()
        if endpoints:
            print()
            for name, state in endpoints:
                status = f"{G}[{state}]{W}" if state == "READY" else f"{DIM}[{state or '?'}]{W}"
                print(f"  {C}Available :{W} {name} {status}")
        else:
            print(f"  {DIM}No serving endpoints found (or could not connect){W}")

    ok, msg = False, ""
    if cur:
        load_env_for_key(key, cur)
        ok, msg = verify_model_endpoint()
        if ok:
            print(f"  {OK} Active: {C}{cur}{W} {G}({msg}){W}")
        else:
            print(f"  {FAIL} Active: {C}{cur}{W} {R}({msg}){W}")
    else:
        print(f"  {WARN} Not configured{W}")

    _print_inactive(inact)

    # Build choices
    choices: list[str] = []
    if cur and ok:
        choices.append("keep")
    # FM profile shortcuts
    for pname, phost, _ in fm_profiles:
        choices.append(f"use profile: {pname} ({phost})")
    # FM workspace setup
    for label, fmhost in FM_WORKSPACES:
        short = fmhost.split("//")[1].split(".")[0]
        choices.append(f"set up: {label} ({short})")
    # Available endpoints from current workspace
    if endpoints:
        for name, _ in endpoints:
            choices.append(f"Available : {name}")
    for i in range(1, len(inact) + 1):
        choices.append(f"activate [{i}]")

    all_choices = choices + ["enter endpoint name or URL manually"]
    ep_choices = [f"Available : {n}" for n, _ in endpoints]
    use_profile_choices = [f"use profile: {pname} ({phost})" for pname, phost, _ in fm_profiles]
    setup_choices = [f"set up: {label} ({fmhost.split('//')[1].split('.')[0]})" for label, fmhost in FM_WORKSPACES]

    while True:
        print(f"\n  {C}Action?{W}")
        for i, c in enumerate(choices, 1):
            print(f"    {B}[{i}]{W} {c}")
        print(f"\n    {B}[{len(all_choices)}]{W} enter endpoint name or URL manually")
        idx = _read_choice(f"  Choice (1-{len(all_choices)}): ", len(all_choices))
        if idx is None:
            return True
        if not (1 <= idx <= len(all_choices)):
            print(f"  {WARN} Invalid choice{W}")
            continue
        choice = all_choices[idx - 1]

        if choice == "keep":
            return True

        if choice and choice.startswith("activate ["):
            num = int(choice.split("[")[1].rstrip("]"))
            _activate_entry(key, inact, num, verify_model_endpoint)
            return True

        # Use an existing matching CLI profile
        if choice in use_profile_choices:
            pidx = use_profile_choices.index(choice)
            pname, phost, _ = fm_profiles[pidx]
            endpoint_url = _fm_invocations_url(phost)
            print(f"\n  {C}Generating 7-day PAT for profile {pname} ...{W}")
            try:
                w = _isolated_client(pname)
                t = w.tokens.create(comment="agent-forge FM endpoint (7-day)", lifetime_seconds=604800)
                if not t.token_value:
                    raise ValueError("No token value returned")
                _save_endpoint_and_token(key, cur, endpoint_url, t.token_value)
            except Exception as e:
                print(f"  {FAIL} Could not generate PAT: {e}{W}")
                print(f"  {DIM}Enter a PAT manually instead:{W}")
                pat = _read_line("PAT for this workspace: ")
                if not pat:
                    continue
                _save_endpoint_and_token(key, cur, endpoint_url, pat)
            return True

        # Set up a new CLI profile for a FM workspace
        if choice in setup_choices:
            sidx = setup_choices.index(choice)
            fm_label, fm_base_host = FM_WORKSPACES[sidx]
            default_name = "e2-demo-field-eng-aws" if sidx == 0 else "adb-field-eng-azure"
            print(f"\n  {C}Setting up CLI profile for {fm_label}{W}")
            print(f"  {DIM}Host: {fm_base_host}{W}")

            pname = _read_line(f"Profile name [{default_name}]: ")
            if pname is None:
                continue
            if not pname:
                pname = default_name

            print(f"\n  {C}Running: databricks auth login --host {fm_base_host} --profile {pname}{W}")
            rc = subprocess.call(
                ["databricks", "auth", "login", "--host", fm_base_host, "--profile", pname],
                cwd=ROOT,
            )
            if rc != 0:
                print(f"  {FAIL} databricks auth login failed (exit {rc}){W}")
                continue

            print(f"  {OK} Profile '{pname}' configured{W}")

            raw = _read_line("Press Enter once browser login is complete, or ESC to cancel: ")
            if raw is None:
                continue

            endpoint_url = _fm_invocations_url(fm_base_host)
            print(f"  {C}Generating 7-day PAT ...{W}")
            token_val: str | None = None
            try:
                w = _isolated_client(pname)
                t = w.tokens.create(comment="agent-forge FM endpoint (7-day)", lifetime_seconds=604800)
                token_val = t.token_value
            except Exception as e:
                print(f"  {FAIL} PAT generation failed ({type(e).__name__}: {e}){W}")
                continue

            _save_endpoint_and_token(key, cur, endpoint_url, token_val)
            return True

        # Pick from available endpoints on current workspace
        if choice in ep_choices:
            val = endpoints[ep_choices.index(choice)][0]
        else:
            val = _read_line("Enter endpoint name or full URL: ")
            if val is None:
                continue
        if not val:
            return True
        if cur:
            comment_active_for_key(ENV_FILE, key)
        write_env_entry(ENV_FILE, key, val)
        load_dotenv(ENV_FILE, override=True)
        load_env_for_key(key, val)
        ok, msg = verify_model_endpoint()
        if ok:
            print(f"  {OK} Set and verified: {msg}{W}")
            print(f"\n  {CONF}✓  Model endpoint configured.{W}")
        else:
            print(f"  {FAIL} Set but verify failed: {msg}{W}")
            abort_step()
        break
    return True


def _endpoint_is_url() -> bool:
    """Return True if AGENT_MODEL_ENDPOINT is currently set to a full URL."""
    ep = os.environ.get("AGENT_MODEL_ENDPOINT", "").strip()
    return ep.startswith("http://") or ep.startswith("https://")


def run_resource_model_token() -> bool:
    """Interactive config for AGENT_MODEL_TOKEN (only relevant when endpoint is a cross-workspace URL)."""
    load_dotenv(ENV_FILE, override=True)

    if not _endpoint_is_url():
        return True  # local endpoint name — token not needed

    key = "AGENT_MODEL_TOKEN"
    active, _, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()

    section("AGENT_MODEL_TOKEN")
    print(f"  {DIM}Cross-workspace endpoint detected — a PAT for that workspace is required.{W}")

    if cur:
        masked = _redact(cur)
        print(f"  {OK} Active: {C}{masked}{W}")
        choices = ["keep", "replace"]
    else:
        print(f"  {WARN} Not set{W}")
        choices = ["enter"]

    while True:
        print(f"\n  {C}Action?{W}")
        for i, c in enumerate(choices, 1):
            print(f"    {B}[{i}]{W} {c}")
        idx = _read_choice(f"  Choice (1-{len(choices)}): ", len(choices))
        if idx is None:
            return True
        if not (1 <= idx <= len(choices)):
            print(f"  {WARN} Invalid choice{W}")
            continue
        choice = choices[idx - 1]

        if choice == "keep":
            return True

        val = _read_line(f"Enter PAT for the endpoint workspace: ")
        if val is None:
            continue   # ESC → back to menu
        if not val:
            print(f"  {WARN} Skipped{W}")
            return True

        comment_active_for_key(ENV_FILE, key)
        write_env_entry(ENV_FILE, key, val)
        load_dotenv(ENV_FILE, override=True)
        print(f"  {OK} AGENT_MODEL_TOKEN set{W}")
        print(f"\n  {CONF}✓  Cross-workspace token saved.{W}")
        break
    return True


def run_resource_mlflow() -> bool:
    """Interactive config for MLFLOW_EXPERIMENT_ID with keep, enter ID manually, create new experiment."""
    load_dotenv(ENV_FILE, override=True)

    key = "MLFLOW_EXPERIMENT_ID"
    active, inactive, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()
    inact = inactive.get(key, [])

    section("MLFLOW_EXPERIMENT_ID")

    ok, msg = False, ""
    if cur:
        load_env_for_key(key, cur)
        ok, msg = verify_mlflow()
        if ok:
            print(f"  {OK} Active: {C}{cur}{W} {G}({msg}){W}")
        else:
            print(f"  {FAIL} Active: {C}{cur}{W} {R}({msg}){W}")
    else:
        print(f"  {WARN} Not configured{W}")

    _print_inactive(inact)

    choices: list[str] = []
    if cur and ok:
        choices.append("keep")
    choices.append("enter ID manually")
    choices.append("create new experiment")
    for i in range(1, len(inact) + 1):
        choices.append(f"activate [{i}]")

    while True:
        choice = prompt_choice("Action?", choices)
        if choice is None:
            print(f"  {DIM}Skipped{W}")
            return True

        if choice == "keep":
            return True
        if choice == "create new experiment":
            try:
                print(f"  {B}Creating MLflow experiment ...{W}\n")
                rc = subprocess.call(
                    ["uv", "run", "python", "data/init/create_mlflow_experiment.py"],
                    cwd=ROOT,
                )
                if rc == 0:
                    load_dotenv(ENV_FILE, override=True)
                    new_id = os.environ.get(key, "").strip()
                    if new_id:
                        print(f"\n  {OK} {G}MLflow experiment created: {new_id}{W}\n")
                        print(f"  {CONF}✓  MLflow experiment created.{W}")
                    else:
                        print(f"\n  {OK} {G}MLflow experiment created. Re-run to verify.{W}\n")
                        print(f"  {CONF}✓  MLflow experiment created.{W}")
                else:
                    print(f"\n  {FAIL} MLflow creation exited with {rc}{W}\n")
                    abort_step()
            except (EOFError, KeyboardInterrupt):
                print(f"  {DIM}Skipped{W}\n")
            return True
        if choice and choice.startswith("activate ["):
            num = int(choice.split("[")[1].rstrip("]"))
            _activate_entry(key, inact, num, verify_mlflow)
            return True

        # enter ID manually
        val = _read_line(f"Enter {key}: ")
        if val is None:
            continue  # ESC → back to menu
        if not val:
            return True
        if cur:
            comment_active_for_key(ENV_FILE, key)
        write_env_entry(ENV_FILE, key, val)
        load_dotenv(ENV_FILE, override=True)
        load_env_for_key(key, val)
        ok, msg = verify_mlflow()
        if ok:
            print(f"  {OK} Set and verified: {msg}{W}")
            print(f"\n  {CONF}✓  MLflow experiment configured.{W}")
        else:
            print(f"  {FAIL} Set but verify failed: {msg}{W}")
            abort_step()
        break
    return True


def verify_mlflow() -> tuple[bool, str]:
    eid = os.environ.get("MLFLOW_EXPERIMENT_ID", "").strip()
    if not eid:
        return False, "not set"
    try:
        w = WorkspaceClient()
        exp = w.experiments.get_experiment(experiment_id=eid)
        return True, getattr(exp, "name", eid)
    except Exception as e:
        return False, str(e)


def verify_app_grants() -> tuple[bool, list[str]]:
    """Verify all grants from run_all_grants.sh are effective for the app service principal.
    Returns (ok, list of issue messages).
    """
    from tools.sql_executor import execute_query, get_warehouse

    app_name = os.environ.get("DBX_APP_NAME", "").strip()
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    wh_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()

    issues: list[str] = []

    if not app_name:
        return False, ["DBX_APP_NAME not set"]
    if "." not in spec:
        return False, ["PROJECT_UNITY_CATALOG_SCHEMA not set (need catalog.schema)"]
    catalog, schema_name = spec.split(".", 1)

    try:
        w = WorkspaceClient()
        w_client, wh_id_sql = get_warehouse()

        # Get app service principal ID
        try:
            app = w.apps.get(name=app_name)
        except Exception as e:
            return False, [f"App '{app_name}' not yet deployed — grants will be applied after deployment, then re-run to verify"]

        sp_id = getattr(app, "service_principal_client_id", None) or getattr(
            app, "oauth2_app_client_id", None
        )
        if not sp_id:
            return False, [f"App '{app_name}' has no service_principal_client_id"]

        # 1. Check UC catalog/schema/table privileges (run_all_grants: grant_app_tables)
        table_priv_sql = f"""
        SELECT table_name, privilege_type
        FROM `{catalog}`.information_schema.table_privileges
        WHERE table_schema = '{schema_name}' AND grantee = '{sp_id}'
        """
        try:
            _, table_rows = execute_query(w_client, wh_id_sql, table_priv_sql)
        except Exception as e:
            issues.append(f"UC table privileges: could not verify ({e})")
        else:
            granted_tables = {
                r[0]
                for r in table_rows
                if r[1] and ("SELECT" in r[1] or "ALL PRIVILEGES" in r[1])
            }
            for t in TABLES_TO_VERIFY:
                if t not in granted_tables:
                    issues.append(f"Table {t}: app has no SELECT/ALL_PRIVILEGES")
            if not table_rows and TABLES_TO_VERIFY:
                issues.append("UC tables: app has no table privileges")

        # 2. Check UC routine privileges (run_all_grants: grant_app_functions)
        routine_priv_sql = f"""
        SELECT routine_name, privilege_type
        FROM `{catalog}`.information_schema.routine_privileges
        WHERE routine_schema = '{schema_name}' AND grantee = '{sp_id}'
        """
        try:
            _, routine_rows = execute_query(w_client, wh_id_sql, routine_priv_sql)
        except Exception as e:
            issues.append(f"UC routine privileges: could not verify ({e})")
        else:
            has_execute = any(r[1] and "EXECUTE" in r[1] for r in routine_rows)
            if not has_execute:
                issues.append("UC routines: app has no EXECUTE on procedures")

        # 3. Check warehouse CAN_USE (run_all_grants: authorize_warehouse_for_app)
        if not wh_id:
            issues.append("DATABRICKS_WAREHOUSE_ID not set")
        else:
            try:
                perm = w.permissions.get(
                    request_object_type="warehouses",
                    request_object_id=wh_id,
                )
                acl = getattr(perm, "access_control_list", []) or []
                has_can_use = False
                for entry in acl:
                    plevel = str(getattr(entry, "permission_level", "") or "")
                    if "CAN_USE" not in plevel.upper():
                        continue
                    sp_name = str(getattr(entry, "service_principal_name", "") or "")
                    sp_id_attr = str(getattr(entry, "service_principal_id", "") or "")
                    if sp_id in (sp_name, sp_id_attr) or sp_id in sp_name:
                        has_can_use = True
                        break
                if not has_can_use:
                    issues.append(f"Warehouse {wh_id}: app has no CAN_USE")
            except Exception as e:
                issues.append(f"Warehouse permissions: could not verify ({e})")

        return len(issues) == 0, issues

    except Exception as e:
        return False, [str(e)]


def load_env_for_key(key: str, value: str) -> None:
    os.environ[key] = value


def run_resource(
    key: str,
    label: str,
    verify_fn,
    prompt_hint: str = "",
    value_choices_fn=None,
) -> bool:
    """Interactive config for one resource. Returns True to continue."""
    load_dotenv(ENV_FILE, override=True)

    active, inactive, _ = parse_env_file(ENV_FILE)
    cur = active.get(key, "").strip()
    inact = inactive.get(key, [])

    section(label)
    if key == "PROJECT_UNITY_CATALOG_SCHEMA":
        load_env_for_key(key, cur or "")
        print_asset_checks()
    ok, msg = False, ""
    if cur:
        load_env_for_key(key, cur)
        ok, msg = verify_fn()
        display = _redact(cur) if key in _SECRET_KEYS else f"{cur[:50]}{'...' if len(cur) > 50 else ''}"
        if ok:
            print(f"  {OK} Active: {C}{display}{W} {G}({msg}){W}")
        else:
            print(f"  {FAIL} Active: {C}{display}{W} {R}({msg}){W}")
    else:
        print(f"  {WARN} Not configured{W}")

    if inact:
        print(f"  {DIM}Inactive:{W}")
        for i, (_, val) in enumerate(inact, 1):
            display = _redact(val) if key in _SECRET_KEYS else f"{val[:50]}{'...' if len(val) > 50 else ''}"
            print(f"    {DIM}[{i}] {display}{W}")

    ADD_NEW_CATALOG = "add new catalog (this will create all related assets)"
    CREATE_ASSETS_NOW = "create all assets now"
    KEEP_AND_CREATE_ASSETS = "keep + create all missing assets"
    USE_EXISTING_CATALOG = "use existing catalog (pick from available)"
    choices: list[str] = []
    tables_ok = True
    if key == "PROJECT_UNITY_CATALOG_SCHEMA" and cur:
        tables_ok, _ = verify_tables()
    if cur and ok:
        if key == "PROJECT_UNITY_CATALOG_SCHEMA":
            choices = ["keep", ADD_NEW_CATALOG]
            if not tables_ok:
                choices.insert(1, KEEP_AND_CREATE_ASSETS)
        else:
            choices = ["keep", "add new"]
    elif cur and key == "PROJECT_UNITY_CATALOG_SCHEMA":
        # Detect whether the catalog itself is inaccessible (vs just missing schema)
        _catalog_accessible = False
        if "." in cur:
            _cat = cur.split(".", 1)[0]
            try:
                WorkspaceClient().catalogs.get(name=_cat)
                _catalog_accessible = True
            except Exception:
                pass
        if _catalog_accessible:
            # Catalog exists, just schema/assets missing — create is safe
            choices = [CREATE_ASSETS_NOW, USE_EXISTING_CATALOG, ADD_NEW_CATALOG]
        else:
            # Catalog not accessible — creating will fail, lead with existing catalog picker
            print(f"  {WARN} Catalog not accessible — cannot create it on this workspace. Pick an existing one.{W}")
            choices = [USE_EXISTING_CATALOG, CREATE_ASSETS_NOW, ADD_NEW_CATALOG]
    elif cur:
        choices = ["add new"]
    else:
        choices = [ADD_NEW_CATALOG] if key == "PROJECT_UNITY_CATALOG_SCHEMA" else ["enter new"]
    for i, (_, val) in enumerate(inact, 1):
        choices.append(f"activate [{i}]")
    if not choices:
        choices = ["enter new"]
    if key == "DATABRICKS_TOKEN":
        choices.append("generate 7-day PAT")

    # Schema invalid and only add-new-catalog (no cur) → run create_all_assets (mandatory)
    if key == "PROJECT_UNITY_CATALOG_SCHEMA" and choices == [ADD_NEW_CATALOG]:
        hint = " (catalog.schema)"
        val = _read_line(f"Enter {key}{hint}: ")
        if not val:
            abort_step()
        assert val  # guaranteed non-None after abort_step()
        if cur:
            comment_active_for_key(ENV_FILE, key)
        write_env_entry(ENV_FILE, key, val)
        load_dotenv(ENV_FILE, override=True)
        load_env_for_key(key, val)
        print(f"  {B}Creating schema, tables, volume, Genie ...{W}\n")
        rc = subprocess.call(
            ["uv", "run", "python", "data/init/create_all_assets.py"],
            cwd=ROOT,
        )
        if rc == 0:
            print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
        else:
            print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
            abort_step()
        return True

    # Genie invalid and only "add new" → branch to asset creation dialog
    ASSET_KEYS = ("PROJECT_GENIE_CHECKIN",)
    if key in ASSET_KEYS and choices == ["add new"]:
        try:
            raw = input(f"  {C}Create project assets now? [y/N]: {W}").strip().lower()
            if raw in ("y", "yes"):
                print(f"  {B}Creating schema, tables, volume, Genie ...{W}\n")
                rc = subprocess.call(
                    ["uv", "run", "python", "data/init/create_all_assets.py"],
                    cwd=ROOT,
                )
                if rc == 0:
                    print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
                else:
                    print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
                    abort_step()
            else:
                print(f"  {DIM}Skipped{W}\n")
                abort_step()
        except (EOFError, KeyboardInterrupt):
            print(f"  {DIM}Skipped{W}\n")
            abort_step()

    while True:
        choice = prompt_choice("Action?" if prompt_hint else "Action?", choices)
        if choice is None:
            continue

        if choice == "keep":
            return True
        if choice == KEEP_AND_CREATE_ASSETS and key == "PROJECT_UNITY_CATALOG_SCHEMA" and cur:
            print(f"  {B}Creating tables, procedures, Genie ...{W}\n")
            rc = subprocess.call(
                ["uv", "run", "python", "data/init/create_all_assets.py"],
                cwd=ROOT,
            )
            if rc == 0:
                print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
                print(f"  {CONF}✓  Assets created.{W}")
            else:
                print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
                abort_step()
            return True
        if choice == CREATE_ASSETS_NOW and key == "PROJECT_UNITY_CATALOG_SCHEMA" and cur:
            print(f"  {B}Creating schema, tables, Genie ...{W}\n")
            rc = subprocess.call(
                ["uv", "run", "python", "data/init/create_all_assets.py"],
                cwd=ROOT,
            )
            if rc == 0:
                print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
                print(f"  {CONF}✓  Assets created.{W}")
            else:
                print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
                abort_step()
            return True
        if choice == USE_EXISTING_CATALOG and key == "PROJECT_UNITY_CATALOG_SCHEMA":
            # List catalogs the user has access to and let them pick one
            try:
                w = WorkspaceClient()
                catalogs = [c.name for c in w.catalogs.list() if c.name]
            except Exception as e:
                print(f"  {FAIL} Could not list catalogs: {e}{W}")
                return True
            if not catalogs:
                print(f"  {WARN} No accessible catalogs found{W}")
                return True
            _, current_schema = (cur.split(".", 1) + ["main"])[:2] if cur else ("", "main")
            print(f"\n  {C}Available catalogs:{W}")
            for i, name in enumerate(catalogs, 1):
                print(f"    {B}[{i}]{W} {name}")
            idx = _read_choice(f"  Pick catalog (1-{len(catalogs)}): ", len(catalogs))
            if idx is None or not (1 <= idx <= len(catalogs)):
                return True
            new_catalog = catalogs[idx - 1]
            new_val = f"{new_catalog}.{current_schema}"
            print(f"  {C}→ Setting PROJECT_UNITY_CATALOG_SCHEMA = {new_val}{W}")
            if cur:
                comment_active_for_key(ENV_FILE, key)
            write_env_entry(ENV_FILE, key, new_val)
            load_dotenv(ENV_FILE, override=True)
            load_env_for_key(key, new_val)
            vok, vmsg = verify_fn()
            if vok:
                print(f"  {OK} {G}{vmsg}{W}")
                print(f"  {CONF}✓  Catalog selected.{W}")
            else:
                print(f"  {WARN} Schema not found yet ({vmsg}) — assets may need creating{W}")
            return True
        if choice == ADD_NEW_CATALOG and key == "PROJECT_UNITY_CATALOG_SCHEMA":
            hint = " (catalog.schema)"
            val = _read_line(f"Enter {key}{hint}: ")
            if val is None:
                continue   # ESC → back to menu
            if not val:
                return True
            if cur:
                comment_active_for_key(ENV_FILE, key)
            write_env_entry(ENV_FILE, key, val)
            load_dotenv(ENV_FILE, override=True)
            load_env_for_key(key, val)
            print(f"  {B}Creating schema, tables, volume, Genie ...{W}\n")
            rc = subprocess.call(
                ["uv", "run", "python", "data/init/create_all_assets.py"],
                cwd=ROOT,
            )
            if rc == 0:
                print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
                print(f"  {CONF}✓  Assets provisioned.{W}")
            else:
                print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
                abort_step()
            return True
        if choice and choice.startswith("activate ["):
            num = int(choice.split("[")[1].rstrip("]"))
            if 1 <= num <= len(inact):
                line_idx = inact[num - 1][0]
                comment_active_for_key(ENV_FILE, key)
                uncomment_line(ENV_FILE, line_idx)
                load_dotenv(ENV_FILE, override=True)
                load_env_for_key(key, inact[num - 1][1])
                ok, msg = verify_fn()
                if ok:
                    print(f"  {OK} Activated and verified: {msg}{W}")
                else:
                    print(f"  {FAIL} Activated but verify failed: {msg}{W}")
                    abort_step()
            return True
        if choice == "generate 7-day PAT" and key == "DATABRICKS_TOKEN":
            host = os.environ.get("DATABRICKS_HOST", "").strip()
            profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "").strip()
            if not host:
                print(f"  {FAIL} DATABRICKS_HOST not set — cannot generate PAT{W}")
                return True
            try:
                if profile:
                    w = WorkspaceClient(host=host, profile=profile)
                else:
                    w = WorkspaceClient(host=host)
                t = w.tokens.create(comment="agent-forge init (7-day)", lifetime_seconds=604800)
                token_value = t.token_value
                if not token_value:
                    print(f"  {FAIL} No token value returned{W}")
                    return True
                if cur:
                    comment_active_for_key(ENV_FILE, key)
                write_env_entry(ENV_FILE, key, token_value)
                load_dotenv(ENV_FILE, override=True)
                load_env_for_key(key, token_value)
                masked = _redact(token_value)
                print(f"  {OK} PAT generated (7 days) and saved: {C}{masked}{W}")
                vok, vmsg = verify_fn()
                if vok:
                    print(f"  {OK} {G}{vmsg}{W}")
                    print(f"\n  {CONF}✓  Token configured and verified.{W}")
                else:
                    print(f"  {FAIL} Verify failed: {R}{vmsg}{W}")
            except Exception as e:
                print(f"  {FAIL} Failed to generate PAT: {e}{W}")
            return True

        # enter new / add new
        if value_choices_fn:
            val = value_choices_fn()
        else:
            hint = f" ({prompt_hint})" if prompt_hint else ""
            val = _read_line(f"Enter {key}{hint}: ")
            if val is None:
                continue   # ESC → back to menu
        if not val:
            return True
        if cur:
            comment_active_for_key(ENV_FILE, key)
        write_env_entry(ENV_FILE, key, val)
        load_dotenv(ENV_FILE, override=True)
        load_env_for_key(key, val)
        ok, msg = verify_fn()
        if ok:
            print(f"  {OK} Set and verified: {msg}{W}")
            print(f"\n  {CONF}✓  {label} configured.{W}")
        else:
            print(f"  {FAIL} Set but verify failed: {msg}{W}")
            abort_step()
        break
    return True


def verify_ka() -> tuple[bool, str]:
    """Check that PROJECT_KA_PASSENGERS is set and the KA is ACTIVE."""
    load_dotenv(ENV_FILE, override=True)
    endpoint_name = os.environ.get("PROJECT_KA_PASSENGERS", "").strip()
    if not endpoint_name:
        return False, "PROJECT_KA_PASSENGERS not set"
    try:
        w = WorkspaceClient()
        for ka in w.knowledge_assistants.list_knowledge_assistants():
            if (ka.endpoint_name or "") == endpoint_name:
                st = ka.state
                raw = (st.value if hasattr(st, "value") else str(st)) if st else "UNKNOWN"
                if raw == "ACTIVE":
                    return True, f"ACTIVE ({endpoint_name})"
                return False, f"{raw} ({endpoint_name})"
        return False, f"endpoint not found: {endpoint_name}"
    except Exception as e:
        return False, str(e)


def run_resource_ka() -> bool:
    """Interactive setup for the passenger rights Knowledge Assistant."""
    load_dotenv(ENV_FILE, override=True)

    section("Knowledge Assistants (data/pdf/)")

    pdfs = sorted((ROOT / "data" / "pdf").glob("*.pdf"))
    if pdfs:
        print(f"  {C}PDFs in data/pdf/:{W}")
        for p in pdfs:
            print(f"    {B}+{W} {p.name}")
    else:
        print(f"  {WARN} No PDF files found in data/pdf/{W}")

    ok, msg = verify_ka()
    if ok:
        print(f"  {OK} KA is ACTIVE: {C}{msg}{W}")
        choices = ["keep", "recreate"]
    else:
        print(f"  {WARN} {msg}{W}")
        choices = []

    # List existing KAs from workspace so user can select one without reprovisioning
    existing_kas: list[tuple[str, str, str]] = []  # (display_name, endpoint_name, state)
    try:
        w = WorkspaceClient()
        for ka in w.knowledge_assistants.list_knowledge_assistants():
            if ka.endpoint_name:
                st = ka.state
                raw = (st.value if hasattr(st, "value") else str(st)) if st else "UNKNOWN"
                existing_kas.append((ka.display_name or ka.endpoint_name, ka.endpoint_name, raw))
    except Exception:
        pass

    if existing_kas and not ok:
        print(f"\n  {C}KAs available in workspace:{W}")
        for name, ep, state in existing_kas:
            status = G if state == "ACTIVE" else DIM
            print(f"    {B}+{W} {name} {status}[{state}]{W} ({ep})")
        for name, ep, state in existing_kas:
            choices.append(f"use: {name} [{state}]")

    choices.append("provision")

    while True:
        print(f"\n  {C}Action?{W}")
        for i, c in enumerate(choices, 1):
            print(f"    {B}[{i}]{W} {c}")
        idx = _read_choice(f"  Choice (1-{len(choices)}): ", len(choices))
        if idx is None:
            return True
        if not (1 <= idx <= len(choices)):
            print(f"  {WARN} Invalid choice{W}")
            continue
        choice = choices[idx - 1]

        if choice == "keep":
            return True

        if choice and choice.startswith("use: "):
            # Find the matching KA and write its endpoint name to env
            label = choice[len("use: "):]  # "name [STATE]"
            for name, ep, state in existing_kas:
                if label == f"{name} [{state}]":
                    comment_active_for_key(ENV_FILE, "PROJECT_KA_PASSENGERS")
                    write_env_entry(ENV_FILE, "PROJECT_KA_PASSENGERS", ep)
                    load_dotenv(ENV_FILE, override=True)
                    print(f"  {OK} PROJECT_KA_PASSENGERS set to {C}{ep}{W}")
                    print(f"\n  {CONF}✓  Knowledge Assistant registered.{W}")
                    vok, vmsg = verify_ka()
                    if vok:
                        print(f"  {OK} {G}{vmsg}{W}")
                    else:
                        print(f"  {WARN} {vmsg}{W}")
                    return True
            return True

        break  # "provision" or "recreate" → fall through

    print(f"\n  {B}Provisioning Knowledge Assistant...{W}\n")

    for label, cmd in [
        ("Create UC volume", ["uv", "run", "python", "scripts/ka/create_volume.py"]),
        ("Upload PDFs", ["uv", "run", "python", "scripts/ka/upload_pdfs.py"]),
        ("Create KA", ["uv", "run", "python", "scripts/ka/create_kas_from_yml.py", "--skip-existing"]),
    ]:
        print(f"  {C}→ {label}...{W}")
        rc = subprocess.call(cmd, cwd=ROOT)
        if rc != 0:
            print(f"  {FAIL} {label} failed (exit {rc}){W}\n")
            return False
        print()

    load_dotenv(ENV_FILE, override=True)
    ok, msg = verify_ka()
    if ok:
        print(f"  {OK} {G}Knowledge Assistant ready: {msg}{W}\n")
        print(f"  {CONF}✓  Knowledge Assistant ready.{W}")
    else:
        print(f"  {WARN} KA provisioned but verify returned: {msg}{W}\n")
    return True


def run_check_only() -> None:
    """Quick check of all resources (non-interactive)."""
    load_dotenv(ENV_FILE, override=True)

    print(f"\n{BOLD}{M}╔══════════════════════════════════════════╗{W}")
    print(f"{BOLD}{M}║  Databricks Environment Check            ║{W}")
    print(f"{BOLD}{M}╚══════════════════════════════════════════╝{W}")

    all_ok = True

    section("Connection")
    host = os.environ.get("DATABRICKS_HOST", "").strip()
    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "").strip()
    if not host:
        print(f"  {FAIL} DATABRICKS_HOST not set")
        all_ok = False
    else:
        print(f"  {OK} DATABRICKS_HOST {C}({host}){W}")
    if not token and not profile:
        print(f"  {FAIL} DATABRICKS_TOKEN or DATABRICKS_CONFIG_PROFILE not set")
        all_ok = False
    else:
        print(f"  {OK} Auth {C}({'token' if token else f'profile={profile}'}){W}")

    if all_ok:
        ok, msg = verify_host_token()
        if ok:
            print(f"  {OK} Connection {C}({msg}){W}")
        else:
            print(f"  {FAIL} Connection {C}({msg}){W}")
            all_ok = False

    section("Warehouse")
    ok, msg = verify_warehouse()
    print(f"  {OK if ok else FAIL} DATABRICKS_WAREHOUSE_ID {C}({msg}){W}")
    if not ok:
        all_ok = False

    uc_failed = False
    section("Unity Catalog")
    ok, msg = verify_schema()
    print(f"  {OK if ok else FAIL} PROJECT_UNITY_CATALOG_SCHEMA {C}({msg}){W}")
    if not ok:
        all_ok = False
        uc_failed = True

    # Tables (tree format)
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    tables = get_csv_tables()
    if "." in spec:
        catalog, schema_name = spec.split(".", 1)
        full_schema = f"{catalog}.{schema_name}"
        try:
            w = WorkspaceClient()
            print(f"  Tables")
            for i, name in enumerate(tables):
                branch = "  \\-- " if i == len(tables) - 1 else "  |-- "
                full_name = f"{full_schema}.{name}"
                try:
                    w.tables.get(full_name)
                    print(f"  {branch}{OK} {name} {C}({full_name}){W}")
                except Exception as e:
                    print(f"  {branch}{FAIL} {name} {C}({e}){W}")
                    all_ok = False
                    uc_failed = True
        except Exception as e:
            print(f"  Tables")
            print(f"  \\-- {FAIL} {e}{W}")
            all_ok = False
            uc_failed = True

    section("Genie")
    ok, msg = verify_genie()
    print(f"  {OK if ok else FAIL} PROJECT_GENIE_CHECKIN {C}({msg}){W}")
    if not ok:
        all_ok = False

    section("Knowledge Assistants")
    ok, msg = verify_ka()
    print(f"  {OK if ok else FAIL} PROJECT_KA_PASSENGERS {C}({msg}){W}")
    if not ok:
        all_ok = False

    section("MLflow")
    ok, msg = verify_mlflow()
    print(f"  {OK if ok else FAIL} MLFLOW_EXPERIMENT_ID {C}({msg}){W}")
    if not ok:
        all_ok = False

    section("Model Endpoint")
    ok, msg = verify_model_endpoint()
    print(f"  {OK if ok else FAIL} AGENT_MODEL_ENDPOINT {C}({msg}){W}")
    if not ok:
        all_ok = False
    if _endpoint_is_url():
        token = os.environ.get("AGENT_MODEL_TOKEN", "").strip()
        tok_ok = bool(token)
        print(f"  {OK if tok_ok else FAIL} AGENT_MODEL_TOKEN {'set' if tok_ok else 'not set (required for cross-workspace URL)'}")

    section("App grants (run_all_grants)")
    grants_ok, grants_issues = verify_app_grants()
    grants_failed = not grants_ok
    if grants_ok:
        app_name = os.environ.get("DBX_APP_NAME", "").strip()
        print(f"  {OK} UC tables, routines, warehouse {C}({app_name}){W}")
    else:
        for issue in grants_issues:
            print(f"  {FAIL} {issue}")
        all_ok = False

    section("Summary")
    if all_ok:
        print(f"  {OK} {G}All resources OK{W}\n")
    else:
        print(f"  {FAIL} {R}Some checks failed{W}\n")
        assets_created = False
        grants_applied = False
        if uc_failed:
            try:
                raw = input(f"  {C}Create project assets now? [y/N]: {W}").strip().lower()
                if raw in ("y", "yes"):
                    print(f"  {B}Creating schema, tables, volume, Genie ...{W}\n")
                    rc = subprocess.call(
                        ["uv", "run", "python", "data/init/create_all_assets.py"],
                        cwd=ROOT,
                    )
                    if rc == 0:
                        print(f"\n  {OK} {G}Assets created. Re-run --check to verify.{W}\n")
                        assets_created = True
                    else:
                        print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
                        abort_step()
            except (EOFError, KeyboardInterrupt):
                print(f"  {DIM}Skipped{W}\n")
        if grants_failed:
            try:
                raw = input(f"  {C}Run apply grants (run_all_grants.sh)? [y/N]: {W}").strip().lower()
                if raw in ("y", "yes"):
                    print(f"  {B}Applying grants ...{W}\n")
                    rc = subprocess.call(
                        ["bash", str(ROOT / "deploy" / "grant" / "run_all_grants.sh")],
                        cwd=ROOT,
                    )
                    if rc == 0:
                        print(f"\n  {OK} {G}Grants applied. Re-run --check to verify.{W}\n")
                        grants_applied = True
                    else:
                        print(f"\n  {FAIL} Grants script exited with {rc}{W}\n")
            except (EOFError, KeyboardInterrupt):
                print(f"  {DIM}Skipped{W}\n")
        if not assets_created and not grants_applied:
            print(FIX_FIRST_MSG)
        sys.exit(1)


def main() -> None:
    if "--check" in sys.argv:
        run_check_only()
        return

    load_dotenv(ENV_FILE, override=True)

    print(f"\n{BOLD}{M}╔══════════════════════════════════════════════════╗{W}")
    print(f"{BOLD}{M}║  Init & Check Databricks Environment (.env.local) ║{W}")
    print(f"{BOLD}{M}╚══════════════════════════════════════════════════╝{W}")

    # Connection: HOST + TOKEN (or PROFILE)
    run_resource_host()

    load_dotenv(ENV_FILE, override=True)
    if not os.environ.get("DATABRICKS_HOST"):
        print(f"  {FAIL} DATABRICKS_HOST required. Aborting.{W}")
        sys.exit(1)

    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "").strip()
    if token:
        run_resource("DATABRICKS_TOKEN", "Connection: DATABRICKS_TOKEN", lambda: verify_host_token(), "dapi...")
    elif profile:
        run_resource_profile()
    else:
        choices = ["DATABRICKS_TOKEN", "DATABRICKS_CONFIG_PROFILE"]
        c = prompt_choice("Which auth?", choices)
        if c is None:
            print(f"  {DIM}Skipped{W}")
        elif "TOKEN" in c:
            run_resource("DATABRICKS_TOKEN", "Connection: DATABRICKS_TOKEN", lambda: verify_host_token(), "dapi...")
        else:
            run_resource_profile()

    load_dotenv(ENV_FILE, override=True)
    run_resource_warehouse()
    run_resource("PROJECT_UNITY_CATALOG_SCHEMA", "PROJECT_UNITY_CATALOG_SCHEMA", verify_schema, "catalog.schema")

    # Step 1: ensure SQL init files exist for all CSVs
    load_dotenv(ENV_FILE, override=True)
    if os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA"):
        sql_paths = ensure_init_sql_files()

        # Step 2: tables check + offer to run SQL files
        ok, msg = verify_tables()
        if not ok:
            section(f"Tables ({', '.join(get_csv_tables())})")
            print(f"  {FAIL} {msg}{W}")
            if sql_paths:
                print(f"\n  SQL files to execute:")
                for i, p in enumerate(sql_paths):
                    branch = "  \\-- " if i == len(sql_paths) - 1 else "  |-- "
                    print(f"{branch}{p.relative_to(ROOT)}")
            try:
                raw = input(f"\n  {C}Run all SQL files and create assets? [y/N]: {W}").strip().lower()
                if raw in ("y", "yes"):
                    print(f"  {B}Creating schema, tables, volume, Genie ...{W}\n")
                    rc = subprocess.call(
                        ["uv", "run", "python", "data/init/create_all_assets.py"],
                        cwd=ROOT,
                    )
                    if rc == 0:
                        print(f"\n  {OK} {G}Assets created. Re-run to verify.{W}\n")
                    else:
                        print(f"\n  {FAIL} Asset creation exited with {rc}{W}\n")
                        abort_step()
                else:
                    print(f"  {DIM}Skipped{W}\n")
                    abort_step()
            except (EOFError, KeyboardInterrupt):
                print(f"  {DIM}Skipped{W}\n")
                abort_step()

    # UC Functions
    section("UC Functions (data/func/)")
    _func_sql = sorted((ROOT / "data" / "func").glob("*.sql"))
    _func_ddl = [p for p in _func_sql if re.search(r"\bCREATE\b", p.read_text(), re.IGNORECASE)]
    if _func_ddl:
        print(f"  {C}Will CREATE OR REPLACE:{W}")
        for p in _func_ddl:
            print(f"    {B}+{W} {p.stem}")
        if len(_func_sql) > len(_func_ddl):
            print(f"  {DIM}Skipping {len(_func_sql) - len(_func_ddl)} query template(s) without CREATE{W}")
    else:
        print(f"  {DIM}No CREATE function files found in data/func/{W}")
    try:
        raw = input(f"\n  {C}Create/replace all UC functions? [y/N]: {W}").strip().lower()
        if raw in ("y", "yes"):
            rc = subprocess.call(["uv", "run", "python", "data/init/create_all_functions.py"], cwd=ROOT)
            if rc == 0:
                print(f"  {OK} {G}Functions created{W}\n")
            else:
                print(f"  {FAIL} create_all_functions exited with {rc}{W}\n")
        else:
            print(f"  {DIM}Skipped{W}")
    except (EOFError, KeyboardInterrupt):
        print(f"\n\n  {WARN} Interrupted — exiting.{W}\n")
        sys.exit(130)

    # UC Procedures
    section("UC Procedures (data/proc/)")
    _proc_sql = sorted((ROOT / "data" / "proc").glob("*.sql"))
    if _proc_sql:
        print(f"  {C}Will CREATE OR REPLACE:{W}")
        for p in _proc_sql:
            print(f"    {B}+{W} {p.stem}")
    else:
        print(f"  {DIM}No procedure files found in data/proc/{W}")
    try:
        raw = input(f"\n  {C}Create/replace all UC procedures? [y/N]: {W}").strip().lower()
        if raw in ("y", "yes"):
            rc = subprocess.call(["uv", "run", "python", "data/init/create_all_procedures.py"], cwd=ROOT)
            if rc == 0:
                print(f"  {OK} {G}Procedures created{W}\n")
            else:
                print(f"  {FAIL} create_all_procedures exited with {rc}{W}\n")
        else:
            print(f"  {DIM}Skipped{W}")
    except (EOFError, KeyboardInterrupt):
        print(f"\n\n  {WARN} Interrupted — exiting.{W}\n")
        sys.exit(130)

    run_resource_genie()
    run_resource_ka()
    run_resource_mlflow()
    run_resource_model_endpoint()
    run_resource_model_token()

    section("Agent Model Test")
    load_dotenv(ENV_FILE, override=True)
    rc = subprocess.call(["uv", "run", "python", "scripts/test_agent_model.py"], cwd=ROOT)
    if rc != 0:
        print(f"  {WARN} Model test failed — see above for details.{W}")

    run_resource("DBX_APP_NAME", "DBX_APP_NAME", lambda: (True, os.environ.get("DBX_APP_NAME", "")), "my-app-name")

    section("Done")
    print(f"  {OK} {G}Configuration saved to {ENV_FILE}{W}\n")
    grants_ok, grants_issues = verify_app_grants()
    if not grants_ok:
        print(f"  {WARN} App grants: {', '.join(grants_issues)}{W}")
        print(f"  {DIM}Run: ./deploy/grant/run_all_grants.sh{W}\n")
    print(f"  {BOLD}{G}╔════════════════════════════════════╗{W}")
    print(f"  {BOLD}{G}║  {OK} You're All Set!{W}                 {BOLD}{G}║{W}")
    print(f"  {BOLD}{G}╚════════════════════════════════════╝{W}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {WARN} Interrupted — exiting.{W}\n")
        sys.exit(130)
    except Exception as e:
        print(f"\n  {FAIL} {e}{W}")
        print(FIX_FIRST_MSG)
        sys.exit(1)
