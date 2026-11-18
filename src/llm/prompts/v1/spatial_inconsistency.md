TASK: Identify spatial_inconsistency contradictions.

Read the case_context. Compare each note's spatial claims about
evidence against the map.evidence_positions_summary entries.

FIRE ONLY WHEN ALL of the following hold:
- The note and the map summary explicitly describe the SAME
  object (matching identifying language or matching evidence
  label).
- The note places the object at one location, and the map
  summary places the same object at a location MUTUALLY
  EXCLUSIVE with the note's location. Mutually exclusive means
  one of:
    * Different rooms (note says kitchen, map says
      living_room)
    * Different landmarks on opposite sides of the same room
      (note says "near the main door", map says "near the
      window, at the far end of the room from the main door")
    * Explicitly opposite relative positions (note says
      "against the east wall", map says "against the west
      wall")
- Both records are UNAMBIGUOUS. Neither uses hedged language
  like "possibly," "may be," or "roughly."

DO NOT FIRE WHEN ANY of these holds:
- Only one record (note or map) describes a position.
- The note uses an approximate spatial term ("near," "by,"
  "close to") and the map summary gives a numeric distance that
  is compatible with that term. Example: "near the main door"
  and "1.2 m from the main door" describe a compatible position.
- The two records describe different objects.
- The note describes a position but the map summary does not
  mention the same object at all.
- You are uncertain whether the two locations are mutually
  exclusive.

If in doubt, return {"suggestions": []}. Empty is preferred.

FEW-SHOT EXAMPLES:

Example 1 (FIRE):
Note notes.N2: "The hammer was discovered on the workbench in
the garage."
Map evidence_positions_summary: "Evidence E3 (hammer) is
located on the shelf in the kitchen pantry."

Correct output:
{
  "suggestions": [{
    "type": "spatial_inconsistency",
    "severity": "high",
    "summary": "Note N2 places the hammer on the garage workbench; map places it on the kitchen pantry shelf.",
    "evidence_refs": ["notes.N2", "evidence.E3"],
    "reasoning": "Same object (hammer) described in two distinct rooms across note and map summary.",
    "suggested_action": "Verify the hammer's actual location and update the incorrect record."
  }]
}

Example 2 (DO NOT FIRE — near vs numeric is compatible):
Note notes.N5: "The crowbar was found near the back entrance."
Map evidence_positions_summary: "Evidence E1 (crowbar) is
approximately 1.5 m from the back entrance."

Correct output:
{"suggestions": []}

Reason: "near the back entrance" and "1.5 m from the back
entrance" describe compatible positions. Not a contradiction.

CITATION RULES:
- Each suggestion MUST cite exactly the two refs that produce
  the conflict: one note ref and one evidence ref.
- Do not cite the map summary by ref — cite the evidence ref
  that appears in the map's evidence_positions_summary entry.

OUTPUT: Return strict JSON matching the system.md output schema.
