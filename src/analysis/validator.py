"""Post-LLM suggestion validation layer.

The validator establishes structural validity and grounding
of LLM suggestions against the provided case_context.

It does NOT establish that the LLM has interpreted the
relationship between cited fields correctly. A suggestion
that passes all checks is one whose cited refs exist and
whose named entities appear in the input — not one whose
claim is semantically correct. Semantic verification remains
the investigator's responsibility.

Limitations of the entity hallucination detector:
- It detects fabricated proper-name-like tokens and unsupported
  numeric literals that do not appear in the case_context or the
  curated generic vocabulary.
- It cannot detect arbitrary fabricated lowercase common nouns.
- It cannot detect whether a genuine entity is used in an
  unsupported claim (e.g., 'notes.N3 says the door was open'
  when N3 says nothing about a door).
- It cannot evaluate relationships between cited fields.

Limitations of the dismissal guard:
- The dismissal guard mechanically ensures that a dismissed detection
  cannot be re-flagged in isolation and requires a corroborating
  note/timeline citation under contextual_contradiction.
- The validator cannot independently prove that the cited source
  actually refutes or challenges the dismissal rationale; semantic
  support remains subject to investigator review.

Limitations of Tier A deduplication:
- Current Tier A rules (A1–A8) produce single-reference structural
  and process flags. Tier B findings are pairwise semantic
  contradictions. Matching refs alone do not establish semantic
  equivalence. Consequently, suppression remains inactive under
  the current rules until a genuine semantic equivalence is defined.
"""

from __future__ import annotations

import re
from typing import Any

from src.analysis.refs import resolve_ref

PERMITTED_TIER_B_TYPES: frozenset[str] = frozenset({
    "spatial_inconsistency",
    "timeline_contradiction",
    "contextual_contradiction",
})

VALID_SEVERITIES: frozenset[str] = frozenset({"low", "medium", "high"})

REQUIRED_SUGGESTION_KEYS: frozenset[str] = frozenset({
    "type",
    "severity",
    "summary",
    "evidence_refs",
    "reasoning",
    "suggested_action",
})

GENERIC_VOCABULARY: frozenset[str] = frozenset({
    # --- Function words & connectives ---
    "a", "an", "the", "is", "was", "are", "were", "be", "been", "being",
    "do", "does", "did", "has", "have", "had", "of", "to", "in", "on",
    "at", "for", "with", "by", "from", "about", "that", "this", "these",
    "those", "and", "or", "but", "if", "then", "so", "as", "not", "no",
    "yes", "into", "onto", "across", "between", "among", "under", "over",
    "through", "after", "before", "during", "while", "against", "within",
    "without", "per", "via", "than", "more", "less", "such", "only",
    "also", "too", "very",

    # --- Pronouns ---
    "it", "its", "he", "she", "they", "their", "theirs", "his", "her",
    "hers", "them", "which", "who", "whom", "whose", "what", "where",
    "when", "why", "how",

    # --- Schema fields & structural keys ---
    "type", "severity", "summary", "reasoning", "suggested", "action",
    "evidence", "refs", "ref", "detection", "detections", "photo", "photos",
    "map", "notes", "note", "timeline", "case", "class", "conf",
    "disposition", "reason", "label", "room", "view", "source", "text",
    "coordinates", "position", "positions", "incident", "window", "start",
    "end", "derived", "facts",

    # --- Analyst & investigation terminology ---
    "verify", "check", "confirm", "confirmed", "review", "reconcile",
    "accurate", "incorrect", "contradictory", "contradiction", "inconsistency",
    "discrepancy", "conflict", "same", "different", "both", "one", "two",
    "other", "cited", "update", "correct", "dismissed", "unreviewed",
    "observation", "statement", "remark", "report", "records", "recorded",
    "asserts", "asserted", "states", "stated", "claims", "claimed",
    "indicates", "indicated", "describes", "described", "location", "locations",
    "time", "times", "event", "events", "entity", "entities", "status",
    "details", "detail", "mutually", "exclusive", "identical", "distinct",
    "primary", "secondary", "ancillary", "minor", "central",
})

# Token extraction regexes for Check 5
NUMERIC_LITERAL_REGEX = re.compile(r"\b\d+(?:[.:-]\d+)+\b|\b\d+\b")
PROPER_NAME_REGEX = re.compile(r"\b[A-Z][a-zA-Z0-9_]*\b")
WORD_SPLIT_REGEX = re.compile(r"[a-zA-Z0-9_.:-]+")


def _build_case_allowlist(case_context: dict[str, Any]) -> set[str]:
    """Build grounded token allowlist from case_context and GENERIC_VOCABULARY."""
    allowlist: set[str] = set(GENERIC_VOCABULARY)

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            node_clean = node.strip().lower()
            if node_clean:
                allowlist.add(node_clean)
                tokens = WORD_SPLIT_REGEX.findall(node_clean)
                for t in tokens:
                    t_stripped = t.strip(".,;:!?\"'()[]{}").lower()
                    if t_stripped:
                        allowlist.add(t_stripped)
        elif isinstance(node, (int, float)):
            allowlist.add(str(node).lower())
        elif isinstance(node, dict):
            # If node has a ref, extract each dotted segment
            ref_val = node.get("ref")
            if isinstance(ref_val, str):
                allowlist.add(ref_val.lower())
                for seg in ref_val.split("."):
                    if seg:
                        allowlist.add(seg.lower())
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(case_context)
    return allowlist


def validate(
    llm_response: dict[str, Any],
    case_context: dict[str, Any],
    tier_a_flags: list[dict[str, Any]],
    assigned_analysis_type: str,
) -> dict[str, Any]:
    """Execute the seven validator checks in order.

    Raises:
        ValueError: If assigned_analysis_type is not one of the permitted
                    Tier B categories.
    """
    # Requirement 1: Validate assigned_analysis_type before processing response
    if assigned_analysis_type not in PERMITTED_TIER_B_TYPES:
        raise ValueError(
            f"Invalid assigned_analysis_type '{assigned_analysis_type}'. "
            f"Must be one of: {sorted(PERMITTED_TIER_B_TYPES)}"
        )

    drop_reasons = {
        "schema_fail": 0,
        "type_mismatch": 0,
        "unresolved_ref": 0,
        "dismissal_guard": 0,
        "hallucination_suspected": 0,
        "deduped_by_tier_a": 0,
    }

    # CHECK 1: Schema validation (Response-level)
    if (
        not isinstance(llm_response, dict)
        or "suggestions" not in llm_response
        or not isinstance(llm_response["suggestions"], list)
    ):
        drop_reasons["schema_fail"] += 1
        return {
            "validated": [],
            "rejected": [],
            "stats": {
                "received": 0,
                "validated": 0,
                "rejected": 0,
                "drop_reasons": drop_reasons,
            },
        }

    raw_suggestions: list[Any] = llm_response["suggestions"]
    received_count = len(raw_suggestions)

    # Empty suggestions list is immediately valid
    if received_count == 0:
        return {
            "validated": [],
            "rejected": [],
            "stats": {
                "received": 0,
                "validated": 0,
                "rejected": 0,
                "drop_reasons": drop_reasons,
            },
        }

    validated: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    # Pre-build grounded allowlist once per validate() call
    allowlist = _build_case_allowlist(case_context)

    # Process individual suggestions (maxItems: 10)
    for idx, raw_sug in enumerate(raw_suggestions):
        # Enforce maxItems: 10
        if idx >= 10:
            rejected.append({
                "suggestion": raw_sug if isinstance(raw_sug, dict) else {"raw": raw_sug},
                "rejection_reason": "schema_fail",
            })
            drop_reasons["schema_fail"] += 1
            continue

        # Check 1: Suggestion-level schema validation
        if not isinstance(raw_sug, dict):
            rejected.append({"suggestion": {"raw": raw_sug}, "rejection_reason": "schema_fail"})
            drop_reasons["schema_fail"] += 1
            continue

        missing_keys = REQUIRED_SUGGESTION_KEYS - set(raw_sug.keys())
        if missing_keys:
            rejected.append({**raw_sug, "rejection_reason": "schema_fail"})
            drop_reasons["schema_fail"] += 1
            continue

        sug_type = raw_sug.get("type")
        severity = raw_sug.get("severity")
        summary = raw_sug.get("summary")
        evidence_refs = raw_sug.get("evidence_refs")
        reasoning = raw_sug.get("reasoning")
        suggested_action = raw_sug.get("suggested_action")

        if (
            sug_type not in PERMITTED_TIER_B_TYPES
            or severity not in VALID_SEVERITIES
            or not isinstance(summary, str)
            or not isinstance(reasoning, str)
            or not isinstance(suggested_action, str)
            or not isinstance(evidence_refs, list)
            or len(evidence_refs) < 1
            or not all(isinstance(r, str) for r in evidence_refs)
        ):
            rejected.append({**raw_sug, "rejection_reason": "schema_fail"})
            drop_reasons["schema_fail"] += 1
            continue

        # Check 2: Per-invocation type check
        if sug_type != assigned_analysis_type:
            rejected.append({**raw_sug, "rejection_reason": "type_mismatch"})
            drop_reasons["type_mismatch"] += 1
            continue

        # Check 3: Ref resolution
        resolved_nodes: list[tuple[str, Any]] = []
        unresolved_found = False
        for ref_str in evidence_refs:
            node = resolve_ref(case_context, ref_str)
            if node is None:
                unresolved_found = True
                break
            resolved_nodes.append((ref_str, node))

        if unresolved_found:
            rejected.append({**raw_sug, "rejection_reason": "unresolved_ref"})
            drop_reasons["unresolved_ref"] += 1
            continue

        # Check 4: Dismissal guard
        dismissal_guard_violated = False
        dismissed_detection_cited = False
        for ref_str, node in resolved_nodes:
            if isinstance(node, dict):
                disp = node.get("disposition")
                reason = node.get("reason")
                if disp == "dismissed" and reason is not None and str(reason).strip():
                    dismissed_detection_cited = True
                    break

        if dismissed_detection_cited:
            if sug_type != "contextual_contradiction":
                dismissal_guard_violated = True
            else:
                # Contextual contradiction citing a dismissed detection requires
                # at least one other cited ref resolving to a note or timeline entry
                has_corroborating_source = False
                for ref_str, _ in resolved_nodes:
                    if ref_str.startswith("notes.") or ref_str.startswith("timeline."):
                        has_corroborating_source = True
                        break
                if not has_corroborating_source:
                    dismissal_guard_violated = True

        if dismissal_guard_violated:
            rejected.append({**raw_sug, "rejection_reason": "dismissal_guard"})
            drop_reasons["dismissal_guard"] += 1
            continue

        # Check 5: Entity hallucination detector
        combined_text = f"{summary} {reasoning} {suggested_action}"

        candidate_tokens: set[str] = set()
        # 1. Numeric literals
        for match in NUMERIC_LITERAL_REGEX.finditer(combined_text):
            candidate_tokens.add(match.group().lower())
        # 2. Capitalized proper-name-like tokens
        for match in PROPER_NAME_REGEX.finditer(combined_text):
            tok = match.group()
            tok_norm = tok.strip(".,;:!?\"'()[]{}").lower()
            if tok_norm:
                candidate_tokens.add(tok_norm)

        unverified_tokens = sorted([t for t in candidate_tokens if t not in allowlist])

        if len(unverified_tokens) >= 2:
            rejected.append({**raw_sug, "rejection_reason": "hallucination_suspected"})
            drop_reasons["hallucination_suspected"] += 1
            continue

        if len(unverified_tokens) == 1:
            validator_status = "warning"
            validation_warning = f"unverified entity: '{unverified_tokens[0]}'"
        else:
            validator_status = "clean"
            validation_warning = None

        # Check 6: Dedup vs Tier A
        # Current Tier A rules (A1–A8) produce single-reference structural and process flags,
        # whereas Tier B findings are pairwise semantic contradictions. Matching refs alone
        # do not establish semantic equivalence. Consequently, suppression remains inactive
        # under the current rule catalog until a genuine semantic equivalence is defined.
        # No current Tier A flag suppresses a Tier B suggestion.
        # (Check 6 is retained in the pipeline for architectural extensibility).

        # Check 7: Severity sanity
        final_severity = severity
        if severity == "high":
            # High severity requires at least two distinct evidence references
            distinct_refs = set(evidence_refs)
            if len(distinct_refs) < 2:
                final_severity = "medium"

        validated_sug = dict(raw_sug)
        validated_sug["severity"] = final_severity
        validated_sug["engine"] = "tier_b"
        validated_sug["validator_status"] = validator_status
        validated_sug["validation_warning"] = validation_warning
        validated.append(validated_sug)

    return {
        "validated": validated,
        "rejected": rejected,
        "stats": {
            "received": received_count,
            "validated": len(validated),
            "rejected": len(rejected),
            "drop_reasons": drop_reasons,
        },
    }
