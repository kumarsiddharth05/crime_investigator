"""Unit and integration tests for Module 2 (YOLO): Data Contracts, Storage, and Detector Backend."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from src.analysis.pipeline import run_pipeline
from src.analysis.refs import resolve_ref
from src.analysis.tier_a import run_tier_a
from src.yolo.__main__ import ActionResult, YoloCLI
from src.yolo.detector import (
    DetectorConfig,
    DetectorOutput,
    ModelProvenance,
    RawPrediction,
    StubDetectorBackend,
    UltralyticsYOLOBackend,
    apply_confidence_filter_and_truncation,
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


# ==============================================================================
# In-Memory Test Image Generators (Pure Python Standard Library)
# ==============================================================================

def create_valid_png(width: int = 16, height: int = 16) -> bytes:
    """Generate a valid, minimal PNG image in-memory."""
    sig = b"\x89PNG\r\n\x1a\n"
    # IHDR chunk: width(4), height(4), bit_depth(1)=8, color_type(1)=0 (grayscale), comp(1)=0, filter(1)=0, interlace(1)=0
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    # Grayscale raw rows (filter byte 0x00 followed by row bytes)
    raw_rows = b"".join(b"\x00" + (b"\x80" * width) for _ in range(height))
    compressed = zlib.compress(raw_rows)
    idat_crc = zlib.crc32(b"IDAT" + compressed)
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)

    iend_crc = zlib.crc32(b"IEND")
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
    return sig + ihdr + idat + iend


def create_valid_jpeg(width: int = 16, height: int = 16) -> bytes:
    """Generate a valid, minimal JPEG image in-memory with SOF0 marker."""
    soi = b"\xff\xd8"
    # SOF0 marker: len=11, precision=8, height, width, 1 component
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    eoi = b"\xff\xd9"
    return soi + sof0 + eoi


def create_valid_bmp(width: int = 16, height: int = 16) -> bytes:
    """Generate a valid, minimal BMP image in-memory."""
    row_stride = ((width * 3 + 3) // 4) * 4
    pixel_bytes = row_stride * height
    file_size = 54 + pixel_bytes
    header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
    dib = struct.pack("<IIIHHIIIIII", 40, width, height, 1, 24, 0, pixel_bytes, 2835, 2835, 0, 0)
    pixels = b"\x00" * pixel_bytes
    return header + dib + pixels


# ==============================================================================
# Stage Y1: Model Validation & Serialization Tests
# ==============================================================================

def test_photo_record_validation() -> None:
    # Valid record
    rec = PhotoRecord(
        photo_id="P1",
        ref="photos.P1",
        case_id="C0",
        original_path="photos/originals/P1_original.png",
        sha256="a" * 64,
        width=640,
        height=480,
        file_size_bytes=1024,
        image_format="png",
        source_filename="test.png",
        ingested_at="2026-11-22T00:00:00Z",
        ingested_by="investigator",
    )
    assert rec.ref == "photos.P1"
    assert rec.to_dict()["width"] == 640
    assert PhotoRecord.from_dict(rec.to_dict()).photo_id == "P1"

    # Invalid ref mismatch
    with pytest.raises(IntegrityError):
        PhotoRecord(
            photo_id="P1",
            ref="photos.P2",
            case_id="C0",
            original_path="path",
            sha256="a" * 64,
            width=640,
            height=480,
            file_size_bytes=100,
            image_format="png",
            source_filename="test.png",
            ingested_at="2026-11-22T00:00:00Z",
            ingested_by="investigator",
        )

    # Invalid width/height
    with pytest.raises(ValueError):
        PhotoRecord(
            photo_id="P1",
            ref="photos.P1",
            case_id="C0",
            original_path="path",
            sha256="a" * 64,
            width=0,
            height=480,
            file_size_bytes=100,
            image_format="png",
            source_filename="test.png",
            ingested_at="2026-11-22T00:00:00Z",
            ingested_by="investigator",
        )

    # Invalid format
    with pytest.raises(ValueError):
        PhotoRecord(
            photo_id="P1",
            ref="photos.P1",
            case_id="C0",
            original_path="path",
            sha256="a" * 64,
            width=100,
            height=100,
            file_size_bytes=100,
            image_format="gif",
            source_filename="test.gif",
            ingested_at="2026-11-22T00:00:00Z",
            ingested_by="investigator",
        )


def test_detection_run_validation() -> None:
    run = DetectionRun(
        run_id="RUN001",
        photo_id="P1",
        case_id="C0",
        model_name="yolov8n.pt",
        model_version="8.0.0",
        weights_identifier="sha256_mock",
        confidence_threshold=0.35,
        iou_threshold=0.5,
        image_size=640,
        device="cpu",
        executed_at="2026-11-22T00:00:00Z",
        status="completed",
    )
    assert run.run_id == "RUN001"
    assert DetectionRun.from_dict(run.to_dict()).status == "completed"

    # Invalid confidence bounds
    with pytest.raises(ValueError):
        DetectionRun(
            run_id="RUN001",
            photo_id="P1",
            case_id="C0",
            model_name="yolov8n.pt",
            model_version="8.0.0",
            weights_identifier="sha256_mock",
            confidence_threshold=0.0,
            iou_threshold=0.5,
            image_size=640,
            device="cpu",
            executed_at="2026-11-22T00:00:00Z",
            status="completed",
        )

    # Invalid status
    with pytest.raises(ValueError):
        DetectionRun(
            run_id="RUN001",
            photo_id="P1",
            case_id="C0",
            model_name="yolov8n.pt",
            model_version="8.0.0",
            weights_identifier="sha256_mock",
            confidence_threshold=0.5,
            iou_threshold=0.5,
            image_size=640,
            device="cpu",
            executed_at="2026-11-22T00:00:00Z",
            status="in_progress",  # type: ignore[arg-type]
        )


def test_detection_candidate_validation() -> None:
    cand = DetectionCandidate(
        det_id="d1",
        ref="photos.P1.d1",
        photo_id="P1",
        run_id="RUN001",
        class_id=0,
        class_name="knife",
        confidence=0.88,
        bbox_xyxy=(10.0, 20.0, 100.0, 150.0),
        image_width=1000,
        image_height=1000,
    )
    # Normalized bbox computed automatically
    assert cand.normalized_bbox_xyxy == (0.01, 0.02, 0.1, 0.15)
    assert cand.disposition == "unreviewed"

    # Inverted bbox rejected
    with pytest.raises(ValueError, match="Invalid bbox_xyxy"):
        DetectionCandidate(
            det_id="d1",
            ref="photos.P1.d1",
            photo_id="P1",
            run_id="RUN001",
            class_id=0,
            class_name="knife",
            confidence=0.88,
            bbox_xyxy=(100.0, 20.0, 10.0, 150.0),  # x_max < x_min
            image_width=1000,
            image_height=1000,
        )

    # NaN / Inf confidence rejected
    with pytest.raises(ValueError):
        DetectionCandidate(
            det_id="d1",
            ref="photos.P1.d1",
            photo_id="P1",
            run_id="RUN001",
            class_id=0,
            class_name="knife",
            confidence=float("nan"),
            bbox_xyxy=(10.0, 20.0, 100.0, 150.0),
            image_width=1000,
            image_height=1000,
        )

    # Dismissed without reason rejected
    with pytest.raises(InvalidTransitionError):
        DetectionCandidate(
            det_id="d1",
            ref="photos.P1.d1",
            photo_id="P1",
            run_id="RUN001",
            class_id=0,
            class_name="knife",
            confidence=0.88,
            bbox_xyxy=(10.0, 20.0, 100.0, 150.0),
            image_width=1000,
            image_height=1000,
            disposition="dismissed",
            dismissal_reason="",
        )

    # Dismissed with reason accepted
    cand_dismissed = DetectionCandidate(
        det_id="d1",
        ref="photos.P1.d1",
        photo_id="P1",
        run_id="RUN001",
        class_id=0,
        class_name="knife",
        confidence=0.88,
        bbox_xyxy=(10.0, 20.0, 100.0, 150.0),
        image_width=1000,
        image_height=1000,
        disposition="dismissed",
        dismissal_reason="Glare artifact",
    )
    assert cand_dismissed.dismissal_reason == "Glare artifact"

    # to_dict and from_dict roundtrip
    d = cand.to_dict()
    assert isinstance(d["bbox_xyxy"], list)
    restored = DetectionCandidate.from_dict(d)
    assert isinstance(restored.bbox_xyxy, tuple)
    assert restored.ref == cand.ref


def test_evidence_and_audit_models() -> None:
    # Manual evidence with empty refs accepted
    ev = EvidenceRecord(
        evidence_id="E1",
        ref="evidence.E1",
        case_id="C0",
        label="Kitchen Knife",
        description="Found on table",
        creation_source="manual",
        photo_refs=[],
        det_refs=[],
    )
    assert ev.creation_source == "manual"
    assert ev.det_refs == []

    # Empty label rejected
    with pytest.raises(ValueError):
        EvidenceRecord(
            evidence_id="E2",
            ref="evidence.E2",
            case_id="C0",
            label="   ",
            description="Blank label",
            creation_source="manual",
            photo_refs=[],
            det_refs=[],
        )

    # ReviewEvent dismissal check
    with pytest.raises(InvalidTransitionError):
        ReviewEvent(
            event_id="REV001",
            case_id="C0",
            detection_ref="photos.P1.d1",
            action="dismissed",
            previous_disposition="unreviewed",
            resulting_disposition="dismissed",
            reviewer_id="inv1",
            timestamp="2026-11-22T00:00:00Z",
            reason="",
        )

    rev = ReviewEvent(
        event_id="REV001",
        case_id="C0",
        detection_ref="photos.P1.d1",
        action="dismissed",
        previous_disposition="unreviewed",
        resulting_disposition="dismissed",
        reviewer_id="inv1",
        timestamp="2026-11-22T00:00:00Z",
        reason="False positive reflection",
    )
    assert ReviewEvent.from_dict(rev.to_dict()).reason == "False positive reflection"


# ==============================================================================
# Stage Y1: YoloCaseStore Ingestion, Integrity & Persistence Tests
# ==============================================================================

def test_store_valid_png_and_jpeg_ingestion(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path)
    png_bytes = create_valid_png(32, 24)
    rec_png = store.ingest_photo("C0", image_bytes=png_bytes, source_filename="scene1.png")

    assert rec_png.photo_id == "P1"
    assert rec_png.ref == "photos.P1"
    assert rec_png.width == 32
    assert rec_png.height == 24
    assert rec_png.image_format == "png"
    assert store.verify_photo_integrity("C0", "P1") is True

    # Ingest JPEG
    jpg_bytes = create_valid_jpeg(40, 30)
    rec_jpg = store.ingest_photo("C0", image_bytes=jpg_bytes, source_filename="scene2.jpg")
    assert rec_jpg.photo_id == "P2"
    assert rec_jpg.image_format == "jpeg"
    assert store.verify_photo_integrity("C0", "P2") is True


def test_store_tamper_detection(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path)
    png_bytes = create_valid_png(16, 16)
    rec = store.ingest_photo("C0", image_bytes=png_bytes, source_filename="scene.png")
    assert store.verify_photo_integrity("C0", rec.photo_id) is True

    # Tamper with file
    orig_file = tmp_path / "C0" / rec.original_path
    data = bytearray(orig_file.read_bytes())
    data[len(data) - 5] ^= 0xFF
    orig_file.write_bytes(bytes(data))

    assert store.verify_photo_integrity("C0", rec.photo_id) is False


def test_store_duplicate_bytes_handling(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path)
    png_bytes = create_valid_png(16, 16)
    rec1 = store.ingest_photo("C0", image_bytes=png_bytes)
    assert rec1.photo_id == "P1"

    # Default duplicate rejection
    with pytest.raises(IntegrityError, match="Photo with identical SHA-256 already exists"):
        store.ingest_photo("C0", image_bytes=png_bytes)

    # Allowed duplicate upload
    rec2 = store.ingest_photo("C0", image_bytes=png_bytes, allow_duplicate_bytes=True)
    assert rec2.photo_id == "P2"
    assert rec2.sha256 == rec1.sha256


def test_store_invalid_photo_rejections(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path, max_file_size_bytes=500)

    # Empty bytes
    with pytest.raises(InvalidPhotoError, match="empty"):
        store.ingest_photo("C0", image_bytes=b"")

    # Plain text / non-image
    with pytest.raises(InvalidPhotoError, match="Unsupported image format"):
        store.ingest_photo("C0", image_bytes=b"Hello world, I am not an image!")

    # Corrupt / truncated header
    with pytest.raises(InvalidPhotoError):
        store.ingest_photo("C0", image_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 5)

    # Oversized image
    with pytest.raises(InvalidPhotoError, match="exceeds maximum"):
        store.ingest_photo("C0", image_bytes=create_valid_png(10, 10) + b"\x00" * 600)

    # Missing file path
    with pytest.raises(InvalidPhotoError, match="not found"):
        store.ingest_photo("C0", source_path=tmp_path / "nonexistent.png")

    # Path traversal in case_id
    with pytest.raises(IntegrityError, match="Path traversal"):
        store.ingest_photo("../evil_case", image_bytes=create_valid_png(10, 10))

    with pytest.raises(IntegrityError, match="Path traversal"):
        store.ingest_photo("case/with/slashes", image_bytes=create_valid_png(10, 10))


def test_monotonic_id_persistence_and_process_restarts(tmp_path: Path) -> None:
    # First process session
    store1 = YoloCaseStore(base_dir=tmp_path)
    p1 = store1.ingest_photo("C1", image_bytes=create_valid_png(10, 10))
    p2 = store1.ingest_photo("C1", image_bytes=create_valid_bmp(10, 10))
    assert p1.photo_id == "P1"
    assert p2.photo_id == "P2"

    d1_id, d1_ref = store1.allocate_detection_ref("C1", "P1")
    d2_id, d2_ref = store1.allocate_detection_ref("C1", "P1")
    d3_id, d3_ref = store1.allocate_detection_ref("C1", "P2")  # photo-scoped
    assert (d1_id, d1_ref) == ("d1", "photos.P1.d1")
    assert (d2_id, d2_ref) == ("d2", "photos.P1.d2")
    assert (d3_id, d3_ref) == ("d1", "photos.P2.d1")

    run1 = store1.allocate_run_id("C1")
    assert run1 == "RUN001"

    ev1_id, ev1_ref = store1.allocate_evidence_id("C1")
    assert (ev1_id, ev1_ref) == ("E1", "evidence.E1")

    # Second process session (simulating restart against same base_dir)
    store2 = YoloCaseStore(base_dir=tmp_path)
    p3 = store2.ingest_photo("C1", image_bytes=create_valid_jpeg(10, 10))
    assert p3.photo_id == "P3"

    next_p1_det_id, next_p1_det_ref = store2.allocate_detection_ref("C1", "P1")
    next_p2_det_id, next_p2_det_ref = store2.allocate_detection_ref("C1", "P2")
    assert (next_p1_det_id, next_p1_det_ref) == ("d3", "photos.P1.d3")
    assert (next_p2_det_id, next_p2_det_ref) == ("d2", "photos.P2.d2")

    run2 = store2.allocate_run_id("C1")
    assert run2 == "RUN002"

    ev2_id, ev2_ref = store2.allocate_evidence_id("C1")
    assert (ev2_id, ev2_ref) == ("E2", "evidence.E2")


def test_candidate_disposition_update_and_audit_history(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path)
    cand = DetectionCandidate(
        det_id="d1",
        ref="photos.P1.d1",
        photo_id="P1",
        run_id="RUN001",
        class_id=42,
        class_name="firearm",
        confidence=0.95,
        bbox_xyxy=(50.0, 60.0, 200.0, 300.0),
        image_width=800,
        image_height=600,
    )
    store.save_candidates("C2", [cand])

    # 1. Confirm candidate
    c_conf = store.update_candidate_disposition("C2", "photos.P1.d1", disposition="confirmed", reviewer_id="agent1")
    assert c_conf.disposition == "confirmed"
    assert c_conf.class_name == "firearm"  # immutable raw field

    # 2. Dismiss without reason -> error
    with pytest.raises(InvalidTransitionError):
        store.update_candidate_disposition("C2", "photos.P1.d1", disposition="dismissed", dismissal_reason="")

    # 3. Dismiss with reason
    c_dism = store.update_candidate_disposition(
        "C2",
        "photos.P1.d1",
        disposition="dismissed",
        dismissal_reason="Training replica prop",
        reviewer_id="agent2",
    )
    assert c_dism.disposition == "dismissed"
    assert c_dism.dismissal_reason == "Training replica prop"

    # Verify review events audit log
    events = store.list_review_events("C2")
    assert len(events) == 2
    assert events[0].event_id == "REV001"
    assert events[0].action == "confirmed"
    assert events[1].event_id == "REV002"
    assert events[1].resulting_disposition == "dismissed"
    assert events[1].reason == "Training replica prop"

    # Corrupt line in reviews.jsonl raises StorageError
    audit_file = tmp_path / "C2" / "audit" / "reviews.jsonl"
    with audit_file.open("a", encoding="utf-8") as f:
        f.write("corrupted JSON content\n")

    with pytest.raises(StorageError, match="Corrupted review log"):
        store.list_review_events("C2")


def test_evidence_events_audit(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path)
    ev = EvidenceRecord(
        evidence_id="E1",
        ref="evidence.E1",
        case_id="C3",
        label="Pocket Watch",
        description="Gold pocket watch",
        creation_source="manual",
    )
    store.save_evidence("C3", ev)

    events = store.list_evidence_events("C3")
    assert len(events) == 1
    assert events[0].event_id == "EVD001"
    assert events[0].action == "created"

    # Corrupted evidence log
    ev_file = tmp_path / "C3" / "audit" / "evidence_events.jsonl"
    with ev_file.open("a", encoding="utf-8") as f:
        f.write("corrupted event\n")

    with pytest.raises(StorageError, match="Corrupted evidence event"):
        store.list_evidence_events("C3")


# ==============================================================================
# Stage Y2: Detector Backend & Configuration Tests
# ==============================================================================

def test_detector_config_validation() -> None:
    # Valid default config
    cfg = DetectorConfig()
    assert cfg.confidence_threshold == 0.35
    assert cfg.device == "auto"

    # Valid devices
    for d in ("auto", "cpu", "cuda", "mps", "cuda:0", "cuda:1"):
        assert DetectorConfig(device=d).device == d

    # Invalid device
    with pytest.raises(ValueError, match="Invalid device"):
        DetectorConfig(device="tpu")

    # Invalid thresholds
    with pytest.raises(ValueError):
        DetectorConfig(confidence_threshold=0.0)
    with pytest.raises(ValueError):
        DetectorConfig(confidence_threshold=1.5)
    with pytest.raises(ValueError):
        DetectorConfig(iou_threshold=-0.1)
    with pytest.raises(ValueError):
        DetectorConfig(image_size=0)
    with pytest.raises(ValueError):
        DetectorConfig(max_candidates=-5)


def test_stub_detector_backend_operations(tmp_path: Path) -> None:
    test_img = tmp_path / "test.png"
    test_img.write_bytes(create_valid_png(64, 64))

    # Pre-configured predictions
    p1 = RawPrediction(class_id=0, class_name="gun", confidence=0.90, bbox_xyxy=(10.0, 10.0, 50.0, 50.0))
    p2 = RawPrediction(class_id=1, class_name="knife", confidence=0.40, bbox_xyxy=(20.0, 20.0, 60.0, 60.0))
    p3 = RawPrediction(class_id=2, class_name="phone", confidence=0.20, bbox_xyxy=(5.0, 5.0, 25.0, 25.0))

    backend = StubDetectorBackend(predictions=[p1, p2, p3])
    assert backend.is_loaded is False

    # Auto-loads on detect + applies confidence filter (0.35 drops p3)
    out = backend.detect(test_img)
    assert backend.is_loaded is True
    assert len(out.predictions) == 2
    assert out.predictions[0].class_name == "gun"
    assert out.predictions[1].class_name == "knife"
    assert out.truncated is False
    assert out.provenance.built_in_nms is True

    # Truncation handling
    cfg_trunc = DetectorConfig(confidence_threshold=0.10, max_candidates=2)
    out_trunc = backend.detect(test_img, config=cfg_trunc)
    assert len(out_trunc.predictions) == 2
    assert out_trunc.raw_prediction_count == 3
    assert out_trunc.truncated is True
    assert "exceeded max_candidates" in (out_trunc.truncation_warning or "")

    # Missing image
    with pytest.raises(DetectorError, match="Image file not found"):
        backend.detect(tmp_path / "nonexistent.png")

    # Fail on load
    fail_load_backend = StubDetectorBackend(fail_on_load=RuntimeError("GPU load error"))
    with pytest.raises(RuntimeError, match="GPU load error"):
        fail_load_backend.load()

    # Fail on detect
    fail_detect_backend = StubDetectorBackend(fail_on_detect=RuntimeError("Inference OOM"))
    with pytest.raises(RuntimeError, match="Inference OOM"):
        fail_detect_backend.detect(test_img)


def test_ultralytics_backend_missing_dependency() -> None:
    # Loader that raises ImportError simulates missing ultralytics
    def mock_missing_loader() -> Any:
        raise ImportError("No module named 'ultralytics'")

    backend = UltralyticsYOLOBackend(_module_loader=mock_missing_loader)
    with pytest.raises(DetectorDependencyError, match="Ultralytics package is not available"):
        backend.load()


def test_ultralytics_backend_mocked_inference(tmp_path: Path) -> None:
    test_img = tmp_path / "photo.jpg"
    test_img.write_bytes(create_valid_jpeg(100, 100))

    # Mock YOLO result and model
    class MockBoxes:
        def __init__(self, xyxy: list[list[float]], conf: list[float], cls: list[float]) -> None:
            self.xyxy = xyxy
            self.conf = conf
            self.cls = cls

    class MockResult:
        def __init__(self) -> None:
            self.boxes = MockBoxes(
                xyxy=[[10.0, 10.0, 40.0, 40.0], [50.0, 50.0, 90.0, 90.0]],
                conf=[0.92, 0.75],
                cls=[0.0, 1.0],
            )
            self.names = {0: "person", 1: "backpack"}

    class MockYOLO:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def predict(self, **kwargs: Any) -> list[Any]:
            return [MockResult()]

    class MockUltralyticsModule:
        __version__ = "8.1.0"
        YOLO = MockYOLO

    backend = UltralyticsYOLOBackend(
        model_name="yolov8n.pt",
        _module_loader=lambda: MockUltralyticsModule(),
    )

    out = backend.detect(test_img)
    assert backend.is_loaded is True
    assert len(out.predictions) == 2
    assert out.predictions[0].class_name == "person"
    assert out.predictions[0].confidence == 0.92
    assert out.predictions[1].class_name == "backpack"
    assert out.provenance.model_version == "8.1.0"
    assert out.provenance.built_in_nms is True


def test_ultralytics_backend_error_handling(tmp_path: Path) -> None:
    test_img = tmp_path / "photo.jpg"
    test_img.write_bytes(create_valid_jpeg(100, 100))

    # Model load failure
    class FailingLoadYOLO:
        def __init__(self, model_name: str) -> None:
            raise RuntimeError("Corrupt weights checkpoint")

    class FailingLoadModule:
        __version__ = "8.1.0"
        YOLO = FailingLoadYOLO

    backend_fail_load = UltralyticsYOLOBackend(_module_loader=lambda: FailingLoadModule())
    with pytest.raises(DetectorError, match="Failed to load YOLO model"):
        backend_fail_load.load()

    # Inference exception
    class FailingPredictYOLO:
        def __init__(self, model_name: str) -> None:
            pass

        def predict(self, **kwargs: Any) -> list[Any]:
            raise RuntimeError("CUDA out of memory")

    class FailingPredictModule:
        __version__ = "8.1.0"
        YOLO = FailingPredictYOLO

    backend_fail_predict = UltralyticsYOLOBackend(_module_loader=lambda: FailingPredictModule())
    with pytest.raises(DetectorError, match="YOLO inference failed"):
        backend_fail_predict.detect(test_img)


def test_store_get_and_list_photos_and_missing_record(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path)
    p = store.ingest_photo("C4", image_bytes=create_valid_png(12, 12), source_filename="img.png")
    assert store.get_photo("C4", "P1").photo_id == "P1"
    assert store.get_photo("C4", "photos.P1").photo_id == "P1"
    assert len(store.list_photos("C4")) == 1

    with pytest.raises(RecordNotFoundError, match="not found"):
        store.get_photo("C4", "P999")


def test_store_detection_runs_persistence(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path)
    run1 = DetectionRun(
        run_id="RUN001",
        photo_id="P1",
        case_id="C5",
        model_name="yolov8n.pt",
        model_version="8.0.0",
        weights_identifier="hash1",
        confidence_threshold=0.35,
        iou_threshold=0.50,
        image_size=640,
        device="cpu",
        executed_at="2026-11-22T00:00:00Z",
        status="completed",
    )
    store.save_detection_run("C5", run1)
    runs = store.list_detection_runs("C5")
    assert len(runs) == 1
    assert runs[0].run_id == "RUN001"

    # Update run
    run1_updated = DetectionRun(
        run_id="RUN001",
        photo_id="P1",
        case_id="C5",
        model_name="yolov8n.pt",
        model_version="8.0.0",
        weights_identifier="hash1",
        confidence_threshold=0.35,
        iou_threshold=0.50,
        image_size=640,
        device="cpu",
        executed_at="2026-11-22T00:00:00Z",
        status="completed",
        preview_path="photos/previews/RUN001_preview.jpg",
    )
    store.save_detection_run("C5", run1_updated)
    runs_after = store.list_detection_runs("C5")
    assert len(runs_after) == 1
    assert runs_after[0].preview_path == "photos/previews/RUN001_preview.jpg"


def test_store_candidate_filtering(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path)
    c1 = DetectionCandidate(
        det_id="d1",
        ref="photos.P1.d1",
        photo_id="P1",
        run_id="RUN001",
        class_id=0,
        class_name="gun",
        confidence=0.8,
        bbox_xyxy=(10.0, 10.0, 50.0, 50.0),
        image_width=100,
        image_height=100,
    )
    c2 = DetectionCandidate(
        det_id="d1",
        ref="photos.P2.d1",
        photo_id="P2",
        run_id="RUN002",
        class_id=1,
        class_name="knife",
        confidence=0.7,
        bbox_xyxy=(20.0, 20.0, 60.0, 60.0),
        image_width=100,
        image_height=100,
    )
    store.save_candidates("C6", [c1, c2])

    assert len(store.list_candidates("C6", photo_id="P1")) == 1
    assert len(store.list_candidates("C6", run_id="RUN002")) == 1
    assert len(store.list_candidates("C6")) == 2

    assert store.get_candidate("C6", "photos.P1.d1").det_id == "d1"
    with pytest.raises(RecordNotFoundError):
        store.get_candidate("C6", "photos.P1.d99")


def test_store_evidence_retrieval_and_missing(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path)
    ev = EvidenceRecord(
        evidence_id="E1",
        ref="evidence.E1",
        case_id="C7",
        label="Shell casing",
        description="9mm casing near door",
        creation_source="manual",
    )
    store.save_evidence("C7", ev)
    assert store.get_evidence("C7", "E1").label == "Shell casing"
    assert store.get_evidence("C7", "evidence.E1").label == "Shell casing"

    with pytest.raises(RecordNotFoundError):
        store.get_evidence("C7", "E99")


def test_stub_backend_prediction_callback_and_dict(tmp_path: Path) -> None:
    test_img = tmp_path / "img_test.png"
    test_img.write_bytes(create_valid_png(16, 16))

    pred = RawPrediction(class_id=5, class_name="cup", confidence=0.75, bbox_xyxy=(5.0, 5.0, 15.0, 15.0))

    # Dict lookup
    backend_dict = StubDetectorBackend(predictions={"img_test.png": [pred]})
    out = backend_dict.detect(test_img)
    assert len(out.predictions) == 1

    # Callable
    backend_callable = StubDetectorBackend(predictions=lambda p: [pred])
    out_call = backend_callable.detect(test_img)
    assert len(out_call.predictions) == 1

    # Invalid object in predictions
    backend_invalid = StubDetectorBackend(predictions=[{"not": "a RawPrediction"}])  # type: ignore[list-item]
    with pytest.raises(DetectorError, match="must be RawPrediction"):
        backend_invalid.detect(test_img)


def test_stub_backend_empty_predictions(tmp_path: Path) -> None:
    test_img = tmp_path / "empty.png"
    test_img.write_bytes(create_valid_png(16, 16))

    backend = StubDetectorBackend(predictions=[])
    out = backend.detect(test_img)
    assert len(out.predictions) == 0
    assert out.raw_prediction_count == 0
    assert out.truncated is False
    assert out.truncation_warning is None


def test_ultralytics_backend_empty_results_and_malformed_boxes(tmp_path: Path) -> None:
    test_img = tmp_path / "photo.png"
    test_img.write_bytes(create_valid_png(32, 32))

    # Empty results
    class EmptyPredictYOLO:
        def __init__(self, model_name: str) -> None:
            pass
        def predict(self, **kwargs: Any) -> list[Any]:
            return []

    class EmptyMod:
        __version__ = "8.1.0"
        YOLO = EmptyPredictYOLO

    backend_empty = UltralyticsYOLOBackend(_module_loader=lambda: EmptyMod())
    out_empty = backend_empty.detect(test_img)
    assert len(out_empty.predictions) == 0

    # Malformed boxes
    class MalformedPredictYOLO:
        def __init__(self, model_name: str) -> None:
            pass
        def predict(self, **kwargs: Any) -> list[Any]:
            class BadResult:
                boxes = "not a boxes object"
            return [BadResult()]

    class MalformedMod:
        __version__ = "8.1.0"
        YOLO = MalformedPredictYOLO

    backend_malformed = UltralyticsYOLOBackend(_module_loader=lambda: MalformedMod())
    with pytest.raises(DetectorError, match="Malformed YOLO inference result"):
        backend_malformed.detect(test_img)


def test_ultralytics_backend_local_weights_sha256_provenance(tmp_path: Path) -> None:
    test_img = tmp_path / "test_scene.png"
    test_img.write_bytes(create_valid_png(16, 16))

    weights_file = tmp_path / "custom_weights.pt"
    weights_content = b"fake-model-weights-bytes-123456"
    weights_file.write_bytes(weights_content)
    expected_hash = hashlib.sha256(weights_content).hexdigest()

    class DummyResult:
        boxes = None
        names = {}

    class DummyYOLO:
        def __init__(self, model_name: str) -> None:
            pass
        def predict(self, **kwargs: Any) -> list[Any]:
            return [DummyResult()]

    class DummyMod:
        __version__ = "8.2.0"
        YOLO = DummyYOLO

    backend = UltralyticsYOLOBackend(
        model_name=str(weights_file),
        _module_loader=lambda: DummyMod(),
    )
    out = backend.detect(test_img)
    assert out.provenance.weights_identifier == expected_hash
    assert out.provenance.model_name == str(weights_file)


# ==============================================================================
# Stage Y3: EXIF Orientation, Letterbox Transforms & Preview Rendering Tests
# ==============================================================================

def create_jpeg_with_exif(width: int = 16, height: int = 16, orientation: int = 1, endian: str = "II") -> bytes:
    """Generate a minimal valid JPEG image in-memory with APP1 Exif orientation tag."""
    soi = b"\xff\xd8"

    fmt_prefix = "<" if endian == "II" else ">"
    endian_bytes = b"II" if endian == "II" else b"MM"

    # TIFF Header (8 bytes): endian(2), magic=42(2), ifd0_offset=8(4)
    tiff_header = endian_bytes + struct.pack(fmt_prefix + "HI", 42, 8)

    # IFD0: num_entries(2)=1, then 12-byte entry: tag=0x0112(2), type=3(2), count=1(4), val=orientation(2), pad=0(2)
    # plus next_ifd_offset=0(4)
    ifd0_entry = struct.pack(fmt_prefix + "HHIHH", 0x0112, 3, 1, orientation, 0)
    ifd0 = struct.pack(fmt_prefix + "H", 1) + ifd0_entry + struct.pack(fmt_prefix + "I", 0)

    exif_payload = b"Exif\x00\x00" + tiff_header + ifd0
    app1_seg_len = 2 + len(exif_payload)
    app1 = b"\xff\xe1" + struct.pack(">H", app1_seg_len) + exif_payload

    # SOF0 marker: len=11, precision=8, height, width, 1 component
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    eoi = b"\xff\xd9"
    return soi + app1 + sof0 + eoi


def test_exif_orientation_parsing() -> None:
    # Test Little-Endian (II) orientations 1, 3, 6, 8
    for ori in (1, 3, 6, 8):
        data_ii = create_jpeg_with_exif(100, 200, orientation=ori, endian="II")
        assert read_exif_orientation(data_ii) == ori

    # Test Big-Endian (MM) orientations 1, 3, 6, 8
    for ori in (1, 3, 6, 8):
        data_mm = create_jpeg_with_exif(100, 200, orientation=ori, endian="MM")
        assert read_exif_orientation(data_mm) == ori

    # Non-JPEG returns None
    assert read_exif_orientation(create_valid_png(16, 16)) is None
    assert read_exif_orientation(b"plain-text-not-an-image") is None

    # JPEG without EXIF APP1 returns None
    assert read_exif_orientation(create_valid_jpeg(16, 16)) is None

    # Test display dimensions in compute_letterbox_metadata
    meta_1 = compute_letterbox_metadata(raw_width=1920, raw_height=1080, target_size=640, exif_orientation=1)
    assert (meta_1.display_width, meta_1.display_height) == (1920, 1080)

    meta_3 = compute_letterbox_metadata(raw_width=1920, raw_height=1080, target_size=640, exif_orientation=3)
    assert (meta_3.display_width, meta_3.display_height) == (1920, 1080)

    # 6 and 8 swap width and height
    meta_6 = compute_letterbox_metadata(raw_width=1920, raw_height=1080, target_size=640, exif_orientation=6)
    assert (meta_6.display_width, meta_6.display_height) == (1080, 1920)

    meta_8 = compute_letterbox_metadata(raw_width=1920, raw_height=1080, target_size=640, exif_orientation=8)
    assert (meta_8.display_width, meta_8.display_height) == (1080, 1920)


def test_store_ingest_photo_with_exif_orientation(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path)
    jpeg_exif_bytes = create_jpeg_with_exif(64, 48, orientation=6, endian="II")
    expected_sha = hashlib.sha256(jpeg_exif_bytes).hexdigest()

    rec = store.ingest_photo("C10", image_bytes=jpeg_exif_bytes, source_filename="exif_test.jpg")
    assert rec.photo_id == "P1"
    assert rec.exif_orientation == 6
    assert rec.sha256 == expected_sha

    # Verify original file on disk is byte-for-byte identical
    stored_path = tmp_path / "C10" / rec.original_path
    assert stored_path.read_bytes() == jpeg_exif_bytes
    assert store.verify_photo_integrity("C10", "P1") is True


def test_letterbox_metadata_and_coordinate_reversal() -> None:
    # 1. Square image (640x640)
    meta_sq = compute_letterbox_metadata(640, 640, target_size=640)
    assert meta_sq.scale == 1.0
    assert (meta_sq.pad_x, meta_sq.pad_y) == (0.0, 0.0)
    assert meta_sq.letterboxed is False

    # 2. Landscape (1920x1080)
    meta_land = compute_letterbox_metadata(1920, 1080, target_size=640)
    assert meta_land.scale == pytest.approx(640.0 / 1920.0)
    assert meta_land.pad_x == 0.0
    assert meta_land.pad_y > 0.0
    assert meta_land.letterboxed is True

    # 3. Portrait (1080x1920)
    meta_port = compute_letterbox_metadata(1080, 1920, target_size=640)
    assert meta_port.scale == pytest.approx(640.0 / 1920.0)
    assert meta_port.pad_x > 0.0
    assert meta_port.pad_y == 0.0
    assert meta_port.letterboxed is True

    # 4. Extreme aspect (2000x200)
    meta_ext = compute_letterbox_metadata(2000, 200, target_size=640)
    assert meta_ext.scale == pytest.approx(640.0 / 2000.0)
    assert meta_ext.pad_y > 0.0

    # 5. Coordinate forward & reversal roundtrip on landscape
    orig_box = (100.0, 150.0, 400.0, 500.0)
    scale = meta_land.scale
    pad_x, pad_y = meta_land.pad_x, meta_land.pad_y

    inf_box = (
        orig_box[0] * scale + pad_x,
        orig_box[1] * scale + pad_y,
        orig_box[2] * scale + pad_x,
        orig_box[3] * scale + pad_y,
    )
    rev_box = reverse_letterbox_bbox(inf_box, meta_land)
    assert rev_box[0] == pytest.approx(orig_box[0], rel=1e-3)
    assert rev_box[1] == pytest.approx(orig_box[1], rel=1e-3)
    assert rev_box[2] == pytest.approx(orig_box[2], rel=1e-3)
    assert rev_box[3] == pytest.approx(orig_box[3], rel=1e-3)

    # 6. Boundary clipping
    out_of_bounds = (-50.0, -50.0, 700.0, 700.0)
    clipped = reverse_letterbox_bbox(out_of_bounds, meta_land)
    assert clipped[0] == 0.0
    assert clipped[1] == 0.0
    assert clipped[2] == meta_land.display_width
    assert clipped[3] == meta_land.display_height

    # 7. Invalid coordinates rejection
    with pytest.raises(DetectorError, match="Non-finite"):
        reverse_letterbox_bbox((float("nan"), 10.0, 50.0, 50.0), meta_land)

    with pytest.raises(DetectorError, match="Non-finite"):
        reverse_letterbox_bbox((10.0, 10.0, float("inf"), 50.0), meta_land)

    # Zero-area / collapsed box
    with pytest.raises(DetectorError, match="Collapsed or zero-area"):
        reverse_letterbox_bbox((100.0, 100.0, 100.0, 100.0), meta_land)


def test_preview_rendering_immutability_and_fallback(tmp_path: Path) -> None:
    orig_file = tmp_path / "original_photo.png"
    orig_bytes = create_valid_png(100, 80)
    orig_file.write_bytes(orig_bytes)
    sha_orig = hashlib.sha256(orig_bytes).hexdigest()

    # 1. Refuse overwrite of original file
    with pytest.raises(IntegrityError, match="cannot overwrite original photo"):
        render_annotated_preview(orig_file, orig_file, [])

    # 2. 0-detection preview writes separate file and leaves original unchanged
    preview_file_empty = tmp_path / "preview_empty.png"
    res_empty = render_annotated_preview(orig_file, preview_file_empty, [], _pil_loader=lambda: None)
    assert res_empty.candidate_count == 0
    assert res_empty.rendered_with == "stdlib_copy"
    assert preview_file_empty.is_file()
    assert hashlib.sha256(orig_file.read_bytes()).hexdigest() == sha_orig

    # 3. Multi-detection preview with unreviewed, confirmed, dismissed candidates
    c1 = DetectionCandidate(
        det_id="d1",
        ref="photos.P1.d1",
        photo_id="P1",
        run_id="RUN001",
        class_id=0,
        class_name="gun",
        confidence=0.91,
        bbox_xyxy=(10.0, 10.0, 40.0, 40.0),
        image_width=100,
        image_height=80,
        disposition="unreviewed",
    )
    c2 = DetectionCandidate(
        det_id="d2",
        ref="photos.P1.d2",
        photo_id="P1",
        run_id="RUN001",
        class_id=1,
        class_name="knife",
        confidence=0.85,
        bbox_xyxy=(50.0, 20.0, 90.0, 60.0),
        image_width=100,
        image_height=80,
        disposition="confirmed",
    )
    c3 = DetectionCandidate(
        det_id="d3",
        ref="photos.P1.d3",
        photo_id="P1",
        run_id="RUN001",
        class_id=2,
        class_name="bottle",
        confidence=0.60,
        bbox_xyxy=(20.0, 50.0, 40.0, 75.0),
        image_width=100,
        image_height=80,
        disposition="dismissed",
        dismissal_reason="Irrelevant trash",
    )

    preview_file_annotated = tmp_path / "preview_annotated.png"
    res_multi = render_annotated_preview(
        orig_file,
        preview_file_annotated,
        [c1, c2, c3],
        _pil_loader=lambda: None,
    )
    assert res_multi.candidate_count == 3
    assert res_multi.rendered_with == "stdlib_png"
    assert preview_file_annotated.is_file()

    # Original SHA-256 remains completely untouched
    assert hashlib.sha256(orig_file.read_bytes()).hexdigest() == sha_orig

    # Generated preview is a valid PNG
    preview_bytes = preview_file_annotated.read_bytes()
    assert preview_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # Re-rendering (e.g. after disposition change) commits cleanly
    c1_confirmed = DetectionCandidate(
        det_id="d1",
        ref="photos.P1.d1",
        photo_id="P1",
        run_id="RUN001",
        class_id=0,
        class_name="gun",
        confidence=0.91,
        bbox_xyxy=(10.0, 10.0, 40.0, 40.0),
        image_width=100,
        image_height=80,
        disposition="confirmed",
    )
    res_updated = render_annotated_preview(
        orig_file,
        preview_file_annotated,
        [c1_confirmed, c2, c3],
        _pil_loader=lambda: None,
    )
    assert res_updated.candidate_count == 3
    assert hashlib.sha256(orig_file.read_bytes()).hexdigest() == sha_orig


def test_preview_rendering_mocked_pillow(tmp_path: Path) -> None:
    orig_file = tmp_path / "photo_pillow.jpg"
    orig_file.write_bytes(create_valid_jpeg(80, 80))
    preview_out = tmp_path / "photo_pillow_preview.jpg"

    # Track Pillow mock method calls
    drawn_rectangles: list[dict[str, Any]] = []
    transpose_called = []

    class MockImageDrawInstance:
        def rectangle(self, xy: list[float], outline: tuple[int, int, int], width: int = 1) -> None:
            drawn_rectangles.append({"xy": xy, "outline": outline, "width": width})

        def text(self, xy: tuple[float, float], text: str, fill: tuple[int, int, int]) -> None:
            pass

    class MockImageInstance:
        mode = "RGB"
        width = 80
        height = 80

        def convert(self, mode: str) -> MockImageInstance:
            return self

        def save(self, fp: Any, format: str) -> None:
            if hasattr(fp, "write"):
                fp.write(b"mocked-pillow-jpeg-data")

    class MockImageOps:
        @staticmethod
        def exif_transpose(img: Any) -> Any:
            transpose_called.append(True)
            return img

    class MockImageDraw:
        @staticmethod
        def Draw(img: Any) -> MockImageDrawInstance:
            return MockImageDrawInstance()

    class MockImage:
        @staticmethod
        def open(fp: Any) -> MockImageInstance:
            return MockImageInstance()

    class MockPILModule:
        Image = MockImage
        ImageDraw = MockImageDraw
        ImageOps = MockImageOps

    cand = DetectionCandidate(
        det_id="d1",
        ref="photos.P1.d1",
        photo_id="P1",
        run_id="RUN001",
        class_id=0,
        class_name="firearm",
        confidence=0.95,
        bbox_xyxy=(10.0, 10.0, 60.0, 60.0),
        image_width=80,
        image_height=80,
        disposition="confirmed",
    )

    result = render_annotated_preview(
        orig_file,
        preview_out,
        [cand],
        _pil_loader=lambda: MockPILModule,
    )

    assert result.rendered_with == "pillow"
    assert len(transpose_called) == 1
    assert len(drawn_rectangles) == 1
    assert drawn_rectangles[0]["outline"] == DISPOSITION_COLORS["confirmed"]
    assert preview_out.read_bytes() == b"mocked-pillow-jpeg-data"


# ==============================================================================
# Stage Y4: Detection Orchestration & Candidate Lifecycle Tests
# ==============================================================================

def test_service_end_to_end_orchestration(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    source_img = tmp_path / "scene_64x48.png"
    img_bytes = create_valid_png(64, 48)
    source_img.write_bytes(img_bytes)
    expected_sha = hashlib.sha256(img_bytes).hexdigest()

    preds = [
        RawPrediction(class_id=0, class_name="knife", confidence=0.88, bbox_xyxy=(10.0, 12.0, 40.0, 36.0)),
        RawPrediction(class_id=1, class_name="phone", confidence=0.62, bbox_xyxy=(42.0, 8.0, 60.0, 30.0)),
    ]
    detector = StubDetectorBackend(predictions=preds)
    service = YoloDetectionService(store, detector, _pil_loader=lambda: None)

    photo = service.register_photo("CASE_Y4_01", source_img, ingested_by="det_01")
    assert photo.photo_id == "P1"
    assert photo.sha256 == expected_sha

    res = service.run_detection("CASE_Y4_01", "P1")
    assert isinstance(res, DetectionRunResult)
    assert res.run.run_id == "RUN001"
    assert res.run.status == "completed"
    assert res.run.truncated is False
    assert res.run.preview_path == "photos/previews/P1_RUN001_annotated.png"
    assert res.warnings == []

    assert len(res.candidates) == 2
    assert [c.ref for c in res.candidates] == ["photos.P1.d1", "photos.P1.d2"]
    assert all(c.disposition == "unreviewed" for c in res.candidates)
    assert all(c.dismissal_reason is None for c in res.candidates)
    assert all(c.normalized_bbox_xyxy is not None for c in res.candidates)

    assert res.preview is not None
    preview_abs = tmp_path / "cases" / "CASE_Y4_01" / res.run.preview_path
    assert preview_abs.is_file()
    assert res.preview.original_sha256 == expected_sha
    assert store.verify_photo_integrity("CASE_Y4_01", "P1") is True


def test_service_zero_detection_completed_run(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    source_img = tmp_path / "empty_64x48.png"
    source_img.write_bytes(create_valid_png(64, 48))

    detector = StubDetectorBackend(predictions=[])
    service = YoloDetectionService(store, detector, _pil_loader=lambda: None)
    service.register_photo("CASE_Y4_EMPTY", source_img)

    res = service.run_detection("CASE_Y4_EMPTY", "P1")
    assert res.run.status == "completed"
    assert res.run.error_message is None
    assert res.candidates == []
    assert res.preview is not None
    assert res.preview.candidate_count == 0
    assert (tmp_path / "cases" / "CASE_Y4_EMPTY" / (res.run.preview_path or "")).is_file()


def test_service_failed_detection_runs_distinguished_from_empty(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    source_img = tmp_path / "fail_64x48.png"
    source_img.write_bytes(create_valid_png(64, 48))

    # 1. DetectorError during detect
    service_err = YoloDetectionService(
        store,
        StubDetectorBackend(fail_on_detect=DetectorError("Inference timeout")),
        _pil_loader=lambda: None,
    )
    service_err.register_photo("CASE_Y4_FAIL", source_img)

    with pytest.raises(DetectorError, match="Inference timeout"):
        service_err.run_detection("CASE_Y4_FAIL", "P1")

    # 2. DetectorDependencyError during load
    service_dep = YoloDetectionService(
        store,
        UltralyticsYOLOBackend(_module_loader=lambda: (_ for _ in ()).throw(ImportError("no ultralytics"))),
        _pil_loader=lambda: None,
    )
    with pytest.raises(DetectorDependencyError):
        service_dep.run_detection("CASE_Y4_FAIL", "P1")

    runs = service_err.list_detection_runs("CASE_Y4_FAIL", photo_id="P1")
    assert len(runs) == 2
    assert all(r.status == "failed" for r in runs)
    assert runs[0].error_message == "Inference timeout"
    assert runs[1].error_message is not None
    assert service_err.list_candidates("CASE_Y4_FAIL", photo_id="P1") == []


def test_service_rerun_preserves_earlier_runs_and_candidates(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    source_img = tmp_path / "rerun_64x48.png"
    source_img.write_bytes(create_valid_png(64, 48))

    preds_r1 = [
        RawPrediction(class_id=0, class_name="knife", confidence=0.80, bbox_xyxy=(5.0, 5.0, 20.0, 20.0)),
        RawPrediction(class_id=1, class_name="cup", confidence=0.70, bbox_xyxy=(25.0, 10.0, 40.0, 30.0)),
    ]
    preds_r2 = [
        RawPrediction(class_id=2, class_name="wallet", confidence=0.90, bbox_xyxy=(30.0, 20.0, 55.0, 44.0)),
    ]

    det = StubDetectorBackend(predictions=preds_r1)
    service = YoloDetectionService(store, det, _pil_loader=lambda: None)
    service.register_photo("CASE_Y4_RERUN", source_img)

    res1 = service.run_detection("CASE_Y4_RERUN", "P1")
    assert res1.run.run_id == "RUN001"
    assert [c.ref for c in res1.candidates] == ["photos.P1.d1", "photos.P1.d2"]

    # Rerun with different predictions
    det.predictions = preds_r2
    res2 = service.run_detection("CASE_Y4_RERUN", "P1")
    assert res2.run.run_id == "RUN002"
    assert [c.ref for c in res2.candidates] == ["photos.P1.d3"]

    # Both runs, all 3 candidates, and both previews remain intact
    all_runs = service.list_detection_runs("CASE_Y4_RERUN", photo_id="P1")
    assert [r.run_id for r in all_runs] == ["RUN001", "RUN002"]
    all_cands = service.list_candidates("CASE_Y4_RERUN", photo_id="P1")
    assert [c.ref for c in all_cands] == ["photos.P1.d1", "photos.P1.d2", "photos.P1.d3"]
    assert (tmp_path / "cases" / "CASE_Y4_RERUN" / (res1.run.preview_path or "")).is_file()
    assert (tmp_path / "cases" / "CASE_Y4_RERUN" / (res2.run.preview_path or "")).is_file()


def test_service_truncation_and_oob_prediction_warnings(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    source_img = tmp_path / "trunc_64x48.png"
    source_img.write_bytes(create_valid_png(64, 48))

    preds = [
        RawPrediction(class_id=0, class_name="item_a", confidence=0.95, bbox_xyxy=(5.0, 5.0, 20.0, 20.0)),
        RawPrediction(class_id=1, class_name="item_oob", confidence=0.90, bbox_xyxy=(100.0, 100.0, 150.0, 150.0)),
        RawPrediction(class_id=2, class_name="item_b", confidence=0.80, bbox_xyxy=(10.0, 10.0, 30.0, 30.0)),
    ]
    det = StubDetectorBackend(predictions=preds)
    cfg = DetectorConfig(confidence_threshold=0.5, max_candidates=2)
    service = YoloDetectionService(store, det, default_config=cfg, _pil_loader=lambda: None)
    service.register_photo("CASE_Y4_TRUNC", source_img)

    res = service.run_detection("CASE_Y4_TRUNC", "P1")
    assert res.run.truncated is True
    assert res.run.truncation_warning is not None
    # item_a kept, item_oob skipped due to OOB (clipped to 64x48 -> zero area), item_b truncated by max_candidates=2
    assert len(res.candidates) == 1
    assert res.candidates[0].class_name == "item_a"
    assert any("Skipped out-of-bounds" in w for w in res.warnings)
    assert any("exceeded max_candidates" in w for w in res.warnings)


def test_service_tampered_original_blocks_inference(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    source_img = tmp_path / "tamper_64x48.png"
    source_img.write_bytes(create_valid_png(64, 48))

    call_count = 0

    def counting_preds(_p: Path) -> list[RawPrediction]:
        nonlocal call_count
        call_count += 1
        return []

    service = YoloDetectionService(store, StubDetectorBackend(predictions=counting_preds), _pil_loader=lambda: None)
    photo = service.register_photo("CASE_Y4_TAMPER", source_img)

    # Corrupt stored original
    orig_file = tmp_path / "cases" / "CASE_Y4_TAMPER" / photo.original_path
    tampered = bytearray(orig_file.read_bytes())
    tampered[-3] ^= 0xFF
    orig_file.write_bytes(bytes(tampered))

    assert service.verify_case_photo_integrity("CASE_Y4_TAMPER") == {"P1": False}
    with pytest.raises(IntegrityError, match="Integrity verification failed"):
        service.run_detection("CASE_Y4_TAMPER", "P1")
    assert call_count == 0


def test_service_restart_recovery_and_regenerate_preview(tmp_path: Path) -> None:
    base_dir = tmp_path / "cases"
    source_img = tmp_path / "restart_64x48.png"
    source_img.write_bytes(create_valid_png(64, 48))

    store1 = YoloCaseStore(base_dir=base_dir)
    det1 = StubDetectorBackend(
        predictions=[RawPrediction(class_id=0, class_name="knife", confidence=0.91, bbox_xyxy=(8.0, 8.0, 32.0, 32.0))]
    )
    service1 = YoloDetectionService(store1, det1, _pil_loader=lambda: None)
    service1.register_photo("CASE_Y4_RESTART", source_img)
    res1 = service1.run_detection("CASE_Y4_RESTART", "P1", generate_preview=False)
    assert res1.preview is None
    assert res1.run.preview_path is None

    # Restart with fresh store and service instances
    store2 = YoloCaseStore(base_dir=base_dir)
    service2 = YoloDetectionService(store2, StubDetectorBackend(), _pil_loader=lambda: None)
    assert len(service2.list_photos("CASE_Y4_RESTART")) == 1
    assert len(service2.list_detection_runs("CASE_Y4_RESTART")) == 1
    assert len(service2.list_candidates("CASE_Y4_RESTART", disposition="unreviewed")) == 1
    assert service2.list_candidates("CASE_Y4_RESTART", disposition="confirmed") == []

    regen = service2.regenerate_preview("CASE_Y4_RESTART", "P1")
    assert regen.candidate_count == 1
    assert Path(regen.preview_path).is_file()
    updated_run = service2.list_detection_runs("CASE_Y4_RESTART", photo_id="P1")[0]
    assert updated_run.preview_path == "photos/previews/P1_RUN001_annotated.png"


# ==============================================================================
# Stage Y5: Investigator Review & Evidence Management Tests
# ==============================================================================

def test_service_confirm_and_dismiss_review(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    img_path = tmp_path / "rev_64x48.png"
    img_path.write_bytes(create_valid_png(64, 48))

    preds = [
        RawPrediction(class_id=0, class_name="knife", confidence=0.90, bbox_xyxy=(5.0, 5.0, 25.0, 25.0)),
        RawPrediction(class_id=1, class_name="glare", confidence=0.55, bbox_xyxy=(30.0, 10.0, 50.0, 30.0)),
        RawPrediction(class_id=2, class_name="shadow", confidence=0.45, bbox_xyxy=(10.0, 30.0, 25.0, 45.0)),
    ]
    service = YoloDetectionService(store, StubDetectorBackend(predictions=preds), _pil_loader=lambda: None)
    service.register_photo("CASE_Y5_REV", img_path)
    res = service.run_detection("CASE_Y5_REV", "P1")
    d1, d2, d3 = res.candidates

    # 1. Confirm d1
    conf_cand, conf_ev = service.confirm_detection("CASE_Y5_REV", d1.ref, reviewer_id="inv_01")
    assert conf_cand.disposition == "confirmed"
    assert conf_cand.dismissal_reason is None
    # Raw fields remain immutable
    assert (conf_cand.class_id, conf_cand.class_name, conf_cand.confidence, conf_cand.bbox_xyxy, conf_cand.run_id) == (
        d1.class_id, d1.class_name, d1.confidence, d1.bbox_xyxy, d1.run_id
    )
    assert conf_ev.action == "confirmed"
    assert conf_ev.previous_disposition == "unreviewed"
    assert conf_ev.resulting_disposition == "confirmed"

    # 2. Dismiss d2 with 1-char reason (valid, no arbitrary 10-char minimum)
    dism_cand, dism_ev = service.dismiss_detection("CASE_Y5_REV", d2.ref, "x", reviewer_id="inv_01")
    assert dism_cand.disposition == "dismissed"
    assert dism_cand.dismissal_reason == "x"
    assert dism_ev.action == "dismissed"
    assert dism_ev.reason == "x"

    # 3. Dismiss d3 with blank reason -> rejected
    with pytest.raises(InvalidTransitionError, match="non-empty"):
        service.dismiss_detection("CASE_Y5_REV", d3.ref, "   ")

    # 4. Direct re-confirm / re-dismiss on already-reviewed candidates -> rejected
    with pytest.raises(InvalidTransitionError, match="already|expected 'unreviewed'"):
        service.confirm_detection("CASE_Y5_REV", d1.ref)
    with pytest.raises(InvalidTransitionError, match="expected 'unreviewed'"):
        service.dismiss_detection("CASE_Y5_REV", d2.ref, "another reason")


def test_service_review_correction_and_unlink_guard(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    img_path = tmp_path / "corr_64x48.png"
    img_path.write_bytes(create_valid_png(64, 48))

    preds = [RawPrediction(class_id=0, class_name="gun", confidence=0.85, bbox_xyxy=(10.0, 10.0, 40.0, 40.0))]
    service = YoloDetectionService(store, StubDetectorBackend(predictions=preds), _pil_loader=lambda: None)
    service.register_photo("CASE_Y5_CORR", img_path)
    d1 = service.run_detection("CASE_Y5_CORR", "P1").candidates[0]

    # Cannot correct unreviewed
    with pytest.raises(InvalidTransitionError, match="unreviewed"):
        service.correct_review_decision("CASE_Y5_CORR", d1.ref, "confirmed")

    # Dismiss -> correct to confirmed -> promote -> blocked from dismissing until unlinked
    service.dismiss_detection("CASE_Y5_CORR", d1.ref, "blur")
    c_conf, ev_corr1 = service.correct_review_decision("CASE_Y5_CORR", d1.ref, "confirmed", reason="Actually clear")
    assert c_conf.disposition == "confirmed"
    assert ev_corr1.action == "corrected"
    assert ev_corr1.previous_disposition == "dismissed"
    assert ev_corr1.resulting_disposition == "confirmed"

    # Promote to evidence.E1
    ev_rec, _ = service.promote_detection_to_evidence("CASE_Y5_CORR", d1.ref, label="Handgun")
    assert ev_rec.ref == "evidence.E1"

    # Blocked from correcting to dismissed while linked to evidence
    with pytest.raises(InvalidTransitionError, match="linked to evidence"):
        service.correct_review_decision("CASE_Y5_CORR", d1.ref, "dismissed", reason="False positive")

    # Unlink first, then dismiss succeeds
    unlinked_ev, unlink_event = service.unlink_detection_from_evidence(
        "CASE_Y5_CORR", "E1", d1.ref, reason="Re-evaluated crop"
    )
    assert unlinked_ev.det_refs == []
    assert unlink_event.action == "unlinked_detection"
    assert unlink_event.details["reason"] == "Re-evaluated crop"

    c_dism, ev_corr2 = service.correct_review_decision(
        "CASE_Y5_CORR", d1.ref, "dismissed", reason="Confirmed reflection"
    )
    assert c_dism.disposition == "dismissed"
    assert ev_corr2.action == "corrected"

    # Append-only review history retains all 3 events
    history = service.list_review_history("CASE_Y5_CORR", detection_ref=d1.ref)
    assert [e.action for e in history] == ["dismissed", "corrected", "corrected"]


def test_service_promote_detection_and_duplicate_guard(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    img_path = tmp_path / "prom_64x48.png"
    img_path.write_bytes(create_valid_png(64, 48))

    preds = [
        RawPrediction(class_id=0, class_name="knife", confidence=0.92, bbox_xyxy=(5.0, 5.0, 20.0, 20.0)),
        RawPrediction(class_id=1, class_name="mug", confidence=0.60, bbox_xyxy=(25.0, 15.0, 45.0, 35.0)),
    ]
    service = YoloDetectionService(store, StubDetectorBackend(predictions=preds), _pil_loader=lambda: None)
    service.register_photo("CASE_Y5_PROM", img_path)
    d1, d2 = service.run_detection("CASE_Y5_PROM", "P1").candidates

    # Reject unreviewed and dismissed promotions
    with pytest.raises(InvalidTransitionError, match="confirmed"):
        service.promote_detection_to_evidence("CASE_Y5_PROM", d1.ref)

    service.dismiss_detection("CASE_Y5_PROM", d2.ref, "irrelevant")
    with pytest.raises(InvalidTransitionError, match="confirmed"):
        service.promote_detection_to_evidence("CASE_Y5_PROM", d2.ref)

    # Confirm and promote d1
    service.confirm_detection("CASE_Y5_PROM", d1.ref)
    ev, ev_event = service.promote_detection_to_evidence("CASE_Y5_PROM", d1.ref, description="Kitchen counter blade")
    assert ev.evidence_id == "E1"
    assert ev.label == "knife"
    assert ev.creation_source == "detection_promoted"
    assert ev.photo_refs == ["photos.P1"]
    assert ev.det_refs == [d1.ref]
    assert ev_event.action == "created"

    # Reject duplicate standalone promotion
    with pytest.raises(InvalidTransitionError, match="already linked"):
        service.promote_detection_to_evidence("CASE_Y5_PROM", d1.ref)


def test_service_multi_photo_and_multi_detection_linking(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    img1 = tmp_path / "p1.png"
    img2 = tmp_path / "p2.png"
    img3 = tmp_path / "p3.png"
    img4 = tmp_path / "p4.png"
    img1.write_bytes(create_valid_png(64, 48))
    img2.write_bytes(create_valid_png(65, 48))
    img3.write_bytes(create_valid_png(66, 48))
    img4.write_bytes(create_valid_png(67, 48))

    det = StubDetectorBackend(
        predictions=[RawPrediction(class_id=0, class_name="knife", confidence=0.88, bbox_xyxy=(5.0, 5.0, 25.0, 25.0))]
    )
    service = YoloDetectionService(store, det, _pil_loader=lambda: None)
    for p in (img1, img2, img3, img4):
        service.register_photo("CASE_Y5_MULTI", p)

    d1 = service.run_detection("CASE_Y5_MULTI", "P1").candidates[0]
    d2 = service.run_detection("CASE_Y5_MULTI", "P2").candidates[0]
    d3 = service.run_detection("CASE_Y5_MULTI", "P3").candidates[0]
    service.confirm_detection("CASE_Y5_MULTI", d1.ref)
    service.confirm_detection("CASE_Y5_MULTI", d2.ref)
    service.confirm_detection("CASE_Y5_MULTI", d3.ref)

    ev1, _ = service.promote_detection_to_evidence("CASE_Y5_MULTI", d1.ref, label="Shared Knife")
    ev1, link2_ev = service.link_detection_to_evidence("CASE_Y5_MULTI", ev1.evidence_id, d2.ref)
    ev1, link3_ev = service.promote_detection_to_evidence("CASE_Y5_MULTI", d3.ref, evidence_id="E1")

    assert ev1.photo_refs == ["photos.P1", "photos.P2", "photos.P3"]
    assert ev1.det_refs == [d1.ref, d2.ref, d3.ref]
    assert link2_ev.action == "linked_detection"
    assert link3_ev.action == "linked_detection"

    # Duplicate detection link and duplicate photo link rejected
    with pytest.raises(InvalidTransitionError, match="already linked"):
        service.link_detection_to_evidence("CASE_Y5_MULTI", "E1", d2.ref)
    with pytest.raises(InvalidTransitionError, match="already linked"):
        service.link_photo_to_evidence("CASE_Y5_MULTI", "E1", "P2")

    # Link P4 directly as photo context
    ev1, p4_ev = service.link_photo_to_evidence("CASE_Y5_MULTI", "E1", "photos.P4")
    assert ev1.photo_refs == ["photos.P1", "photos.P2", "photos.P3", "photos.P4"]
    assert p4_ev.action == "linked_photo"

    # Unlink requires non-empty reason
    with pytest.raises(InvalidTransitionError, match="non-empty reason"):
        service.unlink_detection_from_evidence("CASE_Y5_MULTI", "E1", d2.ref, reason="   ")


def test_service_manual_evidence_and_update_history_restart(tmp_path: Path) -> None:
    base_dir = tmp_path / "cases"
    store1 = YoloCaseStore(base_dir=base_dir)
    img1 = tmp_path / "man_64x48.png"
    img1.write_bytes(create_valid_png(64, 48))

    service1 = YoloDetectionService(store1, StubDetectorBackend(), _pil_loader=lambda: None)
    service1.register_photo("CASE_Y5_MAN", img1)

    # 1. Manual evidence with zero photos/detections
    ev_zero, ev_zero_event = service1.create_manual_evidence(
        "CASE_Y5_MAN", "Witness Statement Item", description="Reported missing watch"
    )
    assert ev_zero.evidence_id == "E1"
    assert ev_zero.creation_source == "manual"
    assert ev_zero.photo_refs == []
    assert ev_zero.det_refs == []
    assert ev_zero_event.action == "created"

    # 2. Manual evidence with deduplicated photo refs
    ev_photo, _ = service1.create_manual_evidence(
        "CASE_Y5_MAN", "Floor Stain", photo_refs=["P1", "photos.P1"]
    )
    assert ev_photo.evidence_id == "E2"
    assert ev_photo.photo_refs == ["photos.P1"]

    # 3. Missing photo rejected
    with pytest.raises(RecordNotFoundError):
        service1.create_manual_evidence("CASE_Y5_MAN", "Bad Ref", photo_refs=["P999"])

    # 4. Update evidence with audit event
    updated_ev, upd_event = service1.update_evidence(
        "CASE_Y5_MAN", "E1", label="Gold Watch", description="Verified serial number"
    )
    assert updated_ev.label == "Gold Watch"
    assert updated_ev.description == "Verified serial number"
    assert upd_event.action == "updated"
    assert upd_event.details["previous"]["label"] == "Witness Statement Item"
    assert upd_event.details["updated"]["label"] == "Gold Watch"

    # 5. Restart store and service, verify persistence & revision history
    store2 = YoloCaseStore(base_dir=base_dir)
    service2 = YoloDetectionService(store2, StubDetectorBackend(), _pil_loader=lambda: None)
    assert service2.get_evidence("CASE_Y5_MAN", "E1").label == "Gold Watch"
    assert len(service2.list_evidence("CASE_Y5_MAN")) == 2
    e1_history = service2.list_evidence_history("CASE_Y5_MAN", evidence_ref="evidence.E1")
    assert [e.action for e in e1_history] == ["created", "updated"]


# ==============================================================================
# Stage Y6: Case-Context Exporter & Frozen Module 1 Integration Tests
# ==============================================================================

def test_exporter_schema_validation_and_invalid_override(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    img1 = tmp_path / "p1.png"
    img2 = tmp_path / "p2.png"
    img3 = tmp_path / "p3.png"
    img1.write_bytes(create_valid_png(64, 48))
    img2.write_bytes(create_valid_png(65, 48))
    img3.write_bytes(create_valid_png(66, 48))

    det = StubDetectorBackend(
        predictions={
            "P1_original.png": [
                RawPrediction(class_id=0, class_name="knife", confidence=0.92, bbox_xyxy=(5.0, 5.0, 25.0, 25.0)),
                RawPrediction(class_id=1, class_name="bottle", confidence=0.65, bbox_xyxy=(30.0, 10.0, 50.0, 35.0)),
                RawPrediction(class_id=2, class_name="phone", confidence=0.50, bbox_xyxy=(10.0, 30.0, 25.0, 44.0)),
            ],
            "P2_original.png": [
                RawPrediction(class_id=0, class_name="knife", confidence=0.89, bbox_xyxy=(8.0, 8.0, 28.0, 28.0)),
            ],
            "P3_original.png": [],
        }
    )
    service = YoloDetectionService(store, det, _pil_loader=lambda: None)
    service.register_photo("CASE_Y6_01", img1, room="kitchen")
    service.register_photo("CASE_Y6_01", img2, room="kitchen")
    service.register_photo("CASE_Y6_01", img3)  # room=None -> never invented

    p1_cands = service.run_detection("CASE_Y6_01", "P1").candidates
    p2_cands = service.run_detection("CASE_Y6_01", "P2").candidates
    p3_res = service.run_detection("CASE_Y6_01", "P3")
    assert p3_res.candidates == []

    # Confirmed, dismissed, and unreviewed detections + multi-photo promoted + manual evidence
    service.confirm_detection("CASE_Y6_01", p1_cands[0].ref)
    service.dismiss_detection("CASE_Y6_01", p1_cands[1].ref, "Homeowner water bottle")
    # p1_cands[2] remains unreviewed
    service.confirm_detection("CASE_Y6_01", p2_cands[0].ref)

    ev1, _ = service.promote_detection_to_evidence("CASE_Y6_01", p1_cands[0].ref, label="Kitchen Knife")
    service.link_detection_to_evidence("CASE_Y6_01", ev1.evidence_id, p2_cands[0].ref)
    service.create_manual_evidence("CASE_Y6_01", "Broken Lock", description="Manual entry with no photo or det")

    exported = service.export_case_context("CASE_Y6_01")
    ctx = exported.case_context
    assert ctx["case"]["id"] == "CASE_Y6_01"
    assert ctx["case"]["rooms_covered"] == ["kitchen"]
    assert len(ctx["photos"]) == 3
    assert "room" not in ctx["photos"][2]  # Never invent room name
    assert len(ctx["evidence"]) == 2
    assert ctx["evidence"][0]["photo_ref"] == "photos.P1"
    assert ctx["evidence"][0]["det_ref"] == p1_cands[0].ref
    assert ctx["evidence"][1]["photo_ref"] is None
    assert ctx["evidence"][1]["det_ref"] is None

    # Every emitted ref resolves via frozen Module 1 refs.py
    for ref in exported.exported_refs:
        assert resolve_ref(ctx, ref) is not None

    # Invalid manual override triggers ExportValidationError
    with pytest.raises(ExportValidationError):
        service.export_case_context("CASE_Y6_01", case_metadata="not-a-dict")  # type: ignore[arg-type]


def test_exporter_layer1_preservation_and_strict_schema_unprojected(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    for idx, w in enumerate((64, 65, 66), start=1):
        p = tmp_path / f"m{idx}.png"
        p.write_bytes(create_valid_png(w, 48))

    det = StubDetectorBackend(
        predictions=[RawPrediction(class_id=0, class_name="knife", confidence=0.90, bbox_xyxy=(5.0, 5.0, 25.0, 25.0))]
    )
    service = YoloDetectionService(store, det, _pil_loader=lambda: None)
    for idx in (1, 2, 3):
        service.register_photo("CASE_Y6_L1", tmp_path / f"m{idx}.png")
        d = service.run_detection("CASE_Y6_L1", f"P{idx}").candidates[0]
        service.confirm_detection("CASE_Y6_L1", d.ref)

    ev1, _ = service.promote_detection_to_evidence("CASE_Y6_L1", "photos.P1.d1")
    service.link_detection_to_evidence("CASE_Y6_L1", ev1.evidence_id, "photos.P2.d1")
    service.link_detection_to_evidence("CASE_Y6_L1", ev1.evidence_id, "photos.P3.d1")

    # Strict schema variant with additionalProperties: false on evidence.items
    base_schema = json.loads(
        (Path(__file__).resolve().parent.parent / "schemas" / "case_context.schema.json").read_text(encoding="utf-8")
    )
    base_schema["properties"]["evidence"]["items"]["additionalProperties"] = False
    strict_schema_path = tmp_path / "strict_schema.json"
    strict_schema_path.write_text(json.dumps(base_schema), encoding="utf-8")

    exported = service.export_case_context("CASE_Y6_L1", schema_path=strict_schema_path)
    assert exported.unprojected_links == {
        "evidence.E1": {
            "photo_refs": ["photos.P2", "photos.P3"],
            "det_refs": ["photos.P2.d1", "photos.P3.d1"],
        }
    }
    assert len(exported.warnings) == 1
    assert "photo_refs" not in exported.case_context["evidence"][0]

    # Layer 1 in YoloCaseStore still retains all 3 links untouched
    stored_ev = service.get_evidence("CASE_Y6_L1", "E1")
    assert stored_ev.photo_refs == ["photos.P1", "photos.P2", "photos.P3"]
    assert stored_ev.det_refs == ["photos.P1.d1", "photos.P2.d1", "photos.P3.d1"]


def test_exporter_frozen_tier_a_and_pipeline_integration(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    img = tmp_path / "scene.png"
    img.write_bytes(create_valid_png(64, 48))

    preds = [
        RawPrediction(class_id=0, class_name="knife", confidence=0.91, bbox_xyxy=(5.0, 5.0, 25.0, 25.0)),
        RawPrediction(class_id=1, class_name="phone", confidence=0.60, bbox_xyxy=(30.0, 10.0, 50.0, 35.0)),
    ]
    service = YoloDetectionService(store, StubDetectorBackend(predictions=preds), _pil_loader=lambda: None)
    service.register_photo("CASE_Y6_M1", img, room="living_room")
    d1, d2 = service.run_detection("CASE_Y6_M1", "P1").candidates

    # Notes exercising A3:
    # - 'phone' is in unreviewed/dismissed detection -> A3 stays silent
    # - 'watch' is in manual evidence label -> A3 stays silent
    # - 'hammer' is absent from all detections & evidence -> A3 fires
    notes = [
        {"ref": "notes.N1", "type": "observation", "text": "Witness saw a phone, a watch, and a hammer."},
    ]

    # 1. Before review & manual watch evidence: d1 & d2 unreviewed -> A1 fires twice; A2 silent; A3 fires for hammer & watch
    exp_before = service.export_case_context("CASE_Y6_M1", notes=notes)
    flags_before = run_tier_a(exp_before.case_context)
    a1_refs = [f["evidence_refs"][0] for f in flags_before if f["rule"] == "A1"]
    assert set(a1_refs) == {d1.ref, d2.ref}
    assert not any(f["rule"] == "A2" for f in flags_before)
    a3_before = [f for f in flags_before if f["rule"] == "A3"]
    assert len(a3_before) == 2
    assert any("hammer" in f["summary"] for f in a3_before)
    assert any("watch" in f["summary"] for f in a3_before)

    # 2. Confirm d1, promote to evidence, dismiss d2 with valid reason, add manual watch evidence
    service.confirm_detection("CASE_Y6_M1", d1.ref)
    service.promote_detection_to_evidence("CASE_Y6_M1", d1.ref, label="knife")
    service.dismiss_detection("CASE_Y6_M1", d2.ref, "Victim phone on charger")
    service.create_manual_evidence("CASE_Y6_M1", "watch", photo_refs=["P1"])

    exp_after = service.export_case_context("CASE_Y6_M1", notes=notes)
    flags_after = run_tier_a(exp_after.case_context)

    # A1 cleared, A2 silent, A3 silent for phone (dismissed det) & watch (manual evidence), A8 fires for unmapped evidence
    assert not any(f["rule"] == "A1" for f in flags_after)
    assert not any(f["rule"] == "A2" for f in flags_after)
    a3_after = [f for f in flags_after if f["rule"] == "A3"]
    assert len(a3_after) == 1 and "hammer" in a3_after[0]["summary"]
    a8_refs = [f["evidence_refs"][0] for f in flags_after if f["rule"] == "A8"]
    assert set(a8_refs) == {"evidence.E1", "evidence.E2"}

    # 3. Feed into frozen run_pipeline in Tier A dry-run mode (zero live LLM calls)
    pipeline_res = run_pipeline(exp_after.case_context, tier_a_only=True, write_audit=False)
    assert pipeline_res.case_id == "CASE_Y6_M1"
    assert pipeline_res.tier_a_flags == flags_after
    assert pipeline_res.tier_b_suggestions == []


# ==============================================================================
# Stage Y7A: Deterministic Menu CLI & Full Offline End-to-End Tests
# ==============================================================================

def _make_scripted_io(inputs: list[str]) -> tuple[Any, Any, list[str]]:
    it = iter(inputs)
    outputs: list[str] = []

    def _input(prompt: str) -> str:
        outputs.append(prompt)
        try:
            return next(it)
        except StopIteration as exc:
            raise EOFError from exc

    def _output(line: str) -> None:
        outputs.append(line)

    return _input, _output, outputs


def test_cli_module_help_subprocess() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    proc = subprocess.run(
        [sys.executable, "-m", "src.yolo", "--help"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0
    assert "--base-dir" in proc.stdout
    assert "--stub" in proc.stdout


def test_cli_error_handling_and_graceful_recovery(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    img = tmp_path / "cli_err.png"
    img.write_bytes(create_valid_png(64, 48))

    # 1. Dependency failure during detection (menu loop stays alive)
    dep_backend = UltralyticsYOLOBackend(
        _module_loader=lambda: (_ for _ in ()).throw(ImportError("no ultralytics"))
    )
    dep_service = YoloDetectionService(store, dep_backend, _pil_loader=lambda: None)
    inp1, out_fn1, _log1 = _make_scripted_io([
        "99",                   # invalid choice
        "3",                    # list photos before selecting case
        "1", "CASE_CLI_ERR",    # select case
        "2", str(img), "", "n", # register photo P1
        "4", "P1", "", "",      # run detection -> DetectorDependencyError
        "13",                   # exit
    ])
    cli1 = YoloCLI(dep_service, input_fn=inp1, output_fn=out_fn1)
    hist1 = cli1.run()
    assert hist1[0].action == "invalid_choice" and hist1[0].status == "failed"
    assert hist1[1].action == "list_photos" and hist1[1].status == "failed"
    assert any(r.action == "menu_4" and r.status == "failed" for r in hist1)
    assert hist1[-1].action == "exit" and hist1[-1].status == "completed"

    # 2. Review skip & blank dismissal reason rejected gracefully
    det_backend = StubDetectorBackend(
        predictions=[RawPrediction(class_id=0, class_name="knife", confidence=0.88, bbox_xyxy=(5.0, 5.0, 25.0, 25.0))]
    )
    ok_service = YoloDetectionService(store, det_backend, _pil_loader=lambda: None)
    inp2, out_fn2, _log2 = _make_scripted_io([
        "4", "P1", "", "",            # run detection -> photos.P1.d1
        "6", "B",                     # skip review
        "6", "photos.P1.d1", "D", "", # blank dismissal reason -> failed cleanly
        "13",
    ])
    cli2 = YoloCLI(ok_service, case_id="CASE_CLI_ERR", input_fn=inp2, output_fn=out_fn2)
    hist2 = cli2.run()
    assert hist2[1].data.get("skipped") is True
    assert hist2[2].status == "failed"
    assert "non-empty" in hist2[2].errors[0]
    assert hist2[-1].action == "exit"


def test_cli_end_to_end_operational_workflow(tmp_path: Path) -> None:
    store = YoloCaseStore(base_dir=tmp_path / "cases")
    img1 = tmp_path / "living.png"
    img2 = tmp_path / "study.png"
    img1.write_bytes(create_valid_png(64, 48))
    img2.write_bytes(create_valid_png(65, 48))
    export_file = tmp_path / "exported_case_context.json"

    det = StubDetectorBackend(
        predictions={
            "P1_original.png": [
                RawPrediction(class_id=0, class_name="knife", confidence=0.92, bbox_xyxy=(5.0, 5.0, 25.0, 25.0)),
                RawPrediction(class_id=1, class_name="bottle", confidence=0.65, bbox_xyxy=(30.0, 10.0, 50.0, 35.0)),
            ],
            "P2_original.png": [
                RawPrediction(class_id=2, class_name="cell_phone", confidence=0.84, bbox_xyxy=(10.0, 10.0, 35.0, 35.0)),
            ],
        }
    )
    service = YoloDetectionService(store, det, _pil_loader=lambda: None)

    scripted_inputs = [
        "1", "CASE_Y7_E2E",                         # Select case
        "2", str(img1), "living_room", "n",         # Register P1
        "2", str(img2), "study", "n",               # Register P2
        "3",                                        # List photos
        "4", "P1", "", "",                          # Detect on P1
        "4", "P2", "", "",                          # Detect on P2
        "5", "", "",                                # View all detections
        "6", "photos.P1.d1", "C",                   # Confirm P1.d1
        "6", "photos.P1.d2", "D", "Water bottle on counter",  # Dismiss P1.d2
        "6", "photos.P2.d1", "C",                   # Confirm P2.d1
        "7", "photos.P1.d1", "", "Kitchen knife", "Found on floor",  # Promote -> E1
        "7", "photos.P2.d1", "", "Victim phone", "On desk",          # Promote -> E2
        "8", "Broken latch", "Door frame damage", "P1",              # Manual -> E3
        "9", "E1", "P", "P2",                       # Link P2 to E1
        "11",                                       # Verify SHA-256 integrity
        "12",                                       # View audit history
        "10", str(export_file),                     # Export validated JSON
        "13",                                       # Exit
    ]
    inp, out_fn, _log = _make_scripted_io(scripted_inputs)
    cli = YoloCLI(service, input_fn=inp, output_fn=out_fn)
    history = cli.run()

    assert all(r.status in ("completed", "completed_with_warnings") for r in history)
    assert history[-1].action == "exit"
    assert export_file.is_file()

    # Validate exported JSON against Draft-07 schema, frozen refs.py, and frozen run_pipeline
    exported_ctx = json.loads(export_file.read_text(encoding="utf-8"))
    schema = json.loads(
        (Path(__file__).resolve().parent.parent / "schemas" / "case_context.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(instance=exported_ctx, schema=schema)

    assert exported_ctx["case"]["id"] == "CASE_Y7_E2E"
    assert exported_ctx["case"]["rooms_covered"] == ["living_room", "study"]
    assert len(exported_ctx["evidence"]) == 3
    assert exported_ctx["evidence"][0]["photo_refs"] == ["photos.P1", "photos.P2"]

    for ref in ("photos.P1", "photos.P2", "photos.P1.d1", "photos.P1.d2", "photos.P2.d1", "evidence.E1", "evidence.E2", "evidence.E3"):
        assert resolve_ref(exported_ctx, ref) is not None

    pipe_res = run_pipeline(exported_ctx, tier_a_only=True, write_audit=False)
    assert pipe_res.case_id == "CASE_Y7_E2E"
    assert not any(f["rule"] in ("A1", "A2") for f in pipe_res.tier_a_flags)
