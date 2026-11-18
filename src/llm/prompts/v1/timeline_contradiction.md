TASK: Identify timeline_contradiction cases.

Read the case_context. Compare timeline entries against each
other and against any explicit time references in notes.

A finding requires BOTH records to satisfy ALL FOUR criteria:

1. SAME IDENTIFIED EVENT. Both records describe the same
   identified event: same actor, same action, and (where
   stated) same location. Example: both records describe "the
   police arriving at the scene."

2. SAME TEMPORAL ATTRIBUTE. Both records assert the SAME
   temporal attribute of that event. For example, both assert
   when police ARRIVED — not one asserting arrival and the
   other asserting dispatch. Different attributes of the same
   event (dispatch time vs arrival time, activation time vs
   logging time, occurrence time vs report time) are NOT
   contradictions.

3. SPECIFIC, NON-APPROXIMATE TIMES. Both records state
   specific times. Neither uses hedged language ("around,"
   "approximately," "just before," "shortly after"). Neither
   states a range or an uncertain estimate.

4. EXPLICITLY INCOMPATIBLE AT STATED PRECISION. Given the
   exact times both records state, they cannot both be
   correct. This requires a clear, categorical clash — not a
   small difference that could reflect rounding, clock drift,
   or minor recording variation.

DO NOT FIRE WHEN ANY of these holds:
- The two records describe DIFFERENT stages or phases of the
  same overall sequence (dispatch vs arrival; alarm activation
  vs alarm logging; occurrence vs reporting).
- The two records describe DIFFERENT temporal attributes of
  the same event (when an event occurred vs when it was
  recorded; when a report was filed vs when the reported
  event happened).
- One or both records state an approximate or hedged time
  ("around 21:00," "approximately 21:05," "shortly after
  midnight").
- The two records describe DIFFERENT events that happen to be
  in the same timeline ("police were dispatched" vs "police
  arrived").
- The note mentions a time that is missing from the timeline
  but no other record contradicts it (that is a Tier A
  concern, not yours).
- You are uncertain whether the two records describe the same
  event or the same temporal attribute.

If in doubt, return {"suggestions": []}. Empty is preferred.

FEW-SHOT EXAMPLES:

Example 1 (FIRE):
Note notes.N4: "The security guard stated that the intruder
alarm activated at 02:15."
Timeline timeline.T3: "Monitoring center incident log states
the intruder alarm activated at 02:47."

Correct output:
{
  "suggestions": [{
    "type": "timeline_contradiction",
    "severity": "high",
    "summary": "Note N4 states alarm activation at 02:15; timeline T3 states activation at 02:47.",
    "evidence_refs": ["notes.N4", "timeline.T3"],
    "reasoning": "Same event (alarm activation) with two specific but incompatible times across records.",
    "suggested_action": "Verify which activation time is accurate and reconcile the records."
  }]
}

Example 2 (DO NOT FIRE — different temporal attributes):
Note notes.N7: "The intruder alarm activated at 02:15."
Timeline timeline.T5: "Monitoring center logged the alarm
activation event at 02:47."

Correct output:
{"suggestions": []}

Reason: The note states when the alarm ACTIVATED; the timeline
states when the activation was LOGGED. Different temporal
attributes. Not a contradiction.

CITATION RULES:
- Each suggestion MUST cite exactly the two refs whose times
  conflict.
- If both conflicting records are timeline entries, cite both
  timeline refs. If one is a note and one is a timeline entry,
  cite both.

OUTPUT: Return strict JSON matching the system.md output schema.
