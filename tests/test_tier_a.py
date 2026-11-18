"""Unit and regression tests for Tier A deterministic rules engine."""

from collections import Counter
import json
from pathlib import Path
import pytest
from src.analysis.tier_a import run_tier_a

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"

CASE_PATHS = sorted(
    [p for p in CASES_DIR.glob("*.json") if not p.name.endswith(".expected.json")],
    key=lambda p: (len(p.stem), p.stem),
)


@pytest.mark.parametrize(
    "case_path",
    CASE_PATHS,
    ids=[p.stem for p in CASE_PATHS],
)
def test_tier_a_against_expected(case_path: Path) -> None:
    expected_path = case_path.parent / f"{case_path.stem}.expected.json"
    assert expected_path.exists(), f"Missing expected fixture: {expected_path.name}"

    with open(case_path, "r", encoding="utf-8") as f:
        case_data = json.load(f)
    with open(expected_path, "r", encoding="utf-8") as f:
        expected_data = json.load(f)

    produced_flags = run_tier_a(case_data)

    # Build multiset of (rule, ref) from produced flags
    produced_tuples: list[tuple[str, str]] = []
    for flag in produced_flags:
        rule = flag["rule"]
        for ref in flag.get("evidence_refs", []):
            produced_tuples.append((rule, ref))
    produced_counter = Counter(produced_tuples)

    # Build multiset of (rule, about_ref) from expected data
    expected_tuples: list[tuple[str, str]] = []
    for exp in expected_data.get("tier_a_expected", []):
        expected_tuples.append((exp["rule"], exp["about_ref"]))
    expected_counter = Counter(expected_tuples)

    # Diagnostic assert
    assert produced_counter == expected_counter, (
        f"Tier A mismatch on {case_path.name}!\n"
        f"  Expected ({len(expected_tuples)}): {sorted(expected_tuples)}\n"
        f"  Produced ({len(produced_tuples)}): {sorted(produced_tuples)}"
    )


def test_clean_cases_return_empty() -> None:
    """Explicitly verify that clean cases produce zero Tier A flags."""
    for case_id in ["C5", "C6", "C7", "C10", "C11", "C12", "C13"]:
        case_path = CASES_DIR / f"{case_id}.json"
        assert case_path.exists(), f"Missing {case_path.name}"
        with open(case_path, "r", encoding="utf-8") as f:
            case_data = json.load(f)
        flags = run_tier_a(case_data)
        assert flags == [], f"Clean case {case_id} produced unexpected Tier A flags: {flags}"
