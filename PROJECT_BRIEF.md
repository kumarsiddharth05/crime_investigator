# PROJECT BRIEF
# Module 2 — YOLO Candidate Detection, Investigator Review & Evidence Management

**Project:** AI-Assisted Crime Scene Investigation and Evidence Analysis System  
**Module:** Module 2 — YOLO Candidate Detection, Investigator Review & Evidence Management  
**Document Type:** Active Module Engineering Specification  
**Status:** **ACTIVE (Stage Y0 Closed; Ready for Stage Y1 Implementation)**  
**Date:** 22 November 2026  

> [!NOTE]
> **4-Document Architecture Notice:**  
> Module 1 (LLM Analysis Module) is complete, verified, and permanently frozen. Its permanent architectural contract, benchmark results, and verification provenance are preserved in [docs/LLM_MODULE_HANDOVER.md](docs/LLM_MODULE_HANDOVER.md).  
> `PROJECT_BRIEF.md` contains strictly the active working specification for the module under development (**Module 2**). When Module 2 is frozen, its permanent record will be preserved in `docs/YOLO_MODULE_HANDOVER.md`, and this document will transition to Module 3.

---

# 1. Document Purpose & Objectives

This document defines the complete active engineering specification for **Module 2 — YOLO Candidate Detection, Investigator Review & Evidence Management**.

### 1.1 Primary Objectives (M2-O1 – M2-O12)

- **M2-O1 (Original Photo Ingestion):** Ingest crime-scene photographs, computing and enforcing SHA-256 immutability.
- **M2-O2 (Automated Candidate Detection):** Execute object detection via a pluggable detector backend to identify visual object candidates.
- **M2-O3 (Candidate Boundary):** Enforce strict separation: `Detection ≠ Evidence ≠ Spatial Position`. Detections are candidate observations, never evidence.
- **M2-O4 (Derived Previews):** Generate separate annotated image previews without modifying original photograph bytes.
- **M2-O5 (Investigator Review Workflow):** Require explicit investigator review for every candidate detection; every candidate begins as `unreviewed`.
- **M2-O6 (Candidate Confirmation):** Enable investigators to confirm candidate detections.
- **M2-O7 (Candidate Dismissal):** Enforce mandatory non-empty rationale when dismissing candidates (rejecting whitespace-only).
- **M2-O8 (Evidence Promotion):** Allow investigators to promote confirmed candidates into formal evidence records.
- **M2-O9 (Manual Evidence Creation):** Provide first-class manual evidence creation for objects missed by detection models (e.g. small, occluded, or non-COCO items).
- **M2-O10 (Traceable Audit History):** Maintain an append-only log of all investigator reviews and evidence revisions.
- **M2-O11 (Schema-Valid Export):** Export structured records into `case_context` JSON conforming strictly to `schemas/case_context.schema.json`.
- **M2-O12 (Module 1 Integration):** Ensure seamless compatibility with frozen Module 1 (reference resolution, Tier A rules A1, A2, A3, A8, and validator).

---

# 2. Locked Architecture Constraints (12 Mandatory Invariants)

1. **`src/yolo/` Package Isolation:** Module 2 logic lives exclusively under `src/yolo/`. Module 1 source files (`src/analysis/*`, `src/llm/*`, `src/workflow/*`), test files, schemas, and fixtures remain untouched and read-only.
2. **Photograph Immutability & SHA-256 Integrity:** Original photograph files must never be modified, overwritten, re-encoded, or annotated in place. Stored original bytes must be verified by SHA-256 hashes.
3. **Separate Annotated Previews:** Visual annotations (bounding boxes, labels, confidence) are written strictly to separate preview image files in dedicated preview directories.
4. **Detection ≠ Evidence:** A machine detection is an unverified candidate observation. It only becomes an evidence record through deliberate investigator confirmation and promotion.
5. **Investigator Authority:** The system never autonomously promotes detections or draws forensic/judicial conclusions.
6. **Mandatory Non-Empty Dismissal Reason:** Dismissing a candidate requires a non-empty, whitespace-trimmed justification string. (No arbitrary character-length minimum; clear, non-empty text required to satisfy schema and Tier A Rule A2).
7. **First-Class Manual Evidence:** Physical evidence identified at the scene without a photo detection can be created with `photo_ref: null` and `det_ref: null`.
8. **Three-Layer Evidence Relationship Model:** Multi-photo and multi-detection relationships are preserved across internal models, standard schema fields, and schema-permitted extensions without data loss.
9. **Offline-First Automated Testing:** All automated tests must run offline using a `StubDetectorBackend` with mock fixtures; no live model weight downloads in CI or unit tests.
10. **Centralized Persistence Ownership:** Module 2 implements lightweight, configurable file/directory storage. It must not implement a competing SQLite database or ORM layer (database persistence is centralized in Module 5).
11. **Original-Pixel Coordinate Integrity:** Bounding box coordinates must be stored in original-image pixel space `[x_min, y_min, x_max, y_max]` relative to original photograph dimensions, accounting for EXIF orientation and letterboxing.
12. **Graceful Candidate Capping:** Candidate detection capping (provisional threshold: 30 candidates per photo) must emit visible truncation warnings rather than silently dropping excess candidates.

---

# 3. Package Layout & Directory Architecture

```text
src/yolo/
├── __init__.py           # Package exports (entities, services, detector protocol)
├── __main__.py           # CLI entry point (python -m src.yolo)
├── models.py             # 5 core dataclasses/Pydantic domain entities
├── store.py              # Photo and record storage with SHA-256 verification
├── detector.py           # DetectorBackend protocol, StubDetectorBackend, Ultralytics wrapper
├── preview.py            # Bounding box rendering (Pillow/OpenCV fallback)
├── service.py            # High-level coordinator API for ingestion, detection, and review
├── exporter.py           # Case context JSON exporter conforming to schema
└── exceptions.py         # Module-specific typed error hierarchy

tests/
└── test_yolo.py          # Comprehensive offline test suite for Module 2

docs/
└── YOLO_MODULE_HANDOVER.md  # Permanent Module 2 freeze & contract handover document
```

### Configurable Runtime Storage
Runtime storage defaults to configurable directories:
- `data/cases/<case_id>/photos/raw/`: Read-only original photograph files.
- `data/cases/<case_id>/photos/previews/`: Derived annotated preview images.
- `data/cases/<case_id>/metadata/`: JSON/JSONL records for candidates, reviews, and evidence.

---

# 4. Core Domain Entities & Reference Syntax

### 4.1 The 5 Core Entities (`src/yolo/models.py`)

1. **`PhotoRecord`**: Represents an ingested crime-scene photograph.
   - `photo_id`: Safe unique ID (e.g. `"P1"`).
   - `ref`: Canonical dotted reference (`"photos.P1"`).
   - `original_path`: Path to preserved raw image.
   - `sha256`: SHA-256 hex digest of raw image bytes.
   - `room`: Optional scene room name (e.g. `"living_room"`).
   - `view`: Descriptive view orientation (e.g. `"overview_south"`).
   - `width`, `height`: Original image dimensions in pixels.
   - `exif_orientation`: Integer orientation tag (1–8).
   - `ingested_at`: ISO-8601 UTC timestamp.

2. **`DetectionRun`**: Provenance container for an inference execution.
   - `run_id`: Unique run identifier (`"run_<timestamp>_<uuid>"`).
   - `photo_id`: Associated photograph ID.
   - `model_name`: Detector identifier (e.g. `"yolov8n.pt"`).
   - `model_provenance`: Backend version and configuration string.
   - `confidence_threshold`: Minimum detection threshold (e.g. `0.25`).
   - `candidates_count`: Number of candidates generated.
   - `created_at`: ISO-8601 UTC timestamp.

3. **`DetectionCandidate`**: Individual object candidate from detector output.
   - `candidate_id`: Photo-scoped ID (e.g. `"P1.d1"`).
   - `ref`: Canonical reference (`"photos.P1.d1"`).
   - `photo_ref`: Source photograph reference (`"photos.P1"`).
   - `run_id`: Associated detection run.
   - `class_name`: Predicted object class (e.g. `"knife"`, `"bottle"`).
   - `confidence`: Confidence score (`0.0`–`1.0`).
   - `bbox_xyxy`: Pixel coordinates `(x_min, y_min, x_max, y_max)` in original image space.
   - `disposition`: Initialized strictly to `"unreviewed"`; transitions to `"confirmed"` or `"dismissed"`.
   - `reason`: Justification string (required if dismissed).

4. **`EvidenceRecord`**: Formally recorded evidence item managed by investigator.
   - `evidence_id`: Sequential ID (e.g. `"E1"`).
   - `ref`: Canonical reference (`"evidence.E1"`).
   - `label`: Investigator-assigned evidence description (e.g. `"kitchen knife"`).
   - `source_type`: `"promoted_detection"` or `"manual_entry"`.
   - `primary_photo_ref`: Primary photo reference (`"photos.P1"` or `None`).
   - `primary_det_ref`: Primary detection reference (`"photos.P1.d1"` or `None`).
   - `all_photo_refs`: List of all associated photographs.
   - `all_det_refs`: List of all associated detection candidates.
   - `created_by`: Investigator identifier.
   - `created_at`: ISO-8601 UTC timestamp.

5. **`ReviewEvent`**: Append-only audit record tracking investigator actions.
   - `event_id`: Unique review event ID (`"rev_<uuid>"`).
   - `target_type`: `"candidate"` or `"evidence"`.
   - `target_ref`: Reference of target item (`"photos.P1.d1"` or `"evidence.E1"`).
   - `action`: `"confirm"`, `"dismiss"`, `"promote"`, `"create_manual"`, `"edit_label"`.
   - `previous_disposition`: State before review.
   - `new_disposition`: State after review.
   - `reason`: Mandatory rationale for dismissals or modifications.
   - `investigator_id`: Identifier of reviewing investigator.
   - `timestamp`: ISO-8601 UTC timestamp.

---

# 5. Three-Layer Evidence Relationship Model

To reconcile schema limitations with real-world crime scene investigation:

```
[Layer 1: Internal Module 2 Data Model]
  EvidenceRecord:
    evidence_id: "E1"
    label: "bloody kitchen knife"
    all_photo_refs: ["photos.P1", "photos.P2"]
    all_det_refs: ["photos.P1.d1", "photos.P2.d3"]

          │  Mapped during export
          ▼
[Layer 2: Standard case_context Contract (schemas/case_context.schema.json)]
  evidence: [
    {
      "ref": "evidence.E1",
      "label": "bloody kitchen knife",
      "photo_ref": "photos.P1",         <-- Single primary photo
      "det_ref": "photos.P1.d1",         <-- Single primary detection
      "map_ref": null

          │  Preserved via additionalProperties: true
          ▼
[Layer 3: Extended Schema-Permitted Metadata]
      "secondary_photo_refs": ["photos.P2"],
      "secondary_det_refs": ["photos.P2.d3"],
      "source_type": "promoted_detection"
    }
  ]
```

- **Manual Evidence:** For evidence created without detections or photos:
  `{"ref": "evidence.E2", "label": "latent print tape lift", "photo_ref": null, "det_ref": null, "map_ref": null}`.
  Conforms to schema and correctly participates in Module 1 Tier A Rule A3.

---

# 6. Detector Backend Strategy & Model Candidates

### 6.1 Detector Backend Protocol (`src/yolo/detector.py`)
```python
class DetectorBackend(Protocol):
    def detect(
        self,
        image_path: Path,
        confidence_threshold: float = 0.25,
    ) -> list[RawDetection]: ...
```

### 6.2 Implementation Strategy
- **`StubDetectorBackend`:** Offline deterministic detector returning programmatic candidate detections from predefined dictionaries. Powers all automated offline tests in CI without network or GPU.
- **`UltralyticsYOLOBackend`:** Lazy-loaded backend importing `ultralytics` only when instantiated. Loads local `.pt` weights.
- **Provisional Leading Model:** `yolov8n.pt` (Nano) is the provisional leading CPU candidate (~6.5 MB, ~3.2M params).
  - *Status:* CPU inference latency and Python 3.14 package compatibility for `ultralytics` and `cv2` are explicitly marked **UNVERIFIED**. Full validation occurs during Stage Y2.
- **Candidate Capping & NMS:**
  - Standard Ultralytics built-in Non-Maximum Suppression (NMS) is utilized; no redundant custom NMS pass without proven necessity.
  - If candidate count exceeds the provisional cap (30 candidates per photo), excess candidates are capped and an explicit truncation warning is logged in `DetectionRun.warnings`.

---

# 7. Module 1 Integration Contracts

Inspected and verified against frozen Module 1 source code:

1. **Tier A Rule A1 (Unreviewed Candidate):** Reads `photos[].detections[].disposition`. Unreviewed candidates trigger Rule A1 flags to alert the investigator.
2. **Tier A Rule A2 (Dismissed Reason Guard):** Reads `photos[].detections[].reason`. Dismissed detections must include a non-empty string.
3. **Tier A Rule A3 (Object Class Consistency):** Authoritative logic in `src/analysis/tier_a.py` checks note keywords against:
   - `all_classes_seen_in_detections` (all detection classes across unreviewed, confirmed, and dismissed).
   - `confirmed_evidence_labels` (all labels in `evidence[].label`).
   *(Rule A3 does not require `photo_ref` or `det_ref` to be populated on evidence items; evidence labels directly satisfy A3).*
4. **Tier A Rule A8 (Map Position Presence):** Reads `evidence[].map_ref` and `map.evidence_positions_summary`. Module 2 outputs `map_ref: null` on newly created evidence. Module 2 must **never** fabricate fake map positions merely to suppress Rule A8.
5. **Reference Resolution (`src/analysis/refs.py`):**
   - Photo references resolve as `photos.P#`.
   - Detection references resolve as `photos.P#.d#` (photo-scoped).
   - Evidence references resolve as `evidence.E#`.
   - `map.E#` resolves via `case_context["map"]["xy_optional"]` (verified).

---

# 8. Locked Y0–Y8 Implementation Sequence

| Stage | Name | Core Responsibilities | Exit Condition |
|---|---|---|---|
| **Y0** | **Pre-Design Inspection & Docs** | Read-only repo audit, 4-doc architecture adoption, handbook cleanup. | **CLOSED (22 Nov 2026)** |
| **Y1** | **Core Entities & Storage** | Implement `models.py`, `store.py`, `exceptions.py`, SHA-256 immutability. | Photo ingestion & hashing passes unit tests. |
| **Y2** | **Detector Backend & Models** | `DetectorBackend` protocol, `StubDetectorBackend`, optional lazy Ultralytics. | Stub detector returns calibrated bounding boxes. |
| **Y3** | **Review Workflow & Evidence** | Confirm/dismiss logic, mandatory reason, evidence promotion, manual evidence. | Review transitions and promotion verified. |
| **Y4** | **Annotated Previews** | Pillow/OpenCV rendering, distinct colors per disposition, separate files. | Previews generated without altering originals. |
| **Y5** | **Investigator CLI Interface** | Interactive CLI for ingestion, candidate review, manual evidence entry. | Non-blocking CLI flows tested with mock I/O. |
| **Y6** | **Case Context Exporter** | Export to `case_context.schema.json`, test with `refs.py` and Tier A rules. | Exported cases pass schema and Module 1 checks. |
| **Y7** | **Automated Test Suite** | Offline test suite (`tests/test_yolo.py`) covering all scenarios. | Full test suite green offline in CI. |
| **Y8** | **Controlled Live Verification & Freeze** | Single controlled real-model run, doc evaluation, `docs/YOLO_MODULE_HANDOVER.md`. | Module 2 frozen; handover approved. |

---

# 9. 26 Completion Criteria (M2-01 – M2-26)

- **M2-01:** Dedicated `src/yolo/` package containing all Module 2 source code.
- **M2-02:** Module 1 source code (`src/analysis/*`, `src/llm/*`, `src/workflow/*`) remains completely untouched.
- **M2-03:** Original photographs remain byte-identical and immutable after ingestion and preview generation.
- **M2-04:** SHA-256 verification detects and rejects photograph file modifications.
- **M2-05:** Pretrained detector backend protocol implemented with pluggable stub and real backends.
- **M2-06:** Model provenance (model name, version, confidence threshold) recorded for every detection run.
- **M2-07:** Dotted detection references follow canonical photo-scoped syntax `photos.P<photo_id>.d<det_id>`.
- **M2-08:** Stored bounding boxes accurately represent original-image pixel coordinates.
- **M2-09:** Annotated preview images are generated as separate files in dedicated preview directories.
- **M2-10:** Every candidate detection starts strictly with `unreviewed` disposition.
- **M2-11:** Candidate confirmation is strictly investigator-controlled; no autonomous confirmation.
- **M2-12:** Mandatory non-empty dismissal reason enforced for dismissed candidates.
- **M2-13:** Append-only review history preserves all investigator review actions.
- **M2-14:** Confirmed detections promote cleanly into structured evidence records.
- **M2-15:** Manual evidence creation supported without requiring photo or detection references.
- **M2-16:** Multi-photo and multi-detection evidence associations preserved via 3-layer model.
- **M2-17:** Evidence revision history tracks modifications to evidence labels and associations.
- **M2-18:** Exported case context validates 100% against `schemas/case_context.schema.json`.
- **M2-19:** Exported detection and evidence references resolve successfully in `src/analysis/refs.py`.
- **M2-20:** Bounding box coordinates and EXIF orientation satisfy Module 3 spatial mapping prerequisites.
- **M2-21:** Storage boundaries and metadata structures cleanly decouple for Module 5 SQLite migration.
- **M2-22:** Comprehensive offline automated test suite passes without network access or live API calls.
- **M2-23:** Controlled live model inference executes successfully on local CPU with provisional `yolov8n.pt`.
- **M2-24:** Detection latency, confidence distribution, and class vocabulary documented in evaluation notes.
- **M2-25:** Permanent `docs/YOLO_MODULE_HANDOVER.md` generated and project records updated.
- **M2-26:** Zero regressions across existing 163 tests, 13 fixtures, and 13 reference checks.

---

# 10. Explicit Exclusions & Out-of-Scope Items

- **Custom Model Training:** No YOLO fine-tuning or custom weight training. Pretrained COCO weights are used strictly as a baseline.
- **Autonomous Forensic Judgments:** No model-determined guilt, suspect profiling, or intent.
- **Planar Spatial Reconstruction:** Floor-plan rectification, 2D coordinates, and camera homography belong strictly to Module 3.
- **Relational Database Engine:** SQLite schema design and table migrations belong strictly to Module 5.
- **PDF Report Generation:** Document rendering belongs strictly to Module 6.
- **Web UI / React Interface:** Web application and frontend state belong strictly to Module 8.

---

# 11. Risk Register

| Risk | Impact | Mitigation Strategy |
|---|---|---|
| **Python 3.14 Wheel Availability** | Missing prebuilt wheels for `opencv-python` or `ultralytics` on Windows. | Implement `StubDetectorBackend` and Pillow rendering fallback first in Y1/Y2; test wheel installation in isolation. |
| **CPU Inference Latency** | Slow inference on 4-core CPU without CUDA acceleration. | Use lightweight `yolov8n.pt` (~3.2M params); keep detection runs asynchronous or cached. |
| **COCO Class Mismatch** | Standard COCO-80 lacks specialized forensic classes (e.g. `gun`, `bloodstain`). | Support manual evidence creation and investigator label editing upon promotion. |
| **Multi-Photo Schema Constraints** | `case_context.schema.json` expects single string `photo_ref`. | Adopt 3-layer evidence relationship model (Layer 1 multi-list, Layer 2 primary ref, Layer 3 extended metadata). |
