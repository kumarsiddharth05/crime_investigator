"""Unit and integration tests for the post-LLM validator module."""

import json
from pathlib import Path
import pytest

from src.analysis.validator import validate

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"


def _load_c4_context() -> dict:
    """Load cases/C4.json as a realistic case_context fixture."""
    with open(CASES_DIR / "C4.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _minimal_context() -> dict:
    """Minimal case_context for isolated single-rule tests."""
    return {
        "case": {
            "id": "C-MIN",
            "type": "assault",
            "title": "Minimal test scene",
            "incident_window": {"start": "2026-01-15T21:00", "end": "2026-01-15T22:00"},
            "rooms_covered": ["kitchen"],
        },
        "evidence": [
            {
                "ref": "evidence.E1",
                "label": "kitchen knife",
                "photo_ref": "photos.P1",
                "det_ref": "photos.P1.d1",
                "map_ref": "map.E1",
            }
        ],
        "photos": [
            {
                "ref": "photos.P1",
                "room": "kitchen",
                "view": "wide view of kitchen counter",
                "detections": [
                    {
                        "ref": "photos.P1.d1",
                        "class": "knife",
                        "conf": 0.95,
                        "disposition": "confirmed",
                        "reason": None,
                    },
                    {
                        "ref": "photos.P1.d2",
                        "class": "cell_phone",
                        "conf": 0.82,
                        "disposition": "dismissed",
                        "reason": "accounted for personal phone",
                    },
                ],
            }
        ],
        "map": {
            "room": "kitchen",
            "reference_points": [],
            "evidence_positions_summary": [
                "Evidence E1 (kitchen knife) is near the window."
            ],
        },
        "timeline": [
            {
                "ref": "timeline.T1",
                "time": "2026-01-15T21:40",
                "description": "Witness reports incident at 21:40",
                "source": "witness",
            }
        ],
        "notes": [
            {
                "ref": "notes.N1",
                "type": "statement",
                "text": "Witness states the kitchen knife was found near the door.",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Test 1: Schema failure drops malformed inputs
# ---------------------------------------------------------------------------
def test_schema_fail_drops_all() -> None:
    ctx = _minimal_context()

    # Response is not a dict
    res1 = validate("not a dict", ctx, [], "spatial_inconsistency")  # type: ignore[arg-type]
    assert res1["validated"] == []
    assert res1["stats"]["received"] == 0
    assert res1["stats"]["drop_reasons"]["schema_fail"] == 1

    # Suggestions key is not a list
    res2 = validate({"suggestions": "not a list"}, ctx, [], "spatial_inconsistency")
    assert res2["validated"] == []
    assert res2["stats"]["received"] == 0
    assert res2["stats"]["drop_reasons"]["schema_fail"] == 1

    # Suggestion missing required keys
    res3 = validate(
        {"suggestions": [{"type": "spatial_inconsistency"}]},
        ctx,
        [],
        "spatial_inconsistency",
    )
    assert res3["validated"] == []
    assert len(res3["rejected"]) == 1
    assert res3["rejected"][0]["rejection_reason"] == "schema_fail"
    assert res3["stats"]["drop_reasons"]["schema_fail"] == 1


# ---------------------------------------------------------------------------
# Test 2: Per-invocation type mismatch is dropped
# ---------------------------------------------------------------------------
def test_type_mismatch_dropped() -> None:
    ctx = _minimal_context()
    response = {
        "suggestions": [
            {
                "type": "timeline_contradiction",
                "severity": "high",
                "summary": "Conflicting times observed.",
                "evidence_refs": ["timeline.T1"],
                "reasoning": "Witness and patrol logs conflict.",
                "suggested_action": "Reconcile timeline.",
            }
        ]
    }
    res = validate(response, ctx, [], "spatial_inconsistency")
    assert res["validated"] == []
    assert len(res["rejected"]) == 1
    assert res["rejected"][0]["rejection_reason"] == "type_mismatch"
    assert res["stats"]["drop_reasons"]["type_mismatch"] == 1


# ---------------------------------------------------------------------------
# Test 3: Empty suggestions array never trips type check
# ---------------------------------------------------------------------------
def test_empty_suggestions_never_trip_type_check() -> None:
    ctx = _minimal_context()
    for cat in ["spatial_inconsistency", "timeline_contradiction", "contextual_contradiction"]:
        res = validate({"suggestions": []}, ctx, [], cat)
        assert res["validated"] == []
        assert res["rejected"] == []
        assert res["stats"]["received"] == 0
        assert sum(res["stats"]["drop_reasons"].values()) == 0


# ---------------------------------------------------------------------------
# Test 4: Invalid invocation type raises controlled ValueError
# ---------------------------------------------------------------------------
def test_invalid_invocation_type_fails_safely() -> None:
    ctx = _minimal_context()
    with pytest.raises(ValueError, match="Invalid assigned_analysis_type"):
        validate({"suggestions": []}, ctx, [], "unknown_arbitrary_category")


# ---------------------------------------------------------------------------
# Test 5: Unresolved references are dropped
# ---------------------------------------------------------------------------
def test_unresolved_ref_dropped() -> None:
    ctx = _minimal_context()
    response = {
        "suggestions": [
            {
                "type": "spatial_inconsistency",
                "severity": "high",
                "summary": "Note places knife near door; map places near window.",
                "evidence_refs": ["notes.N99", "evidence.E1"],
                "reasoning": "Conflicting positions across note and map.",
                "suggested_action": "Verify position.",
            }
        ]
    }
    res = validate(response, ctx, [], "spatial_inconsistency")
    assert res["validated"] == []
    assert len(res["rejected"]) == 1
    assert res["rejected"][0]["rejection_reason"] == "unresolved_ref"
    assert res["stats"]["drop_reasons"]["unresolved_ref"] == 1


# ---------------------------------------------------------------------------
# Test 6: Invented proper name and time are dropped
# ---------------------------------------------------------------------------
def test_invented_time_and_entity_dropped() -> None:
    ctx = _minimal_context()
    response = {
        "suggestions": [
            {
                "type": "spatial_inconsistency",
                "severity": "high",
                "summary": "At 21:37 Glock pistol was discovered near door.",
                "evidence_refs": ["notes.N1", "evidence.E1"],
                "reasoning": "Location conflicts with map.",
                "suggested_action": "Check location.",
            }
        ]
    }
    res = validate(response, ctx, [], "spatial_inconsistency")
    assert res["validated"] == []
    assert len(res["rejected"]) == 1
    assert res["rejected"][0]["rejection_reason"] == "hallucination_suspected"
    assert res["stats"]["drop_reasons"]["hallucination_suspected"] == 1


# ---------------------------------------------------------------------------
# Test 7: Single unverified entity passes with warning
# ---------------------------------------------------------------------------
def test_single_unverified_entity_warns() -> None:
    ctx = _minimal_context()
    response = {
        "suggestions": [
            {
                "type": "spatial_inconsistency",
                "severity": "high",
                "summary": "Witness noted Glock near the kitchen door.",
                "evidence_refs": ["notes.N1", "evidence.E1"],
                "reasoning": "Position conflicts with the map summary.",
                "suggested_action": "Verify the item location.",
            }
        ]
    }
    res = validate(response, ctx, [], "spatial_inconsistency")
    assert len(res["validated"]) == 1
    assert res["validated"][0]["validator_status"] == "warning"
    assert res["validated"][0]["validation_warning"] == "unverified entity: 'glock'"
    assert res["stats"]["drop_reasons"]["hallucination_suspected"] == 0


# ---------------------------------------------------------------------------
# Test 8: Dismissal guard blocks re-flagging a dismissed detection
# ---------------------------------------------------------------------------
def test_dismissal_guard_blocks_refire() -> None:
    ctx = _minimal_context()
    # Attempt 1: Contextual contradiction citing ONLY a dismissed detection
    response1 = {
        "suggestions": [
            {
                "type": "contextual_contradiction",
                "severity": "high",
                "summary": "Dismissed phone requires review.",
                "evidence_refs": ["photos.P1.d2"],
                "reasoning": "Phone dismissal questioned.",
                "suggested_action": "Re-examine phone.",
            }
        ]
    }
    res1 = validate(response1, ctx, [], "contextual_contradiction")
    assert res1["validated"] == []
    assert res1["rejected"][0]["rejection_reason"] == "dismissal_guard"
    assert res1["stats"]["drop_reasons"]["dismissal_guard"] == 1

    # Attempt 2: Spatial inconsistency citing a dismissed detection
    response2 = {
        "suggestions": [
            {
                "type": "spatial_inconsistency",
                "severity": "high",
                "summary": "Dismissed phone location conflict.",
                "evidence_refs": ["photos.P1.d2", "notes.N1"],
                "reasoning": "Phone location conflicts.",
                "suggested_action": "Verify phone location.",
            }
        ]
    }
    res2 = validate(response2, ctx, [], "spatial_inconsistency")
    assert res2["validated"] == []
    assert res2["rejected"][0]["rejection_reason"] == "dismissal_guard"


# ---------------------------------------------------------------------------
# Test 9: Dismissal guard allows genuine contextual contradiction
# ---------------------------------------------------------------------------
def test_dismissal_guard_allows_contradiction() -> None:
    ctx = _load_c4_context()
    # C4's notes.N4 contradicts dismissal rationale of photos.P1.d3 (Device D1)
    response = {
        "suggestions": [
            {
                "type": "contextual_contradiction",
                "severity": "high",
                "summary": "Note N4 states Device D1 is missing; dismissal states it was accounted for.",
                "evidence_refs": ["notes.N4", "photos.P1.d3"],
                "reasoning": "Direct conflict regarding ownership and status of Device D1.",
                "suggested_action": "Reconcile Device D1 status with victim report.",
            }
        ]
    }
    res = validate(response, ctx, [], "contextual_contradiction")
    assert len(res["validated"]) == 1
    assert res["validated"][0]["rejection_reason" if "rejection_reason" in res["validated"][0] else "engine"] == "tier_b"
    assert res["rejected"] == []
    assert res["stats"]["drop_reasons"]["dismissal_guard"] == 0


# ---------------------------------------------------------------------------
# Test 10: Conservative Tier A deduplication preserves pairwise contradictions
# ---------------------------------------------------------------------------
def test_conservative_tier_a_dedup() -> None:
    ctx = _minimal_context()
    # Tier A flag is on single ref: notes.N1
    tier_a_flags = [
        {
            "engine": "tier_a",
            "rule": "A4",
            "severity": "medium",
            "summary": "Note notes.N1 has unrecorded time.",
            "evidence_refs": ["notes.N1"],
            "reasoning": "Timestamp missing in timeline.",
        }
    ]

    # Tier B pairwise suggestion shares notes.N1 but asserts pairwise contradiction with evidence.E1
    response = {
        "suggestions": [
            {
                "type": "spatial_inconsistency",
                "severity": "high",
                "summary": "Note N1 places knife near door; map places near window.",
                "evidence_refs": ["notes.N1", "evidence.E1"],
                "reasoning": "Mutually exclusive locations across note and map.",
                "suggested_action": "Verify position.",
            }
        ]
    }
    res = validate(response, ctx, tier_a_flags, "spatial_inconsistency")
    # Must NOT be dropped: Tier A single-ref flag does not subsume pairwise Tier B finding
    assert len(res["validated"]) == 1
    assert res["rejected"] == []


# ---------------------------------------------------------------------------
# Test 11: Severity sanity downgrades single-ref high severity
# ---------------------------------------------------------------------------
def test_severity_downgrade() -> None:
    ctx = _minimal_context()
    response = {
        "suggestions": [
            {
                "type": "spatial_inconsistency",
                "severity": "high",
                "summary": "Spatial discrepancy noted.",
                "evidence_refs": ["evidence.E1"],
                "reasoning": "Location discrepancy.",
                "suggested_action": "Verify location.",
            },
            {
                "type": "spatial_inconsistency",
                "severity": "high",
                "summary": "Duplicate ref discrepancy.",
                "evidence_refs": ["evidence.E1", "evidence.E1"],
                "reasoning": "Duplicate references should not inflate count.",
                "suggested_action": "Verify location.",
            },
            {
                "type": "spatial_inconsistency",
                "severity": "high",
                "summary": "Spatial conflict noted.",
                "evidence_refs": ["notes.N1", "evidence.E1"],
                "reasoning": "Location conflict across two distinct sources.",
                "suggested_action": "Verify location.",
            },
        ]
    }
    res = validate(response, ctx, [], "spatial_inconsistency")
    assert len(res["validated"]) == 3
    # Single-ref suggestion downgraded to medium
    assert res["validated"][0]["severity"] == "medium"
    # Duplicate ref suggestion downgraded to medium (only 1 distinct ref)
    assert res["validated"][1]["severity"] == "medium"
    # Distinct multi-ref suggestion keeps high
    assert res["validated"][2]["severity"] == "high"


# ---------------------------------------------------------------------------
# Test 12: Legitimate case terminology passes cleanly
# ---------------------------------------------------------------------------
def test_legitimate_case_terminology() -> None:
    ctx = _minimal_context()
    response = {
        "suggestions": [
            {
                "type": "spatial_inconsistency",
                "severity": "medium",
                "summary": "Witness states the kitchen knife was found near the door.",
                "evidence_refs": ["notes.N1", "evidence.E1"],
                "reasoning": "Map summary places kitchen knife near window.",
                "suggested_action": "Verify kitchen knife location.",
            }
        ]
    }
    res = validate(response, ctx, [], "spatial_inconsistency")
    assert len(res["validated"]) == 1
    assert res["validated"][0]["validator_status"] == "clean"
    assert res["validated"][0]["validation_warning"] is None
    assert res["rejected"] == []


# ---------------------------------------------------------------------------
# Test 13: Statistics accounting across mixed valid and rejected suggestions
# ---------------------------------------------------------------------------
def test_stats_accounting() -> None:
    ctx = _load_c4_context()
    tier_a_flags = [{"engine": "tier_a", "rule": "A5", "evidence_refs": ["evidence.E1", "notes.N4"]}]

    suggestions = [
        # 1. Valid clean
        {
            "type": "contextual_contradiction",
            "severity": "high",
            "summary": "Device D1 status conflict.",
            "evidence_refs": ["notes.N4", "photos.P1.d3"],
            "reasoning": "Missing phone vs accounted phone conflict.",
            "suggested_action": "Verify status.",
        },
        # 2. Valid warning (single unverified proper noun Glock)
        {
            "type": "contextual_contradiction",
            "severity": "high",
            "summary": "Device D1 and Glock inquiry.",
            "evidence_refs": ["notes.N4", "photos.P1.d3"],
            "reasoning": "Missing phone vs accounted phone conflict.",
            "suggested_action": "Verify status.",
        },
        # 3. Drop: schema_fail (missing suggested_action)
        {
            "type": "contextual_contradiction",
            "severity": "high",
            "summary": "Missing action field.",
            "evidence_refs": ["notes.N4"],
            "reasoning": "Incomplete schema.",
        },
        # 4. Drop: type_mismatch
        {
            "type": "spatial_inconsistency",
            "severity": "medium",
            "summary": "Spatial issue submitted to contextual invocation.",
            "evidence_refs": ["notes.N4"],
            "reasoning": "Type mismatch.",
            "suggested_action": "Check type.",
        },
        # 5. Drop: unresolved_ref
        {
            "type": "contextual_contradiction",
            "severity": "medium",
            "summary": "Unresolved reference citation.",
            "evidence_refs": ["notes.N999"],
            "reasoning": "Unknown reference.",
            "suggested_action": "Fix ref.",
        },
        # 6. Drop: dismissal_guard (dismissed detection photos.P1.d3 without note/timeline ref)
        {
            "type": "contextual_contradiction",
            "severity": "high",
            "summary": "Re-flagging dismissed detection alone.",
            "evidence_refs": ["photos.P1.d3"],
            "reasoning": "No contradicting source cited.",
            "suggested_action": "Check source.",
        },
        # 7. Drop: hallucination_suspected (Glock and 23:45 unverified)
        {
            "type": "contextual_contradiction",
            "severity": "high",
            "summary": "Glock fired at 23:45 in bedroom.",
            "evidence_refs": ["notes.N4", "photos.P1.d3"],
            "reasoning": "Fabricated time and proper noun.",
            "suggested_action": "Verify time.",
        },
    ]

    res = validate({"suggestions": suggestions}, ctx, tier_a_flags, "contextual_contradiction")
    stats = res["stats"]

    assert stats["received"] == 7
    assert stats["validated"] == 2
    assert stats["rejected"] == 5
    assert stats["received"] == stats["validated"] + stats["rejected"]
    assert stats["rejected"] == sum(stats["drop_reasons"].values())
    assert stats["drop_reasons"]["schema_fail"] == 1
    assert stats["drop_reasons"]["type_mismatch"] == 1
    assert stats["drop_reasons"]["unresolved_ref"] == 1
    assert stats["drop_reasons"]["dismissal_guard"] == 1
    assert stats["drop_reasons"]["hallucination_suspected"] == 1
    assert stats["drop_reasons"]["deduped_by_tier_a"] == 0
