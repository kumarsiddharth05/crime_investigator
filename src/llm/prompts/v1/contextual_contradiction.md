TASK: Identify contextual_contradiction cases.

Read the case_context. Compare notes against dismissed
detections and against other notes for incompatible factual
claims about the same identified entity (person, object, or
event).

FIRE ONLY WHEN ALL of the following hold:
- Two records make claims about the SAME identified entity.
  The identity MUST be established by shared identifying
  language in BOTH records — for example, both records use
  the exact label "Device D1 — pink smartphone with a cracked
  screen," or both refer to the same named person, or both
  reference the same unique object.
- The two claims are MUTUALLY INCOMPATIBLE. That means one
  claim cannot be true if the other is also true. Example:
  one record asserts the device is the victim's, the other
  asserts it does not belong to the victim.
- The contradiction is EXPLICIT — not inferred from context,
  not based on the assumption that two differently-described
  items are the same thing.

DO NOT FIRE WHEN ANY of these holds:
- The two records use different descriptions of an object and
  you would have to INFER they refer to the same thing. For
  example: note says "a phone was on the counter," dismissal
  reason says "the victim's phone was accounted for" — these
  MIGHT refer to the same device, but the identity is not
  established in the text. Do not flag.
- The dismissal reason does not directly contradict the note.
  For example, "observed" vs "accounted for" are compatible.
- One record is vague or incomplete while the other is
  specific. Vagueness is not contradiction.
- The records concern different entities that happen to share
  a category (two different phones, two different knives).
- One record is a reported statement ("the victim said X")
  and the other is a factual record of a different claim.
  Reported speech is not itself a factual contradiction.
- You are uncertain whether the same entity is referenced in
  both records.

If in doubt, return {"suggestions": []}. Empty is preferred.

FEW-SHOT EXAMPLES:

Example 1 (FIRE):
Note notes.N6: "Item K9 — silver pocket watch, engraved case —
was stolen from the bedroom during the break-in."
Dismissal reason on detection photos.P2.d1 (class: watch,
disposition: dismissed): "Item K9 — silver pocket watch,
engraved case — was retained by the victim and was not stolen."

Correct output:
{
  "suggestions": [{
    "type": "contextual_contradiction",
    "severity": "high",
    "summary": "Note N6 states Item K9 was stolen; dismissal reason for P2.d1 states Item K9 was retained, not stolen.",
    "evidence_refs": ["notes.N6", "photos.P2.d1"],
    "reasoning": "Same identified entity (Item K9) with incompatible factual claims about whether it was stolen.",
    "suggested_action": "Verify the watch's status and reconcile the two records."
  }]
}

Example 2 (DO NOT FIRE — identity not established):
Note notes.N3: "A phone was observed on the counter."
Dismissal reason on photos.P1.d1 (class: cell_phone,
disposition: dismissed): "The victim's own phone was accounted
for."

Correct output:
{"suggestions": []}

Reason: The note says "a phone" without identifying it as the
victim's phone. The dismissal mentions "the victim's phone."
Whether these refer to the same device is not established by
the text. Not enough to fire.

CITATION RULES:
- Each suggestion MUST cite exactly two refs: the note ref and
  the dismissed detection ref (or two note refs if the
  contradiction is note-to-note).
- The refs must be the ones whose claims are directly
  incompatible.

OUTPUT: Return strict JSON matching the system.md output schema.
