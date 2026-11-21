"""Prototype JSON file persistence store for investigator workflows.

NOTE: This is a lightweight prototype persistence layer designed for local development,
prototyping, and offline test verification. It is not an enterprise-grade ACID database.

Enforces:
- Separation of immutable analysis snapshots from append-only investigator reviews.
- Strict immutability of original model findings and suggestion payloads.
- Mandatory explanation rationale when dismissing suggestions as 'not_relevant'.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import time
from typing import Any
import uuid

PERMITTED_REVIEW_STATUSES: frozenset[str] = frozenset({
    "pending",
    "acknowledged",
    "not_relevant",
    "deferred",
})

DEFAULT_WORKFLOW_STORE_DIR = Path(__file__).resolve().parent.parent.parent / "runs" / "workflow_history"


class WorkflowStore:
    """File-based prototype persistence store for analysis history and reviews."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else DEFAULT_WORKFLOW_STORE_DIR
        self.analyses_dir = self.base_dir / "analyses"
        self.reviews_dir = self.base_dir / "reviews"
        self.analyses_dir.mkdir(parents=True, exist_ok=True)
        self.reviews_dir.mkdir(parents=True, exist_ok=True)

    def save_analysis(self, response_envelope: dict[str, Any]) -> str:
        """Persist an immutable analysis snapshot.

        Returns:
            The analysis_id of the persisted record.
        """
        data = response_envelope.get("data", {})
        analysis_id = data.get("analysis_id")
        if not analysis_id:
            analysis_id = f"analysis_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            data["analysis_id"] = analysis_id

        case_id = response_envelope.get("case_id", "UNKNOWN")
        request_id = response_envelope.get("request_id", "")
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        record: dict[str, Any] = {
            "analysis_id": analysis_id,
            "request_id": request_id,
            "case_id": case_id,
            "created_at": created_at,
            "response_snapshot": copy.deepcopy(response_envelope),
        }

        analysis_file = self.analyses_dir / f"{analysis_id}.json"
        analysis_file.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return analysis_id

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        """Retrieve an analysis record by its unique ID."""
        analysis_file = self.analyses_dir / f"{analysis_id}.json"
        if not analysis_file.is_file():
            return None
        return json.loads(analysis_file.read_text(encoding="utf-8"))

    def get_case_history(self, case_id: str) -> list[dict[str, Any]]:
        """Retrieve all analysis records for a case, sorted newest first."""
        matching: list[dict[str, Any]] = []
        for file_path in self.analyses_dir.glob("*.json"):
            try:
                rec = json.loads(file_path.read_text(encoding="utf-8"))
                if rec.get("case_id") == case_id:
                    matching.append(rec)
            except (json.JSONDecodeError, OSError):
                continue

        # Sort descending by created_at (newest first)
        matching.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return matching

    def get_latest_analysis(self, case_id: str) -> dict[str, Any] | None:
        """Retrieve the most recent analysis record for a given case."""
        history = self.get_case_history(case_id)
        return history[0] if history else None

    def record_review(
        self,
        analysis_id: str,
        suggestion_id: str,
        review_status: str,
        reviewed_by: str = "investigator",
        comment: str = "",
    ) -> dict[str, Any]:
        """Record an investigator review decision for a specific finding.

        Strictly append-only; never mutates or deletes the underlying analysis snapshot.

        Raises:
            ValueError: If review_status is invalid or if comment is empty for 'not_relevant'.
        """
        if review_status not in PERMITTED_REVIEW_STATUSES:
            raise ValueError(
                f"Invalid review_status: {review_status!r}. "
                f"Permitted statuses: {sorted(PERMITTED_REVIEW_STATUSES)}."
            )

        trimmed_comment = (comment or "").strip()
        if review_status == "not_relevant" and not trimmed_comment:
            raise ValueError("A non-empty comment/reason is mandatory when marking a finding as 'not_relevant'.")

        review_id = f"rev_{uuid.uuid4().hex[:8]}"
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        review_entry: dict[str, Any] = {
            "review_id": review_id,
            "analysis_id": analysis_id,
            "suggestion_id": suggestion_id,
            "review_status": review_status,
            "reviewed_by": reviewed_by,
            "reviewed_at": timestamp,
            "comment": trimmed_comment,
        }

        reviews_file = self.reviews_dir / f"{analysis_id}.jsonl"
        with reviews_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(review_entry, ensure_ascii=False) + "\n")

        return review_entry

    def get_reviews(
        self,
        analysis_id: str,
        suggestion_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve review records for an analysis, optionally filtered by suggestion_id."""
        reviews_file = self.reviews_dir / f"{analysis_id}.jsonl"
        if not reviews_file.is_file():
            return []

        results: list[dict[str, Any]] = []
        with reviews_file.open("r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    entry = json.loads(line_str)
                    if suggestion_id is None or entry.get("suggestion_id") == suggestion_id:
                        results.append(entry)
                except json.JSONDecodeError:
                    continue

        return results

    def get_latest_review_status(self, analysis_id: str, suggestion_id: str) -> str:
        """Return the current review status of a finding (defaults to 'pending')."""
        reviews = self.get_reviews(analysis_id, suggestion_id=suggestion_id)
        if reviews:
            return reviews[-1].get("review_status", "pending")
        return "pending"
