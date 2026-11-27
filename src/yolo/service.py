"""Detection orchestration service and candidate lifecycle management for Module 2 (YOLO)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from src.yolo.detector import DetectorBackend, DetectorConfig
from src.yolo.exceptions import (
    DetectorDependencyError,
    DetectorError,
    IntegrityError,
    InvalidTransitionError,
    RecordNotFoundError,
)
from src.yolo.exporter import ExportResult, export_case_context as _export_case_context
from src.yolo.models import (
    DetectionCandidate,
    DetectionRun,
    EvidenceEvent,
    EvidenceRecord,
    PhotoRecord,
    ReviewEvent,
)
from src.yolo.preview import (
    PreviewResult,
    normalize_bbox_xyxy,
    prepare_image_metadata,
    render_annotated_preview,
    validate_and_clip_bbox,
)
from src.yolo.store import YoloCaseStore


@dataclass
class DetectionRunResult:
    """Result bundle returned by YoloDetectionService.run_detection."""

    run: DetectionRun
    photo: PhotoRecord
    candidates: list[DetectionCandidate]
    preview: PreviewResult | None
    warnings: list[str]


class YoloDetectionService:
    """Orchestrates immutable photo ingestion, integrity checks, YOLO inference, and preview rendering."""

    def __init__(
        self,
        store: YoloCaseStore,
        detector: DetectorBackend,
        *,
        default_config: DetectorConfig | None = None,
        _pil_loader: Any = None,
    ) -> None:
        self.store = store
        self.detector = detector
        self.default_config = default_config or DetectorConfig()
        self._pil_loader = _pil_loader

    def register_photo(
        self,
        case_id: str,
        source_path: Path | str,
        *,
        ingested_by: str = "investigator_01",
        room: str | None = None,
        allow_duplicate_bytes: bool = False,
    ) -> PhotoRecord:
        """Ingests a photo into immutable case storage."""
        return self.store.ingest_photo(
            case_id,
            source_path=source_path,
            ingested_by=ingested_by,
            room=room,
            allow_duplicate_bytes=allow_duplicate_bytes,
        )

    def _build_preview_rel_path(self, photo: PhotoRecord, run_id: str, candidate_count: int) -> str:
        if candidate_count == 0:
            ext = Path(photo.original_path).suffix or ".png"
        else:
            ext = ".png"
        return f"photos/previews/{photo.photo_id}_{run_id}_annotated{ext}"

    def run_detection(
        self,
        case_id: str,
        photo_id: str,
        *,
        config: DetectorConfig | None = None,
        generate_preview: bool = True,
    ) -> DetectionRunResult:
        """Runs candidate detection on a registered photo, persisting run provenance, candidates, and preview."""
        photo = self.store.get_photo(case_id, photo_id)

        if not self.store.verify_photo_integrity(case_id, photo.photo_id):
            raise IntegrityError(
                f"Integrity verification failed for photo '{photo.photo_id}' in case '{case_id}'; inference aborted."
            )

        cfg = config or self.default_config
        case_dir = self.store._get_case_dir(case_id)
        original_abs_path = case_dir / photo.original_path

        meta = prepare_image_metadata(original_abs_path, target_size=cfg.image_size)
        run_id = self.store.allocate_run_id(case_id)

        try:
            output = self.detector.detect(original_abs_path, cfg)
        except (DetectorDependencyError, DetectorError) as exc:
            failed_run = DetectionRun(
                run_id=run_id,
                photo_id=photo.photo_id,
                case_id=case_id,
                model_name=getattr(self.detector, "model_name", cfg.model_name),
                model_version=getattr(
                    self.detector,
                    "model_version",
                    getattr(self.detector, "_model_version", "unknown"),
                ),
                weights_identifier=getattr(
                    self.detector,
                    "weights_identifier",
                    getattr(self.detector, "_weights_identifier", cfg.model_name),
                ),
                confidence_threshold=cfg.confidence_threshold,
                iou_threshold=cfg.iou_threshold,
                image_size=cfg.image_size,
                device=getattr(self.detector, "_device_resolved", cfg.device),
                executed_at=datetime.now(timezone.utc).isoformat(),
                status="failed",
                error_message=str(exc),
            )
            self.store.save_detection_run(case_id, failed_run)
            raise
        except Exception as exc:
            failed_run = DetectionRun(
                run_id=run_id,
                photo_id=photo.photo_id,
                case_id=case_id,
                model_name=getattr(self.detector, "model_name", cfg.model_name),
                model_version=getattr(
                    self.detector,
                    "model_version",
                    getattr(self.detector, "_model_version", "unknown"),
                ),
                weights_identifier=getattr(
                    self.detector,
                    "weights_identifier",
                    getattr(self.detector, "_weights_identifier", cfg.model_name),
                ),
                confidence_threshold=cfg.confidence_threshold,
                iou_threshold=cfg.iou_threshold,
                image_size=cfg.image_size,
                device=getattr(self.detector, "_device_resolved", cfg.device),
                executed_at=datetime.now(timezone.utc).isoformat(),
                status="failed",
                error_message=str(exc),
            )
            self.store.save_detection_run(case_id, failed_run)
            raise DetectorError(f"Unexpected detection failure on '{photo.photo_id}': {exc}") from exc

        warnings: list[str] = []
        new_candidates: list[DetectionCandidate] = []

        for pred in output.predictions:
            try:
                clipped_bbox = validate_and_clip_bbox(
                    pred.bbox_xyxy,
                    meta.display_width,
                    meta.display_height,
                )
            except (ValueError, DetectorError) as err:
                warnings.append(
                    f"Skipped out-of-bounds/zero-area prediction '{pred.class_name}' "
                    f"(conf={pred.confidence:.3f}, bbox={pred.bbox_xyxy}): {err}"
                )
                continue

            det_id, det_ref = self.store.allocate_detection_ref(case_id, photo.photo_id)
            norm_bbox = normalize_bbox_xyxy(clipped_bbox, meta.display_width, meta.display_height)

            candidate = DetectionCandidate(
                det_id=det_id,
                ref=det_ref,
                photo_id=photo.photo_id,
                run_id=run_id,
                class_id=pred.class_id,
                class_name=pred.class_name,
                confidence=pred.confidence,
                bbox_xyxy=clipped_bbox,
                image_width=meta.display_width,
                image_height=meta.display_height,
                normalized_bbox_xyxy=norm_bbox,
                disposition="unreviewed",
                dismissal_reason=None,
            )
            new_candidates.append(candidate)

        self.store.save_candidates(case_id, new_candidates)

        preview_result: PreviewResult | None = None
        rel_preview_path: str | None = None
        if generate_preview:
            rel_preview_path = self._build_preview_rel_path(photo, run_id, len(new_candidates))
            preview_abs_path = case_dir / rel_preview_path
            preview_result = render_annotated_preview(
                original_abs_path,
                preview_abs_path,
                new_candidates,
                exif_orientation=photo.exif_orientation,
                _pil_loader=self._pil_loader,
            )

        if output.truncation_warning:
            warnings.append(output.truncation_warning)

        completed_run = DetectionRun(
            run_id=run_id,
            photo_id=photo.photo_id,
            case_id=case_id,
            model_name=output.provenance.model_name,
            model_version=output.provenance.model_version,
            weights_identifier=output.provenance.weights_identifier,
            confidence_threshold=output.provenance.confidence_threshold,
            iou_threshold=output.provenance.iou_threshold,
            image_size=output.provenance.image_size,
            device=output.provenance.device_resolved,
            executed_at=datetime.now(timezone.utc).isoformat(),
            status="completed",
            truncated=output.truncated,
            truncation_warning=output.truncation_warning,
            preview_path=rel_preview_path,
        )
        self.store.save_detection_run(case_id, completed_run)

        return DetectionRunResult(
            run=completed_run,
            photo=photo,
            candidates=new_candidates,
            preview=preview_result,
            warnings=warnings,
        )

    def list_photos(self, case_id: str) -> list[PhotoRecord]:
        return self.store.list_photos(case_id)

    def list_detection_runs(self, case_id: str, photo_id: str | None = None) -> list[DetectionRun]:
        runs = self.store.list_detection_runs(case_id)
        if photo_id is not None:
            runs = [r for r in runs if r.photo_id == photo_id]
        return runs

    def list_candidates(
        self,
        case_id: str,
        *,
        photo_id: str | None = None,
        run_id: str | None = None,
        disposition: str | None = None,
    ) -> list[DetectionCandidate]:
        cands = self.store.list_candidates(case_id, photo_id=photo_id, run_id=run_id)
        if disposition is not None:
            cands = [c for c in cands if c.disposition == disposition]
        return cands

    def verify_case_photo_integrity(self, case_id: str) -> dict[str, bool]:
        photos = self.store.list_photos(case_id)
        return {p.photo_id: self.store.verify_photo_integrity(case_id, p.photo_id) for p in photos}

    def regenerate_preview(
        self,
        case_id: str,
        photo_id: str,
        *,
        run_id: str | None = None,
    ) -> PreviewResult:
        """Re-renders a fresh annotated preview from the immutable original for the specified or latest completed run."""
        photo = self.store.get_photo(case_id, photo_id)
        if not self.store.verify_photo_integrity(case_id, photo.photo_id):
            raise IntegrityError(
                f"Integrity verification failed for photo '{photo.photo_id}' in case '{case_id}'; preview aborted."
            )

        completed_runs = [
            r
            for r in self.store.list_detection_runs(case_id)
            if r.photo_id == photo.photo_id and r.status == "completed"
        ]
        if run_id is not None:
            matching = [r for r in completed_runs if r.run_id == run_id]
            if not matching:
                raise RecordNotFoundError(
                    f"Completed detection run '{run_id}' for photo '{photo.photo_id}' not found in case '{case_id}'"
                )
            target_run = matching[0]
        else:
            if not completed_runs:
                raise RecordNotFoundError(
                    f"No completed detection runs found for photo '{photo.photo_id}' in case '{case_id}'"
                )
            target_run = completed_runs[-1]

        cands = self.store.list_candidates(case_id, photo_id=photo.photo_id, run_id=target_run.run_id)
        case_dir = self.store._get_case_dir(case_id)
        original_abs_path = case_dir / photo.original_path

        rel_preview_path = target_run.preview_path or self._build_preview_rel_path(
            photo, target_run.run_id, len(cands)
        )
        preview_abs_path = case_dir / rel_preview_path

        result = render_annotated_preview(
            original_abs_path,
            preview_abs_path,
            cands,
            exif_orientation=photo.exif_orientation,
            _pil_loader=self._pil_loader,
        )

        if target_run.preview_path is None:
            updated_run = DetectionRun(
                run_id=target_run.run_id,
                photo_id=target_run.photo_id,
                case_id=target_run.case_id,
                model_name=target_run.model_name,
                model_version=target_run.model_version,
                weights_identifier=target_run.weights_identifier,
                confidence_threshold=target_run.confidence_threshold,
                iou_threshold=target_run.iou_threshold,
                image_size=target_run.image_size,
                device=target_run.device,
                executed_at=target_run.executed_at,
                status=target_run.status,
                truncated=target_run.truncated,
                truncation_warning=target_run.truncation_warning,
                error_message=target_run.error_message,
                preview_path=rel_preview_path,
            )
            self.store.save_detection_run(case_id, updated_run)

        return result


    # --------------------------------------------------------------------------
    # Stage Y5: Investigator Review Transitions
    # --------------------------------------------------------------------------

    def confirm_detection(
        self,
        case_id: str,
        detection_ref: str,
        *,
        reviewer_id: str = "investigator_01",
        regenerate_preview: bool = False,
    ) -> tuple[DetectionCandidate, ReviewEvent]:
        """Confirms an unreviewed detection candidate and appends an audit ReviewEvent."""
        candidate = self.store.get_candidate(case_id, detection_ref)
        if candidate.disposition != "unreviewed":
            raise InvalidTransitionError(
                f"Cannot confirm detection '{candidate.ref}': current disposition is '{candidate.disposition}' (expected 'unreviewed')."
            )

        updated = self.store.update_candidate_disposition(
            case_id,
            candidate.ref,
            "confirmed",
            dismissal_reason=None,
            reviewer_id=reviewer_id,
        )
        if regenerate_preview:
            self.regenerate_preview(case_id, candidate.photo_id, run_id=candidate.run_id)
        rev_event = self.store.list_review_events(case_id, detection_ref=candidate.ref)[-1]
        return updated, rev_event

    def dismiss_detection(
        self,
        case_id: str,
        detection_ref: str,
        reason: str,
        *,
        reviewer_id: str = "investigator_01",
        regenerate_preview: bool = False,
    ) -> tuple[DetectionCandidate, ReviewEvent]:
        """Dismisses an unreviewed detection candidate with a mandatory non-empty reason."""
        candidate = self.store.get_candidate(case_id, detection_ref)
        if candidate.disposition != "unreviewed":
            raise InvalidTransitionError(
                f"Cannot dismiss detection '{candidate.ref}': current disposition is '{candidate.disposition}' (expected 'unreviewed')."
            )
        if not reason or not isinstance(reason, str) or not reason.strip():
            raise InvalidTransitionError("Dismissal reason must be non-empty.")

        updated = self.store.update_candidate_disposition(
            case_id,
            candidate.ref,
            "dismissed",
            dismissal_reason=reason.strip(),
            reviewer_id=reviewer_id,
        )
        if regenerate_preview:
            self.regenerate_preview(case_id, candidate.photo_id, run_id=candidate.run_id)
        rev_event = self.store.list_review_events(case_id, detection_ref=candidate.ref)[-1]
        return updated, rev_event

    def correct_review_decision(
        self,
        case_id: str,
        detection_ref: str,
        new_disposition: str,
        *,
        reason: str | None = None,
        reviewer_id: str = "investigator_01",
        regenerate_preview: bool = False,
    ) -> tuple[DetectionCandidate, ReviewEvent]:
        """Applies a controlled superseding review correction (confirmed <-> dismissed) with append-only audit."""
        candidate = self.store.get_candidate(case_id, detection_ref)
        if candidate.disposition == "unreviewed":
            raise InvalidTransitionError(
                f"Cannot correct unreviewed detection '{candidate.ref}'; use confirm_detection or dismiss_detection."
            )
        if new_disposition not in ("confirmed", "dismissed"):
            raise InvalidTransitionError(
                f"Invalid correction disposition '{new_disposition}'; expected 'confirmed' or 'dismissed'."
            )
        if new_disposition == candidate.disposition:
            raise InvalidTransitionError(
                f"Detection '{candidate.ref}' already has disposition '{candidate.disposition}'."
            )

        clean_reason = reason.strip() if isinstance(reason, str) and reason.strip() else None
        if new_disposition == "dismissed":
            if not clean_reason:
                raise InvalidTransitionError("A non-empty reason is required when correcting disposition to 'dismissed'.")
            linked_ev = [ev.ref for ev in self.store.list_evidence(case_id) if candidate.ref in ev.det_refs]
            if linked_ev:
                raise InvalidTransitionError(
                    f"Cannot dismiss detection '{candidate.ref}' while linked to evidence {linked_ev}; unlink it first."
                )

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
            disposition=new_disposition,  # type: ignore[arg-type]
            dismissal_reason=clean_reason if new_disposition == "dismissed" else None,
        )
        self.store.save_candidates(case_id, [updated])

        state = self.store._load_module_state(case_id)
        event_id = self.store._allocate_review_event_id(state)
        self.store._save_module_state(case_id, state)

        rev_event = ReviewEvent(
            event_id=event_id,
            case_id=case_id,
            detection_ref=candidate.ref,
            action="corrected",
            previous_disposition=candidate.disposition,
            resulting_disposition=new_disposition,  # type: ignore[arg-type]
            reviewer_id=reviewer_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=clean_reason,
        )
        self.store.append_review_event(case_id, rev_event)

        if regenerate_preview:
            self.regenerate_preview(case_id, candidate.photo_id, run_id=candidate.run_id)
        return updated, rev_event

    def list_review_history(
        self,
        case_id: str,
        *,
        detection_ref: str | None = None,
    ) -> list[ReviewEvent]:
        return self.store.list_review_events(case_id, detection_ref=detection_ref)

    # --------------------------------------------------------------------------
    # Stage Y5: Evidence Management & Multi-Photo / Multi-Detection Linking
    # --------------------------------------------------------------------------

    def _persist_updated_evidence(
        self,
        case_id: str,
        evidence: EvidenceRecord,
        action: Literal["created", "updated", "linked_photo", "linked_detection", "unlinked_detection"],
        actor_id: str,
        details: dict[str, Any],
    ) -> EvidenceEvent:
        case_dir = self.store._get_case_dir(case_id)
        evidence_path = case_dir / "evidence" / "records.json"
        raw_list = self.store._read_json(evidence_path, default=[])
        by_ref = {e["ref"]: e for e in raw_list}
        by_ref[evidence.ref] = evidence.to_dict()
        self.store._atomic_write_json(evidence_path, list(by_ref.values()))

        state = self.store._load_module_state(case_id)
        evd_id = self.store._allocate_evidence_event_id(state)
        self.store._save_module_state(case_id, state)

        event = EvidenceEvent(
            event_id=evd_id,
            case_id=case_id,
            evidence_ref=evidence.ref,
            action=action,
            actor_id=actor_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=details,
        )
        self.store.append_evidence_event(case_id, event)
        return event

    def promote_detection_to_evidence(
        self,
        case_id: str,
        detection_ref: str,
        *,
        label: str | None = None,
        description: str = "",
        created_by: str = "investigator_01",
        evidence_id: str | None = None,
    ) -> tuple[EvidenceRecord, EvidenceEvent]:
        """Promotes a confirmed detection into a new EvidenceRecord or links it to an existing one."""
        candidate = self.store.get_candidate(case_id, detection_ref)
        if candidate.disposition != "confirmed":
            raise InvalidTransitionError(
                f"Only 'confirmed' detections can be promoted to evidence; '{candidate.ref}' is '{candidate.disposition}'."
            )

        if evidence_id is not None:
            return self.link_detection_to_evidence(
                case_id,
                evidence_id,
                candidate.ref,
                actor_id=created_by,
            )

        existing_links = [ev.ref for ev in self.store.list_evidence(case_id) if candidate.ref in ev.det_refs]
        if existing_links:
            raise InvalidTransitionError(
                f"Detection '{candidate.ref}' is already linked to evidence {existing_links}; pass evidence_id to link explicitly."
            )

        resolved_label = (label if label is not None else candidate.class_name).strip()
        if not resolved_label:
            raise ValueError("Evidence label must be a non-empty string.")

        ev_id, ev_ref = self.store.allocate_evidence_id(case_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        record = EvidenceRecord(
            evidence_id=ev_id,
            ref=ev_ref,
            case_id=case_id,
            label=resolved_label,
            description=description,
            creation_source="detection_promoted",
            photo_refs=[f"photos.{candidate.photo_id}"],
            det_refs=[candidate.ref],
            created_by=created_by,
            created_at=now_iso,
            updated_at=now_iso,
        )
        self.store.save_evidence(case_id, record, actor_id=created_by)
        event = self.store.list_evidence_events(case_id, evidence_ref=record.ref)[-1]
        return record, event

    def link_detection_to_evidence(
        self,
        case_id: str,
        evidence_id: str,
        detection_ref: str,
        *,
        actor_id: str = "investigator_01",
    ) -> tuple[EvidenceRecord, EvidenceEvent]:
        """Links an additional confirmed detection to an existing EvidenceRecord."""
        evidence = self.store.get_evidence(case_id, evidence_id)
        candidate = self.store.get_candidate(case_id, detection_ref)
        if candidate.disposition != "confirmed":
            raise InvalidTransitionError(
                f"Only 'confirmed' detections can be linked to evidence; '{candidate.ref}' is '{candidate.disposition}'."
            )
        if candidate.ref in evidence.det_refs:
            raise InvalidTransitionError(
                f"Detection '{candidate.ref}' is already linked to evidence '{evidence.ref}'."
            )

        photo_ref = f"photos.{candidate.photo_id}"
        new_det_refs = [*evidence.det_refs, candidate.ref]
        new_photo_refs = (
            list(evidence.photo_refs)
            if photo_ref in evidence.photo_refs
            else [*evidence.photo_refs, photo_ref]
        )

        updated = EvidenceRecord(
            evidence_id=evidence.evidence_id,
            ref=evidence.ref,
            case_id=evidence.case_id,
            label=evidence.label,
            description=evidence.description,
            creation_source=evidence.creation_source,
            photo_refs=new_photo_refs,
            det_refs=new_det_refs,
            created_by=evidence.created_by,
            created_at=evidence.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        event = self._persist_updated_evidence(
            case_id,
            updated,
            "linked_detection",
            actor_id,
            {"detection_ref": candidate.ref, "photo_ref": photo_ref},
        )
        return updated, event

    def link_photo_to_evidence(
        self,
        case_id: str,
        evidence_id: str,
        photo_id_or_ref: str,
        *,
        actor_id: str = "investigator_01",
    ) -> tuple[EvidenceRecord, EvidenceEvent]:
        """Links a registered photo to an existing EvidenceRecord."""
        evidence = self.store.get_evidence(case_id, evidence_id)
        photo = self.store.get_photo(case_id, photo_id_or_ref)
        if photo.ref in evidence.photo_refs:
            raise InvalidTransitionError(
                f"Photo '{photo.ref}' is already linked to evidence '{evidence.ref}'."
            )

        updated = EvidenceRecord(
            evidence_id=evidence.evidence_id,
            ref=evidence.ref,
            case_id=evidence.case_id,
            label=evidence.label,
            description=evidence.description,
            creation_source=evidence.creation_source,
            photo_refs=[*evidence.photo_refs, photo.ref],
            det_refs=list(evidence.det_refs),
            created_by=evidence.created_by,
            created_at=evidence.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        event = self._persist_updated_evidence(
            case_id,
            updated,
            "linked_photo",
            actor_id,
            {"photo_ref": photo.ref},
        )
        return updated, event

    def unlink_detection_from_evidence(
        self,
        case_id: str,
        evidence_id: str,
        detection_ref: str,
        *,
        reason: str,
        actor_id: str = "investigator_01",
    ) -> tuple[EvidenceRecord, EvidenceEvent]:
        """Unlinks a detection from an EvidenceRecord with a mandatory audit reason."""
        if not reason or not isinstance(reason, str) or not reason.strip():
            raise InvalidTransitionError("A non-empty reason is required when unlinking a detection from evidence.")
        evidence = self.store.get_evidence(case_id, evidence_id)
        if detection_ref not in evidence.det_refs:
            raise InvalidTransitionError(
                f"Detection '{detection_ref}' is not linked to evidence '{evidence.ref}'."
            )

        new_det_refs = [ref for ref in evidence.det_refs if ref != detection_ref]
        updated = EvidenceRecord(
            evidence_id=evidence.evidence_id,
            ref=evidence.ref,
            case_id=evidence.case_id,
            label=evidence.label,
            description=evidence.description,
            creation_source=evidence.creation_source,
            photo_refs=list(evidence.photo_refs),
            det_refs=new_det_refs,
            created_by=evidence.created_by,
            created_at=evidence.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        event = self._persist_updated_evidence(
            case_id,
            updated,
            "unlinked_detection",
            actor_id,
            {"detection_ref": detection_ref, "reason": reason.strip()},
        )
        return updated, event

    def create_manual_evidence(
        self,
        case_id: str,
        label: str,
        description: str = "",
        *,
        photo_refs: list[str] | None = None,
        created_by: str = "investigator_01",
    ) -> tuple[EvidenceRecord, EvidenceEvent]:
        """Creates an investigator-authored manual EvidenceRecord without requiring YOLO detections."""
        if not label or not isinstance(label, str) or not label.strip():
            raise ValueError("Evidence label must be a non-empty string.")

        normalized_photo_refs: list[str] = []
        seen: set[str] = set()
        for p_ref in (photo_refs or []):
            photo = self.store.get_photo(case_id, p_ref)
            if photo.ref not in seen:
                seen.add(photo.ref)
                normalized_photo_refs.append(photo.ref)

        ev_id, ev_ref = self.store.allocate_evidence_id(case_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        record = EvidenceRecord(
            evidence_id=ev_id,
            ref=ev_ref,
            case_id=case_id,
            label=label.strip(),
            description=description,
            creation_source="manual",
            photo_refs=normalized_photo_refs,
            det_refs=[],
            created_by=created_by,
            created_at=now_iso,
            updated_at=now_iso,
        )
        self.store.save_evidence(case_id, record, actor_id=created_by)
        event = self.store.list_evidence_events(case_id, evidence_ref=record.ref)[-1]
        return record, event

    def update_evidence(
        self,
        case_id: str,
        evidence_id: str,
        *,
        label: str | None = None,
        description: str | None = None,
        actor_id: str = "investigator_01",
    ) -> tuple[EvidenceRecord, EvidenceEvent]:
        """Updates label and/or description of an existing EvidenceRecord with audit logging."""
        if label is None and description is None:
            raise ValueError("At least one of label or description must be provided.")
        if label is not None and (not isinstance(label, str) or not label.strip()):
            raise ValueError("Evidence label must be a non-empty string.")

        evidence = self.store.get_evidence(case_id, evidence_id)
        previous = {"label": evidence.label, "description": evidence.description}
        new_label = label.strip() if label is not None else evidence.label
        new_description = description if description is not None else evidence.description

        updated = EvidenceRecord(
            evidence_id=evidence.evidence_id,
            ref=evidence.ref,
            case_id=evidence.case_id,
            label=new_label,
            description=new_description,
            creation_source=evidence.creation_source,
            photo_refs=list(evidence.photo_refs),
            det_refs=list(evidence.det_refs),
            created_by=evidence.created_by,
            created_at=evidence.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        event = self._persist_updated_evidence(
            case_id,
            updated,
            "updated",
            actor_id,
            {"previous": previous, "updated": {"label": new_label, "description": new_description}},
        )
        return updated, event

    def get_evidence(self, case_id: str, evidence_id: str) -> EvidenceRecord:
        return self.store.get_evidence(case_id, evidence_id)

    def list_evidence(self, case_id: str) -> list[EvidenceRecord]:
        return self.store.list_evidence(case_id)

    def list_evidence_history(
        self,
        case_id: str,
        *,
        evidence_ref: str | None = None,
    ) -> list[EvidenceEvent]:
        return self.store.list_evidence_events(case_id, evidence_ref=evidence_ref)


    # --------------------------------------------------------------------------
    # Stage Y6: Case-Context Export
    # --------------------------------------------------------------------------

    def export_case_context(self, case_id: str, **kwargs: Any) -> ExportResult:
        """Exports Module 2 case state into a schema-validated Module 1 case_context."""
        return _export_case_context(self.store, case_id, **kwargs)
