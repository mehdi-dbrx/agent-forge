#!/usr/bin/env python3
"""CLI orchestrator for agent prompt generation.

Invoked by the visual backend via subprocess. Communicates progress via
[+]/[~]/[x] prefixed stdout lines and returns results via __RESULT__:{json}.

Modes:
  --mode=generate  --domain="..."  [--tables-json="[...]"]  Generate prompt files
  --mode=save                                                Save prompts to conf/prompt/ (stdin JSON)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


from lib.project_paths import prompt_dir as _resolve_prompt_dir
PROMPT_DIR = _resolve_prompt_dir()


def _emit_result(data: dict | list) -> None:
    """Print a result line the backend can parse."""
    print(f"__RESULT__:{json.dumps(data)}", flush=True)


def mode_generate(domain: str, tables_json: str | None) -> None:
    from data.gen.prompt_generator import generate_prompts

    table_schemas = None
    if tables_json:
        try:
            table_schemas = json.loads(tables_json)
        except json.JSONDecodeError:
            print("[~] Could not parse --tables-json, proceeding without table context")

    try:
        result = generate_prompts(domain, table_schemas)
        _emit_result(result)
    except Exception as e:
        print(f"[x] Prompt generation failed: {e}")
        traceback.print_exc()
        sys.exit(1)


def mode_save() -> None:
    try:
        input_data = json.loads(sys.stdin.read())
        main_prompt = input_data.get("main_prompt", "")
        knowledge_base = input_data.get("knowledge_base", "")
        user_prompt = input_data.get("user_prompt", "")

        PROMPT_DIR.mkdir(parents=True, exist_ok=True)

        (PROMPT_DIR / "main.prompt").write_text(main_prompt, encoding="utf-8")
        print(f"[+] Saved main.prompt ({len(main_prompt.splitlines())} lines)")

        (PROMPT_DIR / "knowledge.base").write_text(knowledge_base, encoding="utf-8")
        print(f"[+] Saved knowledge.base ({len(knowledge_base.splitlines())} lines)")

        (PROMPT_DIR / "user.prompt").write_text(user_prompt, encoding="utf-8")
        print(f"[+] Saved user.prompt")

        _emit_result({"ok": True})
    except Exception as e:
        print(f"[x] Save failed: {e}")
        traceback.print_exc()
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["generate", "save"])
    parser.add_argument("--domain", default="")
    parser.add_argument("--tables-json", default=None)
    args = parser.parse_args()

    if args.mode == "generate":
        if not args.domain:
            print("[x] --domain is required for generate mode")
            sys.exit(1)
        mode_generate(args.domain, args.tables_json)
    elif args.mode == "save":
        mode_save()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[~] Interrupted")
        sys.exit(130)
