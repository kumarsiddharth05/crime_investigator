"""Comprehensive offline mocked test suite for Prompt 14 Investigator Workflow.

Covers all 17 test scenarios in Prompt 14 §H without live API calls or network requests:
1. Case selection (discovered cases + custom path + invalid path).
2. Valid menu operations (complete + each single category).
3. Invalid menu selections.
4. JSON request envelope validation (bad schema version, bad operation, invalid/empty analysis_types, non-dict case_context).
5. Correct pipeline dispatch (semantic gate preserved, 1 category per invocation).
6. Findings display.
7. Empty-result display (exact message verified).
8. Partial completion (completed + ineligible/failed separated; retry only for eligible failed).
9. Technical failure (provider error -> failed, not empty success).
10. Source-reference navigation via refs.py.
11. Review status updates (acknowledged, deferred, not_relevant).
12. Mandatory dismissal reason enforced for not_relevant.
13. Analysis history & view previous analysis.
14. Return navigation across menus/submenus.
15. No fabricated results/references.
16. No LLM-controlled available_actions.
17. Immutability of original model findings after reviews are recorded.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
import httpx
import pytest

from investigator_cli import InvestigatorCLI
from src.analysis.refs import resolve_ref
from src.llm import LLMClient, LLMConfig, LLMTransportError
from src.workflow import (
    EMPTY_SUGGESTIONS_MESSAGE,
    RESULT_STATE_EMPTY,
    RESULT_STATE_FAILURE,
    RESULT_STATE_FINDINGS,
    RESULT_STATE_PARTIAL,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_FAILED,
    WorkflowAdapter,
    WorkflowRequest,
    WorkflowStore,
    validate_request_envelope,
)
from src.workflow.adapter import discover_cases, inspect_source_references, load_case_context
from src.workflow.envelope import get_available_actions

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "cases"

VALID_SPATIAL_PAYLOAD = {
    "suggestions": [
        {
            "type": "spatial_inconsistency",
            "severity": "medium",
            "summary": "Note places knife near door while map places it near window.",
            "evidence_refs": ["notes.N1", "evidence.E1"],
            "reasoning": "Spatial mismatch between officer note N1 and map summary.",
            "suggested_action": "Verify physical placement of E1 against photo P1.",
        }
    ]
}

VALID_TIMELINE_PAYLOAD = {
    "suggestions": [
        {
            "type": "timeline_contradiction",
            "severity": "high",
            "summary": "Timeline entry contradicts witness call time.",
            "evidence_refs": ["timeline.T1", "timeline.T2"],
            "reasoning": "Dispatch timestamp conflicts with witness report.",
            "suggested_action": "Recheck call logs.",
        }
    ]
}

EMPTY_PAYLOAD = {"suggestions": []}


class MockCLI_IO:
    """Mock IO controller for testing interactive CLI flows deterministically."""

    def __init__(self, inputs: list[str]) -> None:
        self.inputs = list(inputs)
        self.outputs: list[str] = []

    def input_fn(self, prompt: str = "") -> str:
        if not self.inputs:
            raise EOFError("No more mock inputs")
        return self.inputs.pop(0)

    def output_fn(self, text: str) -> None:
        self.outputs.append(str(text))

    @property
    def full_output(self) -> str:
        return "\n".join(self.outputs)


def build_mock_client(payload: dict[str, Any] | None = None, raise_exc: Exception | None = None) -> LLMClient:
    """Helper to create an offline mocked LLMClient."""
    def handler(request: httpx.Request) -> httpx.Response:
        if raise_exc is not None:
            raise raise_exc
        body = payload if payload is not None else EMPTY_PAYLOAD
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}]})

    return LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture
def sample_c0() -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "C0.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_c2() -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "C2.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_c11() -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "C11.json").read_text(encoding="utf-8"))


# --- Test 1: Case Selection ---

def test_1_case_selection(tmp_path):
    cases = discover_cases(FIXTURES_DIR)
    assert len(cases) > 0
    assert not any(p.name.endswith(".expected.json") for p in cases)

    store = WorkflowStore(tmp_path / "store")
    adapter = WorkflowAdapter(store=store)

    # 1. Selection via index
    io_idx = MockCLI_IO(["1", "1", "9"])
    cli_idx = InvestigatorCLI(adapter=adapter, store=store, input_fn=io_idx.input_fn, output_fn=io_idx.output_fn, cases_dir=FIXTURES_DIR)
    cli_idx.run()
    assert cli_idx.current_case_id is not None
    assert "Successfully loaded case" in io_idx.full_output

    # 2. Selection via custom valid path
    c0_path = str(FIXTURES_DIR / "C0.json")
    io_custom = MockCLI_IO(["1", "C", c0_path, "9"])
    cli_custom = InvestigatorCLI(adapter=adapter, store=store, input_fn=io_custom.input_fn, output_fn=io_custom.output_fn, cases_dir=FIXTURES_DIR)
    cli_custom.run()
    assert cli_custom.current_case_id in ("C0", "C-2026-001")

    # 3. Selection via invalid path
    io_bad = MockCLI_IO(["1", "C", "cases/non_existent.json", "9"])
    cli_bad = InvestigatorCLI(adapter=adapter, store=store, input_fn=io_bad.input_fn, output_fn=io_bad.output_fn, cases_dir=FIXTURES_DIR)
    cli_bad.run()
    assert "Error loading case file" in io_bad.full_output or "Invalid case selection" in io_bad.full_output


# --- Test 2: Valid Menu Operations ---

def test_2_valid_menu_operations(tmp_path, sample_c0):
    store = WorkflowStore(tmp_path / "store")
    client = build_mock_client(VALID_SPATIAL_PAYLOAD)
    adapter = WorkflowAdapter(store=store, client_factory=lambda: client)

    # Test Complete Analysis (2), Spatial (3), Timeline (4), Contextual (5)
    for opt in ["2", "3", "4", "5"]:
        io = MockCLI_IO(["1", "1", opt, "3", "9"])  # Select case, run option, return to menu, exit
        cli = InvestigatorCLI(adapter=adapter, store=store, input_fn=io.input_fn, output_fn=io.output_fn, cases_dir=FIXTURES_DIR)
        cli.run()
        assert "Analysis Status:" in io.full_output


# --- Test 3: Invalid Menu Selections ---

def test_3_invalid_menu_selections(tmp_path):
    store = WorkflowStore(tmp_path / "store")
    adapter = WorkflowAdapter(store=store)

    io = MockCLI_IO(["foo", "99", "-1", "", "9"])
    cli = InvestigatorCLI(adapter=adapter, store=store, input_fn=io.input_fn, output_fn=io.output_fn, cases_dir=FIXTURES_DIR)
    cli.run()

    assert io.full_output.count("Invalid selection. Please choose an option from the menu") == 4
    assert "Exiting Investigator CLI." in io.full_output


# --- Test 4: JSON Request Envelope Validation ---

def test_4_request_envelope_validation(sample_c0):
    # Bad schema version
    bad_schema = {"schema_version": "2.0", "operation": "analyze", "analysis_types": ["spatial_inconsistency"], "case_context": sample_c0}
    ok, err = validate_request_envelope(bad_schema)
    assert not ok
    assert "Unsupported schema_version" in str(err)

    # Bad operation
    bad_op = {"schema_version": "1.0", "operation": "delete", "analysis_types": ["spatial_inconsistency"], "case_context": sample_c0}
    ok, err = validate_request_envelope(bad_op)
    assert not ok
    assert "Unsupported operation" in str(err)

    # Empty analysis_types
    empty_types = {"schema_version": "1.0", "operation": "analyze", "analysis_types": [], "case_context": sample_c0}
    ok, err = validate_request_envelope(empty_types)
    assert not ok
    assert "analysis_types must be a non-empty list" in str(err)

    # Invalid analysis_type
    invalid_type = {"schema_version": "1.0", "operation": "analyze", "analysis_types": ["ballistics_magic"], "case_context": sample_c0}
    ok, err = validate_request_envelope(invalid_type)
    assert not ok
    assert "Invalid analysis category" in str(err)

    # Non-dict case_context
    non_dict = {"schema_version": "1.0", "operation": "analyze", "analysis_types": ["spatial_inconsistency"], "case_context": "string"}
    ok, err = validate_request_envelope(non_dict)
    assert not ok
    assert "case_context must be a dictionary" in str(err)


# --- Test 5: Correct Pipeline Dispatch ---

def test_5_correct_pipeline_dispatch(tmp_path, sample_c11):
    """Verify semantic gate is preserved and 1-category-per-invocation discipline is enforced."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(VALID_SPATIAL_PAYLOAD)}}]})

    client = LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )

    adapter = WorkflowAdapter(store=WorkflowStore(tmp_path / "store"))
    # In C11, spatial_inconsistency is eligible, but timeline_contradiction has 0 timeline records and is ineligible!
    req = WorkflowRequest.create(
        case_id="C11",
        case_context=sample_c11,
        analysis_types=["spatial_inconsistency", "timeline_contradiction"],
    )
    resp = adapter.execute_request(req, client=client)

    # Timeline contradiction was skipped by semantic gate
    ineligible = [item["category"] for item in resp["data"]["ineligible_categories"]]
    assert "timeline_contradiction" in ineligible
    # Only 1 LLM invocation for the single eligible category
    assert call_count == 1
    assert resp["data"]["completed_categories"] == ["spatial_inconsistency"]


# --- Test 6: Findings Display ---

def test_6_findings_display(tmp_path, sample_c0):
    store = WorkflowStore(tmp_path / "store")
    client = build_mock_client(VALID_SPATIAL_PAYLOAD)
    adapter = WorkflowAdapter(store=store, client_factory=lambda: client)

    io = MockCLI_IO(["1", "1", "3", "3", "9"])
    cli = InvestigatorCLI(adapter=adapter, store=store, input_fn=io.input_fn, output_fn=io.output_fn, cases_dir=FIXTURES_DIR)
    cli.run()

    out = io.full_output
    assert "[Finding #1] ID: S001 | Category: spatial_inconsistency | Severity: MEDIUM" in out
    assert "Summary: Note places knife near door while map places it near window." in out
    assert "Evidence References: notes.N1, evidence.E1" in out
    assert "Validation Status: Validated" in out


# --- Test 7: Empty-Result Display ---

def test_7_empty_result_display(tmp_path, sample_c0):
    store = WorkflowStore(tmp_path / "store")
    client = build_mock_client(EMPTY_PAYLOAD)
    adapter = WorkflowAdapter(store=store, client_factory=lambda: client)

    io = MockCLI_IO(["1", "1", "3", "3", "9"])
    cli = InvestigatorCLI(adapter=adapter, store=store, input_fn=io.input_fn, output_fn=io.output_fn, cases_dir=FIXTURES_DIR)
    cli.run()

    # Must verify the exact required message verbatim
    assert EMPTY_SUGGESTIONS_MESSAGE in io.full_output


# --- Test 8: Partial Completion ---

def test_8_partial_completion(tmp_path, sample_c2):
    """In C2, both spatial and timeline are gate-eligible. Make one fail and one succeed."""
    store = WorkflowStore(tmp_path / "store")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content.decode("utf-8"))
        messages = data.get("messages", [])
        user_prompt = messages[1].get("content", "") if len(messages) > 1 else ""
        if "timeline_contradiction" in user_prompt:
            return httpx.Response(500, text="Internal Server Error")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(VALID_SPATIAL_PAYLOAD)}}]})

    client = LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )
    adapter = WorkflowAdapter(store=store)

    req = WorkflowRequest.create(
        case_id="C2",
        case_context=sample_c2,
        analysis_types=["spatial_inconsistency", "timeline_contradiction"],
    )
    resp = adapter.execute_request(req, client=client)

    assert resp["data"]["result_state"] == RESULT_STATE_PARTIAL
    assert resp["status"] == STATUS_COMPLETED_WITH_WARNINGS
    assert "spatial_inconsistency" in resp["data"]["completed_categories"]
    assert any(fc["category"] == "timeline_contradiction" for fc in resp["data"]["failed_categories"])
    # Retryable contains ONLY the eligible failed category
    assert resp["data"]["retryable_categories"] == ["timeline_contradiction"]


# --- Test 9: Technical Failure ---

def test_9_technical_failure(tmp_path, sample_c0):
    store = WorkflowStore(tmp_path / "store")
    client = build_mock_client(raise_exc=httpx.ConnectError("Network dropped"))
    adapter = WorkflowAdapter(store=store)

    req = WorkflowRequest.create(
        case_id="C0",
        case_context=sample_c0,
        analysis_types=["spatial_inconsistency"],
    )
    resp = adapter.execute_request(req, client=client)

    assert resp["data"]["result_state"] == RESULT_STATE_FAILURE
    assert resp["status"] == STATUS_FAILED
    assert len(resp["errors"]) > 0
    # Must never be disguised as empty suggestions
    assert resp["data"]["result_state"] != RESULT_STATE_EMPTY


# --- Test 10: Source-Reference Navigation via refs.py ---

def test_10_source_reference_navigation(sample_c0):
    refs = ["notes.N1", "evidence.E1", "non_existent.ref"]
    resolved = inspect_source_references(sample_c0, refs)

    assert resolved["notes.N1"] is not None
    assert resolved["notes.N1"].get("ref") == "notes.N1"
    assert resolved["evidence.E1"] is not None
    assert resolved["evidence.E1"].get("ref") == "evidence.E1"
    assert resolved["non_existent.ref"] is None


# --- Test 11: Review Status Updates ---

def test_11_review_status_updates(tmp_path):
    store = WorkflowStore(tmp_path / "store")
    analysis_id = "test_analysis_001"

    # Acknowledged
    r1 = store.record_review(analysis_id, "S001", "acknowledged", comment="Checked by lead detective")
    assert r1["review_status"] == "acknowledged"
    assert store.get_latest_review_status(analysis_id, "S001") == "acknowledged"

    # Deferred
    r2 = store.record_review(analysis_id, "S001", "deferred", comment="Awaiting lab results")
    assert r2["review_status"] == "deferred"
    assert store.get_latest_review_status(analysis_id, "S001") == "deferred"

    # Not relevant (with non-empty reason)
    r3 = store.record_review(analysis_id, "S001", "not_relevant", comment="Known lighting artifact")
    assert r3["review_status"] == "not_relevant"
    assert store.get_latest_review_status(analysis_id, "S001") == "not_relevant"


# --- Test 12: Mandatory Dismissal Reason Enforced ---

def test_12_mandatory_dismissal_reason(tmp_path):
    store = WorkflowStore(tmp_path / "store")

    # Empty string
    with pytest.raises(ValueError, match="non-empty comment/reason is mandatory"):
        store.record_review("A1", "S001", "not_relevant", comment="")

    # Whitespace only
    with pytest.raises(ValueError, match="non-empty comment/reason is mandatory"):
        store.record_review("A1", "S001", "not_relevant", comment="   \t\n  ")

    # CLI rejection of empty dismissal reason
    client = build_mock_client(VALID_SPATIAL_PAYLOAD)
    adapter = WorkflowAdapter(store=store, client_factory=lambda: client)
    # Flow: Select C0 (1, 1), run spatial (3), review status (2), select finding 1 (1),
    # select not_relevant (2), enter empty reason (""), return (3), exit (9)
    io = MockCLI_IO(["1", "1", "3", "2", "1", "2", "", "3", "9"])
    cli = InvestigatorCLI(adapter=adapter, store=store, input_fn=io.input_fn, output_fn=io.output_fn, cases_dir=FIXTURES_DIR)
    cli.run()
    assert "A non-empty reason is mandatory when marking a finding as not relevant." in io.full_output


# --- Test 13: Analysis History & View Previous Analysis ---

def test_13_analysis_history_and_view_previous(tmp_path, sample_c0):
    store = WorkflowStore(tmp_path / "store")
    client = build_mock_client(VALID_SPATIAL_PAYLOAD)
    adapter = WorkflowAdapter(store=store, client_factory=lambda: client)

    case_id = sample_c0.get("case", {}).get("id", "C-2026-001")
    req = WorkflowRequest.create(case_id, sample_c0, ["spatial_inconsistency"])
    resp1 = adapter.execute_request(req)
    resp2 = adapter.execute_request(req)

    history = store.get_case_history(case_id)
    assert len(history) == 2
    latest = store.get_latest_analysis(case_id)
    assert latest is not None
    assert latest["analysis_id"] == history[0]["analysis_id"]

    # View previous analysis via CLI option 6
    io = MockCLI_IO(["1", "1", "6", "3", "9"])
    cli = InvestigatorCLI(adapter=adapter, store=store, input_fn=io.input_fn, output_fn=io.output_fn, cases_dir=FIXTURES_DIR)
    cli.run()
    assert "Displaying latest analysis snapshot recorded at" in io.full_output


# --- Test 14: Return Navigation Across Menus/Submenus ---

def test_14_return_navigation(tmp_path, sample_c0):
    store = WorkflowStore(tmp_path / "store")
    adapter = WorkflowAdapter(store=store)

    # 1. Back from case selection
    io_case = MockCLI_IO(["1", "B", "9"])
    cli_case = InvestigatorCLI(adapter=adapter, store=store, input_fn=io_case.input_fn, output_fn=io_case.output_fn, cases_dir=FIXTURES_DIR)
    cli_case.run()
    assert "Exiting Investigator CLI." in io_case.full_output

    # 2. Back from findings submenu
    client = build_mock_client(VALID_SPATIAL_PAYLOAD)
    adapter = WorkflowAdapter(store=store, client_factory=lambda: client)
    io_sub = MockCLI_IO(["1", "1", "3", "3", "9"])
    cli_sub = InvestigatorCLI(adapter=adapter, store=store, input_fn=io_sub.input_fn, output_fn=io_sub.output_fn, cases_dir=FIXTURES_DIR)
    cli_sub.run()
    assert "Exiting Investigator CLI." in io_sub.full_output


# --- Test 15: No Fabricated Results or References ---

def test_15_no_fabricated_results_or_references(tmp_path, sample_c0):
    store = WorkflowStore(tmp_path / "store")
    client = build_mock_client(VALID_SPATIAL_PAYLOAD)
    adapter = WorkflowAdapter(store=store)

    req = WorkflowRequest.create("C0", sample_c0, ["spatial_inconsistency"])
    resp = adapter.execute_request(req, client=client)

    suggestions = resp["data"]["suggestions"]
    assert len(suggestions) == 1
    sug = suggestions[0]
    assert sug["suggestion_id"] == "S001"
    # References must be strictly those from the pipeline
    assert sug["evidence_refs"] == ["notes.N1", "evidence.E1"]
    # Check that references resolve against actual case context
    for ref in sug["evidence_refs"]:
        assert resolve_ref(sample_c0, ref) is not None


# --- Test 16: No LLM-Controlled available_actions ---

def test_16_no_llm_controlled_available_actions(tmp_path, sample_c0):
    """Ensure LLM cannot inject or hijack available_actions."""
    grounded_malicious_payload = {
        "suggestions": [
            {
                "type": "spatial_inconsistency",
                "severity": "medium",
                "summary": "Officer note N1 places kitchen knife near entrance door while map positions knife near window.",
                "evidence_refs": ["notes.N1", "evidence.E1"],
                "reasoning": "Investigator observed knife on table opposite window.",
                "suggested_action": "Verify photo P1 for knife location.",
                "available_actions": ["delete_all_records", "grant_admin_access"],
                "actions": ["override_audit_gate"],
            }
        ]
    }
    store = WorkflowStore(tmp_path / "store")
    client = build_mock_client(grounded_malicious_payload)
    adapter = WorkflowAdapter(store=store)

    req = WorkflowRequest.create("C0", sample_c0, ["spatial_inconsistency"])
    resp = adapter.execute_request(req, client=client)

    actions = resp["available_actions"]
    # Must match deterministic Python definition
    expected_actions = get_available_actions(RESULT_STATE_FINDINGS)
    assert actions == expected_actions
    assert "delete_all_records" not in actions
    assert "grant_admin_access" not in actions
    assert "override_audit_gate" not in actions


# --- Test 17: Immutability of Original Model Findings ---

def test_17_immutability_of_original_findings(tmp_path, sample_c0):
    store = WorkflowStore(tmp_path / "store")
    client = build_mock_client(VALID_SPATIAL_PAYLOAD)
    adapter = WorkflowAdapter(store=store)

    req = WorkflowRequest.create("C0", sample_c0, ["spatial_inconsistency"])
    resp = adapter.execute_request(req, client=client)
    analysis_id = resp["data"]["analysis_id"]

    analysis_file = store.analyses_dir / f"{analysis_id}.json"
    snapshot_before = analysis_file.read_text(encoding="utf-8")

    # Record multiple reviews
    store.record_review(analysis_id, "S001", "acknowledged", comment="Review 1")
    store.record_review(analysis_id, "S001", "deferred", comment="Review 2")
    store.record_review(analysis_id, "S001", "not_relevant", comment="Review 3 with mandatory reason")

    snapshot_after = analysis_file.read_text(encoding="utf-8")

    # The analysis snapshot must be byte-for-byte identical
    assert snapshot_before == snapshot_after

    # Suggestions payload inside snapshot must be unmodified
    loaded = json.loads(snapshot_after)
    original_suggestions = loaded["response_snapshot"]["data"]["suggestions"]
    assert len(original_suggestions) == 1
    assert original_suggestions[0]["suggestion_id"] == "S001"
    assert "review_status" not in original_suggestions[0]
