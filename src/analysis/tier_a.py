"""Tier A deterministic rules engine.

Pure Python rules that extract structural inconsistencies from case data.
No LLM, no I/O, zero hallucination risk.
"""

from __future__ import annotations

import re
from typing import Any

from src.analysis.refs import resolve_ref

# Rule A3 allowlist of known object classes
A3_OBJECT_ALLOWLIST = [
    "knife",
    "gun",
    "firearm",
    "bottle",
    "phone",
    "cell_phone",
    "laptop",
    "wallet",
    "bag",
    "key",
    "shoe",
    "rope",
    "hammer",
    "screwdriver",
    "watch",
    "jewelry",
    "document",
]

# Rule A7 room allowlist
A7_ROOM_ALLOWLIST = [
    "bedroom",
    "kitchen",
    "study",
    "balcony",
    "garage",
    "bathroom",
    "living_room",
    "hall",
    "dining_room",
    "storeroom",
]

# Time regex: matches HH:MM (e.g. 21:40, 9:45, 09:45)
# In timeline entries, times may be preceded by 'T' (ISO-8601: 2026-01-15T21:45) or word boundary
TIMELINE_TIME_REGEX = re.compile(r"(?:\b|T)((?:[01]?\d|2[0-3]):[0-5]\d)\b")
NOTE_TIME_REGEX = re.compile(r"\b((?:[01]?\d|2[0-3]):[0-5]\d)\b")


def _normalize_time(time_str: str) -> str:
    """Normalize time string to zero-padded HH:MM."""
    parts = time_str.split(":")
    return f"{int(parts[0]):02d}:{parts[1]}"


def _extract_timeline_times(timeline: list[dict[str, Any]]) -> set[str]:
    """Extract all normalized HH:MM times from timeline entries."""
    times = set()
    for entry in timeline:
        time_field = entry.get("time", "")
        if time_field:
            matches = TIMELINE_TIME_REGEX.findall(str(time_field))
            for m in matches:
                times.add(_normalize_time(m))
        desc = entry.get("description", "")
        if desc:
            desc_matches = TIMELINE_TIME_REGEX.findall(str(desc))
            for m in desc_matches:
                times.add(_normalize_time(m))
    return times


def _canonicalize_object_class(class_name: str) -> str:
    """Map related terms (e.g. cell_phone -> phone, backpack -> bag) for equivalence checks."""
    c = class_name.lower().replace("-", "_").strip()
    if c in ("cell_phone", "cell phone", "mobile", "mobile phone", "telephone"):
        return "phone"
    if c in ("backpack", "handbag", "purse", "school bag", "tote bag"):
        return "bag"
    if c in ("jewelry_box", "jewellery", "ornaments"):
        return "jewelry"
    if c in ("wristwatch", "clock"):
        return "watch"
    if c in ("firearm", "pistol", "revolver", "rifle"):
        return "gun"
    return c


def run_tier_a(case_context: dict[str, Any]) -> list[dict[str, Any]]:
    """Execute Tier A deterministic rules on case_context.

    Returns a list of factual structural gap flags.
    """
    flags: list[dict[str, Any]] = []

    photos = case_context.get("photos", [])
    evidence = case_context.get("evidence", [])
    timeline = case_context.get("timeline", [])
    notes = case_context.get("notes", [])
    scene_map = case_context.get("map", {})
    case_info = case_context.get("case", {})

    # Collect known classes from detections
    all_classes_seen_in_detections = set()
    all_confirmed_classes = set()

    for photo in photos:
        photo_ref = photo.get("ref", "unknown_photo")
        detections = photo.get("detections", [])

        for det in detections:
            det_ref = det.get("ref", "unknown_det")
            det_class = det.get("class", "unknown_class")
            conf = det.get("conf", 0.0)
            disp = det.get("disposition")
            reason = det.get("reason")

            canon_class = _canonicalize_object_class(det_class)
            all_classes_seen_in_detections.add(canon_class)
            all_classes_seen_in_detections.add(det_class.lower())

            if disp == "confirmed":
                all_confirmed_classes.add(canon_class)
                all_confirmed_classes.add(det_class.lower())

            # A1: detection disposition == "unreviewed"
            if disp == "unreviewed":
                flags.append({
                    "engine": "tier_a",
                    "rule": "A1",
                    "severity": "medium",
                    "summary": f"Detection {det_class} ({conf}) on {photo_ref} is unreviewed — confirm or dismiss.",
                    "evidence_refs": [det_ref],
                    "reasoning": f"Detection {det_ref} has disposition 'unreviewed' and requires investigator decision.",
                })

            # A2: detection disposition == "dismissed" with null/empty reason
            elif disp == "dismissed":
                if reason is None or not str(reason).strip():
                    flags.append({
                        "engine": "tier_a",
                        "rule": "A2",
                        "severity": "medium",
                        "summary": f"Detection {det_class} on {photo_ref} is dismissed without a recorded reason.",
                        "evidence_refs": [det_ref],
                        "reasoning": f"Detection {det_ref} was marked 'dismissed' but lacks a required justification.",
                    })

    # Collect confirmed evidence classes & labels
    confirmed_evidence_labels = []
    for ev in evidence:
        label = ev.get("label", "").lower()
        if label:
            confirmed_evidence_labels.append(label)

    # Pre-extract timeline times for A4
    timeline_times = _extract_timeline_times(timeline)

    # Pre-compute photo room coverage for A7
    def _add_room_variants(r: str, s: set[str]) -> None:
        norm = r.lower().replace("-", "_").replace(" ", "_").strip()
        s.add(norm)
        if norm.endswith("_room"):
            s.add(norm[:-5])
        else:
            s.add(f"{norm}_room")

    covered_rooms = set()
    for photo in photos:
        room = photo.get("room")
        if room:
            _add_room_variants(str(room), covered_rooms)
    for room in case_info.get("rooms_covered", []):
        if room:
            _add_room_variants(str(room), covered_rooms)

    # Notes checks (A3, A4, A7)
    for note in notes:
        note_ref = note.get("ref", "unknown_note")
        text = note.get("text", "")
        text_lower = text.lower()

        # A3: note mentions an object class in NO detection at all AND no confirmed evidence of that class exists
        for obj_class in A3_OBJECT_ALLOWLIST:
            # Word-boundary search for object keyword
            pattern = rf"\b{re.escape(obj_class)}\b"
            if obj_class == "cell_phone":
                pattern = r"\b(cell[\s_]?phone|phone)\b"
            elif obj_class == "phone":
                pattern = r"\bphone\b"

            if re.search(pattern, text_lower):
                canon = _canonicalize_object_class(obj_class)
                # Check if present in detections
                in_detections = (
                    canon in all_classes_seen_in_detections
                    or obj_class in all_classes_seen_in_detections
                )
                # Check if present in confirmed evidence
                in_evidence = (
                    canon in all_confirmed_classes
                    or obj_class in all_confirmed_classes
                    or any(obj_class in lbl or canon in lbl for lbl in confirmed_evidence_labels)
                )

                if not in_detections and not in_evidence:
                    flags.append({
                        "engine": "tier_a",
                        "rule": "A3",
                        "severity": "low",
                        "summary": f"Note {note_ref} mentions object class '{obj_class}' with no matching detection or confirmed evidence.",
                        "evidence_refs": [note_ref],
                        "reasoning": f"Object keyword '{obj_class}' mentioned in note {note_ref} does not appear in any photo detection or evidence record.",
                    })

        # A4: note contains an HH:MM literal not present in ANY timeline entry
        note_time_matches = NOTE_TIME_REGEX.findall(text)
        for t_match in note_time_matches:
            normalized_t = _normalize_time(t_match)
            if normalized_t not in timeline_times:
                flags.append({
                    "engine": "tier_a",
                    "rule": "A4",
                    "severity": "medium",
                    "summary": f"Note {note_ref} mentions time {normalized_t} which is not present in any timeline entry.",
                    "evidence_refs": [note_ref],
                    "reasoning": f"Timestamp {normalized_t} found in note {note_ref} has no corresponding timeline event record.",
                })

        # A7: note references a room name that has no photo coverage
        for room_candidate in A7_ROOM_ALLOWLIST:
            # Match word boundary for room name
            room_pattern = rf"\b{re.escape(room_candidate.replace('_', ' '))}\b|\b{re.escape(room_candidate)}\b"
            if re.search(room_pattern, text_lower):
                canon_room = room_candidate.lower().replace("-", "_").replace(" ", "_").strip()
                # Ensure it has coverage
                if canon_room not in covered_rooms:
                    flags.append({
                        "engine": "tier_a",
                        "rule": "A7",
                        "severity": "low",
                        "summary": f"Note {note_ref} references room '{room_candidate}' which has no photo coverage.",
                        "evidence_refs": [note_ref],
                        "reasoning": f"Room '{room_candidate}' referenced in note {note_ref} has no photograph coverage or case coverage record.",
                    })

    # Evidence & Map checks (A5, A8)
    map_summary_text = " ".join(scene_map.get("evidence_positions_summary", [])).lower()

    for ev in evidence:
        ev_ref = ev.get("ref", "unknown_evidence")
        label = ev.get("label", "")
        photo_ref = ev.get("photo_ref")
        map_ref = ev.get("map_ref")

        # A5: map evidence position with no photo_ref
        if map_ref and not photo_ref:
            flags.append({
                "engine": "tier_a",
                "rule": "A5",
                "severity": "low",
                "summary": f"Evidence {ev_ref} has a map position but no photo reference.",
                "evidence_refs": [ev_ref],
                "reasoning": f"Orphan evidence: {ev_ref} has a map reference ({map_ref}) but lacks a photo reference.",
            })

        # A8: confirmed evidence with no map position
        # Has map position if map_ref is set OR label appears in map.evidence_positions_summary
        has_map_position = bool(map_ref) or (bool(label) and label.lower() in map_summary_text)
        if not has_map_position:
            flags.append({
                "engine": "tier_a",
                "rule": "A8",
                "severity": "low",
                "summary": f"Confirmed evidence {ev_ref} ({label}) has no position on the scene map.",
                "evidence_refs": [ev_ref],
                "reasoning": f"Evidence {ev_ref} has no map_ref and does not appear in evidence_positions_summary.",
            })

    # Timeline checks (A6)
    for tl in timeline:
        tl_ref = tl.get("ref", "unknown_timeline")
        source = tl.get("source")
        if source is None or not str(source).strip():
            flags.append({
                "engine": "tier_a",
                "rule": "A6",
                "severity": "low",
                "summary": f"Timeline event {tl_ref} has no recorded source.",
                "evidence_refs": [tl_ref],
                "reasoning": f"Timeline entry {tl_ref} lacks an attributed source or has empty metadata.",
            })

    # Internal sanity check: verify every produced ref resolves against case_context
    for flag in flags:
        for ref in flag.get("evidence_refs", []):
            resolved = resolve_ref(case_context, ref)
            if resolved is None:
                raise AssertionError(
                    f"Tier A generated unresolvable ref '{ref}' for rule {flag.get('rule')}"
                )

    return flags
