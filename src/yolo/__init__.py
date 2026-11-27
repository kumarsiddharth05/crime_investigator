"""Module 2 (YOLO): Candidate Detection, Investigator Review & Evidence Management."""

from __future__ import annotations

from src.yolo.__main__ import ActionResult, YoloCLI
from src.yolo.detector import (
    DetectorBackend,
    DetectorConfig,
    DetectorOutput,
    ModelProvenance,
    RawPrediction,
    StubDetectorBackend,
    UltralyticsYOLOBackend,
)
from src.yolo.exceptions import (
    DetectorDependencyError,
    DetectorError,
    ExportValidationError,
    IntegrityError,
    InvalidPhotoError,
    InvalidTransitionError,
    RecordNotFoundError,
    StorageError,
    YoloModuleError,
)
from src.yolo.exporter import (
    ExportResult,
    export_case_context,
    export_yolo_sections,
)
from src.yolo.models import (
    DetectionCandidate,
    DetectionRun,
    EvidenceEvent,
    EvidenceRecord,
    PhotoRecord,
    ReviewEvent,
)
from src.yolo.preview import (
    DISPOSITION_COLORS,
    ImagePrepMetadata,
    PreviewResult,
    compute_letterbox_metadata,
    normalize_bbox_xyxy,
    prepare_image_metadata,
    read_exif_orientation,
    render_annotated_preview,
    reverse_letterbox_bbox,
    validate_and_clip_bbox,
)
from src.yolo.service import DetectionRunResult, YoloDetectionService
from src.yolo.store import YoloCaseStore

__all__ = [
    # Exceptions
    "YoloModuleError",
    "InvalidPhotoError",
    "IntegrityError",
    "RecordNotFoundError",
    "InvalidTransitionError",
    "StorageError",
    "DetectorError",
    "DetectorDependencyError",
    "ExportValidationError",
    # Models
    "PhotoRecord",
    "DetectionRun",
    "DetectionCandidate",
    "EvidenceRecord",
    "ReviewEvent",
    "EvidenceEvent",
    # Storage
    "YoloCaseStore",
    # Detector
    "DetectorConfig",
    "RawPrediction",
    "ModelProvenance",
    "DetectorOutput",
    "DetectorBackend",
    "StubDetectorBackend",
    "UltralyticsYOLOBackend",
    # Preview & Transforms
    "ImagePrepMetadata",
    "PreviewResult",
    "DISPOSITION_COLORS",
    "read_exif_orientation",
    "compute_letterbox_metadata",
    "prepare_image_metadata",
    "reverse_letterbox_bbox",
    "validate_and_clip_bbox",
    "normalize_bbox_xyxy",
    "render_annotated_preview",
    # Service
    "DetectionRunResult",
    "YoloDetectionService",
    # Exporter
    "ExportResult",
    "export_yolo_sections",
    "export_case_context",
    # CLI
    "ActionResult",
    "YoloCLI",
]
