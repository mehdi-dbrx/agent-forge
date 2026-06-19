#!/usr/bin/env python3
"""
Create a Genie space with all tables from PROJECT_UNITY_CATALOG_SCHEMA.

Prints space_id to stdout. Appends to PROJECT_GENIE_SPACES in .env.local.
GENIE_ROOM_NAME env var sets the space title (default: "PROJECT").

Requires: PROJECT_UNITY_CATALOG_SCHEMA, DATABRICKS_WAREHOUSE_ID (or a warehouse in the workspace).
"""
import json
import os
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main():
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA") or ""
    if "." not in spec:
        print("Set PROJECT_UNITY_CATALOG_SCHEMA to catalog.schema in .env.local", file=sys.stderr)
        sys.exit(1)
    catalog, schema = spec.strip().split(".", 1)

    from databricks.sdk import WorkspaceClient
    token = os.environ.get("DATABRICKS_TOKEN")
    # Prefer token over profile to avoid databricks-cli auth when token is set
    if token:
        _profile = os.environ.pop("DATABRICKS_CONFIG_PROFILE", None)
        try:
            w = WorkspaceClient(host=os.environ.get("DATABRICKS_HOST"), token=token)
        finally:
            if _profile is not None:
                os.environ["DATABRICKS_CONFIG_PROFILE"] = _profile
    else:
        w = WorkspaceClient()

    wh_id = os.environ.get("DATABRICKS_WAREHOUSE_ID") or next(iter(w.warehouses.list()), None)
    if not wh_id:
        print("No warehouse. Set DATABRICKS_WAREHOUSE_ID or create one.", file=sys.stderr)
        sys.exit(1)
    wh_id = getattr(wh_id, "id", wh_id)

    tables = list(w.tables.list(catalog_name=catalog, schema_name=schema))
    if not tables:
        print(f"No tables in {catalog}.{schema}. Run csv_to_delta.py first.", file=sys.stderr)
        sys.exit(1)

    table_identifiers = []
    for t in tables:
        full = getattr(t, "full_name", None) or f"{catalog}.{schema}.{t.name}"
        table_identifiers.append(full)

    def gen_id():
        return uuid.uuid4().hex[:24] + "0" * 8

    title = os.environ.get("GENIE_ROOM_NAME", "").strip() or "PROJECT"
    description = os.environ.get("GENIE_DESCRIPTION", "").strip() or "Natural language exploration of project data in Unity Catalog."
    sample_questions = []
    env_var = "PROJECT_GENIE_SPACES"

    serialized = {
        "version": 2,
        "config": {"sample_questions": sample_questions},
        "data_sources": {
            "tables": [{"identifier": tid} for tid in table_identifiers],
            "metric_views": [],
        },
        "instructions": {
            "text_instructions": [],
            "example_question_sqls": [],
            "sql_functions": [],
            "join_specs": [],
            "sql_snippets": {"filters": [], "expressions": [], "measures": []},
        },
        "benchmarks": {"questions": []},
    }

    space = w.genie.create_space(
        warehouse_id=wh_id,
        serialized_space=json.dumps(serialized),
        title=title,
        description=description,
    )
    print(space.space_id)

    # Append space_id to config.json tools.genie_spaces[]
    config_file = os.environ.get("CONFIG_FILE", "")
    if config_file:
        from lib.config_json import read_config, write_config
        config = read_config()
        config.setdefault("tools", {})["genie_spaces"] = [space.space_id]
        config.setdefault("genie_room", {})["name"] = title
        config["genie_room"]["description"] = description
        spaces = config["tools"]["genie_spaces"]
        write_config(config)
        print(f"Updated {config_file} with genie_spaces={spaces}, genie_room.name={title}", file=sys.stderr)
    else:
        # Fallback: write to .env.local (legacy)
        env_path = Path(os.environ.get("ENV_FILE", str(ROOT / ".env.local")))
        import re as _re
        existing = os.environ.get(env_var, "").strip()
        existing_ids = set(existing.split(",")) if existing else set()
        existing_ids.discard("")
        existing_ids.add(space.space_id)
        new_value = ",".join(sorted(existing_ids))
        content = env_path.read_text() if env_path.exists() else ""
        if _re.search(rf'^{env_var}=', content, _re.MULTILINE):
            content = _re.sub(rf'^{env_var}=.*$', f'{env_var}={new_value}', content, flags=_re.MULTILINE)
        else:
            content += f"\n{env_var}={new_value}\n"
        env_path.write_text(content)
        print(f"Updated {env_path} with {env_var}={new_value}", file=sys.stderr)


if __name__ == "__main__":
    main()
