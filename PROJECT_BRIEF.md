# PROJECT_BRIEF — Crime Scene LLM Analysis Harness

## 1. Purpose
A CLI + evaluation harness that proves an LLM can generate grounded,
citation-backed suggestions on structured crime-scene case data, with
zero hallucinations reaching the investigator.

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

## 6. Tier B LLM analysis types (6)
- `spatial_inconsistency` — note says "near X" but map places it >2m away
- `timeline_contradiction` — two timeline entries or a note-vs-timeline time conflict
- `contextual_contradiction` — note directly contradicts a dismissal reason
- `semantic_coverage_gap` — note describes an object/location with no
  photo coverage (semantic, not structural — Tier A handles A7's room case)
- `ambiguity` — note has a dangling reference ("she", "it") with no antecedent
- `follow_up` — a documentation step is missing that is consistent with case type

## 7. LLM output schema
Strict JSON (no markdown fences, no prose). Top level:
`{ "suggestions": [ <suggestion>, ... ] }`, maxItems: 10.
Each suggestion:
```json
{
  "type": "<one of the 6 types above>",
  "severity": "low" | "medium" | "high",
  "summary": "<string, ≤ 25 words>",
  "evidence_refs": ["<dotted ref>", ...], // minItems: 1
  "reasoning": "<string, ≤ 40 words>",
  "suggested_action": "<string, ≤ 25 words>"
}
```

Empty `suggestions: []` is valid and PREFERRED when nothing is wrong.

## 8. Validator checks (6, all mandatory, run in this order)
1. **Schema validation** — fails → drop whole response.
2. **Ref resolution** — every evidence_refs must resolve to a real
   node in case_context; any unresolved ref → drop the suggestion.
3. **Dismissal guard** — if suggestion cites a `dismissed` detection
   with non-null reason, drop unless type is `contextual_contradiction`
   AND a note/timeline ref is also cited.
4. **Entity hallucination detector** — extract proper nouns and all
   numbers from summary+reasoning+suggested_action; any token not
   present in case_context and not a generic word → flag; ≥2 unverified
   tokens → drop; exactly 1 → keep with `validation_warning`.
5. **Dedup vs Tier A** — if semantically identical to a Tier A flag,
   drop the LLM one (Tier A wins).
6. **Severity sanity** — "high" severity requires ≥2 refs OR a direct
   contradiction; else downgrade to "medium".

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
- Tier A recall = 1.0
- Tier B recall ≥ 0.85
- Tier B precision ≥ 0.85
- Hallucination rate = 0.0 (validator-dropped / total suggestions)
- False positives on clean cases = 0
- Median latency < 6 s per case

## 12. Directory layout
```
repo/
  PROJECT_BRIEF.md
  README.md
  pyproject.toml
  schemas/
    case_context.schema.json
  cases/
    C0.json   C0.expected.json
  src/
    analysis/
      __init__.py
      tier_a.py
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
      semantic_coverage_gap.md
      ambiguity.md
      follow_up.md
  scripts/
    check_fixtures.py
  runs/       # audit JSON per analysis run (created at runtime)
  reports/    # eval reports (created at runtime)
  tests/
    test_tier_a.py
    test_validator.py
  analyze.py   # CLI entry
  evaluate.py  # metrics entry
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
