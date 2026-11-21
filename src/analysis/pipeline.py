"""End-to-end analysis pipeline orchestrator.

Orchestrates:
1. Tier A deterministic rule execution (no LLM, no hallucination risk).
2. Semantic gate evaluation to select applicable Tier B categories.
3. Isolated per-category Tier B LLM invocations with controlled retries.
4. Downstream 7-check validation gate auditing all suggestions.
5. Result aggregation, structured audit persistence, and failure isolation.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any
import uuid

from src.analysis.tier_a import run_tier_a
from src.analysis.validator import validate
from src.llm import (
    LLMAuthenticationError,
    LLMClient,
    LLMConfigurationError,
    LLMConfig,
    LLMRateLimitError,
    LLMResponse,
    LLMTransportError,
    PERMITTED_TIER_B_TYPES,
    sanitize_case_context,
)

RUNS_DIR = Path(__file__).resolve().parent.parent.parent / "runs"


TIMELINE_TIME_REGEX = re.compile(r"(?:\b|T)((?:[01]?\d|2[0-3]):[0-5]\d)\b")
NOTE_TIME_REGEX = re.compile(r"\b((?:[01]?\d|2[0-3]):[0-5]\d)\b")
SPATIAL_MODIFIER = (
    r"(?:(?!that\b|which\b|who\b|reported\b|explained\b|said\b|stated\b|claimed\b|"
    r"was\b|were\b|is\b|are\b)[a-z-]+\s+){0,2}"
)
SPATIAL_INDICATOR_PATTERN = re.compile(
    r"\b(?:"
    # 1. Unambiguous locative prepositions: near, next to, under, opposite, behind, etc.
    r"(?:near|next to|beside|across from|opposite|under|underneath|below|above|behind|in front of|adjacent to|against|inside|outside)\s+"
    r"(?:(?:the|a|an|this|that|their|his|her|[a-z]+\'s)\s+)?"
    + SPATIAL_MODIFIER +
    r"(?:door|window|counter|table|desk|floor|wall|sofa|couch|bed|closet|cabinet|credenza|shelf|room|corridor|hallway|entrance|balcony|exit|printer)\b"
    r"|"
    # 2. Place prepositions (on, in, at, from) paired with specific physical/spatial location nouns
    r"(?:on|in|at|from)\s+(?:top of\s+)?(?:(?:the|a|an|this|that|their|his|her|[a-z]+\'s)\s+)?"
    + SPATIAL_MODIFIER +
    r"(?:counter|table|desk|floor|credenza|cabinet|shelf|closet|sofa|couch|bed|wall|ceiling|window|door|entrance|balcony|corridor|hallway|far end)\b"
    r")",
    re.IGNORECASE,
)


def compute_context_hash(case_context: dict[str, Any]) -> str:
    """Compute SHA-256 hash of the sanitized textual case context."""
    sanitized = sanitize_case_context(case_context)
    serialized = json.dumps(sanitized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def evaluate_semantic_gate(case_context: dict[str, Any]) -> list[str]:
    """Evaluate structural preconditions for each Tier B category per PROJECT_BRIEF §6.

    Selects only the Tier B contradiction categories that have cross-source records
    present in the case data to reconcile:
    - spatial_inconsistency: requires spatial information in a valid combination of sources
      (e.g. note with spatial claims and map evidence-position summary, or multiple notes with spatial claims).
    - timeline_contradiction: requires at least two actual time-bearing records across timeline
      entries and notes mentioning project-accepted HH:MM times.
    - contextual_contradiction: requires at least two potentially comparable factual records
      across available case sources (notes, timeline, detections, confirmed evidence).
      Does NOT require dismissed detections (the dismissal guard is enforced downstream in the validator).
    """
    notes = case_context.get("notes", []) or []
    timeline = case_context.get("timeline", []) or []
    map_data = case_context.get("map", {}) or {}
    evidence_positions = map_data.get("evidence_positions_summary", []) or []
    detections = [
        det
        for photo in (case_context.get("photos", []) or [])
        for det in (photo.get("detections", []) or [])
    ]
    evidence_items = case_context.get("evidence", []) or []

    selected: list[str] = []

    # 1. Spatial Inconsistency: spatial note + map summary, or multiple spatial notes
    spatial_notes = [
        n for n in notes
        if isinstance(n, dict) and SPATIAL_INDICATOR_PATTERN.search(n.get("text", ""))
    ]
    valid_map_positions = [
        s for s in evidence_positions
        if isinstance(s, str) and s.strip()
    ]
    if (len(spatial_notes) >= 1 and len(valid_map_positions) >= 1) or len(spatial_notes) >= 2:
        selected.append("spatial_inconsistency")

    # 2. Timeline Contradiction: at least two actual time-bearing records
    time_bearing_timeline = [
        t for t in timeline
        if isinstance(t, dict) and (
            TIMELINE_TIME_REGEX.search(str(t.get("time", "") or ""))
            or TIMELINE_TIME_REGEX.search(str(t.get("description", "") or ""))
        )
    ]
    time_bearing_notes = [
        n for n in notes
        if isinstance(n, dict) and NOTE_TIME_REGEX.search(n.get("text", "") or "")
    ]
    if (len(time_bearing_timeline) + len(time_bearing_notes)) >= 2:
        selected.append("timeline_contradiction")

    # 3. Contextual Contradiction: at least two relevant factual records across available sources
    relevant_notes = [n for n in notes if isinstance(n, dict) and n.get("text", "").strip()]
    relevant_timeline = [t for t in timeline if isinstance(t, dict) and t.get("description", "").strip()]
    relevant_detections = [d for d in detections if isinstance(d, dict) and d.get("class", "").strip()]
    relevant_evidence = [e for e in evidence_items if isinstance(e, dict) and e.get("label", "").strip()]

    total_relevant_records = (
        len(relevant_notes)
        + len(relevant_timeline)
        + len(relevant_detections)
        + len(relevant_evidence)
    )
    if total_relevant_records >= 2:
        selected.append("contextual_contradiction")

    return selected


class PipelineResult(dict):
    """Structured result dictionary returned by run_pipeline."""

    @property
    def case_id(self) -> str:
        return self.get("case_id", "")

    @property
    def run_id(self) -> str:
        return self.get("run_id", "")

    @property
    def context_hash(self) -> str:
        return self.get("context_hash", "")

    @property
    def tier_a_flags(self) -> list[dict[str, Any]]:
        return self.get("tier_a_flags", [])

    @property
    def tier_b_suggestions(self) -> list[dict[str, Any]]:
        return self.get("tier_b_suggestions", [])

    @property
    def rejected_suggestions(self) -> list[dict[str, Any]]:
        return self.get("rejected_suggestions", [])

    @property
    def invocation_outcomes(self) -> list[dict[str, Any]]:
        return self.get("invocation_outcomes", [])

    @property
    def stats(self) -> dict[str, Any]:
        return self.get("stats", {})

    @property
    def audit_path(self) -> str | None:
        return self.get("audit_path")

    @property
    def status(self) -> str:
        return self.get("status", "")


def run_pipeline(
    case_context: dict[str, Any],
    client: LLMClient | None = None,
    config: LLMConfig | None = None,
    tier_b_types: list[str] | None = None,
    all_types: bool = False,
    tier_a_only: bool = False,
    write_audit: bool = True,
    run_dir: Path | None = None,
) -> PipelineResult:
    """Execute the end-to-end crime scene evidence analysis pipeline.

    Args:
        case_context: The structured case data dictionary.
        client: Optional pre-configured LLMClient. If None, created from config.
        config: Optional LLMConfig when creating client.
        tier_b_types: Optional explicit list of Tier B categories to execute.
        all_types: If True, bypasses gate and selects all 3 approved categories.
        tier_a_only: If True, executes only Tier A deterministic engine.
        write_audit: If True, writes structured audit JSON to runs/ directory.
        run_dir: Optional custom directory for audit files (defaults to runs/).

    Returns:
        PipelineResult dictionary containing findings, stats, and audit path.
    """
    case_id = str(case_context.get("case", {}).get("id", "UNKNOWN"))
    run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    start_time = time.perf_counter()
    context_hash = compute_context_hash(case_context)

    # --- STAGE 1: Tier A Deterministic Rules ---
    tier_a_flags = run_tier_a(case_context)

    # --- STAGE 2: Category Selection & Semantic Gate ---
    if tier_a_only:
        selected_categories: list[str] = []
        gate_status = "tier_a_only"
    elif all_types:
        selected_categories = sorted(list(PERMITTED_TIER_B_TYPES))
        gate_status = "all_types_forced"
    elif tier_b_types is not None:
        # Validate requested categories against approved catalog
        invalid_types = set(tier_b_types) - PERMITTED_TIER_B_TYPES
        if invalid_types:
            raise ValueError(
                f"Invalid Tier B category in tier_b_types: {sorted(invalid_types)}. "
                f"Must be subset of: {sorted(PERMITTED_TIER_B_TYPES)}"
            )
        selected_categories = list(tier_b_types)
        gate_status = "selective_override"
    else:
        # Semantic gate evaluates cross-source preconditions
        selected_categories = evaluate_semantic_gate(case_context)
        gate_status = "gate_evaluated" if selected_categories else "gate_skipped"

    # --- STAGE 3: Tier B LLM Invocations & Validation Gate ---
    tier_b_suggestions: list[dict[str, Any]] = []
    rejected_suggestions: list[dict[str, Any]] = []
    invocation_outcomes: list[dict[str, Any]] = []

    combined_stats: dict[str, Any] = {
        "received": 0,
        "validated": 0,
        "rejected": 0,
        "drop_reasons": {
            "schema_fail": 0,
            "type_mismatch": 0,
            "unresolved_ref": 0,
            "dismissal_guard": 0,
            "hallucination_suspected": 0,
            "deduped_by_tier_a": 0,
        },
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "total_latency_ms": 0.0,
    }

    client_owned = False
    active_client = client

    if selected_categories and not tier_a_only:
        if active_client is None:
            active_client = LLMClient(config=config)
            client_owned = True

        try:
            for idx, category in enumerate(selected_categories):
                inv_start = time.perf_counter()
                try:
                    llm_res = active_client.analyze_case(
                        case_context=case_context,
                        assigned_analysis_type=category,
                    )
                    inv_latency = llm_res.latency_ms
                    usage = llm_res.usage
                    combined_stats["total_prompt_tokens"] += usage.get("prompt_tokens", 0)
                    combined_stats["total_completion_tokens"] += usage.get("completion_tokens", 0)
                    combined_stats["total_tokens"] += usage.get("total_tokens", 0)
                    combined_stats["total_latency_ms"] += inv_latency

                    outcome: dict[str, Any] = {
                        "category": category,
                        "status": llm_res.status,
                        "error": llm_res.error,
                        "attempts": llm_res.attempts,
                        "latency_ms": inv_latency,
                        "usage": usage,
                        "provider": llm_res.provider,
                        "model": llm_res.model,
                        "raw_response": llm_res.raw_response,
                    }

                    if llm_res.status == "schema_fail":
                        # Record schema failure explicitly as an invocation drop
                        combined_stats["drop_reasons"]["schema_fail"] += 1
                        invocation_outcomes.append(outcome)
                        continue

                    # Pass successful LLM response into the 7-check validator
                    val_result = validate(
                        llm_response=llm_res,
                        case_context=case_context,
                        tier_a_flags=tier_a_flags,
                        assigned_analysis_type=category,
                    )

                    tier_b_suggestions.extend(val_result["validated"])
                    rejected_suggestions.extend(val_result["rejected"])

                    val_stats = val_result["stats"]
                    combined_stats["received"] += val_stats["received"]
                    combined_stats["validated"] += val_stats["validated"]
                    combined_stats["rejected"] += val_stats["rejected"]
                    for reason, count in val_stats["drop_reasons"].items():
                        combined_stats["drop_reasons"][reason] += count

                    outcome["validated_count"] = len(val_result["validated"])
                    outcome["rejected_count"] = len(val_result["rejected"])
                    invocation_outcomes.append(outcome)

                except (
                    LLMTransportError,
                    LLMAuthenticationError,
                    LLMRateLimitError,
                    LLMConfigurationError,
                ) as err:
                    inv_latency = round((time.perf_counter() - inv_start) * 1000, 2)
                    err_type = type(err).__name__
                    invocation_outcomes.append({
                        "category": category,
                        "status": "error",
                        "error_type": err_type,
                        "error": str(err),
                        "latency_ms": inv_latency,
                    })
        finally:
            # Client ownership rule: Close ONLY if instantiated by the pipeline
            if client_owned and active_client is not None:
                active_client.close()

    total_pipeline_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
    combined_stats["pipeline_latency_ms"] = total_pipeline_time_ms

    # Determine overall status
    if tier_a_only or not selected_categories:
        pipeline_status = "success"
    else:
        total_invocations = len(invocation_outcomes)
        failed_invocations = sum(
            1 for o in invocation_outcomes if o.get("status") in ("error", "schema_fail")
        )
        if failed_invocations == 0:
            pipeline_status = "success"
        elif failed_invocations < total_invocations:
            pipeline_status = "partial_success"
        else:
            pipeline_status = "failure"

    # --- STAGE 4: Audit Record Assembly & Persistence ---
    audit_data: dict[str, Any] = {
        "case_id": case_id,
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "context_hash": context_hash,
        "status": pipeline_status,
        "gate_status": gate_status,
        "selected_categories": selected_categories,
        "tier_a_flags": tier_a_flags,
        "tier_b_suggestions": tier_b_suggestions,
        "rejected_suggestions": rejected_suggestions,
        "invocation_outcomes": invocation_outcomes,
        "stats": combined_stats,
    }

    audit_path_str: str | None = None
    if write_audit:
        target_dir = run_dir or RUNS_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        audit_file = target_dir / f"{case_id}_{run_id}.json"
        audit_file.write_text(json.dumps(audit_data, indent=2, ensure_ascii=False), encoding="utf-8")
        audit_path_str = str(audit_file)

    result_dict: dict[str, Any] = {
        **audit_data,
        "audit_path": audit_path_str,
    }

    return PipelineResult(result_dict)
