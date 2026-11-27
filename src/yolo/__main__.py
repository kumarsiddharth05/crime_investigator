"""Deterministic menu-driven CLI for Module 2 (YOLO Detection & Evidence Management)."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from src.yolo.detector import DetectorBackend, DetectorConfig, StubDetectorBackend, UltralyticsYOLOBackend
from src.yolo.exceptions import YoloModuleError
from src.yolo.service import YoloDetectionService
from src.yolo.store import YoloCaseStore


@dataclass
class ActionResult:
    """Structured action envelope returned by each CLI menu operation."""

    action: str
    case_id: str | None
    status: Literal["completed", "completed_with_warnings", "failed"]
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    available_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class YoloCLI:
    """Interactive deterministic menu CLI wrapping YoloDetectionService."""

    MENU_OPTIONS: tuple[tuple[str, str], ...] = (
        ("1", "Select / Set Case ID"),
        ("2", "Register Photograph"),
        ("3", "List Photographs"),
        ("4", "Run Detection"),
        ("5", "View Detections"),
        ("6", "Review Detection (Confirm / Dismiss / Correct)"),
        ("7", "Promote Confirmed Detection to Evidence"),
        ("8", "Create Manual Evidence"),
        ("9", "Link Photograph / Manage Evidence"),
        ("10", "Export Validated case_context JSON"),
        ("11", "Verify Original-Image SHA-256 Integrity"),
        ("12", "View History (Runs, Reviews, Evidence Events)"),
        ("13", "Exit"),
    )

    def __init__(
        self,
        service: YoloDetectionService,
        *,
        case_id: str | None = None,
        actor_id: str = "investigator_01",
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> None:
        self.service = service
        self.case_id = case_id.strip() if isinstance(case_id, str) and case_id.strip() else None
        self.actor_id = actor_id.strip() or "investigator_01"
        self.input_fn = input_fn
        self.output_fn = output_fn
        self.history: list[ActionResult] = []

    def _emit(self, text: str = "") -> None:
        self.output_fn(text)

    def _prompt(self, label: str) -> str:
        return self.input_fn(label).strip()

    def compute_available_actions(self) -> list[str]:
        """Deterministically computes valid next actions from current case state."""
        actions = ["select_case", "exit"]
        if not self.case_id:
            return actions

        actions.extend(["register_photo", "create_manual_evidence", "view_history"])
        photos = self.service.list_photos(self.case_id)
        if photos:
            actions.extend(["list_photos", "run_detection", "verify_integrity", "export_case_context"])
        else:
            actions.append("export_case_context")

        candidates = self.service.list_candidates(self.case_id)
        if candidates:
            actions.extend(["view_detections", "review_detection"])
        if any(c.disposition == "confirmed" for c in candidates):
            actions.append("promote_detection")

        evidence = self.service.list_evidence(self.case_id)
        if evidence:
            actions.append("manage_evidence")

        return actions

    def _make_result(
        self,
        action: str,
        status: Literal["completed", "completed_with_warnings", "failed"],
        *,
        data: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> ActionResult:
        res = ActionResult(
            action=action,
            case_id=self.case_id,
            status=status,
            data=data or {},
            warnings=warnings or [],
            errors=errors or [],
            available_actions=self.compute_available_actions(),
        )
        self.history.append(res)
        return res

    def _require_case(self, action: str) -> bool:
        if self.case_id:
            return True
        msg = "No active case selected. Choose option 1 (Select / Set Case ID) first."
        self._emit(f"[ERROR] {msg}")
        self._make_result(action, "failed", errors=[msg])
        return False

    def _print_menu(self) -> None:
        self._emit("")
        self._emit("=== Module 2: YOLO Detection & Evidence Management ===")
        self._emit(f"Active Case: {self.case_id or '(none)'} | Actor: {self.actor_id}")
        for key, label in self.MENU_OPTIONS:
            self._emit(f"  [{key}] {label}")

    def _action_select_case(self) -> ActionResult:
        raw = self._prompt("Enter Case ID (or blank/B to cancel): ")
        if not raw or raw.upper() == "B":
            self._emit("Cancelled case selection.")
            return self._make_result("select_case", "completed", data={"cancelled": True})
        self.service.store._validate_safe_name(raw, "case_id")
        self.case_id = raw
        self._emit(f"Active case set to: {self.case_id}")
        return self._make_result("select_case", "completed", data={"case_id": self.case_id})

    def _action_register_photo(self) -> ActionResult:
        if not self._require_case("register_photo"):
            return self.history[-1]
        assert self.case_id is not None

        src = self._prompt("Source image path (or blank/B to cancel): ")
        if not src or src.upper() == "B":
            self._emit("Cancelled photo registration.")
            return self._make_result("register_photo", "completed", data={"cancelled": True})

        room_raw = self._prompt("Room label (optional, blank for none): ")
        room = room_raw if room_raw else None
        dup_raw = self._prompt("Allow duplicate bytes? [y/N]: ").lower()
        allow_dup = dup_raw in ("y", "yes")

        photo = self.service.register_photo(
            self.case_id,
            src,
            ingested_by=self.actor_id,
            room=room,
            allow_duplicate_bytes=allow_dup,
        )
        self._emit(
            f"Registered {photo.ref} ({photo.width}x{photo.height}, {photo.image_format}, sha256={photo.sha256[:12]}...)"
        )
        return self._make_result("register_photo", "completed", data={"photo": photo.to_dict()})

    def _action_list_photos(self) -> ActionResult:
        if not self._require_case("list_photos"):
            return self.history[-1]
        assert self.case_id is not None

        photos = self.service.list_photos(self.case_id)
        if not photos:
            self._emit("No photos registered in this case.")
        for p in photos:
            self._emit(
                f"  {p.ref} | {p.width}x{p.height} | room={p.room or '-'} | exif={p.exif_orientation or '-'} | {p.original_path}"
            )
        return self._make_result("list_photos", "completed", data={"count": len(photos), "photos": [p.photo_id for p in photos]})

    def _action_run_detection(self) -> ActionResult:
        if not self._require_case("run_detection"):
            return self.history[-1]
        assert self.case_id is not None

        photo_id = self._prompt("Photo ID or ref (e.g. P1, or blank/B to cancel): ")
        if not photo_id or photo_id.upper() == "B":
            self._emit("Cancelled detection.")
            return self._make_result("run_detection", "completed", data={"cancelled": True})

        conf_raw = self._prompt(
            f"Confidence threshold override (blank for {self.service.default_config.confidence_threshold}): "
        )
        iou_raw = self._prompt(
            f"IoU threshold override (blank for {self.service.default_config.iou_threshold}): "
        )
        base_cfg = self.service.default_config
        cfg = DetectorConfig(
            model_name=base_cfg.model_name,
            confidence_threshold=float(conf_raw) if conf_raw else base_cfg.confidence_threshold,
            iou_threshold=float(iou_raw) if iou_raw else base_cfg.iou_threshold,
            image_size=base_cfg.image_size,
            max_candidates=base_cfg.max_candidates,
            device=base_cfg.device,
        )

        run_res = self.service.run_detection(self.case_id, photo_id, config=cfg)
        self._emit(
            f"Run {run_res.run.run_id} completed on {run_res.photo.ref}: {len(run_res.candidates)} candidate(s)."
        )
        for w in run_res.warnings:
            self._emit(f"  [WARNING] {w}")
        status: Literal["completed", "completed_with_warnings"] = (
            "completed_with_warnings" if run_res.warnings else "completed"
        )
        return self._make_result(
            "run_detection",
            status,
            data={
                "run_id": run_res.run.run_id,
                "candidate_refs": [c.ref for c in run_res.candidates],
                "preview_path": run_res.run.preview_path,
            },
            warnings=run_res.warnings,
        )

    def _action_view_detections(self) -> ActionResult:
        if not self._require_case("view_detections"):
            return self.history[-1]
        assert self.case_id is not None

        photo_filter = self._prompt("Filter by Photo ID (blank for all): ") or None
        disp_filter = self._prompt("Filter by disposition [unreviewed/confirmed/dismissed] (blank for all): ") or None
        cands = self.service.list_candidates(self.case_id, photo_id=photo_filter, disposition=disp_filter)
        if not cands:
            self._emit("No matching detection candidates found.")
        for c in cands:
            self._emit(
                f"  {c.ref} | {c.class_name} ({c.confidence:.2f}) | {c.disposition} | reason={c.dismissal_reason or '-'}"
            )
        return self._make_result("view_detections", "completed", data={"count": len(cands), "refs": [c.ref for c in cands]})

    def _action_review_detection(self) -> ActionResult:
        if not self._require_case("review_detection"):
            return self.history[-1]
        assert self.case_id is not None

        det_ref = self._prompt("Detection ref (e.g. photos.P1.d1, or blank/B to skip): ")
        if not det_ref or det_ref.upper() == "B":
            self._emit("Skipped detection review.")
            return self._make_result("review_detection", "completed", data={"skipped": True})

        decision = self._prompt("Action [C=confirm, D=dismiss, R=correct, B=cancel]: ").upper()
        if not decision or decision == "B":
            self._emit("Cancelled detection review.")
            return self._make_result("review_detection", "completed", data={"cancelled": True})

        if decision == "C":
            cand, ev = self.service.confirm_detection(self.case_id, det_ref, reviewer_id=self.actor_id)
        elif decision == "D":
            reason = self._prompt("Mandatory dismissal reason: ")
            cand, ev = self.service.dismiss_detection(self.case_id, det_ref, reason, reviewer_id=self.actor_id)
        elif decision == "R":
            new_disp = self._prompt("New disposition [confirmed/dismissed]: ").lower()
            reason = self._prompt("Correction reason (mandatory if dismissed): ")
            cand, ev = self.service.correct_review_decision(
                self.case_id,
                det_ref,
                new_disp,
                reason=reason or None,
                reviewer_id=self.actor_id,
            )
        else:
            msg = f"Invalid review option '{decision}'."
            self._emit(f"[ERROR] {msg}")
            return self._make_result("review_detection", "failed", errors=[msg])

        self._emit(f"Updated {cand.ref} -> {cand.disposition} (event {ev.event_id}).")
        return self._make_result(
            "review_detection",
            "completed",
            data={"det_ref": cand.ref, "disposition": cand.disposition, "event_id": ev.event_id},
        )

    def _action_promote_detection(self) -> ActionResult:
        if not self._require_case("promote_detection"):
            return self.history[-1]
        assert self.case_id is not None

        det_ref = self._prompt("Confirmed detection ref (or blank/B to cancel): ")
        if not det_ref or det_ref.upper() == "B":
            self._emit("Cancelled promotion.")
            return self._make_result("promote_detection", "completed", data={"cancelled": True})

        ev_id_raw = self._prompt("Existing Evidence ID to link (blank to create new): ")
        ev_id = ev_id_raw if ev_id_raw else None
        label: str | None = None
        description = ""
        if ev_id is None:
            label_raw = self._prompt("Evidence label (blank to use detection class): ")
            label = label_raw if label_raw else None
            description = self._prompt("Description (optional): ")

        record, event = self.service.promote_detection_to_evidence(
            self.case_id,
            det_ref,
            label=label,
            description=description,
            created_by=self.actor_id,
            evidence_id=ev_id,
        )
        self._emit(f"Evidence {record.ref} ('{record.label}') updated ({event.action}, event {event.event_id}).")
        return self._make_result(
            "promote_detection",
            "completed",
            data={"evidence_ref": record.ref, "event_id": event.event_id},
        )

    def _action_create_manual_evidence(self) -> ActionResult:
        if not self._require_case("create_manual_evidence"):
            return self.history[-1]
        assert self.case_id is not None

        label = self._prompt("Manual evidence label (or blank/B to cancel): ")
        if not label or label.upper() == "B":
            self._emit("Cancelled manual evidence creation.")
            return self._make_result("create_manual_evidence", "completed", data={"cancelled": True})

        description = self._prompt("Description (optional): ")
        photos_raw = self._prompt("Comma-separated photo IDs/refs (optional, blank for none): ")
        photo_refs = [p.strip() for p in photos_raw.split(",") if p.strip()] if photos_raw else None

        record, event = self.service.create_manual_evidence(
            self.case_id,
            label,
            description=description,
            photo_refs=photo_refs,
            created_by=self.actor_id,
        )
        self._emit(f"Created manual evidence {record.ref} ('{record.label}', event {event.event_id}).")
        return self._make_result(
            "create_manual_evidence",
            "completed",
            data={"evidence_ref": record.ref, "event_id": event.event_id},
        )

    def _action_manage_evidence(self) -> ActionResult:
        if not self._require_case("manage_evidence"):
            return self.history[-1]
        assert self.case_id is not None

        ev_id = self._prompt("Evidence ID or ref (e.g. E1, or blank/B to cancel): ")
        if not ev_id or ev_id.upper() == "B":
            self._emit("Cancelled evidence management.")
            return self._make_result("manage_evidence", "completed", data={"cancelled": True})

        op = self._prompt("Operation [P=link photo, U=update label/desc, X=unlink detection, B=cancel]: ").upper()
        if not op or op == "B":
            self._emit("Cancelled evidence operation.")
            return self._make_result("manage_evidence", "completed", data={"cancelled": True})

        if op == "P":
            photo_ref = self._prompt("Photo ID or ref to link (e.g. P2): ")
            record, event = self.service.link_photo_to_evidence(
                self.case_id, ev_id, photo_ref, actor_id=self.actor_id
            )
        elif op == "U":
            label_raw = self._prompt("New label (blank to keep current): ")
            desc_raw = self._prompt("New description (blank to keep current): ")
            record, event = self.service.update_evidence(
                self.case_id,
                ev_id,
                label=label_raw or None,
                description=desc_raw or None,
                actor_id=self.actor_id,
            )
        elif op == "X":
            det_ref = self._prompt("Detection ref to unlink: ")
            reason = self._prompt("Mandatory unlink reason: ")
            record, event = self.service.unlink_detection_from_evidence(
                self.case_id, ev_id, det_ref, reason=reason, actor_id=self.actor_id
            )
        else:
            msg = f"Invalid evidence operation '{op}'."
            self._emit(f"[ERROR] {msg}")
            return self._make_result("manage_evidence", "failed", errors=[msg])

        self._emit(f"Evidence {record.ref} updated ({event.action}, event {event.event_id}).")
        return self._make_result(
            "manage_evidence",
            "completed",
            data={"evidence_ref": record.ref, "event_id": event.event_id},
        )

    def _action_export_case_context(self) -> ActionResult:
        if not self._require_case("export_case_context"):
            return self.history[-1]
        assert self.case_id is not None

        exported = self.service.export_case_context(self.case_id)
        out_path_raw = self._prompt("Optional output JSON path (blank to skip writing file): ")
        written_path: str | None = None
        if out_path_raw:
            out_p = Path(out_path_raw)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(json.dumps(exported.case_context, indent=2), encoding="utf-8")
            written_path = str(out_p)
            self._emit(f"Exported validated case_context to: {written_path}")

        self._emit(
            f"Export summary: {len(exported.case_context['photos'])} photo(s), "
            f"{len(exported.case_context['evidence'])} evidence item(s), "
            f"{len(exported.exported_refs)} ref(s)."
        )
        for w in exported.warnings:
            self._emit(f"  [WARNING] {w}")

        status: Literal["completed", "completed_with_warnings"] = (
            "completed_with_warnings" if exported.warnings else "completed"
        )
        return self._make_result(
            "export_case_context",
            status,
            data={
                "exported_refs": exported.exported_refs,
                "unprojected_links": exported.unprojected_links,
                "output_path": written_path,
            },
            warnings=exported.warnings,
        )

    def _action_verify_integrity(self) -> ActionResult:
        if not self._require_case("verify_integrity"):
            return self.history[-1]
        assert self.case_id is not None

        results = self.service.verify_case_photo_integrity(self.case_id)
        for pid, ok in results.items():
            self._emit(f"  {pid}: {'PASS' if ok else 'FAIL'}")
        all_ok = all(results.values())
        return self._make_result(
            "verify_integrity",
            "completed" if all_ok else "failed",
            data={"results": results, "all_valid": all_ok},
            errors=[] if all_ok else ["One or more original photos failed SHA-256 verification."],
        )

    def _action_view_history(self) -> ActionResult:
        if not self._require_case("view_history"):
            return self.history[-1]
        assert self.case_id is not None

        runs = self.service.list_detection_runs(self.case_id)
        reviews = self.service.list_review_history(self.case_id)
        ev_events = self.service.list_evidence_history(self.case_id)
        self._emit(
            f"History for {self.case_id}: {len(runs)} run(s), {len(reviews)} review event(s), {len(ev_events)} evidence event(s)."
        )
        return self._make_result(
            "view_history",
            "completed",
            data={
                "run_count": len(runs),
                "review_event_count": len(reviews),
                "evidence_event_count": len(ev_events),
            },
        )

    def run(self) -> list[ActionResult]:
        """Runs the interactive menu loop until Exit (13) or EOF."""
        dispatch: dict[str, Callable[[], ActionResult]] = {
            "1": self._action_select_case,
            "2": self._action_register_photo,
            "3": self._action_list_photos,
            "4": self._action_run_detection,
            "5": self._action_view_detections,
            "6": self._action_review_detection,
            "7": self._action_promote_detection,
            "8": self._action_create_manual_evidence,
            "9": self._action_manage_evidence,
            "10": self._action_export_case_context,
            "11": self._action_verify_integrity,
            "12": self._action_view_history,
        }

        while True:
            self._print_menu()
            try:
                choice = self._prompt("Select option [1-13]: ")
            except EOFError:
                self._emit("Input stream closed. Exiting.")
                self._make_result("exit", "completed")
                break

            if choice == "13":
                self._emit("Exiting Module 2 CLI.")
                self._make_result("exit", "completed")
                break

            handler = dispatch.get(choice)
            if handler is None:
                msg = f"Invalid menu choice '{choice}'. Please select 1-13."
                self._emit(f"[ERROR] {msg}")
                self._make_result("invalid_choice", "failed", errors=[msg])
                continue

            try:
                handler()
            except EOFError:
                self._emit("Input stream closed. Exiting.")
                self._make_result("exit", "completed")
                break
            except (YoloModuleError, ValueError) as exc:
                msg = str(exc)
                self._emit(f"[ERROR] {msg}")
                self._make_result(f"menu_{choice}", "failed", errors=[msg])

        return self.history


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.yolo",
        description="Module 2 (YOLO) Candidate Detection, Review & Evidence Management CLI",
    )
    parser.add_argument("--base-dir", default="data/cases", help="Base directory for case storage (default: data/cases)")
    parser.add_argument("--case-id", default=None, help="Optional initial Case ID")
    parser.add_argument("--actor", default="investigator_01", help="Investigator/actor ID (default: investigator_01)")
    parser.add_argument("--stub", action="store_true", help="Use deterministic StubDetectorBackend for offline mode")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO model name or weights path (default: yolov8n.pt)")
    parser.add_argument("--conf", type=float, default=0.35, help="Confidence threshold (default: 0.35)")
    parser.add_argument("--iou", type=float, default=0.50, help="IoU threshold (default: 0.50)")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size (default: 640)")
    parser.add_argument("--max-candidates", type=int, default=30, help="Maximum candidates per run (default: 30)")
    parser.add_argument("--device", default="auto", help="Target device: auto, cpu, mps, cuda, cuda:<id>")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    store = YoloCaseStore(base_dir=Path(args.base_dir))
    config = DetectorConfig(
        model_name=args.model,
        confidence_threshold=args.conf,
        iou_threshold=args.iou,
        image_size=args.imgsz,
        max_candidates=args.max_candidates,
        device=args.device,
    )
    detector: DetectorBackend
    if args.stub:
        detector = StubDetectorBackend()
    else:
        detector = UltralyticsYOLOBackend(model_name=args.model, device=args.device)

    service = YoloDetectionService(store, detector, default_config=config)
    cli = YoloCLI(service, case_id=args.case_id, actor_id=args.actor)
    cli.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
