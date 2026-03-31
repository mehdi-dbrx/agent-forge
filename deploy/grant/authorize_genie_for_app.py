#!/usr/bin/env python3
"""Add genie_space resource to databricks.yml so app SP gets CAN_RUN.
Reads space_id from PROJECT_GENIE_CHECKIN in .env.local or databricks.yml."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
YML = ROOT / "databricks.yml"


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local")

    # Try databricks.yml first, then env var
    space_id = None
    if YML.exists():
        content = YML.read_text()
        m = re.search(r"genie_space:.*?space_id: '([^']*)'", content, re.DOTALL)
        if m and m.group(1) not in ("PLACEHOLDER_GENIE_ID", ""):
            space_id = m.group(1)

    if not space_id:
        space_id = os.environ.get("PROJECT_GENIE_CHECKIN", "").strip()

    if not space_id:
        print("Error: No space_id found. Set PROJECT_GENIE_CHECKIN in .env.local", file=sys.stderr)
        return 1

    if not YML.exists():
        print(f"Error: {YML} not found. Run deploy/sync_databricks_yml_from_env.py first.", file=sys.stderr)
        return 1

    content = YML.read_text()

    if "genie_space:" in content and space_id in content:
        print(f"genie_space ({space_id}) already in databricks.yml")
        return 0

    block = f"""        - name: 'genie_space'
          genie_space:
            space_id: '{space_id}'
            permission: 'CAN_RUN'
"""
    m2 = re.search(
        r"(        - name: 'sql_warehouse'\n          sql_warehouse:\n            id: '[^']*'\n            permission: 'CAN_USE'\n)",
        content,
    )
    if not m2:
        print("Error: Could not find sql_warehouse block in databricks.yml", file=sys.stderr)
        return 1

    content = content.replace(m2.group(1), m2.group(1).rstrip() + "\n" + block)
    YML.write_text(content)
    print(f"Added genie_space ({space_id}) to databricks.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
