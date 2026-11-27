"""Case-context exporter projecting Module 2 state into Module 1 schema-compliant JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

from src.yolo.exceptions import ExportValidationError
from src.yolo.store import YoloCaseStore

DEFAULT_CASE_CONTEXT_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "schemas" / "case_context.schema.json"
)


@dataclass
class ExportResult:
    """Result bundle returned by export_case_context."""

    case_context: dict[str, Any]
    exported_refs: list[str]
    warnings: list[str]
    unprojected_links: dict[str, dict[str, list[str]]]


def export_yolo_sections(
    store: YoloCaseStore,
    case_id: str,
    *,
    allow_layer3_extensions: bool = True,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
    dict[str, dict[str, list[str]]],
    list[str],
]:
    """Projects Module 2 photos, detections, and 3-layer evidence records for case_context."""
    photos = store.list_photos(case_id)
    candidates = store.list_candidates(case_id)
    evidence_records = store.list_evidence(case_id)

    cands_by_photo: dict[str, list[dict[str, Any]]] = {}
    for cand in candidates:
        det_entry: dict[str, Any] = {
            "ref": cand.ref,
            "class": cand.class_name,
            "conf": round(float(cand.confidence), 4),
            "disposition": cand.disposition,
            "reason": cand.dismissal_reason if cand.disposition == "dismissed" else None,
        }
        cands_by_photo.setdefault(cand.photo_id, []).append(det_entry)

    photos_out: list[dict[str, Any]] = []
    rooms_seen: set[str] = set()
    rooms_covered: list[str] = []

    for photo in photos:
        photo_entry: dict[str, Any] = {
            "ref": photo.ref,
            "detections": cands_by_photo.get(photo.photo_id, []),
        }
        if photo.room and photo.room.strip():
            clean_room = photo.room.strip()
            photo_entry["room"] = clean_room
            if clean_room not in rooms_seen:
                rooms_seen.add(clean_room)
                rooms_covered.append(clean_room)
        photos_out.append(photo_entry)

    evidence_out: list[dict[str, Any]] = []
    unprojected_links: dict[str, dict[str, list[str]]] = {}
    warnings: list[str] = []

    for ev in evidence_records:
        # Layer 2: standard primary single refs (nullable when absent, e.g. manual evidence)
        primary_photo_ref: str | None = ev.photo_refs[0] if ev.photo_refs else None
        primary_det_ref: str | None = ev.det_refs[0] if ev.det_refs else None

        ev_entry: dict[str, Any] = {
            "ref": ev.ref,
            "label": ev.label,
            "photo_ref": primary_photo_ref,
            "det_ref": primary_det_ref,
            "map_ref": None,
        }

        secondary_photos = ev.photo_refs[1:] if len(ev.photo_refs) > 1 else []
        secondary_dets = ev.det_refs[1:] if len(ev.det_refs) > 1 else []

        # Layer 3: secondary associations only if schema permits additionalProperties
        if secondary_photos or secondary_dets:
            if allow_layer3_extensions:
                ev_entry["photo_refs"] = list(ev.photo_refs)
                ev_entry["det_refs"] = list(ev.det_refs)
            else:
                unprojected_links[ev.ref] = {
                    "photo_refs": secondary_photos,
                    "det_refs": secondary_dets,
                }
                warnings.append(
                    f"Evidence '{ev.ref}' has secondary links omitted due to schema restrictions: "
                    f"photo_refs={secondary_photos}, det_refs={secondary_dets}"
                )

        evidence_out.append(ev_entry)

    return photos_out, evidence_out, rooms_covered, unprojected_links, warnings


def _load_schema(schema_path: Path) -> dict[str, Any]:
    with schema_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ExportValidationError(f"Schema at '{schema_path}' is not a JSON object.")
    return data


def export_case_context(
    store: YoloCaseStore,
    case_id: str,
    *,
    case_metadata: dict[str, Any] | None = None,
    notes: list[dict[str, Any]] | None = None,
    timeline: list[dict[str, Any]] | None = None,
    map_data: dict[str, Any] | None = None,
    derived_facts: dict[str, Any] | None = None,
    validate_schema: bool = True,
    schema_path: Path | None = None,
) -> ExportResult:
    """Assembles and validates a complete Module 1 case_context dict from Module 2 storage."""
    resolved_schema_path = schema_path or DEFAULT_CASE_CONTEXT_SCHEMA_PATH
    schema: dict[str, Any] | None = None
    allow_layer3 = True

    if resolved_schema_path.is_file():
        schema = _load_schema(resolved_schema_path)
        ev_items = schema.get("properties", {}).get("evidence", {}).get("items", {})
        if isinstance(ev_items, dict):
            allow_layer3 = bool(ev_items.get("additionalProperties", True))
    elif validate_schema:
        raise ExportValidationError(f"Case context schema not found: {resolved_schema_path}")

    photos_out, evidence_out, rooms_covered, unprojected_links, warnings = export_yolo_sections(
        store,
        case_id,
        allow_layer3_extensions=allow_layer3,
    )

    if case_metadata is None:
        case_obj: Any = {
            "id": case_id,
            "rooms_covered": rooms_covered,
        }
    elif isinstance(case_metadata, dict):
        case_obj = {
            "id": case_id,
            "rooms_covered": rooms_covered,
            **case_metadata,
        }
    else:
        case_obj = case_metadata

    case_context: dict[str, Any] = {
        "case": case_obj,
        "evidence": evidence_out,
        "photos": photos_out,
        "map": map_data if map_data is not None else {"evidence_positions_summary": []},
        "timeline": timeline if timeline is not None else [],
        "notes": notes if notes is not None else [],
        "derived_facts": derived_facts if derived_facts is not None else {},
    }

    if validate_schema and schema is not None:
        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(case_context), key=lambda e: list(e.path))
        if errors:
            formatted = [
                f"{'.'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
                for err in errors
            ]
            raise ExportValidationError(
                f"Exported case_context failed schema validation ({len(formatted)} error(s)): "
                + "; ".join(formatted)
            )

    exported_refs: list[str] = []
    for p in photos_out:
        exported_refs.append(p["ref"])
        for d in p.get("detections", []):
            exported_refs.append(d["ref"])
    for e in evidence_out:
        exported_refs.append(e["ref"])

    return ExportResult(
        case_context=case_context,
        exported_refs=exported_refs,
        warnings=warnings,
        unprojected_links=unprojected_links,
    )
