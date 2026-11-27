"""Module 2 (YOLO) exception hierarchy."""

from __future__ import annotations


class YoloModuleError(Exception):
    """Base exception for all Module 2 (YOLO) errors."""


class InvalidPhotoError(YoloModuleError):
    """Raised when photo file is missing, empty, unreadable, corrupt, or unsupported format."""


class IntegrityError(YoloModuleError):
    """Raised on duplicate SHA-256 upload (when disallowed), file conflicts, or path containment violations."""


class RecordNotFoundError(YoloModuleError):
    """Raised when a photo, detection run, candidate, or evidence record cannot be found."""


class InvalidTransitionError(YoloModuleError):
    """Raised on illegal state/disposition transitions or invalid review actions."""


class StorageError(YoloModuleError):
    """Raised on storage I/O, atomic write, or corrupted JSON / JSONL failures."""


class DetectorError(YoloModuleError):
    """Raised on model loading, inference execution, or malformed prediction outputs."""


class DetectorDependencyError(DetectorError):
    """Raised when optional detector backend dependency (e.g. ultralytics) is missing."""


class ExportValidationError(YoloModuleError):
    """Raised when exported case_context fails Draft-07 schema validation."""
