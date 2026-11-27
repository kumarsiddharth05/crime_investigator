"""Domain models and data contracts for Module 2 (YOLO)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from src.yolo.exceptions import IntegrityError, InvalidTransitionError


@dataclass
class PhotoRecord:
    photo_id: str
    ref: str
    case_id: str
    original_path: str
    sha256: str
    width: int
    height: int
    file_size_bytes: int
    image_format: str
    source_filename: str
    ingested_at: str
    ingested_by: str
    room: str | None = None
    exif_orientation: int | None = None

    def __post_init__(self) -> None:
        if not self.photo_id or not isinstance(self.photo_id, str):
            raise IntegrityError("photo_id must be a non-empty string")
        if self.ref != f"photos.{self.photo_id}":
            raise IntegrityError(f"ref must match 'photos.{self.photo_id}', got '{self.ref}'")
        if not self.case_id or not isinstance(self.case_id, str):
            raise IntegrityError("case_id must be a non-empty string")
        if not self.original_path or not isinstance(self.original_path, str):
            raise IntegrityError("original_path must be a non-empty string")
        if not self.sha256 or len(self.sha256) != 64 or not all(c in "0123456789abcdefABCDEF" for c in self.sha256):
            raise IntegrityError(f"sha256 must be a 64-character hex string, got '{self.sha256}'")
        if not isinstance(self.width, int) or self.width <= 0:
            raise ValueError(f"width must be a positive integer, got {self.width}")
        if not isinstance(self.height, int) or self.height <= 0:
            raise ValueError(f"height must be a positive integer, got {self.height}")
        if not isinstance(self.file_size_bytes, int) or self.file_size_bytes <= 0:
            raise ValueError(f"file_size_bytes must be a positive integer, got {self.file_size_bytes}")
        normalized_fmt = self.image_format.lower()
        if normalized_fmt not in ("jpeg", "png", "bmp", "webp"):
            raise ValueError(f"image_format must be one of jpeg, png, bmp, webp; got '{self.image_format}'")
        self.image_format = normalized_fmt

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhotoRecord:
        return cls(**data)


@dataclass
class DetectionRun:
    run_id: str
    photo_id: str
    case_id: str
    model_name: str
    model_version: str
    weights_identifier: str
    confidence_threshold: float
    iou_threshold: float
    image_size: int
    device: str
    executed_at: str
    status: Literal["completed", "failed"]
    truncated: bool = False
    truncation_warning: str | None = None
    error_message: str | None = None
    preview_path: str | None = None

    def __post_init__(self) -> None:
        if not self.run_id or not isinstance(self.run_id, str):
            raise IntegrityError("run_id must be a non-empty string")
        if not self.photo_id or not isinstance(self.photo_id, str):
            raise IntegrityError("photo_id must be a non-empty string")
        if not self.case_id or not isinstance(self.case_id, str):
            raise IntegrityError("case_id must be a non-empty string")
        if not (0.0 < self.confidence_threshold <= 1.0) or not math.isfinite(self.confidence_threshold):
            raise ValueError(f"confidence_threshold must be in (0.0, 1.0], got {self.confidence_threshold}")
        if not (0.0 < self.iou_threshold <= 1.0) or not math.isfinite(self.iou_threshold):
            raise ValueError(f"iou_threshold must be in (0.0, 1.0], got {self.iou_threshold}")
        if not isinstance(self.image_size, int) or self.image_size <= 0:
            raise ValueError(f"image_size must be a positive integer, got {self.image_size}")
        if self.status not in ("completed", "failed"):
            raise ValueError(f"status must be 'completed' or 'failed', got '{self.status}'")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DetectionRun:
        return cls(**data)


@dataclass
class DetectionCandidate:
    det_id: str
    ref: str
    photo_id: str
    run_id: str
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    image_width: int
    image_height: int
    normalized_bbox_xyxy: tuple[float, float, float, float] | None = None
    disposition: Literal["unreviewed", "confirmed", "dismissed"] = "unreviewed"
    dismissal_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.det_id or not isinstance(self.det_id, str):
            raise IntegrityError("det_id must be a non-empty string")
        if not self.photo_id or not isinstance(self.photo_id, str):
            raise IntegrityError("photo_id must be a non-empty string")
        if self.ref != f"photos.{self.photo_id}.{self.det_id}":
            raise IntegrityError(f"ref must match 'photos.{self.photo_id}.{self.det_id}', got '{self.ref}'")
        if not self.class_name or not isinstance(self.class_name, str) or not self.class_name.strip():
            raise ValueError("class_name must be a non-empty string")
        if not math.isfinite(self.confidence) or not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be a finite float in [0.0, 1.0], got {self.confidence}")

        # Ensure tuple representation for bbox_xyxy
        if not isinstance(self.bbox_xyxy, (tuple, list)) or len(self.bbox_xyxy) != 4:
            raise ValueError(f"bbox_xyxy must be 4 coordinates, got {self.bbox_xyxy}")
        coords = (
            float(self.bbox_xyxy[0]),
            float(self.bbox_xyxy[1]),
            float(self.bbox_xyxy[2]),
            float(self.bbox_xyxy[3]),
        )
        if not all(math.isfinite(c) for c in coords):
            raise ValueError(f"bbox_xyxy coordinates must be finite, got {coords}")
        x_min, y_min, x_max, y_max = coords
        if x_max <= x_min or y_max <= y_min:
            raise ValueError(f"Invalid bbox_xyxy dimensions: x_max ({x_max}) <= x_min ({x_min}) or y_max ({y_max}) <= y_min ({y_min})")
        self.bbox_xyxy = coords

        if not isinstance(self.image_width, int) or self.image_width <= 0:
            raise ValueError(f"image_width must be positive int, got {self.image_width}")
        if not isinstance(self.image_height, int) or self.image_height <= 0:
            raise ValueError(f"image_height must be positive int, got {self.image_height}")

        if self.normalized_bbox_xyxy is None:
            self.normalized_bbox_xyxy = (
                x_min / self.image_width,
                y_min / self.image_height,
                x_max / self.image_width,
                y_max / self.image_height,
            )
        else:
            if not isinstance(self.normalized_bbox_xyxy, (tuple, list)) or len(self.normalized_bbox_xyxy) != 4:
                raise ValueError("normalized_bbox_xyxy must have 4 coordinates")
            norm_coords = (
                float(self.normalized_bbox_xyxy[0]),
                float(self.normalized_bbox_xyxy[1]),
                float(self.normalized_bbox_xyxy[2]),
                float(self.normalized_bbox_xyxy[3]),
            )
            if not all(math.isfinite(c) for c in norm_coords):
                raise ValueError(f"normalized_bbox_xyxy must be finite, got {norm_coords}")
            nx_min, ny_min, nx_max, ny_max = norm_coords
            if nx_max <= nx_min or ny_max <= ny_min:
                raise ValueError(f"Invalid normalized_bbox_xyxy: nx_max ({nx_max}) <= nx_min ({nx_min}) or ny_max ({ny_max}) <= ny_min ({ny_min})")
            self.normalized_bbox_xyxy = norm_coords

        if self.disposition not in ("unreviewed", "confirmed", "dismissed"):
            raise ValueError(f"disposition must be one of unreviewed, confirmed, dismissed; got '{self.disposition}'")

        if self.disposition == "dismissed":
            if not self.dismissal_reason or not isinstance(self.dismissal_reason, str) or not self.dismissal_reason.strip():
                raise InvalidTransitionError("dismissal_reason must be non-empty after stripping when disposition is 'dismissed'")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bbox_xyxy"] = list(self.bbox_xyxy)
        if self.normalized_bbox_xyxy is not None:
            d["normalized_bbox_xyxy"] = list(self.normalized_bbox_xyxy)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DetectionCandidate:
        data_copy = dict(data)
        if "bbox_xyxy" in data_copy and isinstance(data_copy["bbox_xyxy"], list):
            data_copy["bbox_xyxy"] = tuple(data_copy["bbox_xyxy"])
        if "normalized_bbox_xyxy" in data_copy and isinstance(data_copy["normalized_bbox_xyxy"], list):
            data_copy["normalized_bbox_xyxy"] = tuple(data_copy["normalized_bbox_xyxy"])
        return cls(**data_copy)


@dataclass
class EvidenceRecord:
    evidence_id: str
    ref: str
    case_id: str
    label: str
    description: str
    creation_source: Literal["detection_promoted", "manual"]
    photo_refs: list[str] = field(default_factory=list)
    det_refs: list[str] = field(default_factory=list)
    created_by: str = "investigator"
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_id or not isinstance(self.evidence_id, str):
            raise IntegrityError("evidence_id must be a non-empty string")
        if self.ref != f"evidence.{self.evidence_id}":
            raise IntegrityError(f"ref must match 'evidence.{self.evidence_id}', got '{self.ref}'")
        if not self.case_id or not isinstance(self.case_id, str):
            raise IntegrityError("case_id must be a non-empty string")
        if not self.label or not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("label must be a non-empty string")
        if self.creation_source not in ("detection_promoted", "manual"):
            raise ValueError(f"creation_source must be 'detection_promoted' or 'manual', got '{self.creation_source}'")
        if self.creation_source == "detection_promoted" and not self.det_refs:
            raise ValueError("detection_promoted evidence must have at least one det_ref")
        if not self.created_at:
            now_iso = datetime.now(timezone.utc).isoformat()
            self.created_at = now_iso
            self.updated_at = now_iso

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRecord:
        return cls(**data)


@dataclass
class ReviewEvent:
    event_id: str
    case_id: str
    detection_ref: str
    action: Literal["confirmed", "dismissed", "corrected"]
    previous_disposition: str
    resulting_disposition: Literal["unreviewed", "confirmed", "dismissed"]
    reviewer_id: str
    timestamp: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id or not isinstance(self.event_id, str):
            raise IntegrityError("event_id must be a non-empty string")
        if not self.case_id or not isinstance(self.case_id, str):
            raise IntegrityError("case_id must be a non-empty string")
        if not self.detection_ref or not isinstance(self.detection_ref, str):
            raise IntegrityError("detection_ref must be a non-empty string")
        if self.action not in ("confirmed", "dismissed", "corrected"):
            raise ValueError(f"action must be one of confirmed, dismissed, corrected; got '{self.action}'")
        if self.resulting_disposition not in ("unreviewed", "confirmed", "dismissed"):
            raise ValueError(f"resulting_disposition must be one of unreviewed, confirmed, dismissed; got '{self.resulting_disposition}'")
        if self.resulting_disposition == "dismissed":
            if not self.reason or not isinstance(self.reason, str) or not self.reason.strip():
                raise InvalidTransitionError("reason must be non-empty when resulting_disposition is 'dismissed'")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewEvent:
        return cls(**data)


@dataclass
class EvidenceEvent:
    event_id: str
    case_id: str
    evidence_ref: str
    action: Literal["created", "updated", "linked_photo", "linked_detection", "unlinked_detection"]
    actor_id: str
    timestamp: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id or not isinstance(self.event_id, str):
            raise IntegrityError("event_id must be a non-empty string")
        if not self.case_id or not isinstance(self.case_id, str):
            raise IntegrityError("case_id must be a non-empty string")
        if not self.evidence_ref or not isinstance(self.evidence_ref, str):
            raise IntegrityError("evidence_ref must be a non-empty string")
        if self.action not in ("created", "updated", "linked_photo", "linked_detection", "unlinked_detection"):
            raise ValueError(f"Invalid action '{self.action}' for EvidenceEvent")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceEvent:
        return cls(**data)
