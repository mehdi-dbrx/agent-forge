"""Generate and run E2E test scripts for generated functions and procedures.

Reads the generated SQL files, asks the LLM to generate test cases,
runs them against the warehouse, and reports pass/fail per routine.

Flow: read SQL files + seed data → LLM generates test script → execute → verify results.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from data.gen.llm_client import call_llm_json, call_llm
from lib.project_paths import gen_dir


TEST_SYSTEM_PROMPT = """\
You are a SQL test generator for Databricks Unity Catalog.

You will receive:
1. A list of generated SQL functions and procedures
2. The table schemas with sample data (first few rows)
3. The schema name where everything lives

Your job: generate a JSON array of test cases. Each test case:
- Calls a function or procedure with REALISTIC inputs that match EXISTING data
- Then runs a verification query to confirm the expected result

CRITICAL RULES:
- For functions (RETURNS TABLE): use SELECT * FROM schema.func(args) syntax
  NO TABLE() wrapper. Databricks table functions are called directly in FROM clause.
  Correct:   SELECT * FROM space.hotel.search_available_rooms('2025-08-01', '2025-08-05')
  Wrong:     SELECT * FROM TABLE(space.hotel.search_available_rooms('2025-08-01', '2025-08-05'))
  Wrong:     SELECT space.hotel.search_available_rooms('2025-08-01', '2025-08-05')
- For procedures (CALL): test with CALL schema.proc(args), then verify with a SELECT
- For procedures that take a reservation_id: use a KNOWN literal ID from the seed data,
  NEVER use a subquery as a CALL argument (causes "args must be foldable" error)
  Correct:   CALL schema.cancel_reservation('RES-00001')
  Wrong:     CALL schema.cancel_reservation((SELECT reservation_id FROM ...))
- Use ACTUAL values from the seed data (real IDs, real names from the sample rows)
- For procedures that INSERT: verify the row EXISTS after the call
- For procedures that UPDATE: verify the column CHANGED after the call
- For procedures that DELETE/cancel: verify the status CHANGED after the call
- Every test must have a verification SELECT that checks actual data, not just "no error"
- Use a unique test prefix (__TEST__) in any created data so it can be cleaned up
- Include a cleanup step at the end that removes all __TEST__ rows

Return ONLY a JSON object with this structure:
{
  "tests": [
    {
      "name": "test_search_available_rooms",
      "description": "Verify search returns rooms for valid dates",
      "steps": [
        {
          "sql": "SELECT * FROM TABLE(schema.search_available_rooms('2025-08-01', '2025-08-05'))",
          "expect": "rows > 0",
          "description": "Should return available rooms"
        }
      ]
    },
    {
      "name": "test_make_reservation",
      "description": "Verify reservation is created and visible in table",
      "steps": [
        {
          "sql": "CALL schema.register_new_guest('__TEST__-G1', 'Test User', ...)",
          "expect": "success",
          "description": "Register test guest"
        },
        {
          "sql": "SELECT * FROM schema.travelers WHERE traveler_id = '__TEST__-G1'",
          "expect": "rows == 1",
          "description": "Guest must exist"
        },
        {
          "sql": "CALL schema.make_reservation('__TEST__-G1', 'HTL-001', ...)",
          "expect": "success",
          "description": "Create reservation"
        },
        {
          "sql": "SELECT * FROM schema.reservations WHERE traveler_id = '__TEST__-G1'",
          "expect": "rows == 1",
          "description": "Reservation must exist in table"
        }
      ]
    }
  ],
  "cleanup": [
    "DELETE FROM schema.reservations WHERE traveler_id LIKE '__TEST__%'",
    "DELETE FROM schema.travelers WHERE traveler_id LIKE '__TEST__%'"
  ]
}

IMPORTANT: Use the ACTUAL schema name provided, not 'schema'. Use ACTUAL IDs from the sample data for lookups (hotel_id, room_type_id etc). For new records, use __TEST__ prefix."""


def _read_sql_files(directory: Path) -> list[dict]:
    """Read all SQL files from a directory, return [{name, sql}]."""
    results = []
    if not directory.exists():
        return results
    for f in sorted(directory.glob("*.sql")):
        results.append({"name": f.stem, "sql": f.read_text()})
    return results


def _read_csv_sample(csv_dir: Path, max_rows: int = 5) -> list[dict]:
    """Read first N rows from each CSV, return [{name, headers, sample_rows}]."""
    results = []
    if not csv_dir.exists():
        return results
    for f in sorted(csv_dir.glob("*.csv")):
        lines = f.read_text().strip().split("\n")
        if not lines:
            continue
        headers = lines[0]
        sample = lines[1:max_rows + 1]
        results.append({"name": f.stem, "headers": headers, "sample_rows": sample})
    return results


def generate_tests(schema: str) -> dict:
    """Generate test cases for all generated functions and procedures.
    Returns the test spec as a dict."""
    gd = gen_dir()

    # Gather SQL files
    functions = _read_sql_files(gd / "func")
    procedures = _read_sql_files(gd / "proc")

    if not functions and not procedures:
        print("[x] No generated functions or procedures found")
        return {"tests": [], "cleanup": []}

    # Gather sample data
    csv_samples = _read_csv_sample(gd / "csv")
    if not csv_samples:
        # Try demo data
        demo_csv = ROOT / "data" / "demo" / "csv"
        csv_samples = _read_csv_sample(demo_csv)

    # Build context for LLM
    context_parts = [f"Schema: {schema}\n"]

    if csv_samples:
        context_parts.append("## Sample Data\n")
        for table in csv_samples:
            context_parts.append(f"### {table['name']}")
            context_parts.append(table["headers"])
            for row in table["sample_rows"]:
                context_parts.append(row)
            context_parts.append("")

    context_parts.append("## Functions\n")
    for fn in functions:
        # Replace placeholder with actual schema
        sql = fn["sql"].replace("__SCHEMA_QUALIFIED__", schema)
        context_parts.append(f"### {fn['name']}\n```sql\n{sql}\n```\n")

    context_parts.append("## Procedures\n")
    for proc in procedures:
        sql = proc["sql"].replace("__SCHEMA_QUALIFIED__", schema)
        context_parts.append(f"### {proc['name']}\n```sql\n{sql}\n```\n")

    user_prompt = "\n".join(context_parts)

    print(f"[~] Generating test cases for {len(functions)} functions + {len(procedures)} procedures...")
    sys.stdout.flush()

    result = call_llm_json(TEST_SYSTEM_PROMPT, user_prompt, max_tokens=8192)
    tests = result.get("tests", [])
    print(f"[+] Generated {len(tests)} test case(s)")

    return result


def run_tests(schema: str, test_spec: dict) -> list[dict]:
    """Run test cases against the warehouse. Returns list of results."""
    from tools.sql_executor import get_warehouse, execute_statement, execute_query

    w, wh_id = get_warehouse()
    results = []

    tests = test_spec.get("tests", [])
    cleanup = test_spec.get("cleanup", [])

    for test in tests:
        test_name = test.get("name", "unnamed")
        test_result = {"name": test_name, "description": test.get("description", ""), "steps": [], "passed": True}

        print(f"\n[~] Running: {test_name}")
        sys.stdout.flush()

        for step in test.get("steps", []):
            sql = step.get("sql", "")
            expect = step.get("expect", "success")
            desc = step.get("description", "")

            step_result = {"sql": sql[:100], "description": desc, "expect": expect, "passed": False, "actual": ""}

            try:
                if sql.strip().upper().startswith("CALL"):
                    execute_statement(w, wh_id, sql)
                    step_result["actual"] = "executed"
                    step_result["passed"] = True if expect == "success" else True
                else:
                    columns, rows = execute_query(w, wh_id, sql)
                    row_count = len(rows)
                    step_result["actual"] = f"{row_count} row(s)"

                    # Check expectation
                    if expect == "rows > 0":
                        step_result["passed"] = row_count > 0
                    elif expect == "rows == 0":
                        step_result["passed"] = row_count == 0
                    elif expect.startswith("rows == "):
                        expected_count = int(expect.split("== ")[1])
                        step_result["passed"] = row_count == expected_count
                    elif expect == "success":
                        step_result["passed"] = True
                    else:
                        step_result["passed"] = row_count > 0

            except Exception as e:
                step_result["actual"] = f"ERROR: {e}"
                step_result["passed"] = False

            status = "[+]" if step_result["passed"] else "[x]"
            print(f"  {status} {desc}: expected {expect}, got {step_result['actual']}")
            sys.stdout.flush()

            test_result["steps"].append(step_result)
            if not step_result["passed"]:
                test_result["passed"] = False

        results.append(test_result)

    # Cleanup
    if cleanup:
        print("\n[~] Cleaning up test data...")
        sys.stdout.flush()
        for sql in cleanup:
            try:
                execute_statement(w, wh_id, sql)
            except Exception as e:
                print(f"  [~] Cleanup warning: {e}")

    # Summary
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    print(f"\n{'[+]' if failed == 0 else '[x]'} Results: {passed} passed, {failed} failed out of {len(results)} tests")

    return results


def _emit_result(data: dict | list) -> None:
    print(f"__RESULT__:{json.dumps(data)}", flush=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Test generator and runner for generated routines")
    parser.add_argument("--mode", required=True, choices=["generate", "run", "generate-and-run"])
    args = parser.parse_args()

    schema = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "")
    if not schema:
        print("[x] PROJECT_UNITY_CATALOG_SCHEMA is required")
        sys.exit(1)

    if args.mode == "generate":
        spec = generate_tests(schema)
        # Save test spec
        test_file = gen_dir() / "test_spec.json"
        test_file.write_text(json.dumps(spec, indent=2))
        print(f"[+] Test spec saved to {test_file}")
        _emit_result(spec)

    elif args.mode == "run":
        test_file = gen_dir() / "test_spec.json"
        if not test_file.exists():
            print("[x] No test spec found. Run --mode=generate first.")
            sys.exit(1)
        spec = json.loads(test_file.read_text())
        results = run_tests(schema, spec)
        failed = [r for r in results if not r["passed"]]
        _emit_result({"results": results, "passed": len(results) - len(failed), "failed": len(failed)})
        if failed:
            sys.exit(1)

    elif args.mode == "generate-and-run":
        spec = generate_tests(schema)
        test_file = gen_dir() / "test_spec.json"
        test_file.write_text(json.dumps(spec, indent=2))
        results = run_tests(schema, spec)
        failed = [r for r in results if not r["passed"]]
        _emit_result({"results": results, "passed": len(results) - len(failed), "failed": len(failed)})
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    main()
