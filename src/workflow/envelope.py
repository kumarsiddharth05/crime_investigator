"""Workflow request and response envelopes, status mapping, and validation.

Enforces schema_version="1.0" with strictly deterministic action generation
and explicit result states:
- findings_returned
- empty_suggestions
- partial_completion
- technical_failure
"""

from __future__ import annotations

import copy
from typing import Any
import uuid

SCHEMA_VERSION: str = "1.0"
PERMITTED_OPERATIONS: frozenset[str] = frozenset({"analyze"})
PERMITTED_TIER_B_TYPES: frozenset[str] = frozenset({
    "spatial_inconsistency",
    "timeline_contradiction",
    "contextual_contradiction",
})

STATUS_COMPLETED: str = "completed"
STATUS_COMPLETED_WITH_WARNINGS: str = "completed_with_warnings"
STATUS_FAILED: str = "failed"

RESULT_STATE_FINDINGS: str = "findings_returned"
RESULT_STATE_EMPTY: str = "empty_suggestions"
RESULT_STATE_PARTIAL: str = "partial_completion"
RESULT_STATE_FAILURE: str = "technical_failure"

RESULT_STATES: frozenset[str] = frozenset({
    RESULT_STATE_FINDINGS,
    RESULT_STATE_EMPTY,
    RESULT_STATE_PARTIAL,
    RESULT_STATE_FAILURE,
})

EMPTY_SUGGESTIONS_MESSAGE: str = (
    "No contradictions were identified in the selected analysis category using the available case information."
)

_DETERMINISTIC_ACTIONS: dict[str, list[str]] = {
    RESULT_STATE_FINDINGS: [
        "view_findings",
        "review_findings",
        "inspect_source_references",
        "run_analysis",
        "view_case_history",
        "return_to_menu",
    ],
    RESULT_STATE_EMPTY: [
        "run_another_category",
        "view_analysis_details",
        "run_analysis",
        "return_to_menu",
    ],
    RESULT_STATE_PARTIAL: [
        "retry_failed_categories",
        "view_findings",
        "view_error_details",
        "return_to_menu",
    ],
    RESULT_STATE_FAILURE: [
        "retry_analysis",
        "view_error_details",
        "return_to_menu",
    ],
    "initial": [
        "select_case",
        "run_analysis",
        "view_previous_analysis",
        "exit",
    ],
    "post_review": [
        "view_findings",
        "review_findings",
        "view_case_history",
        "return_to_menu",
    ],
}


def get_available_actions(result_state: str) -> list[str]:
    """Return deterministic available actions for an application state.

    Actions are strictly controlled by Python state logic. LLM responses
    cannot define, extend, or influence this list.
    """
    return list(_DETERMINISTIC_ACTIONS.get(result_state, ["return_to_menu"]))


class WorkflowRequest(dict):
    """Structured request envelope for workflow operations."""

    @classmethod
    def create(
        cls,
        case_id: str,
        case_context: dict[str, Any],
        analysis_types: list[str],
        request_id: str | None = None,
        operation: str = "analyze",
    ) -> WorkflowRequest:
        return cls({
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id or f"req_{uuid.uuid4().hex[:8]}",
            "case_id": case_id,
            "operation": operation,
            "analysis_types": list(analysis_types),
            "case_context": case_context,
        })


class WorkflowResponse(dict):
    """Structured response envelope for workflow operations."""

    @property
    def schema_version(self) -> str:
        return self.get("schema_version", "")

    @property
    def request_id(self) -> str:
        return self.get("request_id", "")

    @property
    def case_id(self) -> str:
        return self.get("case_id", "")

    @property
    def status(self) -> str:
        return self.get("status", "")

    @property
    def result_state(self) -> str:
        return self.get("data", {}).get("result_state", "")

    @property
    def suggestions(self) -> list[dict[str, Any]]:
        return self.get("data", {}).get("suggestions", [])

    @property
    def available_actions(self) -> list[str]:
        return self.get("available_actions", [])


def validate_request_envelope(request: Any) -> tuple[bool, str | None]:
    """Validate incoming request envelope structure and parameters.

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(request, dict):
        return False, "Request must be a JSON dictionary object."

    schema_version = request.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        return False, f"Unsupported schema_version: {schema_version!r}. Must be {SCHEMA_VERSION!r}."

    operation = request.get("operation")
    if operation not in PERMITTED_OPERATIONS:
        return False, f"Unsupported operation: {operation!r}. Must be one of: {sorted(PERMITTED_OPERATIONS)}."

    analysis_types = request.get("analysis_types")
    if not isinstance(analysis_types, list) or len(analysis_types) == 0:
        return False, "analysis_types must be a non-empty list of Tier B categories."

    invalid_types = set(analysis_types) - PERMITTED_TIER_B_TYPES
    if invalid_types:
        return False, (
            f"Invalid analysis category in analysis_types: {sorted(invalid_types)}. "
            f"Permitted categories: {sorted(PERMITTED_TIER_B_TYPES)}."
        )

    case_context = request.get("case_context")
    if not isinstance(case_context, dict):
        return False, "case_context must be a dictionary containing structured case records."

    return True, None


def create_failed_response(
    request_id: str | None,
    case_id: str | None,
    error_message: str,
    operation: str = "analyze",
) -> WorkflowResponse:
    """Build a structured failed response envelope for technical or validation failures."""
    data: dict[str, Any] = {
        "analysis_id": None,
        "result_state": RESULT_STATE_FAILURE,
        "tier_a_flags": [],
        "suggestions": [],
        "completed_categories": [],
        "ineligible_categories": [],
        "failed_categories": [],
        "retryable_categories": [],
        "validation_summary": {
            "received": 0,
            "validated": 0,
            "rejected": 0,
            "drop_reasons": {},
        },
    }
    return WorkflowResponse({
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id or f"req_{uuid.uuid4().hex[:8]}",
        "case_id": case_id or "UNKNOWN",
        "module": "llm_analysis",
        "operation": operation,
        "status": STATUS_FAILED,
        "data": data,
        "warnings": [],
        "errors": [error_message],
        "available_actions": get_available_actions(RESULT_STATE_FAILURE),
    })


def build_response_envelope(
    request_id: str,
    case_id: str,
    analysis_id: str,
    tier_a_flags: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    completed_categories: list[str],
    ineligible_categories: list[dict[str, str]],
    failed_categories: list[dict[str, Any]],
    validation_summary: dict[str, Any],
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> WorkflowResponse:
    """Construct a typed WorkflowResponse with deterministic status and presentation mapping.

    Presentation States:
    1. findings_returned: validated Tier B suggestions present and no partial failures.
    2. empty_suggestions: all eligible categories completed with 0 validated suggestions and 0 failures.
    3. partial_completion: mix of completed and ineligible/failed categories.
    4. technical_failure: all attempted categories failed or critical failure.
    """
    warn_list = list(warnings or [])
    err_list = list(errors or [])

    # Retryable categories include only eligible categories that failed during execution.
    # Gate-ineligible categories are strictly non-retryable without new case data.
    retryable_categories = [
        fc["category"] for fc in failed_categories if "category" in fc
    ]

    total_attempted = len(completed_categories) + len(failed_categories)

    if total_attempted > 0 and len(completed_categories) == 0 and len(failed_categories) > 0:
        result_state = RESULT_STATE_FAILURE
        status = STATUS_FAILED
    elif len(failed_categories) > 0:
        result_state = RESULT_STATE_PARTIAL
        status = STATUS_COMPLETED_WITH_WARNINGS
    else:
        # No failed categories
        if len(suggestions) > 0:
            result_state = RESULT_STATE_FINDINGS
            status = STATUS_COMPLETED_WITH_WARNINGS if (ineligible_categories or warn_list) else STATUS_COMPLETED
        else:
            result_state = RESULT_STATE_EMPTY
            status = STATUS_COMPLETED_WITH_WARNINGS if (ineligible_categories or warn_list) else STATUS_COMPLETED

    # Build response data container
    data: dict[str, Any] = {
        "analysis_id": analysis_id,
        "result_state": result_state,
        "tier_a_flags": copy.deepcopy(tier_a_flags),
        "suggestions": copy.deepcopy(suggestions),
        "completed_categories": list(completed_categories),
        "ineligible_categories": copy.deepcopy(ineligible_categories),
        "failed_categories": copy.deepcopy(failed_categories),
        "retryable_categories": retryable_categories,
        "validation_summary": copy.deepcopy(validation_summary),
    }

    available_actions = get_available_actions(result_state)

    return WorkflowResponse({
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "case_id": case_id,
        "module": "llm_analysis",
        "operation": "analyze",
        "status": status,
        "data": data,
        "warnings": warn_list,
        "errors": err_list,
        "available_actions": available_actions,
    })
