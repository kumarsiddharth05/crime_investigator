# Final LLM Analysis Module Handover Document (Prompt 15)
## AI-Assisted Crime Scene Investigation and Evidence Analysis System

**Module:** Module 1 — LLM Analysis Module & Interaction Workflow Prototype  
**Date of Freeze:** 21 November 2026  
**Status:** **FROZEN & VERIFIED**  
**Freeze Readiness Verdict:** **PASS**  
**Authoritative Project Records:** `README.md`, `full _roadmap.md`, `PROJECT_BRIEF.md`, `PLAN.md`  

---

## 1. Architecture & 14-Point Verification Checklist (§A)

The LLM Analysis Module and its workflow layer comprise exactly 14 verified architectural components. All files are present at their canonical repository locations:

| # | Component | Exact Path | Role & Verified Status |
|---|---|---|---|
| 1 | Tier A Rules Engine | `src/analysis/tier_a.py` | Deterministic rules A1–A8; zero LLM dependency. **[VERIFIED]** |
| 2 | 7-Stage Validator Gate | `src/analysis/validator.py` | Defense-in-depth gate auditing all model suggestions. **[VERIFIED]** |
| 3 | Reference Resolver | `src/analysis/refs.py` | Strict dotted ref lookup (`notes.N#`, `photos.P#.d#`, etc.). **[VERIFIED]** |
| 4 | Pipeline Orchestrator | `src/analysis/pipeline.py` | Orchestrates Tier A, semantic gate, 1-per-call Tier B, audit logs. **[VERIFIED]** |
| 5 | Analysis Package Exports | `src/analysis/__init__.py` | Public interface exposing `run_pipeline`, `evaluate_semantic_gate`. **[VERIFIED]** |
| 6 | Multi-Provider Client | `src/llm/client.py` | Unified HTTPX client with `GroqRateLimiter` & structured JSON mode. **[VERIFIED]** |
| 7 | Prompt Builder | `src/llm/prompt_builder.py` | Dynamic prompt assembly and text sanitization. **[VERIFIED]** |
| 8 | Versioned Prompts | `src/llm/prompts/v1/*.md` | `system.md`, `spatial_inconsistency.md`, `timeline_contradiction.md`, `contextual_contradiction.md`. **[VERIFIED]** |
| 9 | LLM Package Exports | `src/llm/__init__.py` | Public interface exposing `LLMClient`, `LLMConfig`, exceptions. **[VERIFIED]** |
| 10 | Workflow Envelopes | `src/workflow/envelope.py` | Typed request/response envelopes (`v1.0`), status & 4 result states. **[VERIFIED]** |
| 11 | Prototype Store | `src/workflow/store.py` | Separate immutable analysis & append-only review persistence. **[VERIFIED]** |
| 12 | Pipeline Adapter | `src/workflow/adapter.py` | 1-category-per-call adapter, gate preservation, source inspection. **[VERIFIED]** |
| 13 | Workflow Package Exports | `src/workflow/__init__.py` | Public interface exposing `WorkflowAdapter`, `WorkflowStore`, envelopes. **[VERIFIED]** |
| 14 | Executable CLIs | `evaluate.py`, `analyze.py`, `investigator_cli.py` | Live benchmark harness, single-case analysis CLI, and 9-option interactive prototype CLI. **[VERIFIED]** |

---

## 2. Module Responsibilities & Strict Boundaries (§G)

Module 1 serves exclusively as a **semantic reconciliation and contradiction analysis engine**.

### Boundaries and Invariants
- **No Image Processing:** Module 1 has zero dependency on YOLO, OpenCV, PyTorch, PIL, image decoders, or raw image bytes. It never accesses photograph files directly.
- **No UI Framework Dependencies:** Zero dependency on React, Vue, Flask, FastAPI, WebSockets, or browser DOM state. The CLI (`investigator_cli.py`) utilizes standard Python streams with dependency-injected I/O.
- **No ORM or Database Locking:** Operates strictly on in-memory Python dictionaries deserialized from `case_context` JSON. Persistence is strictly decoupled via `src/workflow/store.py`.
- **No Guilt Attribution:** Never draws conclusions of guilt, never profiles suspects, and never invents forensic hypotheses.
- **Deterministic Precedence:** Tier A deterministic rules execute first without LLM calls. If semantic preconditions are absent, Tier B LLM calls are skipped entirely.

---

## 3. Input & Output Contracts (§C)

### 3.1 Contract Separation
System design strictly separates two distinct contract layers:
1. **Case Data Contract (`schemas/case_context.schema.json`):** Domain data assembled by upstream modules (and Module 5 SQLite builder).
2. **Workflow Interaction Envelopes (`src/workflow/envelope.py`):** Application-level request/response protocol governing CLI and future UI interaction.

---

### 3.2 Domain Case Context Contract (`schemas/case_context.schema.json`)
The case context JSON contains 7 required top-level keys:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "case": {
    "id": "C-2026-001",
    "type": "burglary",
    "title": "Residential burglary — Davangere",
    "incident_window": { "start": "2026-10-14T20:00:00Z", "end": "2026-10-14T23:30:00Z" },
    "rooms_covered": ["living_room", "bedroom"]
  },
  "evidence": [
    {
      "ref": "evidence.E1",
      "label": "bloody kitchen knife",
      "photo_ref": "photos.P1",
      "det_ref": "photos.P1.d1",
      "map_ref": "map.E1"
    }
  ],
  "photos": [
    {
      "ref": "photos.P1",
      "room": "living_room",
      "view": "overview_south",
      "detections": [
        {
          "ref": "photos.P1.d1",
          "class": "knife",
          "conf": 0.92,
          "disposition": "confirmed",
          "reason": null
        },
        {
          "ref": "photos.P1.d2",
          "class": "bottle",
          "conf": 0.88,
          "disposition": "dismissed",
          "reason": "Homeowner water bottle"
        }
      ]
    }
  ],
  "map": {
    "evidence_positions_summary": [
      "Evidence E1 (bloody kitchen knife) is positioned at approx (3.8, 2.9) m — about 2.9 m from the main entrance door and ~2.3 m from the living room window, near the south wall."
    ]
  },
  "timeline": [
    {
      "ref": "timeline.T1",
      "time": "21:15",
      "source": "neighbor_interview",
      "description": "Neighbor reported hearing loud crash from apartment."
    }
  ],
  "notes": [
    {
      "ref": "notes.N1",
      "type": "observation",
      "text": "First responding officer observed kitchen knife near the main entrance door."
    }
  ],
  "derived_facts": []
}
```

#### Dotted Reference Syntax (`src/analysis/refs.py`)
All cross-source links resolve using dotted string paths:
- `notes.N#`: Direct lookup in `case_context["notes"]` matching item with `ref == "notes.N#"`.
- `photos.P#.d#`: Navigates to photo with `ref == "photos.P#"`, then detection with `ref == "photos.P#.d#"`.
- `evidence.E#`: Direct lookup in `case_context["evidence"]`.
- `timeline.T#`: Direct lookup in `case_context["timeline"]`.
- `map.E#`: Direct lookup in `case_context["map"]["xy_optional"]` (or `map["reference_points"]`). *(Verified against `src/analysis/refs.py` and case fixtures).*

---

### 3.3 Workflow Interaction Envelopes (`src/workflow/envelope.py`)

#### Request Envelope (`schema_version="1.0"`)
```json
{
  "schema_version": "1.0",
  "request_id": "req_8b7c3d2e",
  "case_id": "C-2026-002",
  "operation": "analyze",
  "analysis_types": [
    "spatial_inconsistency"
  ],
  "case_context": { ... }
}
```
- `schema_version`: Must equal `"1.0"`.
- `operation`: Must equal `"analyze"`.
- `analysis_types`: Non-empty list containing a subset of `{"spatial_inconsistency", "timeline_contradiction", "contextual_contradiction"}`.

#### Response Envelope (`schema_version="1.0"`)
```json
{
  "schema_version": "1.0",
  "request_id": "req_8b7c3d2e",
  "case_id": "C-2026-002",
  "module": "llm_analysis",
  "operation": "analyze",
  "status": "completed",
  "data": {
    "analysis_id": "analysis_1795281314_3c9e3ff9",
    "result_state": "findings_returned",
    "tier_a_flags": [],
    "suggestions": [
      {
        "suggestion_id": "S001",
        "type": "spatial_inconsistency",
        "severity": "high",
        "summary": "Note N1 places the knife near the main door; map places it near the window far from the main door.",
        "evidence_refs": ["notes.N1", "evidence.E1"],
        "reasoning": "Officer observation N1 directly conflicts with mapped planar coordinates for knife E1.",
        "suggested_action": "Recheck physical measurement logs and photo P1 perspective."
      }
    ],
    "completed_categories": ["spatial_inconsistency"],
    "ineligible_categories": [],
    "failed_categories": [],
    "retryable_categories": [],
    "validation_summary": {
      "received": 1,
      "validated": 1,
      "rejected": 0,
      "drop_reasons": {
        "schema_fail": 0,
        "type_mismatch": 0,
        "unresolved_ref": 0,
        "dismissal_guard": 0,
        "hallucination_suspected": 0,
        "deduped_by_tier_a": 0
      }
    }
  },
  "warnings": [],
  "errors": [],
  "available_actions": [
    "view_findings",
    "review_findings",
    "inspect_source_references",
    "run_analysis",
    "view_case_history",
    "return_to_menu"
  ]
}
```

#### The 4 Presentation States (`data.result_state`)
1. `findings_returned`: Validated Tier B suggestions present with zero execution errors (`status="completed"` or `"completed_with_warnings"` if gate skipped other requested categories).
2. `empty_suggestions`: All eligible requested categories ran cleanly with 0 validated suggestions and 0 failures (`status="completed"` or `"completed_with_warnings"`). Displays exact message: `"No contradictions were identified in the selected analysis category using the available case information."`
3. `partial_completion`: Mix of completed and failed/ineligible categories (`status="completed_with_warnings"`). Completed results preserved; `retryable_categories` lists only eligible failed categories.
4. `technical_failure`: All attempted categories failed due to transport, parsing, or auth errors (`status="failed"`). Never disguised as empty suggestions.

#### Investigator Review Record (`src/workflow/store.py`)
Appended to `runs/workflow_history/reviews/<analysis_id>.jsonl`:
```json
{
  "review_id": "rev_29e91097",
  "analysis_id": "analysis_1795281314_3c9e3ff9",
  "suggestion_id": "S001",
  "review_status": "acknowledged",
  "reviewed_by": "investigator_01",
  "reviewed_at": "2026-11-21T17:15:39Z",
  "comment": "Live workflow verification"
}
```
- Permitted `review_status`: `pending`, `acknowledged`, `not_relevant`, `deferred`.
- Mandatory explanation: If `review_status == "not_relevant"`, `comment` must be non-empty whitespace-trimmed text; raises `ValueError` if missing.
- Separate storage: The analysis snapshot in `analyses/<analysis_id>.json` is strictly immutable and never mutated when reviews are logged.

---

## 4. Provider Configuration & Model Replacement Procedure (§B)

### 4.1 Active Production Target
- **Provider:** Groq
- **Model:** `openai/gpt-oss-120b`
- **Inference Endpoint:** `https://api.groq.com/openai/v1/chat/completions`
- **Output Mode:** Structured JSON (`response_format={"type": "json_object"}`)
- **Temperature:** `0.0` (fixed)
- **Timeout:** `20.0` seconds

### 4.2 Environment Variables
- `LLM_PROVIDER=groq`
- `LLM_MODEL=openai/gpt-oss-120b`
- `GROQ_API_KEY=<secret>` (falls back to `LLM_API_KEY` if unset)
- `GROQ_COOLDOWN_SECONDS=20.0` (rate-limiter pacing)

### 4.3 Pacing & Transport Retry Policy
- **Pacing (`GroqRateLimiter`):**
  - Thread-safe class tracking `last_call_time`. Enforces minimum 20.0s sleep between calls.
  - Header inspection: If `x-ratelimit-remaining-tokens < 2500`, pauses automatically.
  - On HTTP 429: Parses `Retry-After` header or `"try again in Xs"` regex and waits specified interval.
- **Zero Transport Retries:**
  - Network timeouts, connection drops, HTTP 429, and HTTP 5xx raise immediate non-retryable exceptions (`LLMTransportError`, `LLMRateLimitError`).
  - `max_attempts` (up to 2 retries) applies **strictly** to HTTP 200 OK responses with invalid JSON or schema parse failures.

### 4.4 Dormant Maintenance Procedure: Step-by-Step Model Replacement
*(Dormant Maintenance Procedure — Not an active recommendation. Module 1 is frozen on Groq `openai/gpt-oss-120b`. This procedure is documented strictly for future operational maintenance if the active model is deprecated).*

To replace or upgrade the LLM provider/model if required in future operations:
1. Update `.env` (e.g., `LLM_PROVIDER=groq`, `LLM_MODEL=<new-model>`).
2. Run offline test suite:
   ```powershell
   pytest -q
   ```
3. Run dry-run evaluation to verify harness and prompt rendering without API calls:
   ```powershell
   python evaluate.py --dry-run-llm
   ```
4. Run full 13-fixture checkpointed benchmark with single concurrency:
   ```powershell
   python evaluate.py --max-concurrency 1
   ```
5. Confirm benchmark criteria:
   - Tier A Recall: `1.00`
   - Tier B Recall: `>= 0.80` (production model achieved `1.00`)
   - Tier B Precision: `>= 0.80` (production model achieved `1.00`)
   - Clean-Case False Positives: `0`
   - Zero HTTP 429 errors.

---

## 5. Analysis Semantics (§D)

### 5.1 Tier A Deterministic Rules (`src/analysis/tier_a.py`)
- `A1`: Unreviewed candidate detection (`disposition == "unreviewed"`).
- `A2`: Dismissed detection with null or empty dismissal reason.
- `A3`: Note mentions physical evidence class absent from all detections (confirmed, dismissed, unreviewed) and confirmed evidence items.
- `A4`: Note contains explicit `HH:MM` time absent from timeline records.
- `A5`: Mapped evidence coordinate missing `photo_ref`.
- `A6`: Timeline entry missing cited `source`.
- `A7`: Note mentions room name with zero photo coverage.
- `A8`: Confirmed evidence item missing 2D map coordinates.
*(Rule A9 is removed and permanently prohibited).*

### 5.2 Tier B Categories & Semantic Gate (`src/analysis/pipeline.py`)
The 3 approved Tier B categories are executed strictly 1 category per LLM call:
1. `spatial_inconsistency`: Physical location mismatch between notes and map summary, or between multiple notes. Requires spatial indicator keywords + map summary or >=2 spatial notes.
2. `timeline_contradiction`: Chronological conflict between time-bearing notes/timeline entries. Requires >=2 valid `HH:MM` timestamps.
3. `contextual_contradiction`: Factual conflict across comparable case records. Requires >=2 relevant descriptive records across notes, timeline, detections, or evidence.

### 5.3 7-Stage Validation Gate (`src/analysis/validator.py`)
1. **Schema Check:** Validates structure against `REQUIRED_SUGGESTION_KEYS`; caps at 10 suggestions.
2. **Category Check:** Verifies suggestion `type` matches the category assigned for this invocation.
3. **Reference Resolution:** Confirms every cited ref resolves to an existing node in `case_context`.
4. **Dismissal Guard:** Drops non-contextual suggestions citing dismissed detections; for contextual contradictions, requires an additional note or timeline record.
5. **Hallucination Detector:** Tokenizes suggestion entities against case context allowlist + 172-token `GENERIC_VOCABULARY`. >=2 unverified tokens causes rejection; 1 token causes warning.
6. **Tier A Deduplication:** Inactive for pairwise contradictions; exact-ref suppression prohibited.
7. **Severity Sanity:** Downgrades `high` severity to `medium` if fewer than 2 distinct evidence refs are cited.

### 5.4 Investigator Responsibilities
- Model suggestions are analytical aids, not judicial proof.
- **Acknowledgement does not establish factual truth:** The CLI explicitly presents: `Finding marked as acknowledged. (Note: Acknowledgement does not establish factual truth.)`

---

## 6. Evaluation Results & Reproducibility (§E)

### Preserved Benchmark Artifacts
- **Full Run Report (JSON):** [reports/eval_20261121_130243.json](file:///d:/Project/AI_Assisted_CrimeInvestigation_and_Evidence_Analysis/reports/eval_20261121_130243.json) (20,108 bytes)
- **Summary Report (Markdown):** [reports/eval_20261121_130243.md](file:///d:/Project/AI_Assisted_CrimeInvestigation_and_Evidence_Analysis/reports/eval_20261121_130243.md) (2,494 bytes)
- **Incremental Checkpoint:** [reports/checkpoints/eval_checkpoint_20261121_130243.json](file:///d:/Project/AI_Assisted_CrimeInvestigation_and_Evidence_Analysis/reports/checkpoints/eval_checkpoint_20261121_130243.json) (17,171 bytes)

### Benchmark Summary on Groq `openai/gpt-oss-120b` (21 Nov 2026)
- **Fixtures Evaluated:** All 13 canonical fixtures (`C0–C7`, `C10–C14`).
- **Tier A Recall:** `1.00` (3/3 flags identified) — **PASS**
- **Tier B Recall:** `1.00` (5/5 expected contradictions detected: 2 contextual, 2 spatial, 1 timeline) — **PASS**
- **Tier B Precision:** `1.00` (5 validated / 5 returned) — **PASS**
- **Clean-Case False Positives:** `0` (across 7 clean fixtures) — **PASS**
- **Validator Rejection Rate:** `0/5` (0%) — **PASS**
- **API Errors / 429s:** `0 / 0` across 29 live HTTP requests — **PASS**
- **Latency / Token Breakdown (Informational):**
  - Prompt Tokens: 76,839 | Completion Tokens: 6,907 | Total Tokens: 83,746
  - Provider Latency: Min 538.6 ms | Median 22,626.6 ms | Max 72,102.9 ms
  - Cooldown Time: 425.21 s | Total Benchmark Duration: 762.49 s

---

## 7. Fresh Offline Test Verification (§F)

Executed from repository root on Python 3.14:
- `pytest -q`: **163 passed, 1 warning** (exit `0`)
- `pytest tests/test_workflow.py -v`: **17 passed, 1 warning** (exit `0`)
- `python scripts/check_fixtures.py`: **13/13 fixtures valid** against Draft-07 schema (exit `0`)
- `python scripts/check_refs.py`: **13/13 refs resolved** across all cases (exit `0`)
- `pyrefly check src/ tests/`: **0 errors** (1 suppressed, 3 warnings not shown; exit `0`)

---

## 8. Known Limitations

1. **Regression Scope vs. Real-World Variance:** The 13 fixtures represent specific regression baselines; they do not constitute statistical proof across arbitrary unconstrained real-world crime scenes.
2. **Heuristic Hallucination Detector:** Check 5 utilizes a 172-token vocabulary heuristic. It flags novel capitalized named entities and ungrounded nouns, but cannot catch plausible common-noun substitutions or prove semantic truth.
3. **Prototype File Persistence:** `src/workflow/store.py` uses JSON files under `runs/workflow_history/`. It is a lightweight prototype store for development and testing, not an enterprise ACID database.
4. **Context Budgeting Deferred:** Truncation and token-budget limits (~4,000 tokens) are deferred to Module 5 (Production Case Context Builder), where SQLite records are assembled.
5. **Live Verification Status of Alternative Adapters:** Non-Groq adapters (OpenAI, Gemini, Anthropic, OpenRouter) are implemented and unit-tested with mocked transports, but were not subjected to the live 13-fixture benchmark.

---

## 9. Operational Commands

### Offline Testing & Validation
```powershell
# Run full unit and regression test suite
pytest -q

# Run workflow prototype mocked tests
pytest tests/test_workflow.py -v

# Validate JSON schema compliance of all 13 fixtures
python scripts/check_fixtures.py

# Validate cross-source reference integrity across all fixtures
python scripts/check_refs.py

# Run static type checking
pyrefly check src/ tests/
```

### Evaluation Harness & Analysis CLIs
```powershell
# Dry-run evaluation (no live API requests)
python evaluate.py --dry-run-llm

# Live benchmark against all 13 fixtures (concurrency 1, paced)
python evaluate.py --max-concurrency 1

# Analyze a single case via CLI (Tier A only)
python analyze.py cases/C0.json --tier-a-only

# Analyze a single case via CLI with production Groq
python analyze.py cases/C2.json --type spatial_inconsistency

# Launch interactive 9-option Investigator CLI
python investigator_cli.py
```

---

## 10. Integration Requirements for Future Modules & Explicit Freeze Verdict

### Contract Requirements for Upstream Modules
- **Module 2 (YOLO Candidate Detection):**
  - Must write candidate detections under `photos[].detections[]` with `ref` format `photos.P<photo_id>.d<det_id>`.
  - Must set `disposition` to `"unreviewed"`, `"confirmed"`, or `"dismissed"`.
  - If `disposition == "dismissed"`, a non-empty `reason` string is mandatory (enforced by schema and Tier A Rule A2).
  - Must never mutate raw original photos; annotated previews must be stored separately.
- **Module 3 (OpenCV Planar Mapping):**
  - Must output planar coordinates under `map.evidence_positions_summary[]` with explicit reference to confirmed evidence items (`evidence.E#`).
  - Coordinate summaries must mention physical reference markers (e.g., entrance door, window) to satisfy spatial semantic gate preconditions.
- **Module 4 (Timeline Construction):**
  - Must output entries under `timeline[]` with `ref` format `timeline.T#`.
  - Must preserve `HH:MM` time format and cite explicit `source` (enforced by Tier A Rule A6).
- **Module 5 (Production Case Context Builder):**
  - Must assemble SQLite tables into valid JSON strictly matching `schemas/case_context.schema.json`.
  - Must enforce context size constraints and token budgeting (~4,000 tokens) prior to invoking `WorkflowAdapter`.
- **Module 6 (ReportLab Report Generation):**
  - Consumes `WorkflowResponse` JSON.
  - Must render Tier A flags, validated Tier B suggestions, and investigator review status clearly separated from raw model outputs.
- **Module 8 (Final Menu-Based UI):**
  - Replaces CLI presentation layer by calling `WorkflowAdapter.execute_request()` and `WorkflowStore`.
  - Must honor deterministic `available_actions` and presentation states.

---

### Explicit Freeze Verdict

```text
================================================================================
FINAL VERDICT: FREEZE READINESS: PASS
================================================================================
Module 1 (LLM Analysis Module) and Prompt 14 (Workflow Prototype) satisfy all
forensic, architectural, operational, and testing criteria.

Codebase is formally FROZEN. Active development proceeds to Module 2 (YOLO).
================================================================================
```
