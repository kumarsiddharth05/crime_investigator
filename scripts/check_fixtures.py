#!/usr/bin/env python3
"""Validate case fixtures against schemas/case_context.schema.json."""

import json
import sys
from pathlib import Path
import jsonschema
from jsonschema import Draft7Validator


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    schema_path = repo_root / "schemas" / "case_context.schema.json"
    cases_dir = repo_root / "cases"

    if not schema_path.exists():
        print(f"Error: Schema not found at {schema_path}", file=sys.stderr)
        return 1

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        Draft7Validator.check_schema(schema)
        print(f"[OK] Schema is valid Draft-07: {schema_path.name}")
    except Exception as e:
        print(f"[FAIL] Schema validation error: {e}", file=sys.stderr)
        return 1

    validator = Draft7Validator(schema)

    if not cases_dir.exists():
        print(f"Error: Cases directory not found at {cases_dir}", file=sys.stderr)
        return 1

    case_files = sorted(
        p for p in cases_dir.glob("*.json") if not p.name.endswith(".expected.json")
    )

    if not case_files:
        print("Error: No case files found in cases/", file=sys.stderr)
        return 1

    failures = 0
    for case_file in case_files:
        expected_file = cases_dir / f"{case_file.stem}.expected.json"
        print(f"Checking fixture: {case_file.name} ...")

        # 1. Validate case JSON against schema
        try:
            with open(case_file, "r", encoding="utf-8") as f:
                case_data = json.load(f)
            validator.validate(case_data)
            print(f"  [PASS] {case_file.name} matches case_context.schema.json")
        except jsonschema.ValidationError as ve:
            print(f"  [FAIL] Schema error in {case_file.name}: {ve.message} at {list(ve.path)}", file=sys.stderr)
            failures += 1
            continue
        except Exception as e:
            print(f"  [FAIL] Could not parse {case_file.name}: {e}", file=sys.stderr)
            failures += 1
            continue

        # 2. Check matching expected file
        if not expected_file.exists():
            print(f"  [FAIL] Missing matching expected file: {expected_file.name}", file=sys.stderr)
            failures += 1
            continue

        try:
            with open(expected_file, "r", encoding="utf-8") as f:
                expected_data = json.load(f)
            # Basic validation of expected structure
            if not isinstance(expected_data, dict):
                raise ValueError("Expected root to be a JSON object")
            if "clean" not in expected_data:
                raise ValueError("Missing 'clean' field")
            if "tier_a_expected" not in expected_data or not isinstance(expected_data["tier_a_expected"], list):
                raise ValueError("Missing or invalid 'tier_a_expected' list")
            if "tier_b_expected" not in expected_data or not isinstance(expected_data["tier_b_expected"], list):
                raise ValueError("Missing or invalid 'tier_b_expected' list")
            print(f"  [PASS] Matching {expected_file.name} exists and is valid")
        except Exception as e:
            print(f"  [FAIL] Invalid expected fixture {expected_file.name}: {e}", file=sys.stderr)
            failures += 1

    if failures > 0:
        print(f"\nFixture verification failed with {failures} error(s).", file=sys.stderr)
        return 1

    print(f"\n[SUCCESS] All {len(case_files)} case fixture(s) validated successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
