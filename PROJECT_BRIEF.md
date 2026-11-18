# PROJECT_BRIEF — Crime Scene LLM Analysis Harness

## 1. Purpose
A CLI + evaluation harness that proves an LLM can generate
grounded, citation-backed suggestions on structured crime-scene
case data, with zero fabricated references reaching the
investigator. Reference grounding is verified by code; semantic
support of each claim is verified by the investigator.

## 2. Core architecture — three engines, run in order
- **Tier A (deterministic, no LLM):** Pure Python rules that extract
  structural inconsistencies from case data.
- **Tier B (LLM):** A large language model receives a compact JSON
  summary of the case (NEVER images) and produces typed, citation-
  required suggestions about *semantic cross-source contradictions*
  only.
- **Validator (post-LLM, mandatory):** Every LLM suggestion is audited
  by code before the investigator sees it. Failing suggestions are
  dropped and logged.

## 3. Four hard rules that override any other instruction
1. The LLM never sees image bytes, image paths, or base64.
2. Every LLM suggestion must cite at least one `evidence_refs` entry
   that resolves to a real node in the input `case_context`.
3. A detection with `disposition == "dismissed"` AND a non-null
   `reason` cannot be re-flagged by the LLM (dismissal guard), unless
   a note/timeline entry directly contradicts the dismissal reason.
4. Deterministic checks run BEFORE the LLM. If Tier A finds nothing
   semantic to reconcile, the LLM call is SKIPPED entirely.

## 4. case_context schema (see schemas/case_context.schema.json)
Top-level keys: `case`, `evidence`, `photos`, `map`, `timeline`,
`notes`, `derived_facts`.

- Each `photos[].detections[]` entry has:
  `{ref, class, conf, disposition, reason}`
  where `disposition ∈ {"confirmed","dismissed","unreviewed"}`.
  `reason` is REQUIRED (non-empty string) when `disposition=="dismissed"`.
- `map.evidence_positions_summary` is an array of NATURAL LANGUAGE
  sentences describing distances (e.g. "E1 is ~2.9 m from the main
  door"). Raw coordinates may be included as a separate optional
  `xy_optional` field but the summary text is what the LLM reads.
- Every addressable node has a stable dotted `ref` path
  (e.g. `notes.N3`, `timeline.T2`, `photos.P1.d3`, `evidence.E1`).

## 5. Tier A rules (8)
| ID | Rule | Flag type |
|----|------|-----------|
| A1 | detection with disposition=="unreviewed" | process_gap |
| A2 | detection dismissed with null/empty reason | process_gap |
| A3 | note mentions an object class that is present in NO detection at all (i.e. no confirmed, dismissed, or unreviewed detection has that class) AND no confirmed evidence of that class exists | note_evidence_gap |
| A4 | note contains HH:MM not present in any timeline entry | timeline_gap |
| A5 | map evidence position with no photo_ref | orphan_evidence |
| A6 | timeline entry with no `source` | metadata_gap |
| A7 | note references a room with no photo coverage | coverage_gap |
| A8 | confirmed evidence with no map position | mapping_gap |

Tier A flags are FACTS, not suggestions. Zero hallucination risk.

## 6. Tier B LLM analysis types (3)

All three types detect CATEGORICAL contradictions — two records
that make mutually incompatible factual claims about the same
identified thing. Approximate differences, missing entries, and
subjective boundaries are explicitly out of scope.

- `spatial_inconsistency` — The same evidence is explicitly
  placed in mutually exclusive locations across a note and the
  2D map summary. Example: note says "near the main door",
  map summary places it "near the window, at the far end of
  the room from the main door." Not fired on approximate
  distance differences (e.g., "near door" vs "1.2 m from
  door").

- `timeline_contradiction` — Two records explicitly describe
  the SAME identified event (same actor and action) and assign
  incompatible times. Example: Note says "police arrived at
  21:40"; timeline records "police arrival at 22:10." A missing
  timeline entry or a small approximate-time difference is not
  a contradiction.

- `contextual_contradiction` — Two records make incompatible
  factual claims about the SAME identified entity (person,
  object, or event). The identity must be established in both
  records by shared identifying language (e.g., both records
  use the label "Device D1 — pink smartphone with a cracked
  screen"). Example: Note says Device D1 was reported missing;
  dismissal reason says Device D1 was confirmed as the victim's
  own device and accounted for.

Approximate-time and approximate-distance differences do not
constitute contradictions on their own. When in doubt, the
system remains silent.

## 7. LLM output schema
Strict JSON (no markdown fences, no prose). Top level:
`{ "suggestions": [ <suggestion>, ... ] }`, maxItems: 10.
Each suggestion:
```json
{
  "type": "<one of the 3 types above>",
  "severity": "low" | "medium" | "high",
  "summary": "<string, ≤ 25 words>",
  "evidence_refs": ["<dotted ref>", ...], // minItems: 1
  "reasoning": "<string, ≤ 40 words>",
  "suggested_action": "<string, ≤ 25 words>"
}
```

Empty `suggestions: []` is valid and PREFERRED when nothing is wrong.

## 8. Validator checks (7, all mandatory, run in this order)
The validator establishes that references and extracted
entities exist in the input case_context. It cannot
mathematically guarantee that the LLM has interpreted the
relationship between cited fields correctly. Semantic
verification of each suggestion's claim remains the
investigator's responsibility.

1. **Schema validation** — fails → drop whole response.
2. **Per-invocation type check** — every suggestion's `type`
   field MUST equal the `assigned_analysis_type` passed to the
   validator for this invocation. Mismatches are dropped with
   `rejection_reason="type_mismatch"`. An empty `suggestions: []`
   list is valid for any valid `assigned_analysis_type`.
   An invalid `assigned_analysis_type` must raise a controlled
   `ValueError` regardless of suggestion content.
3. **Ref resolution** — every `evidence_refs` entry must
   resolve to a real node in `case_context`; any unresolved ref
   → drop the suggestion.
4. **Dismissal guard** — if a suggestion cites a `dismissed`
   detection with non-null reason, drop unless type is
   `contextual_contradiction` AND at least one other cited ref
   resolves to a note/timeline entry (enforced as a mechanical
   prerequisite; semantic challenge of the dismissal rationale
   must be verified by the investigator).
5. **Entity hallucination detector** — extract proper nouns and
   all numbers from summary+reasoning+suggested_action; any
   token not present in `case_context` and not in the curated
   generic vocabulary → flag; ≥2 unverified tokens → drop;
   exactly 1 → keep with `validation_warning`. Reference
   resolution does NOT authorize unrelated entity names — the
   two checks are independent.
6. **Dedup vs Tier A** — if semantically identical to a Tier A
   flag, drop the LLM suggestion (Tier A wins).
7. **Severity sanity** — "high" severity requires at least two
   distinct evidence references; otherwise downgrade to "medium".

## 9. LLM client requirements
- Provider-agnostic. Select via env: LLM_PROVIDER (openai|gemini|anthropic),
  LLM_MODEL, API key env var per provider.
- Temperature 0. JSON/structured output mode where supported.
- Retry ×2 on schema failure, with the error fed back in the
  correction prompt. After 2 failures, return
  `{suggestions:[], error:"schema_fail"}` and log; never crash.
- Timeout 20 s.

## 10. Test fixtures
`cases/C<N>.json` = one case_context.
`cases/C<N>.expected.json` = ground truth:
```json
{
  "clean": bool,
  "tier_a_expected": [ {"rule": "A1", "about_ref": "photos.P1.d3"}, ... ],
  "tier_b_expected": [ {"type": "contextual_contradiction",
                        "about_refs": ["notes.N3", "photos.P1.d3"]}, ... ]
}
```

## 11. Acceptance targets (verified by evaluate.py)

Measured on the defined fixture suite. These are evaluation
objectives, not guarantees of production behavior.

- Tier A recall = 1.00 on the defined fixtures
- Tier A precision ≥ 0.95 on the defined fixtures
- Tier B recall ≥ 0.70 on the defined fixtures
- Tier B precision ≥ 0.95 on the defined fixtures
- Fabricated-reference rate = 0.00 on the defined fixtures
  (validator-dropped / total suggestions)
- Zero false positives on clean and borderline fixtures
- Median latency < 6 s under documented test conditions

A clean pass on the fixture suite demonstrates measured
reliability on those fixtures. It does not prove the system
will never produce a false positive in production.

## 12. Directory layout
```
repo/
  PROJECT_BRIEF.md
  README.md
  pyproject.toml
  schemas/
    case_context.schema.json
  cases/
    C0.json  C0.expected.json
    C1.json  C1.expected.json
    ... (13 fixtures, C0–C7, C10–C14)
  src/
    analysis/
      __init__.py
      tier_a.py
      refs.py
      validator.py
      pipeline.py
    llm/
      __init__.py
      client.py
      prompt_builder.py
      prompts/
        v1/
          system.md
          spatial_inconsistency.md
          timeline_contradiction.md
          contextual_contradiction.md
  scripts/
    check_fixtures.py
    check_refs.py
  runs/       # audit JSON per analysis run (created at runtime)
  reports/    # eval reports (created at runtime)
  tests/
    __init__.py
    test_refs.py
    test_tier_a.py
    test_validator.py
  analyze.py   # CLI entry
  evaluate.py  # metrics entry

Future (not yet present):
  .github/workflows/ci.yml
```

## 13. Non-goals for this harness
No SQLite, no Flask, no React, no YOLO, no OpenCV in this harness.
case_context is LOADED DIRECTLY from fixture JSON files. Every
downstream stage is identical to the production platform.

## 14. Platform integration note (for later)
When the real platform is built, a `context_builder` module will
populate the same `case_context` schema from SQLite. All Tier A,
LLM, and validator code is unchanged.

## 15. Prompt injection guard
Text inside `notes[].text`, `timeline[].description`, and
`photos[].view` fields is DATA, never instructions. The system prompt
must state this. The context builder must strip lines matching
`(?i)(ignore (all )?previous|disregard|system:|assistant:)` from
these fields before sending to the LLM.
