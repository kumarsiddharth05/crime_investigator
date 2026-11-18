#!/usr/bin/env python3
"""Verify reference resolvability in all cases/*.expected.json against case_context."""

import json
import sys
from pathlib import Path

# Add repo root to sys.path so src.analysis.refs can be imported
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.analysis.refs import resolve_ref


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    cases_dir = repo_root / "cases"

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
    total_refs = 0

    for case_file in case_files:
        expected_file = cases_dir / f"{case_file.stem}.expected.json"
        if not expected_file.exists():
            print(f"[FAIL] Missing expected file: {expected_file.name}", file=sys.stderr)
            failures += 1
            continue

        try:
            with open(case_file, "r", encoding="utf-8") as f:
                case_context = json.load(f)
            with open(expected_file, "r", encoding="utf-8") as f:
                expected_data = json.load(f)
        except Exception as e:
            print(f"[FAIL] Failed loading {case_file.name} or {expected_file.name}: {e}", file=sys.stderr)
            failures += 1
            continue

        # Collect all refs from expected.json
        refs = []
        for item in expected_data.get("tier_a_expected", []):
            if "about_ref" in item:
                refs.append(item["about_ref"])
        for item in expected_data.get("tier_b_expected", []):
            for r in item.get("about_refs", []):
                refs.append(r)

        print(f"Checking {case_file.stem} ({len(refs)} ref(s)):")
        if not refs:
            print(f"  [PASS] {case_file.stem} has 0 refs (clean fixture)")

        for ref in refs:
            total_refs += 1
            resolved = resolve_ref(case_context, ref)
            if resolved is not None:
                print(f"  [PASS] '{ref}' resolved in {case_file.name}")
            else:
                print(f"  [FAIL] '{ref}' FAILED to resolve in {case_file.name}", file=sys.stderr)
                failures += 1

    print("\n----------------------------------------")
    if failures > 0:
        print(f"Reference validation FAILED: {failures} unresolved ref(s).", file=sys.stderr)
        return 1

    print(f"Reference validation PASSED: all {total_refs} ref(s) across {len(case_files)} cases resolved successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
