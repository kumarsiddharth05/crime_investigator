"""Unit and integration tests for Module 2 (YOLO): Data Contracts, Storage, and Detector Backend."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest

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

    # Detection promoted without det_refs rejected
    with pytest.raises(ValueError):
        EvidenceRecord(
            evidence_id="E2",
            ref="evidence.E2",
            case_id="C0",
            label="Gun",
            description="Promoted from candidate",
            creation_source="detection_promoted",
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
