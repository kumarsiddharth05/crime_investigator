"""Unit and integration tests for analysis pipeline orchestrator and CLI.

All tests run completely offline with mocked transport calls.
No live API keys or external network connections are required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest
import httpx

from analyze import main
from src.analysis import (
    PipelineResult,
    compute_context_hash,
    evaluate_semantic_gate,
    run_pipeline,
)
from src.llm import (
    DEFAULT_TEMPERATURE,
    LLMAuthenticationError,
    LLMClient,
    LLMConfig,
    LLMResponse,
    LLMTransportError,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "cases"

VALID_SUGGESTION_PAYLOAD = {
    "suggestions": [
        {
            "type": "spatial_inconsistency",
            "severity": "medium",
            "summary": "Note places E1 near door while map summary places it near window.",
            "evidence_refs": ["notes.N1", "evidence.E1"],
            "reasoning": "N1 states evidence is near entrance, but map positions it across the room.",
            "suggested_action": "Verify physical placement of E1 against photo P1.",
        }
    ]
}


@pytest.fixture
def sample_c0_context() -> dict[str, Any]:
    c0_path = FIXTURES_DIR / "C0.json"
    return json.loads(c0_path.read_text(encoding="utf-8"))


@pytest.fixture
def sample_c2_context() -> dict[str, Any]:
    c2_path = FIXTURES_DIR / "C2.json"
    return json.loads(c2_path.read_text(encoding="utf-8"))


# --- 1. Tier A-Only Execution ---

def test_pipeline_tier_a_only(sample_c0_context, tmp_path):
    result = run_pipeline(
        case_context=sample_c0_context,
        tier_a_only=True,
        run_dir=tmp_path,
    )
    assert isinstance(result, PipelineResult)
    assert result.status == "success"
    assert len(result.tier_a_flags) > 0  # C0 has A1 and A6 flags
    assert len(result.tier_b_suggestions) == 0
    assert len(result.invocation_outcomes) == 0
    assert result.stats["received"] == 0


# --- 2. Semantic Gate Precondition Evaluation & Regression Tests ---

def test_semantic_gate_selection():
    # Case with spatial note and map evidence summary -> spatial_inconsistency
    ctx_spatial = {
        "notes": [{"ref": "notes.N1", "text": "Officer placed knife near the entrance door."}],
        "map": {"evidence_positions_summary": ["E1 is near door"]},
    }
    selected = evaluate_semantic_gate(ctx_spatial)
    assert "spatial_inconsistency" in selected
    assert "timeline_contradiction" not in selected
    assert "contextual_contradiction" not in selected

    # Case with >= 2 timeline entries -> timeline_contradiction and contextual_contradiction
    ctx_timeline = {
        "timeline": [
            {"ref": "timeline.T1", "time": "21:00", "description": "Neighbor reports scream"},
            {"ref": "timeline.T2", "time": "21:30", "description": "Police arrival on scene"},
        ]
    }
    selected = evaluate_semantic_gate(ctx_timeline)
    assert "timeline_contradiction" in selected
    assert "contextual_contradiction" in selected
    assert "spatial_inconsistency" not in selected

    # Clean case with no cross-source preconditions -> gate skips entirely
    clean_ctx = {
        "notes": [],
        "timeline": [{"ref": "timeline.T1", "time": "21:00", "description": "Single event"}],
        "map": {"evidence_positions_summary": []},
        "photos": [],
        "evidence": [],
    }
    selected = evaluate_semantic_gate(clean_ctx)
    assert selected == []


def test_contextual_eligible_without_dismissed_detections():
    """Prove contextual analysis runs without any dismissed detections when comparable claims exist."""
    # Case A: Two notes making claims about an object/actor (no photos or detections at all)
    ctx_two_notes = {
        "notes": [
            {"ref": "notes.N1", "text": "Victim states the red backpack was inside the closet."},
            {"ref": "notes.N2", "text": "Officer observed red backpack on the living room floor."},
        ]
    }
    selected_a = evaluate_semantic_gate(ctx_two_notes)
    assert "contextual_contradiction" in selected_a

    # Case B: One note and one confirmed detection (zero dismissed detections)
    ctx_note_and_confirmed = {
        "notes": [{"ref": "notes.N1", "text": "Witness says suspect held a silver revolver."}],
        "photos": [
            {
                "ref": "photos.P1",
                "detections": [
                    {"ref": "photos.P1.d1", "class": "firearm", "disposition": "confirmed", "reason": None}
                ],
            }
        ],
    }
    selected_b = evaluate_semantic_gate(ctx_note_and_confirmed)
    assert "contextual_contradiction" in selected_b

    # Case C: One note and one confirmed evidence item
    ctx_note_and_evidence = {
        "notes": [{"ref": "notes.N1", "text": "Victim identified watch as gold Rolex."}],
        "evidence": [{"ref": "evidence.E1", "label": "stainless steel digital watch"}],
    }
    selected_c = evaluate_semantic_gate(ctx_note_and_evidence)
    assert "contextual_contradiction" in selected_c


def test_contextual_alternative_source_combinations():
    """Prove contextual analysis is eligible with alternative source combinations including detection + evidence."""
    # Case with 1 photo detection and 1 confirmed evidence item (0 notes and 0 timeline entries)
    ctx_det_and_evidence = {
        "photos": [
            {
                "ref": "photos.P1",
                "detections": [
                    {"ref": "photos.P1.d1", "class": "cell_phone", "disposition": "confirmed"}
                ],
            }
        ],
        "evidence": [{"ref": "evidence.E1", "label": "Device D1 pink smartphone"}],
    }
    selected = evaluate_semantic_gate(ctx_det_and_evidence)
    assert "contextual_contradiction" in selected

    # Case with 1 timeline event and 1 confirmed evidence item
    ctx_timeline_and_evidence = {
        "timeline": [{"ref": "timeline.T1", "time": "21:00", "description": "Suspect dropped crowbar"}],
        "evidence": [{"ref": "evidence.E1", "label": "iron prybar"}],
    }
    selected_te = evaluate_semantic_gate(ctx_timeline_and_evidence)
    assert "contextual_contradiction" in selected_te


def test_contextual_skipped_when_no_comparable_claims():
    """Prove contextual analysis is skipped when fewer than 2 relevant factual records are available."""
    # Only 1 isolated note, no timeline, no detections, no evidence
    ctx_single_note = {
        "notes": [{"ref": "notes.N1", "text": "Single note with no other records."}],
        "timeline": [],
        "photos": [],
        "evidence": [],
    }
    selected = evaluate_semantic_gate(ctx_single_note)
    assert "contextual_contradiction" not in selected

    # 1 evidence item only, no notes, no timeline, no detections
    ctx_single_evidence = {
        "evidence": [{"ref": "evidence.E1", "label": "lone knife"}],
    }
    selected_ev = evaluate_semantic_gate(ctx_single_evidence)
    assert "contextual_contradiction" not in selected_ev

    # Empty records without actual descriptive content (e.g. empty strings / empty dicts)
    ctx_empty_records = {
        "notes": [{"ref": "notes.N1", "text": "   "}],
        "timeline": [{"ref": "timeline.T1", "description": ""}],
        "photos": [{"ref": "photos.P1", "detections": [{"class": ""}]}],
        "evidence": [{"ref": "evidence.E1", "label": "  "}],
    }
    selected_empty = evaluate_semantic_gate(ctx_empty_records)
    assert "contextual_contradiction" not in selected_empty


def test_spatial_not_selected_for_notes_without_spatial_claims():
    """Prove spatial analysis is NOT selected merely because two notes exist without spatial claims."""
    ctx_non_spatial_notes = {
        "notes": [
            {"ref": "notes.N1", "text": "Neighbor appeared visibly distressed and nervous."},
            {"ref": "notes.N2", "text": "Victim reported hearing arguments yesterday."},
        ],
        "map": {"evidence_positions_summary": []},
    }
    selected = evaluate_semantic_gate(ctx_non_spatial_notes)
    assert "spatial_inconsistency" not in selected


def test_spatial_precision_positive_and_negative_expressions():
    """Prove spatial gate accepts genuine spatial expressions and rejects non-spatial sentences using matching words."""
    # Positive examples: meaningful spatial placement expressions
    positives = [
        "The suspect stood near the main door.",
        "Device D1 was left on the kitchen counter.",
        "The safe was positioned opposite the window.",
        "The envelope was hidden under the table.",
        "Blood traces were found inside the room.",
    ]
    for expr in positives:
        ctx_pos = {
            "notes": [{"ref": "notes.N1", "text": expr}],
            "map": {"evidence_positions_summary": ["E1 is near window."]},
        }
        assert "spatial_inconsistency" in evaluate_semantic_gate(ctx_pos), f"Failed to detect positive spatial expression: {expr}"

    # Negative examples: sentences that mention objects/grammatical phrases without expressing spatial placement
    negatives = [
        ("The door was damaged during entry.", "The window was broken from outside."),
        ("She was on the phone with dispatch.", "The officer completed the interview."),
        ("The floor plan was discussed by detectives.", "The table discussion ended late."),
        ("Near the victim reported that the window was broken.", "Witness confirmed hearing glass shatter."),
        ("Beside the witness explained that the door was damaged.", "Investigator logged the statement."),
        ("The officer said that the table discussion ended.", "Patrol unit resumed neighborhood canvass."),
    ]
    for note1, note2 in negatives:
        ctx_neg = {
            "notes": [
                {"ref": "notes.N1", "text": note1},
                {"ref": "notes.N2", "text": note2},
            ],
            "map": {"evidence_positions_summary": []},
        }
        assert "spatial_inconsistency" not in evaluate_semantic_gate(ctx_neg), f"Incorrectly triggered spatial analysis on negative expressions: {note1} | {note2}"


def test_spatial_eligible_for_valid_alternative_combinations():
    """Prove spatial analysis remains eligible for valid alternative spatial source combinations."""
    # Combination A: Note with spatial claim + map evidence position summary
    ctx_note_and_map = {
        "notes": [{"ref": "notes.N1", "text": "Knife observed near the living room door."}],
        "map": {"evidence_positions_summary": ["Evidence E1 is near the window."]},
    }
    selected_a = evaluate_semantic_gate(ctx_note_and_map)
    assert "spatial_inconsistency" in selected_a

    # Combination B: Multiple notes containing spatial claims (even with no map summary)
    ctx_two_spatial_notes = {
        "notes": [
            {"ref": "notes.N1", "text": "Knife was placed on the study desk."},
            {"ref": "notes.N2", "text": "Knife was recovered from under the sofa."},
        ],
        "map": {"evidence_positions_summary": []},
    }
    selected_b = evaluate_semantic_gate(ctx_two_spatial_notes)
    assert "spatial_inconsistency" in selected_b


def test_timeline_ignores_entries_without_usable_times():
    """Prove timeline analysis ignores timeline entries without usable times."""
    # 2 timeline entries, but neither has a usable time matching the project format
    ctx_unusable_timeline = {
        "timeline": [
            {"ref": "timeline.T1", "time": None, "description": "Neighbor called police"},
            {"ref": "timeline.T2", "time": "approx evening", "description": "Patrol dispatched"},
        ],
        "notes": [],
    }
    selected = evaluate_semantic_gate(ctx_unusable_timeline)
    assert "timeline_contradiction" not in selected

    # 1 timeline entry with valid time + 1 entry with null time -> only 1 usable time -> skipped
    ctx_one_valid_time = {
        "timeline": [
            {"ref": "timeline.T1", "time": "21:45", "description": "Valid time"},
            {"ref": "timeline.T2", "time": None, "description": "Unusable time"},
        ],
        "notes": [],
    }
    selected_one = evaluate_semantic_gate(ctx_one_valid_time)
    assert "timeline_contradiction" not in selected_one


def test_timeline_eligible_with_multiple_notes_no_timeline():
    """Prove timeline analysis remains eligible with multiple time-bearing notes and no timeline entries."""
    ctx_notes_with_times = {
        "timeline": [],
        "notes": [
            {"ref": "notes.N1", "text": "Witness logged the commotion at 21:40."},
            {"ref": "notes.N2", "text": "First officer documented arrival at 22:15."},
        ],
    }
    selected = evaluate_semantic_gate(ctx_notes_with_times)
    assert "timeline_contradiction" in selected


def test_dismissal_guard_operates_in_validator_during_pipeline(sample_c0_context, tmp_path):
    """Prove dismissal guard continues to enforce validation drops inside the validator during pipeline runs."""
    # Suggestion cites dismissed detection photos.P1.d2 without any note/timeline ref
    dismissed_ref_payload = {
        "suggestions": [
            {
                "type": "contextual_contradiction",
                "severity": "medium",
                "summary": "Water bottle dismissal contradiction.",
                "evidence_refs": ["photos.P1.d2"],  # Cited alone without note/timeline
                "reasoning": "Bottle was dismissed as homeowner water bottle.",
                "suggested_action": "Verify bottle ownership.",
            }
        ]
    }

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(dismissed_ref_payload)}}]})

    client = LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )

    result = run_pipeline(
        case_context=sample_c0_context,
        client=client,
        tier_b_types=["contextual_contradiction"],
        run_dir=tmp_path,
    )

    # Suggestion must be dropped by the validator's dismissal guard (Check 4)
    assert len(result.tier_b_suggestions) == 0
    assert len(result.rejected_suggestions) == 1
    assert result.rejected_suggestions[0]["rejection_reason"] == "dismissal_guard"
    assert result.stats["drop_reasons"]["dismissal_guard"] == 1


def test_semantic_gate_skips_when_no_preconditions(tmp_path):
    clean_ctx = {
        "case": {"id": "CLEAN-01"},
        "notes": [],
        "timeline": [{"ref": "timeline.T1", "time": "21:00", "description": "D1"}],
        "map": {"evidence_positions_summary": []},
        "photos": [],
    }
    result = run_pipeline(case_context=clean_ctx, run_dir=tmp_path)
    assert result.status == "success"
    assert result["gate_status"] == "gate_skipped"
    assert len(result.tier_b_suggestions) == 0
    assert len(result.invocation_outcomes) == 0


# --- 3. All-Types and Selective Execution ---

def test_all_types_execution(sample_c2_context, tmp_path):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"suggestions": []})}}]})

    client = LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )
    result = run_pipeline(
        case_context=sample_c2_context,
        client=client,
        all_types=True,
        run_dir=tmp_path,
    )
    assert result["gate_status"] == "all_types_forced"
    assert len(result.invocation_outcomes) == 3
    categories = [o["category"] for o in result.invocation_outcomes]
    assert categories == ["contextual_contradiction", "spatial_inconsistency", "timeline_contradiction"]


def test_selective_execution(sample_c2_context, tmp_path):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"suggestions": []})}}]})

    client = LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )
    result = run_pipeline(
        case_context=sample_c2_context,
        client=client,
        tier_b_types=["spatial_inconsistency"],
        run_dir=tmp_path,
    )
    assert result["gate_status"] == "selective_override"
    assert len(result.invocation_outcomes) == 1
    assert result.invocation_outcomes[0]["category"] == "spatial_inconsistency"


def test_invalid_tier_b_type_raises(sample_c2_context):
    with pytest.raises(ValueError, match="Invalid Tier B category"):
        run_pipeline(
            case_context=sample_c2_context,
            tier_b_types=["invented_category"],
        )


# --- 4. Mocked Full Pipeline Execution ---

def test_mocked_full_pipeline(sample_c2_context, tmp_path):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(VALID_SUGGESTION_PAYLOAD)}}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
            },
        )

    client = LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )
    result = run_pipeline(
        case_context=sample_c2_context,
        client=client,
        tier_b_types=["spatial_inconsistency"],
        run_dir=tmp_path,
    )
    assert result.status == "success"
    assert len(result.tier_b_suggestions) == 1
    assert result.tier_b_suggestions[0]["type"] == "spatial_inconsistency"
    assert result.stats["validated"] == 1
    assert result.stats["total_tokens"] == 140


# --- 5. Empty Responses & Schema Failure Distinguishability ---

def test_successful_empty_response(sample_c2_context, tmp_path):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"suggestions": []})}}]},
        )

    client = LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )
    result = run_pipeline(
        case_context=sample_c2_context,
        client=client,
        tier_b_types=["spatial_inconsistency"],
        run_dir=tmp_path,
    )
    assert result.status == "success"
    assert result.tier_b_suggestions == []
    assert result.rejected_suggestions == []
    assert result.invocation_outcomes[0]["status"] == "success"


def test_schema_failure_handling(sample_c2_context, tmp_path):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "Malformed Non-JSON"}}]})

    client = LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )
    result = run_pipeline(
        case_context=sample_c2_context,
        client=client,
        tier_b_types=["spatial_inconsistency"],
        run_dir=tmp_path,
    )
    assert result.status == "failure"  # Sole invocation failed schema retries
    assert result.tier_b_suggestions == []
    assert result.invocation_outcomes[0]["status"] == "schema_fail"
    assert result.invocation_outcomes[0]["error"] == "schema_fail"
    assert result.stats["drop_reasons"]["schema_fail"] == 1


# --- 6. Provider Exceptions and Partial Success ---

def test_provider_transport_error_handling(sample_c2_context, tmp_path):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway")

    client = LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )
    result = run_pipeline(
        case_context=sample_c2_context,
        client=client,
        tier_b_types=["spatial_inconsistency"],
        run_dir=tmp_path,
    )
    assert result.status == "failure"
    assert result.invocation_outcomes[0]["status"] == "error"
    assert result.invocation_outcomes[0]["error_type"] == "LLMTransportError"


def test_partial_success_preserves_valid_results(sample_c2_context, tmp_path):
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First category succeeds
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(VALID_SUGGESTION_PAYLOAD)}}]},
            )
        # Second category suffers transport drop
        return httpx.Response(500, text="Internal Server Error")

    client = LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )
    result = run_pipeline(
        case_context=sample_c2_context,
        client=client,
        tier_b_types=["spatial_inconsistency", "timeline_contradiction"],
        run_dir=tmp_path,
    )
    assert result.status == "partial_success"
    # The valid suggestion from spatial_inconsistency is preserved!
    assert len(result.tier_b_suggestions) == 1
    assert result.tier_b_suggestions[0]["type"] == "spatial_inconsistency"
    assert result.invocation_outcomes[0]["status"] == "success"
    assert result.invocation_outcomes[1]["status"] == "error"


# --- 7. Audit Provenance and Client Ownership ---

def test_audit_provenance_and_cleanliness(sample_c2_context, tmp_path):
    # Pollute context with prohibited image fields to verify sanitization
    polluted = json.loads(json.dumps(sample_c2_context))
    polluted["photos"][0]["image_bytes"] = "PROHIBITED_BYTES"
    polluted["photos"][0]["file_path"] = "/tmp/photo.jpg"

    result = run_pipeline(
        case_context=polluted,
        tier_a_only=True,
        run_dir=tmp_path,
        write_audit=True,
    )
    assert result.audit_path is not None
    audit_file = Path(result.audit_path)
    assert audit_file.exists()

    audit_text = audit_file.read_text(encoding="utf-8")
    assert "PROHIBITED_BYTES" not in audit_text
    assert "/tmp/photo.jpg" not in audit_text
    assert result.context_hash == compute_context_hash(sample_c2_context)


def test_client_ownership_not_closed_when_caller_supplied(sample_c2_context, tmp_path):
    client = LLMClient(
        config=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}))),
    )
    run_pipeline(
        case_context=sample_c2_context,
        client=client,
        tier_a_only=True,
        run_dir=tmp_path,
    )
    # Pipeline must not have closed caller-supplied client
    assert not client._http_client.is_closed
    client.close()


# --- 8. CLI Invocations and Exit Codes ---

def test_cli_tier_a_only():
    exit_code = main(["cases/C0.json", "--tier-a-only", "--no-audit"])
    assert exit_code == 0


def test_cli_file_not_found():
    exit_code = main(["cases/NON_EXISTENT_CASE.json"])
    assert exit_code == 1


def test_cli_configuration_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Tier B without API key -> exit code 2
    exit_code = main(["cases/C0.json", "--provider", "openai", "--model", "gpt-4o"])
    assert exit_code == 2


def test_cli_output_file(tmp_path):
    out_file = tmp_path / "test_cli_output.json"
    exit_code = main(["cases/C0.json", "--tier-a-only", "--output", str(out_file), "--no-audit"])
    assert exit_code == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert "tier_a_flags" in data
    assert len(data["tier_a_flags"]) > 0
