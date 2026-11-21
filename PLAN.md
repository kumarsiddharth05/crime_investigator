# PLAN.md — Operational Project Plan & Continuity Record
## AI-Assisted Crime Scene Investigation and Evidence Analysis System

**Repository:** `kumarsiddharth05/crime_investigator`  
**Production LLM:** Groq — `openai/gpt-oss-120b`  
**Current Stage:** **Module 1 (LLM Analysis Module) FROZEN; Module 2 (YOLO Detection & Evidence Management) ACTIVE — Stages Y1, Y2 & Y3 COMPLETE; Stage Y4 next.**  
**4-Document Architecture Authority Hierarchy:**
1. `README.md` — Permanent entry point, system overview, project status, core principles.
2. `full _roadmap.md` — Master project roadmap, sequence, cross-module criteria.
3. `PROJECT_BRIEF.md` — Authoritative active-module engineering specification (currently Module 2).
4. `PLAN.md` — Reconciled operational record, active roadmap, and decision/implementation ledger.
*(Permanent Handover Documents: `docs/*_HANDOVER.md` record frozen contracts for completed modules).*

---

## 1. Project Overview

- **Objective:** Build a structured, traceable, menu-driven **AI-Assisted Crime Scene Investigation and Evidence Analysis System** organizing crime-scene photographs, candidate object detections, investigator-confirmed evidence, 2D planar spatial representations, source-backed timelines, categorized case notes, cross-source consistency analysis, and traceable reports.
- **Intended Users:** Crime scene investigators and case analysts working in a controlled workspace (not a chatbot).
- **Non-Negotiable Forensic Boundaries:**
  - Never determine guilt, profile suspects, invent facts, or replace investigator judgment.
  - LLM is strictly a semantic reconciliation assistant operating on structured JSON (`case_context`), never raw images.
  - A YOLO detection is a candidate requiring investigator review, never automatically evidence.
  - A 2D rectified map is a planar floor representation with geometric limitations, not an architectural floor plan or 3D reconstruction.
  - Timelines and notes preserve uncertainty, approximate times, and conflicting accounts without silent overwriting.

---

## 2. System Architecture

### 8-Stage Conceptual Pipeline vs. Current Harness
1. Investigator trigger (`analyze.py` / future Prompt 14 workflow & UI).
2. Case Context Builder (**Pending — Module 5**): SQLite → `case_context` JSON matching `schemas/case_context.schema.json`. *(Current harness loads `cases/C*.json` directly.)*
3. Tier A deterministic rules (`src/analysis/tier_a.py`, rules A1–A8).
4. Semantic eligibility gate (`src/analysis/pipeline.py`).
5. Prompt construction (`src/llm/prompt_builder.py` + `src/llm/prompts/v1/*.md`).
6. Single-category LLM invocation (`src/llm/client.py`, Groq `openai/gpt-oss-120b` via HTTPX + `GroqRateLimiter`).
7. 7-stage defense-in-depth validator (`src/analysis/validator.py` + `src/analysis/refs.py`).
8. Audit logging (`runs/`, SHA-256 context hash) and future separate investigator review persistence (Prompt 14).

### Core Dependencies (`pyproject.toml`)
`httpx>=0.27.0`, `jsonschema>=4.20.0`, `pytest>=8.0.0`, `python-dotenv>=1.0.0`, `pyyaml>=6.0`, `rich>=13.0.0`, `tenacity>=8.2.0`. Optional extras: `openai`, `google-genai`, `anthropic`. Groq uses `httpx` directly.

---

## 3. Approved Requirements & Constraints (Locked)

- **Tier A (Exact Set: A1–A8; A9 removed & prohibited):**
  - `A1` unreviewed detection; `A2` dismissed detection with null/empty reason; `A3` note mentions object class absent from **all** detections (confirmed/dismissed/unreviewed) and confirmed evidence; `A4` note contains `HH:MM` absent from timeline (preserving approximate wording); `A5` mapped evidence without `photo_ref`; `A6` timeline entry without source; `A7` note mentions room without photo coverage; `A8` confirmed evidence without map position.
- **Tier B (Exact Set: 3 categories, 1 per LLM request; empty `suggestions` valid):**
  - `spatial_inconsistency`, `timeline_contradiction`, `contextual_contradiction`.
  - Removed & prohibited: `ambiguity`, `follow_up`, `semantic_coverage_gap`.
- **Validator (`validate(llm_response, case_context, tier_a_flags, assigned_analysis_type)`) — 7 Ordered Checks:**
  1. Schema validation (max 10 suggestions; usable list => `received == validated + rejected` and `rejected == sum(drop_reasons.values())`; unusable list => `received=0, schema_fail=1`).
  2. Assigned category match (invalid configured category raises `ValueError` even on empty list).
  3. Reference resolution against `case_context`.
  4. Dismissal guard (non-contextual rejects dismissed detection with reason; `contextual_contradiction` requires an additional note or timeline ref—mechanical prerequisite, not semantic proof).
  5. Heuristic entity hallucination detector (context allowlist + 172-token `GENERIC_VOCABULARY`; >=2 unverified => reject, 1 => warning, 0 => clean).
  6. Tier A deduplication (inactive for current single-ref Tier A vs. pairwise Tier B; generic exact-ref suppression prohibited).
  7. Severity sanity (`high` requires >=2 distinct evidence refs; else downgraded to `medium`).
- **Fixtures:** Exact 13-fixture set (`C0–C7`, `C10–C14`). `C8`, `C9`, and `llm context.txt` are deleted and prohibited.
- **Operational Rules:** Manual user control over all Git operations; no live LLM API calls without explicit authorization; never expose `.env` secrets; preserve all historical evaluation reports and checkpoints.

---

## 4. Architecture Decision Record (ADR)

| ID | Decision | Rationale | Status |
|---|---|---|---|
| **ADR-01** | LLM restricted to structured-JSON semantic reconciliation; no images, no autonomous conclusions. | Forensic defensibility and investigator authority. | **Locked** |
| **ADR-02** | Separate deterministic Tier A (A1–A8) from semantic Tier B (3 categories); ban A9 and removed categories. | Prevents speculative noise and redundant LLM calls. | **Locked** |
| **ADR-03** | One Tier B category per LLM invocation; empty `suggestions` valid. | Enforces precision and clean-case restraint. | **Locked** |
| **ADR-04** | Retain 7-check validator with category-sensitive dismissal guard and no generic Tier A exact-ref suppression. | Defense-in-depth without false suppression. | **Locked** |
| **ADR-05** | Finalize production LLM on **Groq `openai/gpt-oss-120b`** via HTTPX. | Passed full 13-fixture live evaluation; Gemini/OpenRouter hit deprecation/free-tier quota limits. | **Locked** |
| **ADR-06** | Retire 6,000 ms latency pass/fail threshold; report provider latency, complete-case latency, cooldown, and total duration separately as informational. | Analytical accuracy prioritized over wall-clock speed. | **Locked** |
| **ADR-07** | Treat validator rejection rate (`rejected / received`) as diagnostic by reason, distinct from semantic hallucination rate. | Structural/type/ref rejections are not all hallucinations. | **Locked** |
| **ADR-08** | Keep verified `GroqRateLimiter` (`src/llm/client.py`) as-is: thread-safe 20.0s default cooldown (`GROQ_COOLDOWN_SECONDS`), `Retry-After` / `"try again in Xs"` backoff on 429, and `x-ratelimit-remaining-tokens < 2500` header pacing; **zero** HTTP 429/5xx transport retries (`max_attempts` retries 200 OK JSON schema repair only). | Verified in source inspection and 29-request live benchmark (0 errors, 0 HTTP 429s); simple, tested, no redesign needed. | **Locked (Verified)** |
| **ADR-09** | Keep `evaluate.py` live-mode acceptance targets as-is (`median_latency_ms` and `hallucination_rate` excluded from `required_targets` in live mode; display fields preserved for unit-test compatibility). | Intentional behaviour verified in source; avoids unnecessary churn before freeze. | **Locked (Verified)** |
| **ADR-10** | Defer context token-budget limiting (~4,000 tokens) to Module 5 (Production Case Context Builder); keep `src/llm/prompt_builder.py` as-is for Module 1. | Current fixtures fit comfortably within limits; real budgeting belongs where DB records are assembled. | **Locked (Verified)** |
| **ADR-11** | Skip Prompt 13 (no analytical defects in Prompt 12.2); freeze Module 1 and proceed sequentially: Prompt 14 → YOLO → OpenCV → Timeline → Case Context → Reports → Final Menu UI. | Clean 1.00 benchmark pass; incremental integration at each module boundary. | **Locked** |

---

## 5. Implementation Status

| Component | Location | Status | Verification |
|---|---|---|---|
| Case Context Schema & 13 Fixtures | `schemas/case_context.schema.json`, `cases/C*.json` | **Complete (Frozen)** | 13/13 schema & 13/13 ref checks passed. |
| Tier A Engine (A1–A8) | `src/analysis/tier_a.py`, `tests/test_tier_a.py` | **Complete (Frozen)** | Passed in 146-test suite & 3/3 live eval. |
| Reference Resolver & 7-Check Validator | `src/analysis/refs.py`, `src/analysis/validator.py` | **Complete (Frozen)** | Passed in 146-test suite & 0/5 live rejections. |
| Pipeline & Semantic Gates | `src/analysis/pipeline.py`, `tests/test_pipeline.py` | **Complete (Frozen)** | Passed in 146-test suite & live eval. |
| Prompt Builder & v1 Prompts | `src/llm/prompt_builder.py`, `src/llm/prompts/v1/*.md` | **Complete (Frozen)** | Verified live; token budgeting deferred to Module 5. |
| LLM Client (Groq + Rate Limiter) | `src/llm/client.py`, `tests/test_client.py` | **Complete (Frozen)** | Verified live (29 reqs, 0 errors) + source audit. |
| Optional Adapters (OpenAI/Anthropic/Gemini/OpenRouter) | `src/llm/client.py` | **Implemented (Live-Unverified)** | Unit/mock tests only; not active production targets. |
| Evaluation Harness & Checkpointing | `evaluate.py`, `tests/test_evaluate.py` | **Complete (Frozen)** | Completed 13-fixture live run + 28 unit tests. |
| CLI Entry Point | `analyze.py` | **Complete (Frozen)** | `--provider` help updated to include `groq`, `openrouter`. |
| Prompt 14 — Investigator Interaction Workflow Prototype | `src/workflow/`, `investigator_cli.py`, `tests/test_workflow.py` | **Complete** | 17/17 mocked workflow tests, 163/163 pytest suite, 0 Pyrefly errors, and 1 controlled live Groq workflow test (C2 spatial_inconsistency) passed on 21 Nov 2026. |
| Module 2 — YOLO Candidate Detection & Evidence Management | `src/yolo/`, `tests/test_yolo.py`, `docs/YOLO_MODULE_HANDOVER.md` | **Active (Stages Y1–Y3 Complete)** | Stages Y1, Y2, Y3 verified (29/29 unit tests, 192/192 full pytest, 0 Pyrefly errors); Stage Y4 next. |
| Modules 3–8 (Spatial, Timeline, Case Context, Reports, Menu UI) | Not created | **Pending** | Sequential roadmap after Module 2 (see `full _roadmap.md`). |

---

## 6. Completed Milestones

1. **Core Contracts, Tier A & Validator (Prompts 2.7–3):** Implemented schema, refs, A1–A8, and 7-check validator.
2. **Pipeline, Semantic Gates & CLI (Prompt 5):** Implemented `pipeline.py` and `analyze.py`.
3. **Evaluation Harness & Multi-Provider Client (Prompts 6–11):** Implemented `evaluate.py`, 5 provider adapters, and CI `.[all]` fix.
4. **Live Groq Evaluation (Prompt 12.2 — 21 Nov 2026):** Completed all 13 fixtures via production pipeline on Groq `openai/gpt-oss-120b` with 1.00 Tier A recall, 1.00 Tier B precision/recall, 0 clean-case FPs, 0 API/429 errors. Prompt 13 skipped.
5. **Baseline Audit & Module 1 Freeze:** Verified `CI` green on `origin/main` (`9c20fa94904b`), inspected `client.py`, `evaluate.py`, `prompt_builder.py`, and `analyze.py`, fixed `analyze.py` provider help text, and established `PLAN.md`.
6. **Prompt 14 — Investigator Interaction Workflow Prototype (21 Nov 2026):** Implemented request/response envelope (`schema_version="1.0"`), 4 result presentation states, deterministic Python-only available actions, prototype separate immutable analysis & append-only review persistence under `runs/workflow_history/`, 1-category-per-invocation adapter wrapping frozen pipeline, and 9-option interactive CLI. Verified with 17/17 offline mocked tests, full 163-test pytest suite, 0 Pyrefly errors, and 1 controlled live Groq integration test on `cases/C2.json` (`spatial_inconsistency`, 1 HTTP request).
7. **Prompt 15 — Final LLM Analysis Module Freeze & Handover (21 Nov 2026):** Generated standalone final module handover document (`docs/LLM_MODULE_HANDOVER.md`) detailing the 14 architecture components, module boundaries, exact input/output and workflow interaction envelope schemas, Groq configuration and model replacement procedure, analysis semantics (A1–A8, 3 Tier B categories, 7-check validator), evaluation reproducibility, offline test verification, known limitations, operational commands, upstream module integration requirements, and explicit Freeze Readiness: PASS verdict.
8. **Module 2 Stage Y0 Pre-Design Inspection & Closure (22 Nov 2026):** Completed strictly read-only pre-design audit of repository contracts, Python 3.14 CPU environment, and active documentation. Adopted 4-document governance model; closed 6 Y0 corrections (locked Y1–Y8 sequence, corrected Tier A Rule A3 semantics, provisional yolov8n.pt CPU strategy with unverified Python 3.14 vision compatibility, 3-layer evidence representation, documentation alignment, and verified map.E# resolution). Ready for Stage Y1.
9. **Module 2 Stages Y1 & Y2 — Core Entities, Storage, Audit & Detector Backend (22 Nov 2026):** Implemented the 5 core domain entities (`PhotoRecord`, `DetectionRun`, `DetectionCandidate`, `EvidenceRecord`, `ReviewEvent`, `EvidenceEvent`), atomic file storage & SHA-256 integrity verification (`src/yolo/store.py`), monotonic photo-scoped ID counters, append-only JSONL audit logging, `DetectorBackend` protocol, deterministic `StubDetectorBackend`, and lazy-loaded `UltralyticsYOLOBackend` (`src/yolo/detector.py`). Verified with 24/24 unit tests in `tests/test_yolo.py`, 187/187 full pytest suite, 13/13 fixtures and refs, and 0 Pyrefly errors.
10. **Module 2 Stage Y3 — EXIF Orientation, Letterbox Transforms & Separate Preview Rendering (22 Nov 2026):** Implemented pure-stdlib JPEG EXIF orientation extraction (II and MM byte orders for IFD0 tag 0x0112), dimension swapping (for orientations 5, 6, 7, 8), aspect-preserving letterbox scale and padding computation (`ImagePrepMetadata`), reversible letterbox coordinate mapping with boundary clipping and zero-area validation (`reverse_letterbox_bbox`), and separate annotated preview generation (`render_annotated_preview`) with strict immutability guards (`output_path != original_path`, verified SHA-256 preservation), 0-detection handling, color-coded yellow/green/grey candidate outlines, pure stdlib PNG fallback, and optional Pillow integration. Verified with 29/29 unit tests in `tests/test_yolo.py`, 192/192 full pytest suite, 13/13 fixtures and refs, and 0 Pyrefly errors. Ready for Stage Y4.

---

## 7. Evaluation Results (Prompt 12.2 — 21 Nov 2026)

- **Provider / Model:** Groq `openai/gpt-oss-120b` (`evaluate.py --max-concurrency 1`, 20s cooldown)
- **Analytical Metrics:** Tier A Recall `1.00` (3/3) **PASS** | Tier A Precision `1.00` | Tier B Recall `1.00` (5/5: 2 contextual, 2 spatial, 1 timeline) **PASS** | Tier B Precision `1.00` **PASS** | Clean-Case FPs `0` (7 clean cases) **PASS** | Validator Rejections `0/5` (diagnostic) | API Errors / 429s `0 / 0`.
- **Operational / Latency (Informational):** 29 HTTP requests | 83,746 tokens (76,839 prompt / 6,907 completion) | Provider latency min/median/max: `538.6 / 22,626.6 / 72,102.9 ms` | Complete-case latency min/median/max: `1,655.4 / 66,208.4 / 106,852.1 ms` | Cooldown wait: `425.21 s` | Total duration: `762.49 s`.
- **Preserved Artifacts (Verified Intact):**
  - `reports/eval_20261121_130243.json` (20,108 bytes)
  - `reports/eval_20261121_130243.md` (2,494 bytes)
  - `reports/checkpoints/eval_checkpoint_20261121_130243.json` (17,171 bytes)
- **Qualification:** Controlled 13-fixture regression pass; not statistical proof of general real-world forensic reliability. Zero validator rejections does not independently prove zero possible semantic hallucinations.

---

## 8. Known Risks & Deferred Items

- **Python Version Parity:** CI runs Python 3.11 (`pip install -e ".[all]"`); local environment runs Python 3.14 without optional `openai`/`anthropic` SDKs.
- **AnyIO Pytest Warning:** `PytestRemovedIn10Warning` (`CallSpec2`) from installed AnyIO plugin (external dependency warning).
- **Orphaned File:** Untracked `Misc/limit.py` scratch script (outside app/tests).
- **Production Context Alignment:** Future Module 5 (Case Context Builder) must strictly conform to `schemas/case_context.schema.json` and implement context size/token budgeting.

---

## 9. Verification & CI State

- **GitHub Actions `CI` on `origin/main` (`9c20fa94904b`):** **CONFIRMED GREEN (`success`)** (`2026-11-21T14:03:29Z`).
- **Offline Verification Suite (Python 3.14):**
  - `pytest tests/test_yolo.py -v`: **29 passed, 1 warning** (exit `0`).
  - `pytest -q`: **192 passed, 1 warning** (exit `0`).
  - `python scripts/check_fixtures.py`: **13/13 fixtures valid** (exit `0`).
  - `python scripts/check_refs.py`: **13/13 refs resolved** (exit `0`).
  - `pyrefly check src/ tests/`: **0 errors** (6 suppressed, 4 warnings not shown; exit `0`).
- **Controlled Live Groq Workflow Test (21 Nov 2026):** Exactly 1 live Groq HTTP request on `cases/C2.json` (`spatial_inconsistency`), returning `status="completed"`, `result_state="findings_returned"` (1 validated suggestion `S001` citing `notes.N1` and `evidence.E1`), reference resolution confirmed via `refs.py`, investigator review logged, and original model findings verified unmutated.
- **Git Control:** Managed exclusively by project owner; coordinator/executor never run unapproved Git mutations.

---

## 10. Roadmap

- **Completed & Frozen / Verified:** Module 1 — LLM Analysis Module (Tier A, Semantic Gates, Tier B, Validator, Groq Client, Evaluation Harness, CLI); Prompt 14 — Investigator Interaction Workflow Prototype; Prompt 15 — Final LLM Analysis Module Freeze & Handover (`docs/LLM_MODULE_HANDOVER.md`).
- **Active Module:** **Module 2 — YOLO Candidate Detection, Investigator Review & Evidence Management** (Stages Y0, Y1, Y2, Y3 complete; see `PROJECT_BRIEF.md` for complete active engineering specification).
- **Immediate Next Task:** **Module 2 — Stage Y4: Multi-Photo Ingestion Pipeline & Exif Batch Ingestion** (implementing multi-photo ingestion orchestrator, metadata extraction, and case batch management).
- **Subsequent Modules:** Module 2 (YOLO Candidate Detection) → Module 3 (OpenCV 4-Point Planar Mapping) → Module 4 (Timeline Construction) → Module 5 (SQLite Case Context Builder + token budgeting) → Module 6 (ReportLab Report Generation) → Incremental & End-to-End Integration → Module 8 (Final Menu-Based UI).
- **Deferred:** SIFT/ORB, `findHomography`+RANSAC, image stitching, COLMAP, live verification of backup LLM providers.
- **Excluded:** Chatbot UI, custom YOLO training, autonomous guilt/forensic conclusions, `A9`, `C8`, `C9`, `llm context.txt`, removed Tier B categories.

---

## 11. Operating Protocol

1. Coordinator reviews `PLAN.md` and latest verified executor output, selects the single best engineering approach, and emits a focused Antigravity execution prompt (`Goal`, `Target Files`, `Exact Changes & Edge Cases`, `Verification Check`).
2. User approves and runs the prompt in Antigravity IDE, returning exact command outputs and exit codes.
3. Coordinator audits results and proposes exact `PLAN.md` updates (never claiming `PLAN.md` updated until executor confirms).
4. Zero unapproved Git operations and zero unapproved live LLM API calls.

---

## 12. Context Management & Chat Handover Protocol

- **Thresholds:** Prepare continuity checkpoint at ~200,000 conversation tokens; perform mandatory comprehensive checkpoint at ~250,000 tokens (estimate conservatively if no meter is available). Also update `PLAN.md` after every major milestone, bug fix, or architectural decision.
- **Checkpoint Rules:** Propose exact `PLAN.md` updates (never claim applied until Antigravity confirms); record verified facts with dates/milestones; preserve historical decisions and rejected approaches; emit a self-contained new-chat handover instructing the next coordinator to read `PLAN.md` and relevant handbooks before proposing work. Checkpointing authorizes no source edits or Git actions on its own.

---

## 13. Decision & Implementation Ledger

### Entry 1 — Prompt 12.2 Groq Pacing, Checkpointing & Live Evaluation
- **Problem:** Full 13-fixture live evaluation (~29 Groq requests) timed out at 10 minutes and bypassed pipeline-internal category sleep (`idx > 0`) because `evaluate.py` invoked `run_pipeline()` per category.
- **Reason:** Pacing lived inside the category loop rather than the HTTP transport layer, and runs lacked incremental checkpointing.
- **Approved Solution:** Added thread-safe transport-layer `GroqRateLimiter` (20s default cooldown + header-aware `Retry-After` and `< 2500` remaining-token backoff, zero HTTP 429/5xx retries) in `src/llm/client.py`, removed pipeline sleep, and added atomic per-fixture/category checkpointing in `evaluate.py`.
- **Files Affected:** `evaluate.py`, `src/analysis/pipeline.py`, `src/llm/__init__.py`, `src/llm/client.py`, `tests/test_client.py`, `tests/test_evaluate.py`.
- **Verification:** Completed 13-fixture live eval on 21 Nov 2026 (29 reqs, 0 errors/429s, Tier A recall 1.00, Tier B precision/recall 1.00, 0 clean FPs). Offline suite: 146 passed, 13 fixtures, 13 refs, 0 Pyrefly errors. CI green on `origin/main` (`9c20fa94904b`).
- **Remaining Issues:** None blocking; Module 1 frozen.

### Entry 2 — Module 1 Baseline Audit, `analyze.py` Help Fix & `PLAN.md` Freeze Record
- **Problem:** Four open discrepancies required ground-truth resolution before freezing Module 1 (`client.py` limiter/retries, `evaluate.py` latency/rejection labels, `analyze.py` provider help text, `prompt_builder.py` token budget), and no reconciled `PLAN.md` existed.
- **Reason:** Preventing undocumented drift before starting Prompt 14.
- **Approved Solution:** Kept `client.py`, `evaluate.py`, and `prompt_builder.py` as-is (token budgeting deferred to Module 5); updated `analyze.py` `--provider` help text to include `groq` and `openrouter`; created `PLAN.md` recording Module 1 as formally frozen.
- **Files Affected:** `analyze.py`, `PLAN.md`.
- **Verification:** Completed 146 unit tests and verified `--provider` help text. Module 1 formally frozen.
- **Remaining Issues:** None; unblocks Prompt 14 (Investigator Interaction Workflow Prototype).

### Entry 3 — Prompt 14 Investigator Interaction Workflow Prototype
- **Problem:** Module 1 lacked an investigator-facing workflow layer distinguishing analysis states, presenting findings cleanly without chatbot interaction, managing source-reference navigation, and logging investigator review decisions without mutating analytical snapshots.
- **Reason:** Forensic traceability requires that investigator reviews (acknowledged, not_relevant [mandatory reason], deferred) never mutate or overwrite original model suggestions, that semantic gate preconditions and 1-category-per-invocation discipline remain intact, and that workflow actions are deterministically controlled by application state rather than LLM text.
- **Approved Solution:** Created `src/workflow/envelope.py` (typed request/response validation, 4 presentation states, deterministic actions), `src/workflow/store.py` (file-based prototype persistence separating immutable analysis snapshots from append-only review logs), `src/workflow/adapter.py` (thin adapter wrapping frozen `run_pipeline()` with semantic gate checks, 1-category-per-call, deterministic S001.. IDs, dynamic case discovery, and `refs.py` inspection), and `investigator_cli.py` (9-option interactive menu with injectable I/O).
- **Files Affected:** `src/workflow/__init__.py`, `src/workflow/envelope.py`, `src/workflow/store.py`, `src/workflow/adapter.py`, `investigator_cli.py`, `tests/test_workflow.py`, `PLAN.md`.
- **Verification:** 17/17 offline mocked workflow tests passing, 163/163 pytest passing (exit 0), 13/13 fixtures and refs passing, 0 Pyrefly errors, and 1 controlled live Groq integration test on `cases/C2.json` (`spatial_inconsistency`, 1 HTTP request, 1 validated finding, verified unmutated snapshot and review logging).
- **Remaining Issues:** None; Module 1 and Prompt 14 fully verified and frozen. Unblocks Module 2 (YOLO Detection Module).

### Entry 4 — Prompt 15 Final LLM Analysis Module Freeze & Handover
- **Problem:** Transitioning from Module 1 to Module 2 (YOLO) through Module 5 (Case Context Builder) required an authoritative, self-contained contract specification and formal freeze document to ensure zero undocumented drift or breaking schema changes.
- **Reason:** Upstream visual and database modules must adhere to exact contract preconditions (e.g. `photos.P#.d#` candidate detection structure, mandatory dismissal reasons for Tier A Rule A2, planar coordinate format for spatial gate, `HH:MM` timeline formats for Rule A6).
- **Approved Solution:** Created `docs/LLM_MODULE_HANDOVER.md` encompassing all 10 required handover sections (§A–§G), confirmed all 14 architectural components, verified zero code churn, executed offline test suite, and recorded official Freeze Readiness: PASS.
- **Files Affected:** `docs/LLM_MODULE_HANDOVER.md`, `PLAN.md`.
- **Verification:** 163/163 pytest passing (exit 0), 17/17 workflow mocked tests passing (exit 0), 13/13 fixtures and refs passing (exit 0), 0 Pyrefly errors (exit 0).
- **Remaining Issues:** None; Module 1 is permanently frozen. Next active milestone is Module 2 (YOLO Detection Module).

### Entry 5 — Module 2 Stage Y0 Closure & 4-Document Architecture Alignment
- **Problem:** Beginning Module 2 (YOLO) implementation without auditing active contracts risks schema drift, false assumptions regarding Tier A rules (such as Rule A3 checking evidence labels vs photo/det refs), unverified Python 3.14 library compatibility, and confusion from obsolete handbook references.
- **Reason:** Ensuring strict contract adherence, confirming CPU-only hardware reality (Windows 10, 4 cores, no CUDA), and establishing the clean 4-document architecture before generating a single line of Module 2 code.
- **Approved Solution:** Executed strictly read-only Stage Y0 inspection; retired obsolete handbooks; adopted 4-document governance (`README.md`, `full _roadmap.md`, `PROJECT_BRIEF.md`, `PLAN.md`, plus `docs/*_HANDOVER.md`); confirmed the 6 Y0 corrections:
  1. *Locked Y1–Y8 sequence:* Approved sequential implementation roadmap Y1 through Y8.
  2. *Corrected A3 rule logic:* Confirmed `src/analysis/tier_a.py` checks note keywords against all detection classes (any disposition) and confirmed evidence labels (does not require populated `photo_ref`/`det_ref`).
  3. *Provisional model strategy:* Adopted `DetectorBackend` protocol + `StubDetectorBackend` + lazy `UltralyticsYOLOBackend`; noted `yolov8n.pt` strictly as provisional CPU candidate with Python 3.14 compatibility explicitly unverified.
  4. *3-layer evidence representation:* Preserved internal multi-photo lists, standard schema primary refs, and schema-permitted extended fields (`additionalProperties: true`).
  5. *Documentation alignment:* Aligned active documentation, eliminated obsolete handbook references, and established `PROJECT_BRIEF.md` as the dedicated Module 2 active specification.
  6. *Verified `map.E#`:* Confirmed `map.E#` resolves accurately against `case_context["map"]["xy_optional"]` via `src/analysis/refs.py`.
- **Files Affected:** `README.md`, `PROJECT_BRIEF.md`, `PLAN.md`, `docs/LLM_MODULE_HANDOVER.md`.
- **Verification:** Read-only inspection verified: Python 3.14.0 CPU-only environment; 163 pytest passing, 13/13 fixtures and refs passing; zero code churn.
- **Remaining Issues:** Stage Y0 closed. Stage Y1 (Core Domain Entities & Storage Layout) is the immediate active task.

### Entry 6 — Module 2 Stages Y1 & Y2 Core Contracts, Storage & Detector Backend
- **Problem:** Module 2 required typed domain contracts, SHA-256 tamper-evident photo storage, atomic persistence, photo-scoped monotonic ID generation, append-only review/evidence auditing, and a decoupled detector backend protocol before introducing computer vision or model weights.
- **Reason:** Establishing pure-standard-library data storage and abstract detector protocol prevents tight coupling to optional ML dependencies (such as `ultralytics`), guarantees process-restart safety, preserves offline CI testing, and ensures forensic immutability.
- **Approved Solution:** Implemented `src/yolo/exceptions.py` (structured error hierarchy), `src/yolo/models.py` (5 core entities + audit events with strict validation and dict serialization), `src/yolo/store.py` (`YoloCaseStore` with atomic JSON writes, SHA-256 duplication checks, original photo preservation, photo-scoped `photos.P#.d#` counters, and append-only JSONL logs), `src/yolo/detector.py` (`DetectorConfig`, `RawPrediction`, `ModelProvenance`, `DetectorOutput`, `DetectorBackend` protocol, deterministic `StubDetectorBackend`, and lazy-loaded `UltralyticsYOLOBackend`), and `src/yolo/__init__.py`.
- **Files Affected:** `src/yolo/__init__.py`, `src/yolo/exceptions.py`, `src/yolo/models.py`, `src/yolo/store.py`, `src/yolo/detector.py`, `tests/test_yolo.py`, `PLAN.md`.
- **Verification:** 24/24 unit tests in `tests/test_yolo.py`, 187/187 full pytest suite (exit 0), 13/13 case fixtures and refs (exit 0), and 0 Pyrefly type errors across `src/` and `tests/`.
- **Remaining Issues:** None; unblocks Stage Y3 (Ingestion Pipeline & Exif Orientation Correction).

### Entry 7 — Module 2 Stage Y3 EXIF Orientation, Letterbox Transforms & Separate Previews
- **Problem:** Camera EXIF rotation tags (especially orientations 6 and 8 from mobile/field cameras) invert display aspect ratios, causing letterbox inference coordinates to misalign with original pixel space if uncorrected. Furthermore, generating visual overlays directly onto original photos violates forensic immutability.
- **Reason:** Standard library parsing of TIFF headers in APP1 segments ensures zero external dependencies while accurately determining display dimensions. Letterbox coordinate inversion maps model predictions back to original coordinates, while strict output path collision checks and SHA-256 assertions guarantee the original crime scene photo is never mutated.
- **Approved Solution:** Implemented `src/yolo/preview.py` with `read_exif_orientation` (parsing APP1 Exif TIFF structures in both little-endian II and big-endian MM), `compute_letterbox_metadata` (computing scale and centered letterbox padding), `reverse_letterbox_bbox` (reversing letterboxing and clipping with `DetectorError` validation), and `render_annotated_preview` (atomic rendering with immutable original verification, stdlib PNG fallback with yellow/green/grey color coding, and optional Pillow support). Integrated EXIF extraction into `YoloCaseStore.ingest_photo` to record `PhotoRecord.exif_orientation` without altering original bytes.
- **Files Affected:** `src/yolo/preview.py`, `src/yolo/store.py`, `src/yolo/__init__.py`, `tests/test_yolo.py`, `PLAN.md`.
- **Verification:** 29/29 unit tests in `tests/test_yolo.py`, 192/192 full pytest suite (exit 0), 13/13 case fixtures and refs (exit 0), and 0 Pyrefly type errors across `src/` and `tests/`.
- **Remaining Issues:** None; unblocks Stage Y4.
