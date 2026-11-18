"""Unit and integration tests for evaluation harness (evaluate.py).

All tests run completely offline without external network calls or live API keys.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest

from evaluate import (
    ACCEPTANCE_TARGETS,
    EvaluationLLMClient,
    discover_fixtures,
    evaluate_all,
    evaluate_case,
    format_aggregate_table,
    format_per_case_table,
    main,
    match_tier_a,
    match_tier_b,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "cases"


# --- 1 & 2: Fixture Discovery Tests ---

def test_dynamic_discovery_includes_all_matched_fixtures():
    fixtures = discover_fixtures(FIXTURES_DIR)
    stems = [stem for stem, _, _ in fixtures]
    # Verify C0-C7 and C10-C14 are included
    for expected_stem in ["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C10", "C11", "C12", "C13", "C14"]:
        assert expected_stem in stems, f"Expected {expected_stem} in discovered fixtures"
    assert len(fixtures) == 13


def test_fixtures_without_expected_files_excluded(tmp_path):
    # Create test directory with matched and unmatched fixtures
    (tmp_path / "C99.json").write_text("{}", encoding="utf-8")
    (tmp_path / "C99.expected.json").write_text("{}", encoding="utf-8")
    (tmp_path / "C100.json").write_text("{}", encoding="utf-8")  # No matching .expected.json

    fixtures = discover_fixtures(tmp_path)
    stems = [stem for stem, _, _ in fixtures]
    assert "C99" in stems
    assert "C100" not in stems
    assert len(fixtures) == 1


# --- 3 & 4: Tier A Matching Tests ---

def test_tier_a_matching_requires_rule_and_reference():
    expected = [
        {"rule": "A1", "about_ref": "photos.P1.d3"},
        {"rule": "A6", "about_ref": "timeline.T2"},
    ]
    # Produced has matching A1, but rule mismatch for A6 (A7 instead of A6)
    produced = [
        {"rule": "A1", "evidence_refs": ["photos.P1.d3"]},
        {"rule": "A7", "evidence_refs": ["timeline.T2"]},
    ]
    match = match_tier_a(expected, produced)
    assert match["tp"] == 1
    assert match["fn"] == 1
    assert match["fp"] == 1
    assert match["recall"] == 0.5
    assert match["precision"] == 0.5


def test_tier_a_no_double_counting_across_invocations(tmp_path):
    # Evaluating a fixture with 3 categories must not multiply Tier A findings
    c0_case = FIXTURES_DIR / "C0.json"
    c0_expected = FIXTURES_DIR / "C0.expected.json"
    client = EvaluationLLMClient(mode="dry_run")

    result = evaluate_case("C0", c0_case, c0_expected, client)
    # C0 has exactly 2 expected Tier A flags (A1 and A6)
    assert result["tier_a"]["expected_count"] == 2
    assert result["tier_a"]["tp"] == 2
    assert result["tier_a"]["fp"] == 0
    assert result["tier_a"]["fn"] == 0


# --- 5, 6 & 7: Tier B Matching Tests ---

def test_tier_b_matching_order_insensitive_exact_refs():
    expected = [
        {
            "type": "contextual_contradiction",
            "about_refs": ["notes.N3", "photos.P1.d4"],
        }
    ]
    # Produced has reversed order of refs
    produced = [
        {
            "type": "contextual_contradiction",
            "evidence_refs": ["photos.P1.d4", "notes.N3"],
        }
    ]
    match = match_tier_b(expected, produced, is_clean=False)
    assert match["tp"] == 1
    assert match["fn"] == 0
    assert match["fp"] == 0
    assert match["recall"] == 1.0
    assert match["precision"] == 1.0


def test_tier_b_suggestion_cannot_satisfy_multiple_expected():
    expected = [
        {"type": "spatial_inconsistency", "about_refs": ["notes.N1", "evidence.E1"]},
        {"type": "spatial_inconsistency", "about_refs": ["notes.N1", "evidence.E1"]},
    ]
    # Only 1 produced suggestion
    produced = [
        {"type": "spatial_inconsistency", "evidence_refs": ["notes.N1", "evidence.E1"]},
    ]
    match = match_tier_b(expected, produced, is_clean=False)
    assert match["tp"] == 1
    assert match["fn"] == 1
    assert match["fp"] == 0


def test_rejected_suggestions_never_count_as_validated_findings(tmp_path):
    # If LLM produces suggestions with hallucinated/unresolved refs, validator drops them
    c2_case = FIXTURES_DIR / "C2.json"
    c2_expected = FIXTURES_DIR / "C2.expected.json"

    # Stub returns a suggestion citing non-existent ref
    invalid_stub = {
        "C2:spatial_inconsistency": {
            "suggestions": [
                {
                    "type": "spatial_inconsistency",
                    "severity": "medium",
                    "summary": "Fake summary",
                    "evidence_refs": ["notes.N9999_NON_EXISTENT"],
                    "reasoning": "Fake reasoning",
                    "suggested_action": "Fake action",
                }
            ]
        }
    }
    client = EvaluationLLMClient(mode="stub", stub_responses=invalid_stub)
    result = evaluate_case("C2", c2_case, c2_expected, client)

    # Suggestion was rejected by validator, so validated count must be 0
    assert result["tier_b"]["validated_count"] == 0
    assert result["tier_b"]["tp"] == 0
    assert result["rejections"]["rejected"] == 1
    assert result["rejections"]["drop_reasons"]["unresolved_ref"] == 1


# --- 8 & 9: Soft Expected Entries Tests ---

def test_soft_expected_entries_behavior():
    expected = [
        {
            "type": "timeline_contradiction",
            "about_refs": ["timeline.T1", "timeline.T2"],
            "soft": True,
        }
    ]
    # Scenario A: Missed soft entry -> 0 FN
    match_missed = match_tier_b(expected, [], is_clean=False)
    assert match_missed["tp"] == 0
    assert match_missed["fn"] == 0
    assert match_missed["fp"] == 0

    # Scenario B: Matched soft entry -> bonus hit, not FP
    produced = [
        {"type": "timeline_contradiction", "evidence_refs": ["timeline.T1", "timeline.T2"]}
    ]
    match_hit = match_tier_b(expected, produced, is_clean=False)
    assert match_hit["bonus_hits"] == 1
    assert match_hit["fp"] == 0
    assert match_hit["fn"] == 0


# --- 10 & 11: Clean-Case False Positives & Zero-Denominator Tests ---

def test_clean_case_tier_b_false_positives():
    expected = []  # Clean case
    produced = [
        {"type": "spatial_inconsistency", "evidence_refs": ["notes.N1", "evidence.E1"]}
    ]
    match = match_tier_b(expected, produced, is_clean=True)
    assert match["tp"] == 0
    assert match["fn"] == 0
    assert match["fp"] == 1  # Validated suggestion on clean case is an FP


def test_zero_denominator_metrics():
    # When expected and produced are both empty
    match_a = match_tier_a([], [])
    assert match_a["recall"] is None
    assert match_a["precision"] is None

    match_b = match_tier_b([], [], is_clean=True)
    assert match_b["recall"] is None
    assert match_b["precision"] is None


# --- 12: Rejection Rate and Drop Reasons Aggregation ---

def test_rejection_rate_and_drop_reasons():
    per_case = [
        {
            "fixture_stem": "C0",
            "clean": False,
            "tier_a": {"tp": 2, "fn": 0, "fp": 0, "recall": 1.0, "precision": 1.0},
            "tier_b": {"tp": 1, "fn": 0, "fp": 0, "bonus_hits": 0, "recall": 1.0, "precision": 1.0},
            "rejections": {
                "received": 5,
                "rejected": 2,
                "drop_reasons": {
                    "schema_fail": 1,
                    "type_mismatch": 0,
                    "unresolved_ref": 1,
                    "dismissal_guard": 0,
                    "hallucination_suspected": 0,
                    "deduped_by_tier_a": 0,
                },
            },
            "latency_ms": 10.0,
            "errors": [],
        }
    ]
    # Check table formatting shows numerator and denominator
    table = format_per_case_table(per_case)
    assert "2/5" in table


# --- 13: Dry-Run Mode Tests ---

def test_dry_run_executes_offline_and_returns_empty(tmp_path):
    reports_dir = tmp_path / "reports"
    eval_data = evaluate_all(
        cases_dir=FIXTURES_DIR,
        mode="dry_run",
    )
    assert eval_data["mode"] == "dry_run"
    assert eval_data["rate_limited_count"] == 0
    # Tier A recall is 1.00 on all fixtures
    assert eval_data["targets"]["tier_a_recall"]["status"] == "PASS"
    # Tier A precision is informational
    assert eval_data["targets"]["tier_a_precision"]["status"] == "INFO"
    # Tier B recall is 0.00 in dry-run because stub returns no suggestions
    assert eval_data["targets"]["tier_b_recall"]["status"] == "FAIL"
    # Dry-run latency is non-representative and marked N/A (not PASS)
    assert eval_data["targets"]["median_latency_ms"]["status"] == "N/A"
    assert "dry-run" in eval_data["targets"]["median_latency_ms"]["display_value"]
    # Clean case count is dynamically derived as 7
    assert eval_data["clean_cases_count"] == 7
    # Overall passed is False
    assert eval_data["passed"] is False


# --- 14 & 15: Stub Mode Tests ---

def test_stub_mode_replays_and_validates(tmp_path):
    stub_file = tmp_path / "stub_responses.json"
    stub_content = {
        "C2:spatial_inconsistency": {
            "suggestions": [
                {
                    "type": "spatial_inconsistency",
                    "severity": "medium",
                    "summary": "Knife near window conflicts with note.",
                    "evidence_refs": ["notes.N1", "evidence.E1"],
                    "reasoning": "N1 states near door, map places near window.",
                    "suggested_action": "Verify position.",
                }
            ]
        }
    }
    stub_file.write_text(json.dumps(stub_content), encoding="utf-8")

    c2_case = FIXTURES_DIR / "C2.json"
    c2_expected = FIXTURES_DIR / "C2.expected.json"
    client = EvaluationLLMClient(mode="stub", stub_responses=stub_content)

    res = evaluate_case("C2", c2_case, c2_expected, client)
    assert res["tier_b"]["tp"] == 1
    assert res["tier_b"]["recall"] == 1.0


def test_missing_stub_entry_raises_error(tmp_path):
    stub_file = tmp_path / "stub_responses.json"
    # Empty stub dictionary
    stub_file.write_text("{}", encoding="utf-8")

    c0_case = FIXTURES_DIR / "C0.json"
    c0_expected = FIXTURES_DIR / "C0.expected.json"
    client = EvaluationLLMClient(mode="stub", stub_responses={})

    # Must record error rather than silently defaulting to empty
    res = evaluate_case("C0", c0_case, c0_expected, client)
    assert len(res["errors"]) > 0
    assert "Missing stub response" in res["errors"][0]


# --- 16: Report Generation Tests ---

def test_reports_generated_json_and_markdown(tmp_path):
    reports_dir = tmp_path / "reports"
    exit_code = main(["--dry-run-llm", "--reports-dir", str(reports_dir)])
    assert exit_code == 1  # Tier B recall fails in dry run

    json_files = list(reports_dir.glob("eval_*.json"))
    md_files = list(reports_dir.glob("eval_*.md"))
    assert len(json_files) == 1
    assert len(md_files) == 1

    # Verify JSON content
    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert "targets" in data
    assert "per_case" in data
    assert data["mode"] == "dry_run"

    # Verify Markdown content
    md_text = md_files[0].read_text(encoding="utf-8")
    assert "| Case | Clean? | A-recall |" in md_text
    assert "Tier A recall" in md_text


# --- 17: Exit Codes Tests ---

def test_main_cli_exit_codes(tmp_path):
    reports_dir = tmp_path / "reports"

    # 1. Dry run fails targets -> exit code 1
    code_dry = main(["--dry-run-llm", "--reports-dir", str(reports_dir)])
    assert code_dry == 1

    # 2. Invalid concurrency -> exit code 2
    code_invalid_conc = main(["--dry-run-llm", "--max-concurrency", "0"])
    assert code_invalid_conc == 2

    # 3. Non-existent stub file -> exit code 2
    code_missing_stub = main(["--stub-llm", "non_existent_stub.json"])
    assert code_missing_stub == 2


# --- 18: Concurrency Validation & Execution Tests ---

def test_concurrency_validation():
    # Negative or zero concurrency is rejected
    assert main(["--max-concurrency", "-1"]) == 2
    assert main(["--max-concurrency", "0"]) == 2


def test_max_concurrency_live_execution(tmp_path):
    # Verify execution with max_concurrency > 1 runs cleanly without errors
    # Using dry_run mode in evaluate_all with max_concurrency=2
    eval_data = evaluate_all(
        cases_dir=FIXTURES_DIR,
        mode="dry_run",
        max_concurrency=2,
    )
    assert eval_data["max_concurrency"] == 2
    assert len(eval_data["per_case"]) == 13


# --- 19: Regression Tests for Approved Acceptance Targets & Reporting ---

def test_approved_acceptance_targets_thresholds():
    """Verify exact approved thresholds from PROJECT_BRIEF.md §11."""
    assert ACCEPTANCE_TARGETS["tier_a_recall"]["target"] == 1.00
    assert ACCEPTANCE_TARGETS["tier_a_recall"]["op"] == "=="
    assert ACCEPTANCE_TARGETS["tier_a_recall"]["required"] is True

    # Tier A precision is informational only
    assert ACCEPTANCE_TARGETS["tier_a_precision"]["required"] is False
    assert ACCEPTANCE_TARGETS["tier_a_precision"]["display"] == "Informational"

    assert ACCEPTANCE_TARGETS["tier_b_recall"]["target"] == 0.85
    assert ACCEPTANCE_TARGETS["tier_b_recall"]["op"] == ">="
    assert ACCEPTANCE_TARGETS["tier_b_recall"]["display"] == "≥0.85"
    assert ACCEPTANCE_TARGETS["tier_b_recall"]["required"] is True

    assert ACCEPTANCE_TARGETS["tier_b_precision"]["target"] == 0.85
    assert ACCEPTANCE_TARGETS["tier_b_precision"]["op"] == ">="
    assert ACCEPTANCE_TARGETS["tier_b_precision"]["display"] == "≥0.85"
    assert ACCEPTANCE_TARGETS["tier_b_precision"]["required"] is True

    assert ACCEPTANCE_TARGETS["hallucination_rate"]["target"] == 0.00
    assert ACCEPTANCE_TARGETS["hallucination_rate"]["op"] == "=="
    assert ACCEPTANCE_TARGETS["hallucination_rate"]["required"] is True

    assert ACCEPTANCE_TARGETS["clean_cases_fp"]["target"] == 0
    assert ACCEPTANCE_TARGETS["clean_cases_fp"]["op"] == "=="
    assert ACCEPTANCE_TARGETS["clean_cases_fp"]["required"] is True

    assert ACCEPTANCE_TARGETS["median_latency_ms"]["target"] == 6000.0
    assert ACCEPTANCE_TARGETS["median_latency_ms"]["op"] == "<"
    assert ACCEPTANCE_TARGETS["median_latency_ms"]["display"] == "<6000 ms"
    assert ACCEPTANCE_TARGETS["median_latency_ms"]["required"] is True


def test_dynamic_clean_case_count():
    """Verify dynamic derivation of clean case count from expected files."""
    clean_fixtures = [
        f for f in FIXTURES_DIR.glob("*.expected.json")
        if json.loads(f.read_text(encoding="utf-8")).get("clean", False)
    ]
    expected_clean_count = len(clean_fixtures)
    assert expected_clean_count == 7  # C5, C6, C7, C10, C11, C12, C13

    eval_data = evaluate_all(cases_dir=FIXTURES_DIR, mode="dry_run")
    assert eval_data["clean_cases_count"] == expected_clean_count
    assert eval_data["clean_cases_count"] == 7
    assert eval_data["total_fixtures_count"] == 13

    # Clean cases false positives target reports clean count and passes on dry-run
    assert eval_data["targets"]["clean_cases_fp"]["clean_cases_count"] == 7
    assert eval_data["targets"]["clean_cases_fp"]["status"] == "PASS"


def test_dry_run_and_stub_latency_marked_non_representative(tmp_path):
    """Dry-run and stub latency must be marked N/A rather than passing with 0 ms."""
    eval_data = evaluate_all(cases_dir=FIXTURES_DIR, mode="dry_run")
    latency_target = eval_data["targets"]["median_latency_ms"]
    assert latency_target["status"] == "N/A"
    assert latency_target["status"] != "PASS"
    assert latency_target["display_value"] == "N/A (dry-run)"
    assert latency_target["value"] is None

    # Stub mode also marks latency as non-representative
    stub_file = tmp_path / "stub.json"
    stub_file.write_text("{}", encoding="utf-8")
    # Stub without full fixtures returns N/A for latency
    eval_stub = evaluate_all(
        cases_dir=FIXTURES_DIR,
        mode="stub",
        stub_path=stub_file,
    )
    stub_latency = eval_stub["targets"]["median_latency_ms"]
    assert stub_latency["status"] == "N/A"
    assert stub_latency["status"] != "PASS"
    assert stub_latency["display_value"] == "N/A (stub replay)"


def test_live_latency_evaluated_against_six_second_target(monkeypatch):
    """In live mode, median latency must be evaluated against the 6000 ms threshold using per-case values."""
    import statistics
    from src.llm import LLMConfig

    live_cfg = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test-mock-key")

    # Mock evaluate_case to simulate distinct live per-case latencies
    latencies = [1000.0 + i * 200.0 for i in range(13)]  # median is 2200.0 ms (< 6000 ms)

    call_count = 0
    def mock_eval_case_fast(stem, case_p, exp_p, client):
        nonlocal call_count
        res = evaluate_case(stem, case_p, exp_p, EvaluationLLMClient(mode="dry_run"))
        res["latency_ms"] = latencies[call_count % len(latencies)]
        call_count += 1
        return res

    monkeypatch.setattr("evaluate.evaluate_case", mock_eval_case_fast)
    eval_fast = evaluate_all(cases_dir=FIXTURES_DIR, mode="live", live_config=live_cfg)
    assert eval_fast["targets"]["median_latency_ms"]["status"] == "PASS"
    assert eval_fast["targets"]["median_latency_ms"]["value"] == statistics.median(latencies)
    assert len(eval_fast["latency_ms"]["values"]) == 13
    assert sorted(eval_fast["latency_ms"]["values"]) == sorted(latencies)

    # Slow cases: median >= 6000 ms
    slow_latencies = [6000.0 + i * 100.0 for i in range(13)]
    slow_call_count = 0
    def mock_eval_case_slow(stem, case_p, exp_p, client):
        nonlocal slow_call_count
        res = evaluate_case(stem, case_p, exp_p, EvaluationLLMClient(mode="dry_run"))
        res["latency_ms"] = slow_latencies[slow_call_count % len(slow_latencies)]
        slow_call_count += 1
        return res

    monkeypatch.setattr("evaluate.evaluate_case", mock_eval_case_slow)
    eval_slow = evaluate_all(cases_dir=FIXTURES_DIR, mode="live", live_config=live_cfg)
    assert eval_slow["targets"]["median_latency_ms"]["status"] == "FAIL"
    assert eval_slow["targets"]["median_latency_ms"]["value"] == statistics.median(slow_latencies)


def test_one_latency_measurement_per_case_with_multiple_categories(monkeypatch):
    """Verify exactly one wall-clock latency measurement per case when multiple categories run."""
    c5_case = FIXTURES_DIR / "C5.json"
    c5_expected = FIXTURES_DIR / "C5.expected.json"

    # In live mode, client.mode == "live"
    # Create an EvaluationLLMClient that records mock suggestions
    class MockLiveLLMClient(EvaluationLLMClient):
        def __init__(self):
            super().__init__(mode="live")
        def analyze_case(self, case_context, assigned_analysis_type):
            from src.llm import LLMResponse
            return LLMResponse({
                "suggestions": [],
                "status": "success",
                "error": None,
                "raw_response": '{"suggestions": []}',
                "provider": "mock_live",
                "model": "mock_model",
                "attempts": 1,
                "latency_ms": 150.0,
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            })

    mock_client = MockLiveLLMClient()
    result = evaluate_case("C5", c5_case, c5_expected, mock_client)

    # C5 is clean, so all 3 Tier B categories run
    assert len(result["categories_run"]) == 3
    # Exactly one latency measurement per case
    assert isinstance(result["latency_ms"], float)
    assert result["latency_ms"] >= 0.0
    # Individual provider latencies are kept separate for diagnostics
    assert len(result["diagnostic_provider_latencies_ms"]) == 3
    for prov_lat in result["diagnostic_provider_latencies_ms"]:
        assert prov_lat == 150.0
    # result["latency_ms"] is NOT the sum or median of provider latencies; it is the wall-clock time
    assert result["latency_ms"] != 150.0


def test_no_false_pass_when_required_metric_is_na():
    """If any required acceptance metric is N/A, overall status must NOT be PASS."""
    eval_data = evaluate_all(cases_dir=FIXTURES_DIR, mode="dry_run")
    # In dry-run, tier_b_precision is N/A and tier_b_recall is FAIL
    assert eval_data["targets"]["tier_b_precision"]["status"] == "N/A"
    assert eval_data["targets"]["tier_b_recall"]["status"] == "FAIL"
    assert eval_data["passed"] is False

    # Even if tier_a_recall, clean_fp, and hallucination_rate pass, N/A on a required metric fails overall
    assert eval_data["targets"]["tier_a_recall"]["status"] == "PASS"
    assert eval_data["targets"]["hallucination_rate"]["status"] == "PASS"
    assert eval_data["targets"]["clean_cases_fp"]["status"] == "PASS"
    assert eval_data["passed"] is False

