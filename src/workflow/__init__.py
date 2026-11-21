"""Workflow orchestration and investigator interaction prototype module.

Provides:
- Request/response envelopes and validation (schema_version="1.0").
- Prototype JSON file persistence store.
- Pipeline adapter wrapping the frozen LLM analysis engine.
"""

from src.workflow.adapter import WorkflowAdapter
from src.workflow.envelope import (
    EMPTY_SUGGESTIONS_MESSAGE,
    PERMITTED_OPERATIONS,
    PERMITTED_TIER_B_TYPES,
    RESULT_STATE_EMPTY,
    RESULT_STATE_FAILURE,
    RESULT_STATE_FINDINGS,
    RESULT_STATE_PARTIAL,
    RESULT_STATES,
    SCHEMA_VERSION,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_FAILED,
    WorkflowRequest,
    WorkflowResponse,
    build_response_envelope,
    create_failed_response,
    get_available_actions,
    validate_request_envelope,
)
from src.workflow.store import WorkflowStore

__all__ = [
    "EMPTY_SUGGESTIONS_MESSAGE",
    "PERMITTED_OPERATIONS",
    "PERMITTED_TIER_B_TYPES",
    "RESULT_STATE_EMPTY",
    "RESULT_STATE_FAILURE",
    "RESULT_STATE_FINDINGS",
    "RESULT_STATE_PARTIAL",
    "RESULT_STATES",
    "SCHEMA_VERSION",
    "STATUS_COMPLETED",
    "STATUS_COMPLETED_WITH_WARNINGS",
    "STATUS_FAILED",
    "WorkflowAdapter",
    "WorkflowRequest",
    "WorkflowResponse",
    "WorkflowStore",
    "build_response_envelope",
    "create_failed_response",
    "get_available_actions",
    "validate_request_envelope",
]
