"""Workflow adapter wrapping the frozen LLM analysis pipeline and reference resolver.

Maintains strict separation:
- Calls frozen run_pipeline() without modifying Module 1 logic.
- Preserves the semantic eligibility gate (no bypass).
- Preserves 1-category-per-invocation execution.
- Generates deterministic suggestion IDs (S001, S002, ...) strictly from real pipeline outputs.
- Provides dynamic case discovery and source reference inspection.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import time
from typing import Any, Callable
import uuid

from src.analysis.pipeline import evaluate_semantic_gate, run_pipeline
from src.analysis.refs import resolve_ref
from src.llm import LLMClient
from src.workflow.envelope import (
    WorkflowRequest,
    WorkflowResponse,
    build_response_envelope,
    create_failed_response,
    validate_request_envelope,
)
from src.workflow.store import WorkflowStore

CASES_DIR = Path(__file__).resolve().parent.parent.parent / "cases"


def discover_cases(cases_dir: Path | str | None = None) -> list[Path]:
    """Discover available case JSON files, excluding expected fixture baselines."""
    root = Path(cases_dir) if cases_dir else CASES_DIR
    if not root.is_dir():
        return []
    case_paths = [
        p for p in root.glob("*.json")
        if not p.name.endswith(".expected.json")
    ]
    return sorted(case_paths, key=lambda p: p.name)


def load_case_context(path: Path | str) -> dict[str, Any]:
    """Load case context JSON from an arbitrary file path."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Case context file not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def inspect_source_references(
    case_context: dict[str, Any],
    refs: list[str],
) -> dict[str, Any]:
    """Inspect and resolve cited source references against case records."""
    results: dict[str, Any] = {}
    for ref in refs:
        resolved = resolve_ref(case_context, ref)
        results[ref] = resolved
    return results


class WorkflowAdapter:
    """Thin orchestration adapter interfacing between workflow requests and pipeline."""

    def __init__(
        self,
        store: WorkflowStore | None = None,
        client_factory: Callable[[], LLMClient] | None = None,
    ) -> None:
        self.store = store
        self.client_factory = client_factory

    def execute_request(
        self,
        request: dict[str, Any] | WorkflowRequest,
        client: LLMClient | None = None,
    ) -> WorkflowResponse:
        """Execute a workflow request against the frozen pipeline.

        Preserves:
        - Strict JSON request envelope validation.
        - Semantic eligibility gate per requested category.
        - 1-category-per-invocation discipline.
        """
        is_valid, validation_err = validate_request_envelope(request)
        if not is_valid:
            req_id = request.get("request_id") if isinstance(request, dict) else None
            req_case_id = request.get("case_id") if isinstance(request, dict) else None
            return create_failed_response(
                request_id=req_id,
                case_id=req_case_id,
                error_message=validation_err or "Invalid request envelope",
            )

        case_context: dict[str, Any] = request["case_context"]
        case_id: str = str(request.get("case_id") or case_context.get("case", {}).get("id", "UNKNOWN"))
        request_id: str = str(request.get("request_id") or f"req_{uuid.uuid4().hex[:8]}")
        analysis_types: list[str] = list(request["analysis_types"])

        analysis_id = f"analysis_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # Resolve LLM client
        active_client = client
        if active_client is None and self.client_factory is not None:
            active_client = self.client_factory()

        # Step 1: Execute Tier A deterministic rules
        tier_a_res = run_pipeline(
            case_context=case_context,
            tier_a_only=True,
            write_audit=False,
        )
        tier_a_flags = tier_a_res.tier_a_flags

        # Step 2: Semantic gate evaluation
        eligible_gate_types = set(evaluate_semantic_gate(case_context))

        completed_categories: list[str] = []
        ineligible_categories: list[dict[str, str]] = []
        failed_categories: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []

        all_validated_suggestions: list[dict[str, Any]] = []
        validation_summary: dict[str, Any] = {
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
        }

        # Step 3: Execute requested categories with 1-category-per-invocation discipline
        for category in analysis_types:
            if category not in eligible_gate_types:
                reason = f"Preconditions for {category} not satisfied in case context."
                ineligible_categories.append({"category": category, "reason": reason})
                warnings.append(f"Category '{category}' skipped: {reason}")
                continue

            # Eligible: execute single category
            try:
                cat_result = run_pipeline(
                    case_context=case_context,
                    client=active_client,
                    tier_b_types=[category],
                    write_audit=False,
                )

                # Update validation summary stats
                stats = cat_result.stats
                validation_summary["received"] += stats.get("received", 0)
                validation_summary["validated"] += stats.get("validated", 0)
                validation_summary["rejected"] += stats.get("rejected", 0)
                for k, v in stats.get("drop_reasons", {}).items():
                    validation_summary["drop_reasons"][k] = (
                        validation_summary["drop_reasons"].get(k, 0) + v
                    )

                # Check outcome for this invocation
                cat_failed = False
                cat_error = None
                for outcome in cat_result.invocation_outcomes:
                    if outcome.get("status") in ("error", "schema_fail"):
                        cat_failed = True
                        cat_error = outcome.get("error") or outcome.get("status")
                        break

                if cat_failed or cat_result.status == "failure":
                    err_msg = cat_error or "Category analysis failed during execution."
                    failed_categories.append({"category": category, "error": err_msg})
                    errors.append(f"Category '{category}' failed: {err_msg}")
                else:
                    completed_categories.append(category)
                    for sug in cat_result.tier_b_suggestions:
                        all_validated_suggestions.append(copy.deepcopy(sug))

            except Exception as exc:
                err_msg = str(exc) or type(exc).__name__
                failed_categories.append({"category": category, "error": err_msg})
                errors.append(f"Category '{category}' failed: {err_msg}")

        # Step 4: Assign deterministic suggestion IDs S001, S002, ... strictly from real suggestions
        for idx, sug in enumerate(all_validated_suggestions):
            sug["suggestion_id"] = f"S{idx + 1:03d}"

        # Step 5: Build response envelope
        response = build_response_envelope(
            request_id=request_id,
            case_id=case_id,
            analysis_id=analysis_id,
            tier_a_flags=tier_a_flags,
            suggestions=all_validated_suggestions,
            completed_categories=completed_categories,
            ineligible_categories=ineligible_categories,
            failed_categories=failed_categories,
            validation_summary=validation_summary,
            warnings=warnings,
            errors=errors,
        )

        # Step 6: Persist analysis snapshot if store is configured
        if self.store is not None:
            self.store.save_analysis(response)

        return response
