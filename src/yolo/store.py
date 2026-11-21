"""Case storage, immutable photo persistence, and audit logging for Module 2 (YOLO)."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.yolo.exceptions import (
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


class YoloCaseStore:
    """Store for case photos, detection runs, candidates, evidence, and audit logs."""

    def __init__(
        self,
        base_dir: Path | str = Path("data/cases"),
        max_file_size_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.max_file_size_bytes = max_file_size_bytes

    def _validate_safe_name(self, name: str, field_name: str = "identifier") -> str:
        if not name or not isinstance(name, str) or not name.strip():
            raise IntegrityError(f"{field_name} must be a non-empty string")
        cleaned = name.strip()
        if any(c in cleaned for c in ('/', '\\', '\0', ':')) or ".." in cleaned:
            raise IntegrityError(f"Path traversal or invalid characters detected in {field_name}: '{name}'")
        return cleaned

    def _get_case_dir(self, case_id: str) -> Path:
        safe_case = self._validate_safe_name(case_id, "case_id")
        case_dir = (self.base_dir / safe_case).resolve()
        try:
            case_dir.relative_to(self.base_dir)
        except ValueError:
            raise IntegrityError(f"Path traversal detected for case_id '{case_id}' outside base_dir")
        return case_dir

    def _ensure_case_layout(self, case_dir: Path) -> None:
        (case_dir / "photos" / "originals").mkdir(parents=True, exist_ok=True)
        (case_dir / "photos" / "previews").mkdir(parents=True, exist_ok=True)
        (case_dir / "detections").mkdir(parents=True, exist_ok=True)
        (case_dir / "evidence").mkdir(parents=True, exist_ok=True)
        (case_dir / "audit").mkdir(parents=True, exist_ok=True)

    def _atomic_write_json(self, file_path: Path, data: Any) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=file_path.parent,
                delete=False,
            ) as f:
                temp_file = Path(f.name)
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, file_path)
        except Exception as exc:
            if temp_file and temp_file.is_file():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise StorageError(f"Failed to atomically write {file_path}: {exc}") from exc

    def _read_json(self, file_path: Path, default: Any = None) -> Any:
        if not file_path.is_file():
            return default
        try:
            with file_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            raise StorageError(f"Failed to read or parse JSON file {file_path}: {exc}") from exc

    def _load_module_state(self, case_id: str) -> dict[str, Any]:
        case_dir = self._get_case_dir(case_id)
        self._ensure_case_layout(case_dir)
        state_path = case_dir / "module_state.json"
        if not state_path.is_file():
            initial_state = {
                "schema_version": "1.0",
                "case_id": case_id,
                "next_photo_num": 1,
                "per_photo_det_num": {},
                "next_evidence_num": 1,
                "next_run_num": 1,
                "next_review_event_num": 1,
                "next_evidence_event_num": 1,
                "photos": {},
            }
            self._atomic_write_json(state_path, initial_state)
            return initial_state

        state = self._read_json(state_path)
        if not isinstance(state, dict):
            raise StorageError(f"Invalid module_state.json format in case {case_id}")
        return state

    def _save_module_state(self, case_id: str, state: dict[str, Any]) -> None:
        case_dir = self._get_case_dir(case_id)
        state_path = case_dir / "module_state.json"
        self._atomic_write_json(state_path, state)

    def allocate_photo_id(self, case_id: str) -> str:
        state = self._load_module_state(case_id)
        num = state.get("next_photo_num", 1)
        state["next_photo_num"] = num + 1
        self._save_module_state(case_id, state)
        return f"P{num}"

    def allocate_detection_ref(self, case_id: str, photo_id: str) -> tuple[str, str]:
        safe_photo = self._validate_safe_name(photo_id, "photo_id")
        state = self._load_module_state(case_id)
        per_photo = state.setdefault("per_photo_det_num", {})
        cur = per_photo.get(safe_photo, 1)
        per_photo[safe_photo] = cur + 1
        self._save_module_state(case_id, state)
        det_id = f"d{cur}"
        ref = f"photos.{safe_photo}.{det_id}"
        return det_id, ref

    def allocate_run_id(self, case_id: str) -> str:
        state = self._load_module_state(case_id)
        num = state.get("next_run_num", 1)
        state["next_run_num"] = num + 1
        self._save_module_state(case_id, state)
        return f"RUN{num:03d}"

    def allocate_evidence_id(self, case_id: str) -> tuple[str, str]:
        state = self._load_module_state(case_id)
        num = state.get("next_evidence_num", 1)
        state["next_evidence_num"] = num + 1
        self._save_module_state(case_id, state)
        evidence_id = f"E{num}"
        ref = f"evidence.{evidence_id}"
        return evidence_id, ref

    def _allocate_review_event_id(self, state: dict[str, Any]) -> str:
        num = state.get("next_review_event_num", 1)
        state["next_review_event_num"] = num + 1
        return f"REV{num:03d}"

    def _allocate_evidence_event_id(self, state: dict[str, Any]) -> str:
        num = state.get("next_evidence_event_num", 1)
        state["next_evidence_event_num"] = num + 1
        return f"EVD{num:03d}"

    def _inspect_image_header(self, data: bytes) -> tuple[str, int, int]:
        """Pure standard library image magic and dimension header parser."""
        if len(data) < 8:
            raise InvalidPhotoError("Image data too short to determine format")

        # 1. PNG
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            if len(data) < 24:
                raise InvalidPhotoError("Truncated PNG header")
            if data[12:16] != b"IHDR":
                raise InvalidPhotoError("PNG does not start with IHDR chunk")
            w, h = struct.unpack(">II", data[16:24])
            if w <= 0 or h <= 0:
                raise InvalidPhotoError(f"Invalid PNG dimensions: {w}x{h}")
            return "png", w, h

        # 2. JPEG
        if data.startswith(b"\xff\xd8\xff"):
            offset = 2
            found_sof = False
            data_len = len(data)
            while offset < data_len - 1:
                if data[offset] != 0xFF:
                    offset += 1
                    continue
                while offset < data_len and data[offset] == 0xFF:
                    offset += 1
                if offset >= data_len:
                    break
                marker = data[offset]
                offset += 1
                # Baseline, Extended Sequential, Progressive, Lossless SOF markers
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    if offset + 7 > data_len:
                        raise InvalidPhotoError("Truncated JPEG SOF segment")
                    h = struct.unpack(">H", data[offset + 3 : offset + 5])[0]
                    w = struct.unpack(">H", data[offset + 5 : offset + 7])[0]
                    if w <= 0 or h <= 0:
                        raise InvalidPhotoError(f"Invalid JPEG dimensions: {w}x{h}")
                    return "jpeg", w, h
                elif marker in (0xD9, 0xDA):
                    # End of Image or Start of Scan reached before SOF
                    break
                elif marker in (0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8):
                    continue
                else:
                    if offset + 2 > data_len:
                        break
                    seg_len = struct.unpack(">H", data[offset : offset + 2])[0]
                    offset += seg_len
            raise InvalidPhotoError("Valid JPEG SOF marker not found")

        # 3. BMP
        if data.startswith(b"BM"):
            if len(data) < 26:
                raise InvalidPhotoError("Truncated BMP header")
            dib_size = struct.unpack("<I", data[14:18])[0]
            if dib_size >= 40:
                if len(data) < 26:
                    raise InvalidPhotoError("Truncated BMP header")
                w = struct.unpack("<i", data[18:22])[0]
                h = abs(struct.unpack("<i", data[22:26])[0])
            elif dib_size == 12:
                if len(data) < 22:
                    raise InvalidPhotoError("Truncated BMP header")
                w = struct.unpack("<H", data[18:20])[0]
                h = struct.unpack("<H", data[20:22])[0]
            else:
                raise InvalidPhotoError(f"Unsupported BMP DIB header size: {dib_size}")
            if w <= 0 or h <= 0:
                raise InvalidPhotoError(f"Invalid BMP dimensions: {w}x{h}")
            return "bmp", w, h

        # 4. WEBP
        if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
            if len(data) < 16:
                raise InvalidPhotoError("Truncated WEBP header")
            chunk_type = data[12:16]
            if chunk_type == b"VP8 ":
                if len(data) < 30:
                    raise InvalidPhotoError("Truncated VP8 WEBP header")
                w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
                h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            elif chunk_type == b"VP8L":
                if len(data) < 25:
                    raise InvalidPhotoError("Truncated VP8L WEBP header")
                if data[20] != 0x2F:
                    raise InvalidPhotoError("Corrupted VP8L signature")
                b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
                w = 1 + (b0 | ((b1 & 0x3F) << 8))
                h = 1 + (((b1 >> 6) & 0x03) | (b2 << 2) | ((b3 & 0x0F) << 10))
            elif chunk_type == b"VP8X":
                if len(data) < 30:
                    raise InvalidPhotoError("Truncated VP8X WEBP header")
                w = 1 + struct.unpack("<I", data[24:27] + b"\x00")[0]
                h = 1 + struct.unpack("<I", data[27:30] + b"\x00")[0]
            else:
                raise InvalidPhotoError(f"Unsupported WEBP format chunk: {chunk_type!r}")
            if w <= 0 or h <= 0:
                raise InvalidPhotoError(f"Invalid WEBP dimensions: {w}x{h}")
            return "webp", w, h

        raise InvalidPhotoError("Unsupported image format or unrecognized image magic bytes")

    def ingest_photo(
        self,
        case_id: str,
        image_bytes: bytes | None = None,
        source_path: Path | str | None = None,
        source_filename: str | None = None,
        ingested_by: str = "investigator",
        room: str | None = None,
        allow_duplicate_bytes: bool = False,
    ) -> PhotoRecord:
        """Atomically ingests a photo, enforcing SHA-256 integrity, format checks, and immutability."""
        case_dir = self._get_case_dir(case_id)
        self._ensure_case_layout(case_dir)

        if image_bytes is None:
            if source_path is None:
                raise InvalidPhotoError("Either image_bytes or source_path must be provided")
            src_p = Path(source_path)
            if not src_p.is_file():
                raise InvalidPhotoError(f"Source photo file not found: {source_path}")
            try:
                raw_bytes = src_p.read_bytes()
            except Exception as exc:
                raise InvalidPhotoError(f"Failed to read source photo: {exc}") from exc
            if source_filename is None:
                source_filename = src_p.name
        else:
            raw_bytes = image_bytes

        if not raw_bytes:
            raise InvalidPhotoError("Photo data is empty (0 bytes)")
        if len(raw_bytes) > self.max_file_size_bytes:
            raise InvalidPhotoError(f"Photo size {len(raw_bytes)} bytes exceeds maximum {self.max_file_size_bytes} bytes")

        img_format, width, height = self._inspect_image_header(raw_bytes)
        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()

        # Check duplicate hash within case
        state = self._load_module_state(case_id)
        photos_meta: dict[str, Any] = state.setdefault("photos", {})
        for existing_id, meta in photos_meta.items():
            if meta.get("sha256") == sha256_hash:
                if not allow_duplicate_bytes:
                    raise IntegrityError(
                        f"Photo with identical SHA-256 already exists in case '{case_id}': {existing_id}"
                    )

        # Allocate photo ID
        photo_id = self.allocate_photo_id(case_id)
        ext = ".jpg" if img_format == "jpeg" else f".{img_format}"
        target_filename = f"{photo_id}_original{ext}"
        rel_path = f"photos/originals/{target_filename}"
        target_path = case_dir / "photos" / "originals" / target_filename

        if target_path.exists():
            raise IntegrityError(f"Target photo file already exists: {target_path}")

        # Atomically write original image
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target_path.parent,
                delete=False,
            ) as f:
                temp_file = Path(f.name)
                f.write(raw_bytes)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, target_path)
        except Exception as exc:
            if temp_file and temp_file.is_file():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise StorageError(f"Failed to write photo original file: {exc}") from exc

        now_iso = datetime.now(timezone.utc).isoformat()
        clean_filename = self._validate_safe_name(source_filename or target_filename, "source_filename")

        from src.yolo.preview import read_exif_orientation

        exif_orientation = read_exif_orientation(raw_bytes)

        record = PhotoRecord(
            photo_id=photo_id,
            ref=f"photos.{photo_id}",
            case_id=case_id,
            original_path=rel_path,
            sha256=sha256_hash,
            width=width,
            height=height,
            file_size_bytes=len(raw_bytes),
            image_format=img_format,
            source_filename=clean_filename,
            ingested_at=now_iso,
            ingested_by=ingested_by,
            room=room,
            exif_orientation=exif_orientation,
        )

        # Update records.json and module_state.json
        records_path = case_dir / "photos" / "records.json"
        existing_records_raw = self._read_json(records_path, default=[])
        existing_records_raw.append(record.to_dict())
        self._atomic_write_json(records_path, existing_records_raw)

        # Re-fetch state and save photo meta
        state = self._load_module_state(case_id)
        state.setdefault("photos", {})[photo_id] = {
            "ref": record.ref,
            "sha256": record.sha256,
            "original_path": record.original_path,
        }
        self._save_module_state(case_id, state)

        return record

    def verify_photo_integrity(self, case_id: str, photo_id: str) -> bool:
        photo = self.get_photo(case_id, photo_id)
        case_dir = self._get_case_dir(case_id)
        original_full = case_dir / photo.original_path
        if not original_full.is_file():
            return False
        try:
            data = original_full.read_bytes()
            computed_sha = hashlib.sha256(data).hexdigest()
            return computed_sha == photo.sha256
        except Exception:
            return False

    def get_photo(self, case_id: str, photo_id: str) -> PhotoRecord:
        safe_photo = self._validate_safe_name(photo_id, "photo_id")
        photos = self.list_photos(case_id)
        for p in photos:
            if p.photo_id == safe_photo or p.ref == safe_photo:
                return p
        raise RecordNotFoundError(f"Photo '{photo_id}' not found in case '{case_id}'")

    def list_photos(self, case_id: str) -> list[PhotoRecord]:
        case_dir = self._get_case_dir(case_id)
        records_path = case_dir / "photos" / "records.json"
        raw = self._read_json(records_path, default=[])
        return [PhotoRecord.from_dict(d) for d in raw]

    def save_detection_run(self, case_id: str, run: DetectionRun) -> None:
        case_dir = self._get_case_dir(case_id)
        runs_path = case_dir / "detections" / "runs.json"
        runs_raw = self._read_json(runs_path, default=[])
        # Update or append
        updated = False
        for i, r in enumerate(runs_raw):
            if r.get("run_id") == run.run_id:
                runs_raw[i] = run.to_dict()
                updated = True
                break
        if not updated:
            runs_raw.append(run.to_dict())
        self._atomic_write_json(runs_path, runs_raw)

    def list_detection_runs(self, case_id: str) -> list[DetectionRun]:
        case_dir = self._get_case_dir(case_id)
        runs_path = case_dir / "detections" / "runs.json"
        runs_raw = self._read_json(runs_path, default=[])
        return [DetectionRun.from_dict(r) for r in runs_raw]

    def save_candidates(self, case_id: str, candidates: list[DetectionCandidate]) -> None:
        case_dir = self._get_case_dir(case_id)
        candidates_path = case_dir / "detections" / "candidates.json"
        existing = self._read_json(candidates_path, default=[])
        by_ref = {c["ref"]: c for c in existing}
        for cand in candidates:
            by_ref[cand.ref] = cand.to_dict()
        self._atomic_write_json(candidates_path, list(by_ref.values()))

    def get_candidate(self, case_id: str, det_ref: str) -> DetectionCandidate:
        candidates = self.list_candidates(case_id)
        for c in candidates:
            if c.ref == det_ref or c.det_id == det_ref:
                return c
        raise RecordNotFoundError(f"Candidate '{det_ref}' not found in case '{case_id}'")

    def list_candidates(
        self,
        case_id: str,
        photo_id: str | None = None,
        run_id: str | None = None,
    ) -> list[DetectionCandidate]:
        case_dir = self._get_case_dir(case_id)
        candidates_path = case_dir / "detections" / "candidates.json"
        raw = self._read_json(candidates_path, default=[])
        res = [DetectionCandidate.from_dict(d) for d in raw]
        if photo_id is not None:
            res = [c for c in res if c.photo_id == photo_id]
        if run_id is not None:
            res = [c for c in res if c.run_id == run_id]
        return res

    def update_candidate_disposition(
        self,
        case_id: str,
        det_ref: str,
        disposition: str,
        dismissal_reason: str | None = None,
        reviewer_id: str = "investigator",
    ) -> DetectionCandidate:
        candidate = self.get_candidate(case_id, det_ref)
        if disposition not in ("unreviewed", "confirmed", "dismissed"):
            raise InvalidTransitionError(f"Invalid disposition: '{disposition}'")
        if disposition == "dismissed":
            if not dismissal_reason or not isinstance(dismissal_reason, str) or not dismissal_reason.strip():
                raise InvalidTransitionError("dismissal_reason is required when disposition is 'dismissed'")

        # Raw detection fields must remain immutable
        prev_disp = candidate.disposition
        action_name = "confirmed" if disposition == "confirmed" else "dismissed" if disposition == "dismissed" else "corrected"

        updated = DetectionCandidate(
            det_id=candidate.det_id,
            ref=candidate.ref,
            photo_id=candidate.photo_id,
            run_id=candidate.run_id,
            class_id=candidate.class_id,
            class_name=candidate.class_name,
            confidence=candidate.confidence,
            bbox_xyxy=candidate.bbox_xyxy,
            image_width=candidate.image_width,
            image_height=candidate.image_height,
            normalized_bbox_xyxy=candidate.normalized_bbox_xyxy,
            disposition=disposition,  # type: ignore[arg-type]
            dismissal_reason=dismissal_reason if disposition == "dismissed" else None,
        )

        self.save_candidates(case_id, [updated])

        # Allocate review event
        state = self._load_module_state(case_id)
        event_id = self._allocate_review_event_id(state)
        self._save_module_state(case_id, state)

        rev_event = ReviewEvent(
            event_id=event_id,
            case_id=case_id,
            detection_ref=candidate.ref,
            action=action_name,  # type: ignore[arg-type]
            previous_disposition=prev_disp,
            resulting_disposition=disposition,  # type: ignore[arg-type]
            reviewer_id=reviewer_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=dismissal_reason if disposition == "dismissed" else None,
        )
        self.append_review_event(case_id, rev_event)
        return updated

    def save_evidence(self, case_id: str, evidence: EvidenceRecord, actor_id: str = "investigator") -> None:
        case_dir = self._get_case_dir(case_id)
        evidence_path = case_dir / "evidence" / "records.json"
        raw_list = self._read_json(evidence_path, default=[])
        by_ref = {e["ref"]: e for e in raw_list}
        is_new = evidence.ref not in by_ref
        by_ref[evidence.ref] = evidence.to_dict()
        self._atomic_write_json(evidence_path, list(by_ref.values()))

        # Record evidence event
        state = self._load_module_state(case_id)
        evd_id = self._allocate_evidence_event_id(state)
        self._save_module_state(case_id, state)

        action = "created" if is_new else "updated"
        event = EvidenceEvent(
            event_id=evd_id,
            case_id=case_id,
            evidence_ref=evidence.ref,
            action=action,  # type: ignore[arg-type]
            actor_id=actor_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details={"label": evidence.label, "source": evidence.creation_source},
        )
        self.append_evidence_event(case_id, event)

    def get_evidence(self, case_id: str, evidence_id_or_ref: str) -> EvidenceRecord:
        records = self.list_evidence(case_id)
        for e in records:
            if e.evidence_id == evidence_id_or_ref or e.ref == evidence_id_or_ref:
                return e
        raise RecordNotFoundError(f"Evidence '{evidence_id_or_ref}' not found in case '{case_id}'")

    def list_evidence(self, case_id: str) -> list[EvidenceRecord]:
        case_dir = self._get_case_dir(case_id)
        evidence_path = case_dir / "evidence" / "records.json"
        raw_list = self._read_json(evidence_path, default=[])
        return [EvidenceRecord.from_dict(d) for d in raw_list]

    def append_review_event(self, case_id: str, event: ReviewEvent) -> None:
        case_dir = self._get_case_dir(case_id)
        audit_path = case_dir / "audit" / "reviews.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
                f.flush()
        except Exception as exc:
            raise StorageError(f"Failed to append review event to {audit_path}: {exc}") from exc

    def list_review_events(self, case_id: str, detection_ref: str | None = None) -> list[ReviewEvent]:
        case_dir = self._get_case_dir(case_id)
        audit_path = case_dir / "audit" / "reviews.jsonl"
        if not audit_path.is_file():
            return []
        events: list[ReviewEvent] = []
        try:
            with audit_path.open("r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f, start=1):
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        data = json.loads(line_str)
                        ev = ReviewEvent.from_dict(data)
                        if detection_ref is None or ev.detection_ref == detection_ref:
                            events.append(ev)
                    except Exception as err:
                        raise StorageError(f"Corrupted review log entry at line {line_idx} in {audit_path}: {err}") from err
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"Failed reading review events: {exc}") from exc
        return events

    def append_evidence_event(self, case_id: str, event: EvidenceEvent) -> None:
        case_dir = self._get_case_dir(case_id)
        audit_path = case_dir / "audit" / "evidence_events.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
                f.flush()
        except Exception as exc:
            raise StorageError(f"Failed to append evidence event to {audit_path}: {exc}") from exc

    def list_evidence_events(self, case_id: str, evidence_ref: str | None = None) -> list[EvidenceEvent]:
        case_dir = self._get_case_dir(case_id)
        audit_path = case_dir / "audit" / "evidence_events.jsonl"
        if not audit_path.is_file():
            return []
        events: list[EvidenceEvent] = []
        try:
            with audit_path.open("r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f, start=1):
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        data = json.loads(line_str)
                        ev = EvidenceEvent.from_dict(data)
                        if evidence_ref is None or ev.evidence_ref == evidence_ref:
                            events.append(ev)
                    except Exception as err:
                        raise StorageError(f"Corrupted evidence event log entry at line {line_idx} in {audit_path}: {err}") from err
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"Failed reading evidence events: {exc}") from exc
        return events
