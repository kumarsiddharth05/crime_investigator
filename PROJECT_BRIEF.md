# PROJECT_BRIEF — Crime Scene LLM Analysis Harness

## 1. Purpose
A CLI and evaluation harness that proves a Large Language Model (LLM) can generate grounded, citation-backed suggestions on structured crime-scene case data, with zero fabricated references reaching the investigator. Reference grounding is mathematically verified by deterministic code; semantic support of each claim remains the investigator's responsibility to verify.

## 2. Core pipeline architecture — Five distinct stages
The analysis pipeline executes five distinct stages in order:

1. **Tier A Deterministic Rules Engine (No LLM):** Pure Python rules that inspect structural case data and extract deterministic facts (e.g., unreviewed detections, orphan map positions, timeline gaps). These findings are facts, not suggestions, with zero hallucination risk. Tier A does NOT act as a semantic eligibility gate for Tier B.
2. **Semantic Gate (Pre-LLM Category Selection):** A deterministic inspection function (`evaluate_semantic_gate`) that evaluates whether sufficient cross-source records exist in the case data to warrant evaluating each Tier B category. If a category lacks cross-source data to reconcile (e.g., no spatial notes, fewer than two time-bearing records), that category invocation is skipped entirely, conserving tokens and preventing false positives.
3. **Tier B LLM Analysis Engine:** An LLM receives a compact JSON representation of the case (NEVER image bytes or base64) and produces typed, citation-required suggestions about *semantic cross-source contradictions* only. Each invocation handles exactly one assigned analysis type.
4. **Post-LLM Validator (Mandatory 7-stage gate):** Every LLM suggestion is audited by code before presentation to an investigator. Suggestions that violate schema, mismatch assigned types, cite unresolvable references, breach dismissal guards, or introduce ungrounded entities are dropped and logged.
5. **Pipeline Orchestrator & Audit Persistence:** Coordinates Tier A, the Semantic Gate, Tier B invocations, and the Validator; enforces provider pacing and error handling; calculates context hashes (SHA-256); and persists immutable execution audit records to `runs/`.

## 3. Four hard rules that override any other instruction
1. **No Image Data:** The LLM never sees image bytes, image paths, or base64.
2. **Strict Reference Grounding:** Every LLM suggestion must cite at least one `evidence_refs` entry that resolves to a real node in the input `case_context`.
3. **Dismissal Guard:** A detection with `disposition == "dismissed"` AND a non-null `reason` cannot be re-flagged by the LLM, unless the analysis type is `contextual_contradiction` AND at least one other cited ref resolves to a note or timeline entry (establishing a valid cross-source challenge to the dismissal rationale).
4. **Independent Semantic Eligibility:** The Semantic Gate independently determines whether each Tier B category has sufficient relevant records. Tier A deterministic checks extract structural facts independently and do NOT govern Tier B semantic eligibility.

## 4. case_context schema (see schemas/case_context.schema.json)
Top-level keys: `case`, `evidence`, `photos`, `map`, `timeline`, `notes`, `derived_facts`.

- Each `photos[].detections[]` entry has:
  `{ref, class, conf, disposition, reason}`
  where `disposition ∈ {"confirmed","dismissed","unreviewed"}`.
  `reason` is REQUIRED (non-empty string) when `disposition == "dismissed"`.
- `map.evidence_positions_summary` is an array of NATURAL LANGUAGE sentences describing physical locations and relative distances (e.g., "E1 is ~2.9 m from the main door"). Raw coordinates may be included as a separate optional `xy_optional` field, but the summary text is what the LLM reads.
- Every addressable node has a stable dotted `ref` path (e.g., `notes.N3`, `timeline.T2`, `photos.P1.d3`, `evidence.E1`).

## 5. Tier A rules (8)
The deterministic Tier A engine enforces exactly eight rules (A1–A8). Rule A9 is not part of the active catalog:

| ID | Rule | Flag type |
|---|---|---|
| A1 | detection with disposition == "unreviewed" | process_gap |
| A2 | detection dismissed with null or empty reason | process_gap |
| A3 | note mentions an object class that is present in NO detection at all (i.e. no confirmed, dismissed, or unreviewed detection has that class) AND no confirmed evidence of that class exists | note_evidence_gap |
| A4 | note contains HH:MM not present in any timeline entry | timeline_gap |
| A5 | map evidence position with no photo_ref | orphan_evidence |
| A6 | timeline entry with no `source` | metadata_gap |
| A7 | note references a room with no photo coverage | coverage_gap |
| A8 | confirmed evidence with no map position | mapping_gap |

Tier A flags represent objective structural deficiencies. They are not suggestions and carry zero hallucination risk.

## 6. Tier B LLM analysis types (3)
Tier B detects CATEGORICAL contradictions — two records that make mutually incompatible factual claims about the same identified entity or event. Approximate differences, omissions, subjective boundaries, and follow-up inquiries are explicitly out of scope:

- `spatial_inconsistency` — The same evidence item is explicitly placed in mutually exclusive physical locations across a note and the 2D map summary (or across distinct notes). Example: note says "near the main door", map summary places it "near the window, at the far end of the room from the main door." Not fired on approximate distance differences (e.g., "near door" vs "1.2 m from door").
- `timeline_contradiction` — Two records explicitly describe the SAME identified event (same actor and action) and assign incompatible times. Example: note says "police arrived at 21:40"; timeline records "police arrival at 22:10." A missing timeline entry or approximate interval difference is not a contradiction.
- `contextual_contradiction` — Two records make incompatible factual claims about the SAME identified entity (person, object, or event). Identity must be established in both records by shared identifying language (e.g., both records use the label "Device D1 — pink smartphone with a cracked screen"). Example: note says Device D1 was reported missing; dismissal reason says Device D1 was confirmed as the victim's own device and accounted for.

No other categories (e.g., ambiguity, follow-up, or semantic coverage gaps) are permitted. When in doubt, the system remains silent.

## 7. LLM output schema
Strict JSON (no markdown fences, no conversational prose preamble or trailer).
Top level: `{ "suggestions": [ <suggestion>, ... ] }`, maxItems: 10.
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

An empty suggestions list (`{ "suggestions": [] }`) is valid and PREFERRED when no categorical contradiction exists.

## 8. Validator checks (7, all mandatory, run in this order)
The validator establishes that references and extracted entities exist in the input `case_context`. It cannot mathematically guarantee that the LLM has interpreted the semantic relationship between cited fields correctly; semantic verification of each claim remains the investigator's responsibility:

1. **Schema validation:** Validates JSON structure, required keys, and types. Fails → drop whole response (`schema_fail`).
2. **Per-invocation type check:** Every suggestion's `type` field MUST equal the `assigned_analysis_type` passed to the validator for that invocation. Mismatches are dropped (`type_mismatch`).
3. **Reference resolution:** Every cited `evidence_refs` entry must resolve to an existing dotted node in `case_context`. Any unresolved reference drops the individual suggestion (`unresolved_ref`).
4. **Dismissal guard:** If a suggestion cites a dismissed detection with a non-null reason, drop unless type is `contextual_contradiction` AND at least one other cited reference resolves to a note or timeline entry (`dismissal_guard`).
5. **Entity hallucination detector:** Extracts proper nouns and numeric tokens from `summary`, `reasoning`, and `suggested_action`. If tokens are not present in `case_context` and not in the curated domain allowlist:
   - $\ge 2$ unverified tokens $\rightarrow$ drop suggestion (`hallucination_suspected`).
   - Exactly $1$ unverified token $\rightarrow$ retain suggestion with `validation_warning`.
6. **Tier A deduplication check:** Verifies whether a suggestion duplicates a Tier A finding. Generic reference-based suppression is inactive because shared references do not establish semantic equivalence between structural Tier A flags (e.g. process/coverage gaps) and pairwise semantic Tier B contradictions. Tier A flags do not automatically suppress Tier B suggestions.
7. **Severity sanity check:** A "high" severity rating requires at least two distinct evidence references; otherwise, it is automatically downgraded to "medium".

## 9. LLM provider architecture

### Implemented Provider Adapters
The codebase provides a unified client abstraction (`LLMClient`) supporting five provider backends:
1. **OpenAI (`openai`):** Native OpenAI chat completions API via `_call_openai_compatible`.
2. **Gemini (`gemini`):** Google GenAI SDK (`google-genai` 3.5.0) via `client.interactions.create` with structured JSON output mode.
3. **Anthropic (`anthropic`):** Anthropic Messages API (`/v1/messages`).
4. **OpenRouter (`openrouter`):** OpenAI-compatible completions endpoint (`https://openrouter.ai/api/v1/chat/completions`).
5. **Groq (`groq`):** High-speed LPU inference via OpenAI-compatible endpoint (`https://api.groq.com/openai/v1/chat/completions`).

### Selected Production Configuration
- **Provider:** `groq`
- **Model:** `openai/gpt-oss-120b` (120B parameter open-weights reasoning model)
- **Endpoint:** `https://api.groq.com/openai/v1/chat/completions`
- **API Key Environment Variable:** `GROQ_API_KEY` (with fallback to `LLM_API_KEY`)
- **Evaluation Status:** Verified in empirical single-case tests (1.87 s latency, 100% precision and recall on target fixtures); full 13-fixture benchmark has not yet been executed or passed.

### Execution Control, Error Handling, and Pacing
- **Temperature:** Fixed at 0.0 for deterministic evaluation.
- **Application-Level Schema Repair:** If a model response fails JSON shape validation, up to 2 correction attempts (3 total attempts) are performed with validation error feedback passed in the conversational history.
- **HTTP Transport Retries:** Zero automatic retries. Network errors, HTTP 4xx, and 5xx raise controlled non-retryable exceptions (`LLMTransportError`, `LLMAuthenticationError`, `LLMRateLimitError`, `LLMConfigurationError`).
- **Timeout:** Default 20.0 seconds (`DEFAULT_TIMEOUT_SECONDS`).
- **Groq Rate-Limit Pacing:** A 12.0-second inter-invocation sleep is enforced between multi-category calls on Groq within the pipeline to prevent exceeding Groq's free-tier 8,000 Tokens Per Minute (TPM) quota.

## 10. Test fixtures
- `cases/C<N>.json` = Case context file.
- `cases/C<N>.expected.json` = Ground truth evaluation expectations:
```json
{
  "clean": bool,
  "tier_a_expected": [ {"rule": "A1", "about_ref": "photos.P1.d3"}, ... ],
  "tier_b_expected": [ {"type": "contextual_contradiction",
                        "about_refs": ["notes.N3", "photos.P1.d3"]}, ... ]
}
```
Currently 13 fixtures are defined: `C0`–`C7`, `C10`–`C14`.

## 11. Acceptance targets (verified by evaluate.py)
Measured across the defined 13-fixture suite:

| Metric | Target | Constraint Type | Description |
|---|---:|---|---|
| Tier A recall | 1.00 | Required | All ground-truth structural gaps must be detected |
| Tier A precision | Informational | Informational | Real case structural facts detected beyond expected set are tracked without failing the run |
| Tier B recall | $\ge 0.85$ | Required | At least 85% of expected semantic contradictions detected |
| Tier B precision | $\ge 0.85$ | Required | At least 85% of validated suggestions must match expected findings |
| Hallucination / Rejection rate | 0.00 | Required | Zero suggestions dropped due to unverified entity hallucination |
| Clean-case false positives | 0 | Required | Zero Tier B suggestions produced on clean cases (`C5`, `C6`, `C7`, `C10`, `C11`, `C12`, `C13`) |
| Median complete-case latency | < 6000 ms | Required | End-to-end wall-clock latency per case under documented test conditions |

*Note on Grounding Distinction:* Fabricated-reference rate measures references failing ref resolution; hallucination rate measures unverified entity names or numbers in suggestion text. Both must be 0.00.  
*Performance Qualification:* A clean pass on the fixture suite demonstrates measured reliability on those specific fixtures; it does not mathematically prove that the system will never produce a false positive in production.

## 12. Directory layout
The actual repository directory layout is structured as follows:

```
repo/
  .github/
    workflows/
      ci.yml
  .gitignore
  analyze.py                      # CLI case analysis entry point
  evaluate.py                     # Evaluation benchmark harness
  full _roadmap.md                # Master implementation roadmap
  PROJECT_BRIEF.md                # Technical specification & source of truth
  pyproject.toml                  # Python build & tool configuration
  README.md                       # Project overview & documentation
  cases/                          # 13 test fixtures and ground truth files
    C0.json  C0.expected.json
    ...
    C14.json C14.expected.json
  Misc/                           # Documentation diagrams and background materials
  reports/                        # Evaluation reports (.gitkeep, runtime JSON & Markdown)
  runs/                           # Analysis run audit records (.gitkeep, runtime JSON)
  schemas/
    case_context.schema.json      # Schema contract for case_context
  scripts/
    check_fixtures.py             # Fixture integrity validation
    check_refs.py                 # Reference syntax & resolution validation
  src/
    analysis/
      __init__.py
      pipeline.py                 # End-to-end pipeline orchestrator & semantic gate
      refs.py                     # Dotted reference resolver
      tier_a.py                   # Deterministic Tier A rules engine (A1–A8)
      validator.py                # 7-stage post-LLM validation gate
    llm/
      __init__.py
      client.py                   # Provider-agnostic LLM client & provider adapters
      prompt_builder.py           # Case context prompt builder & serializer
      prompts/
        v1/
          contextual_contradiction.md
          spatial_inconsistency.md
          system.md
          timeline_contradiction.md
  tests/
    __init__.py
    test_client.py                # LLM client & provider adapter unit tests
    test_evaluate.py              # Evaluation harness unit tests
    test_pipeline.py              # Pipeline integration tests
    test_tier_a.py                # Deterministic Tier A rule tests
    test_validator.py             # 7-stage validator unit tests
```

## 13. Harness boundaries & Non-goals
The current harness deliberately excludes downstream production dependencies:
- **No SQLite:** The harness loads `case_context` directly from fixture JSON files.
- **No React frontend:** The investigator interaction prototype is a menu-driven CLI workflow test, not the final web UI.
- **No YOLO runtime dependency:** Object detections are pre-recorded in the `photos[].detections[]` fixture arrays.
- **No OpenCV runtime dependency:** Spatial distances are pre-computed in `map.evidence_positions_summary`.

## 14. Platform integration contract (for future modules)
When the broader platform is constructed:
- The **Case Context Module** must query SQLite / storage and assemble data strictly matching `schemas/case_context.schema.json`.
- The **Analysis Engine** remains completely decoupled from database ORM models, YOLO detection models, and OpenCV processing pipelines. It receives only validated `case_context` JSON.

## 15. Investigator interaction workflow (Prototype specification)
To validate the human-in-the-loop experience prior to full UI implementation, an investigator-facing interaction flow is defined:

1. **Operation Selection:** The investigator selects a target case and chooses an operation: Complete Analysis, Spatial Inconsistency only, Timeline Contradiction only, or Contextual Contradiction only.
2. **Application-Generated Request:** The application builds a structured request combining the unmodified `case_context` with the selected operation.
3. **Preservation of Case Context:** The input `case_context` is treated as immutable read-only data; the analysis engine never mutates the case context.
4. **Standardized Response Envelope:** The pipeline returns a standardized envelope detailing execution status (`completed`, `partial_success`, `failed`), metadata, Tier A facts, Tier B validated suggestions, and rejected items with drop reasons.
5. **Application-Controlled Actions:** The application—NEVER the LLM—controls workflow navigation and available review options.
6. **Investigator Review Decisions:** The investigator can review individual suggestions and record human decisions:
   - *View sources:* Display cited notes, timeline entries, or detection rationale.
   - *Acknowledge:* Mark the contradiction as reviewed and corroborated.
   - *Not relevant:* Mark the contradiction as non-actionable or explained by unrecorded context.
   - *Defer:* Leave for follow-up investigation.
7. **Audit & Decision Separation:** Human review decisions are stored separately from original analysis results. Original model findings remain immutable for auditing and reproducibility.

## 16. Prompt injection guard
Text inside `notes[].text`, `timeline[].description`, and `photos[].view` fields is DATA, never instructions. The system prompt explicitly instructs the LLM to treat case text strictly as passive data. The prompt serializer strips lines matching `(?i)(ignore (all )?previous|disregard|system:|assistant:)` from these fields before building the LLM prompt payload.
