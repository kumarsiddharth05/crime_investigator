# EXECUTOR CODEBASE HANDBOOK
## AI-Assisted Crime Scene Investigation and Evidence Analysis

**Repository:** `AI_Assisted_CrimeInvestigation_and_Evidence_Analysis`  
**Active branch:** `main`  
**Previous development branch:** `feature/live-gemini-evaluation`  
**Merge status:** Feature branch changes merged into `main` — confirmed by user  
**Latest commit:** Post-merge HEAD not yet verified  
**Working tree:** Post-merge cleanliness not yet verified  
**Production LLM:** Groq — `openai/gpt-oss-120b`  
**Current development stage:** LLM Analysis Module live evaluation completed; final implementation review and formal freeze remain. Investigator interaction workflow is the next planned development task.

---

# 1. GIT AND WORKSPACE STATE

## 1.1 Current Git State

The changes previously developed on `feature/live-gemini-evaluation` have been merged into `main`.

| Property | Current value |
|---|---|
| Active branch | `main` |
| Previous feature branch | `feature/live-gemini-evaluation` |
| Merge status | Merged into `main` |
| Latest commit | Post-merge HEAD not yet verified |
| Working tree | Not yet verified |
| Post-merge CI | Not yet verified |

### Historical pre-merge workspace state

The last executor scan, before the merge, reported:

- Branch: `feature/live-gemini-evaluation`
- HEAD: `6b86f8a8bfb2b17bc76a6474083464447ef12b75`
- Working tree: DIRTY
- Six modified tracked files.
- Two untracked handbook files.

The six modified files were:

| File | Reported modification |
|---|---|
| `evaluate.py` | Incremental checkpointing, latency policy and report enrichment |
| `src/analysis/pipeline.py` | Removal of hardcoded pacing sleep |
| `src/llm/__init__.py` | Exports `GroqRateLimiter` and `groq_rate_limiter` |
| `src/llm/client.py` | Groq rate limiter implementation and request integration |
| `tests/test_client.py` | Rate limiter tests and mock cooldown configuration |
| `tests/test_evaluate.py` | Checkpoint tests and acceptance-target assertions |

The two untracked files were:

- `Coordinator_Handbook.md`
- `Executer_Handbook.md`

This is a historical snapshot, not a description of the current `main` working tree.

**Do not use the old feature-branch commit hash as the current `main` HEAD.**

The executor should inspect the current repository before making further changes. Do not reset, discard, stage, commit, push, merge or otherwise alter Git state without explicit authorization.

## 1.2 Live Evaluation Artifact Verification

The pre-merge executor scan confirmed that all three evaluation artifacts existed:

| Artifact | Status at last scan | Reported size |
|---|---|---:|
| `reports/eval_20261121_130243.json` | EXISTS | 20,108 bytes |
| `reports/eval_20261121_130243.md` | EXISTS | 2,494 bytes |
| `reports/checkpoints/eval_checkpoint_20261121_130243.json` | EXISTS | 17,171 bytes |

These files represent the completed live evaluation. Preserve them as historical benchmark records.

Their continued presence after the merge has not been independently rechecked.

---

# 2. ACTUAL FOLDER AND FILE STRUCTURE

The following tree is based on the last executor workspace scan, before the merge. The current `main` tree should be checked before relying on it as an exact present-day inventory.

```text
AI_Assisted_CrimeInvestigation_and_Evidence_Analysis/
│
├── .env
├── .gitignore
├── analyze.py
├── evaluate.py
├── Coordinator_Handbook.md
├── Executer_Handbook.md
├── full _roadmap.md
├── PROJECT_BRIEF.md
├── pyproject.toml
├── pyrightconfig.json
├── README.md
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── cases/
│   ├── C0.json
│   ├── C0.expected.json
│   ├── C1.json
│   ├── C1.expected.json
│   ├── C2.json
│   ├── C2.expected.json
│   ├── C3.json
│   ├── C3.expected.json
│   ├── C4.json
│   ├── C4.expected.json
│   ├── C5.json
│   ├── C5.expected.json
│   ├── C6.json
│   ├── C6.expected.json
│   ├── C7.json
│   ├── C7.expected.json
│   ├── C10.json
│   ├── C10.expected.json
│   ├── C11.json
│   ├── C11.expected.json
│   ├── C12.json
│   ├── C12.expected.json
│   ├── C13.json
│   ├── C13.expected.json
│   ├── C14.json
│   └── C14.expected.json
│
├── Misc/
│   ├── AI Crime Scene Investigation Flowchart.png
│   ├── AI-Assisted Crime Scene Investigation Architecture.png
│   ├── AI-Assisted_Digital_Forensics.pptx
│   ├── Gemini_Generated_Image_kt8qk3kt8qk3kt8q.png
│   ├── limit.py
│   ├── SYNOPSIS.docx
│   ├── SYNOPSIS.pdf
│   └── WhatsApp Image 2026-10-27 at 9.59.29 AM.jpeg
│
├── reports/
│   ├── .gitkeep
│   ├── eval_20261121_130243.json
│   ├── eval_20261121_130243.md
│   └── checkpoints/
│       └── eval_checkpoint_20261121_130243.json
│
├── runs/
│   ├── .gitkeep
│   └── C-2026-00*_run_*.json
│
├── schemas/
│   └── case_context.schema.json
│
├── scripts/
│   ├── check_fixtures.py
│   └── check_refs.py
│
├── src/
│   ├── __init__.py
│   │
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── pipeline.py
│   │   ├── refs.py
│   │   ├── tier_a.py
│   │   └── validator.py
│   │
│   └── llm/
│       ├── __init__.py
│       ├── client.py
│       ├── prompt_builder.py
│       │
│       └── prompts/
│           └── v1/
│               ├── contextual_contradiction.md
│               ├── spatial_inconsistency.md
│               ├── system.md
│               └── timeline_contradiction.md
│
└── tests/
    ├── __init__.py
    ├── test_client.py
    ├── test_evaluate.py
    ├── test_pipeline.py
    ├── test_tier_a.py
    └── test_validator.py
```

## 2.1 Key File Responsibilities

| File | Purpose |
|---|---|
| `analyze.py` | Investigator-facing command-line entry point for case analysis |
| `evaluate.py` | Benchmark harness, fixture execution, metric calculation, checkpointing and report generation |
| `pyproject.toml` | Python package metadata, dependency declarations and tool configuration |
| `PROJECT_BRIEF.md` | Project architecture, requirements, prompt specifications and evaluation criteria |
| `full _roadmap.md` | Multi-stage development roadmap and implementation prompts |
| `README.md` | High-level project documentation and usage instructions |
| `.env` | Local environment configuration and provider credentials; never commit secrets |
| `.gitignore` | Excludes environment secrets, generated runtime data and other unwanted files |
| `.github/workflows/ci.yml` | GitHub Actions automated verification workflow |
| `schemas/case_context.schema.json` | JSON Schema Draft-07 specification for case context |
| `scripts/check_fixtures.py` | Validates case fixtures and expected-result files |
| `scripts/check_refs.py` | Validates reference paths in expected fixture findings |
| `src/analysis/pipeline.py` | Orchestrates Tier A, semantic eligibility, LLM analysis, validation and audit logging |
| `src/analysis/tier_a.py` | Deterministic A1–A8 rule engine |
| `src/analysis/validator.py` | Validates and filters structured LLM suggestions |
| `src/analysis/refs.py` | Resolves dotted references to case-context records |
| `src/llm/client.py` | Provider adapters, normalized response handling and Groq request pacing |
| `src/llm/prompt_builder.py` | Context sanitization, serialization and prompt assembly |
| `src/llm/prompts/v1/system.md` | System-level analysis instructions and output constraints |
| `src/llm/prompts/v1/contextual_contradiction.md` | Contextual contradiction task prompt |
| `src/llm/prompts/v1/spatial_inconsistency.md` | Spatial inconsistency task prompt |
| `src/llm/prompts/v1/timeline_contradiction.md` | Timeline contradiction task prompt |
| `tests/test_client.py` | Provider client and rate limiter unit tests |
| `tests/test_evaluate.py` | Evaluation metrics, checkpointing and resume tests |
| `tests/test_pipeline.py` | Pipeline, eligibility gate and CLI tests |
| `tests/test_tier_a.py` | Deterministic rule engine tests |
| `tests/test_validator.py` | Validator behaviour and rejection tests |
| `cases/` | Thirteen established benchmark fixtures and corresponding expected results |
| `reports/` | Evaluation reports and checkpoint artifacts |
| `runs/` | Generated pipeline execution audit records |
| `Misc/` | Academic documents, diagrams and reference assets |

---

# 3. TECHNOLOGY STACK AND DEPENDENCIES

## 3.1 Core Technology Stack

| Component | Technology |
|---|---|
| Language | Python |
| Runtime used for reported offline verification | Python 3.14 |
| Package management | Python `pyproject.toml` |
| HTTP transport | HTTPX |
| Structured validation | JSON Schema |
| Environment configuration | python-dotenv |
| Terminal interface | Rich |
| Test framework | pytest |
| Static diagnostics | Pyrefly |
| CI | GitHub Actions |
| LLM provider | Groq |
| Production model | `openai/gpt-oss-120b` |
| Case data format | JSON |
| Prompt format | Markdown |
| Audit storage | JSON files |
| Evaluation storage | JSON and Markdown |

## 3.2 Declared Dependencies

Source: `pyproject.toml`.

### Core dependencies

| Package | Declared version |
|---|---|
| `httpx` | `>=0.27.0` |
| `jsonschema` | `>=4.20.0` |
| `pytest` | `>=8.0.0` |
| `python-dotenv` | `>=1.0.0` |
| `pyyaml` | `>=6.0` |
| `rich` | `>=13.0.0` |
| `tenacity` | `>=8.2.0` |

### Optional provider dependencies

| Package | Optional extra |
|---|---|
| `openai` | `openai`, `all` |
| `google-genai` | `gemini`, `all` |
| `anthropic` | `anthropic`, `all` |

Groq uses an HTTP-compatible adapter. A dedicated Groq SDK is not required by the reported implementation.

## 3.3 Installed Dependencies at Last Scan

The executor identified the active interpreter as:

`C:\Users\Dell\AppData\Local\Programs\Python\Python314\python.exe`

Reported installed packages:

| Package | Installed version | Status |
|---|---:|---|
| `httpx` | 0.28.1 | Installed |
| `jsonschema` | 4.26.0 | Installed |
| `pytest` | 9.2.0 | Installed |
| `python-dotenv` | 1.2.2 | Installed |
| `PyYAML` | 6.0.3 | Installed |
| `rich` | 15.0.0 | Installed |
| `tenacity` | 9.1.4 | Installed |
| `google-genai` | 3.5.0 | Installed |
| `crime-scene-llm-harness` | 0.1.0 | Installed in editable mode |
| `openai` | — | Not installed |
| `anthropic` | — | Not installed |

These versions describe the scanned Windows environment, not every development or CI environment.

## 3.4 Installation Commands

Core installation:

```bash
pip install -e .
```

All optional provider dependencies:

```bash
pip install -e ".[all]"
```

The CI workflow uses the all-extras installation command.

---

# 4. COMPLETED AND VERIFIED FEATURES

The following sections describe the established application architecture and reported implementation. Verification status is distinguished from live-provider verification.

## 4.1 Case Context and Data Contracts

The analysis engine accepts structured `case_context` JSON.

The evaluator loads fixture JSON directly. It does not require a production database or image-processing subsystem.

The case context can contain structured records for:

- Case metadata.
- Evidence.
- Investigator notes.
- Photographs and object detections.
- Map information.
- Timeline entries.
- Derived facts.

The LLM receives serialized structured context, not raw image bytes, image files or base64 image payloads.

References use stable dotted identifiers, including:

```text
notes.N3
photos.P1.d3
evidence.E1
timeline.T2
```

The schema is defined in:

`schemas/case_context.schema.json`

Fixture validation has passed for all thirteen established fixtures.

## 4.2 Tier A — Deterministic Rule Engine

Implementation:

`src/analysis/tier_a.py`

Tests:

`tests/test_tier_a.py`

Tier A performs deterministic structural and consistency checks without depending on an LLM response.

The approved rule set is A1–A8:

| Rule | Actual rule |
|---|---|
| A1 | Unreviewed detection |
| A2 | Dismissed detection with a null or empty dismissal reason |
| A3 | A note mentions an object class that appears in no detection of any disposition and has no confirmed evidence record of that class |
| A4 | A note contains an HH:MM time absent from all timeline entries |
| A5 | A mapped evidence position has no `photo_ref` |
| A6 | A timeline entry has no source |
| A7 | A note references a room with no photo coverage |
| A8 | Confirmed evidence has no map position |

Important A3 behaviour:

A3 must remain silent if the object class appears in any detection, regardless of whether that detection is confirmed, dismissed or unreviewed.

A dismissed or unreviewed detection still counts as a detection for this rule.

The removed A9 coverage-gap rule must not be reintroduced.

**Verification:** The complete offline suite passed. The executor also reported that the dedicated Tier A test file passed in the current workspace.

## 4.3 Tier B — Semantic Contradiction Analysis

The LLM is responsible for identifying semantic contradictions that deterministic rules cannot reliably establish.

Exactly three categories are supported:

1. `spatial_inconsistency`
2. `timeline_contradiction`
3. `contextual_contradiction`

### Spatial inconsistency

Identifies explicit incompatible locations assigned to the same evidence or identified object.

Example: an investigator note places an item near the main entrance while the map places that same item near a window on the opposite side of the room.

### Timeline contradiction

Identifies explicitly incompatible specific times associated with the same identified event and temporal attribute.

Approximate timestamps or small differences are not automatically contradictions.

### Contextual contradiction

Identifies incompatible factual claims concerning the same identified person, object or event.

Entity identity must be established rather than inferred from generic references.

Removed categories:

- `ambiguity`
- `follow_up`
- `semantic_coverage_gap`

These must not be reintroduced as Tier B categories or replacement categories.

An empty suggestions list is valid for any of the three assigned analysis types.

Each invocation is assigned one analysis type and uses its corresponding task prompt.

## 4.4 Semantic Eligibility Gate

Implementation:

`src/analysis/pipeline.py`

The gate determines whether sufficient structured information exists to justify invoking a particular Tier B category.

Established eligibility logic:

| Category | Eligibility principle |
|---|---|
| Spatial | At least one spatial note with a valid map position, or at least two spatial notes |
| Timeline | At least two actual time-bearing records across notes and timeline |
| Contextual | At least two relevant factual records across notes, timeline, detections and evidence |

The gate is deterministic. It does not ask the LLM to decide which application actions should be available.

The eligibility checks prevent unnecessary model calls when the case context lacks the minimum relevant information.

## 4.5 Reference Resolution

Implementation:

`src/analysis/refs.py`

The reference resolver resolves dotted identifiers against the case context.

Examples:

```text
notes.N4
photos.P1.d3
evidence.E1
timeline.T2
```

The resolver is used by the validator to establish whether model-supplied references point to actual case records.

The separate reference verification script checks expected fixture references.

## 4.6 Defense-in-Depth Validator

Implementation:

`src/analysis/validator.py`

The validator applies seven checks in order:

1. Schema validation.
2. Assigned analysis type validation.
3. Reference resolution.
4. Dismissal guard.
5. Entity hallucination detection.
6. Deduplication against Tier A.
7. Severity sanity.

### Schema validation

Checks response structure and individual suggestion fields, including:

- Required keys.
- Valid category.
- Valid severity.
- String fields.
- Reference list.
- Maximum suggestion count.

An empty suggestions list is valid.

Malformed responses without a usable suggestions list are handled as response-level schema failures.

### Assigned type validation

A suggestion must match the category assigned to that particular LLM invocation.

### Reference resolution

Every supplied reference must resolve to a real record in the provided case context.

### Dismissal guard

A suggestion citing dismissed evidence with a nonempty dismissal reason is subject to a category-sensitive guard.

Non-contextual suggestions citing dismissed evidence are rejected.

A contextual contradiction may pass this guard when it also cites another note or timeline reference.

This is a mechanical prerequisite, not proof that the note actually challenges the dismissal.

### Entity hallucination detection

The validator uses an allowlist derived from case-context values and reference segments, together with curated generic vocabulary.

It checks suspicious numeric and capitalized proper-name-like tokens.

The detector is a heuristic. It does not establish full semantic correctness or detect every possible fabricated lowercase noun.

### Tier A deduplication

Tier A flags are primarily single-reference structural or process findings. Tier B findings are pairwise semantic contradictions.

Matching references alone do not establish that a Tier B suggestion duplicates a Tier A flag.

No generic exact-reference suppression should be introduced.

### Severity sanity

A high-severity suggestion requires at least two distinct evidence references. Otherwise, its severity is downgraded to medium.

## 4.7 Prompt Builder

Implementation:

`src/llm/prompt_builder.py`

Responsibilities include:

- Context sanitization.
- XML-style serialization.
- Prompt assembly.
- Keeping case information separate from system instructions.
- Preventing user-supplied case text from becoming trusted instructions.

Production prompt templates are stored under:

`src/llm/prompts/v1/`

The directory contains the system prompt and three category-specific task prompts.

## 4.8 LLM Client and Provider Architecture

Implementation:

`src/llm/client.py`

The client supports multiple provider adapters through a normalized response interface.

Reported provider adapters:

- Groq.
- OpenAI.
- Gemini Interactions.
- Anthropic.
- OpenRouter.

Production configuration is fixed:

| Setting | Value |
|---|---|
| Provider | `groq` |
| Model | `openai/gpt-oss-120b` |
| Endpoint | `https://api.groq.com/openai/v1/chat/completions` |
| Transport | HTTPX |
| Dedicated Groq SDK | Not required |

Groq is the finalized production provider and model.

Provider selection is not an active project task.

### Groq Rate Limiter

The current merged implementation should be treated as the development baseline, subject to source inspection.

The last executor scan reported:

- Thread-safe coordination using `threading.Lock`.
- Default cooldown of 20 seconds between consecutive requests.
- Configurable cooldown through `GROQ_COOLDOWN_SECONDS`.
- Cooldown wait-time tracking.
- Rate-limit response handling.

The limiter is integrated at the client/transport layer rather than relying on the old pipeline-level sleep.

**Implementation discrepancy requiring review:** The executor report also claimed dynamic token-bucket throttling when `x-ratelimit-remaining-tokens` falls below 2500 and automatic `Retry-After` handling. The approved Prompt 12.2 design called for a simple, thread-safe fixed cooldown without a complex token bucket. Inspect the merged source and compare it with the approved design before changing anything.

The executor report also claimed immediate retries for HTTP 500/502/503/504. An earlier audit recorded zero transport retries. The merged source must be inspected to establish the actual retry policy. Do not introduce retries or change their behaviour without reviewing the approved requirements.

### Provider verification status

| Provider | Status |
|---|---|
| Groq `openai/gpt-oss-120b` | Live evaluation completed |
| OpenAI | Live operation unverified |
| Anthropic | Live operation unverified |
| Gemini | Live operation unverified in the current evaluation phase |
| OpenRouter | Live operation unverified in the current evaluation phase |

Mocked unit tests do not establish successful live provider operation.

## 4.9 Evaluation Harness

Implementation:

`evaluate.py`

Tests:

`tests/test_evaluate.py`

The harness executes the actual production pipeline using the established benchmark fixtures.

It supports:

- Dry-run evaluation.
- Stubbed evaluation.
- Live evaluation.
- Fixture discovery.
- Tier A comparison.
- Tier B comparison.
- Precision and recall calculations.
- Clean-case false-positive measurement.
- Validator rejection statistics.
- Provider latency measurement.
- Complete-case latency measurement.
- Token usage tracking.
- API error reporting.
- JSON and Markdown report generation.

The harness evaluates all thirteen established fixtures:

```text
C0, C1, C2, C3, C4,
C5, C6, C7,
C10, C11, C12, C13, C14
```

### Checkpointing

The current implementation reports incremental checkpointing using:

- `save_checkpoint`
- `load_checkpoint`

Checkpoint files are stored under:

`reports/checkpoints/`

Reported behaviour:

- Atomic writes using temporary files and replacement.
- Per-category and per-fixture progress persistence.
- Configuration and fixture fingerprinting.
- Resume of completed work without repeating completed API requests.
- Detection of incompatible checkpoint configurations.

The checkpoint fingerprint is intended to account for provider, model, prompts, fixtures and evaluation configuration.

Checkpointing is covered by `tests/test_evaluate.py` and the live evaluation produced an archived checkpoint.

## 4.10 CLI Investigation Interface

Implementation:

`analyze.py`

The current CLI runs the analysis pipeline using a supplied case JSON file.

Example:

```bash
python analyze.py cases/C0.json
```

Reported command-line controls include:

- `--tier-a-only`
- `--type`
- `--all-types`
- `--no-audit`
- `--output`
- `--provider`
- `--model`

The terminal presentation uses Rich panels and tables.

This is a CLI analysis interface, not the final investigator interaction system.

---

# 5. LIVE EVALUATION RESULTS

## 5.1 Evaluation Configuration

| Parameter | Result |
|---|---|
| Provider | Groq |
| Model | `openai/gpt-oss-120b` |
| Fixtures | 13 |
| HTTP requests | 29 |
| Concurrency | 1 |
| Cooldown | 20 seconds |
| Total tokens | 83,746 |
| Prompt tokens | 76,839 |
| Completion tokens | 6,907 |
| Total duration | 762.49 seconds |
| API errors | 0 |
| HTTP 429 responses | 0 |

## 5.2 Analytical Results

| Metric | Result |
|---|---:|
| Tier A expected findings detected | 3/3 |
| Tier A recall | 1.00 |
| Tier A precision | 1.00 |
| Tier B expected findings matched | 5/5 |
| Tier B recall | 1.00 |
| Tier B precision | 1.00 |
| Clean fixtures | 7 |
| Clean-case false positives | 0 |
| Suggestions received | 5 |
| Suggestions validated | 5 |
| Validator rejections | 0 |

Tier B category breakdown:

| Category | Expected findings | Matched |
|---|---:|---:|
| Contextual contradiction | 2 | 2 |
| Spatial inconsistency | 2 | 2 |
| Timeline contradiction | 1 | 1 |

All thirteen fixtures completed.

The benchmark passed the established analytical acceptance criteria.

## 5.3 Latency Results

| Metric | Result |
|---|---:|
| Median provider latency | 22,626.6 ms |
| Minimum provider latency | 538.6 ms |
| Maximum provider latency | 72,102.9 ms |
| Median complete-case latency | 66,208.4 ms |
| Minimum complete-case latency | 1,655.4 ms |
| Maximum complete-case latency | 106,852.1 ms |
| Total cooldown wait | 425.21 seconds |

The previous 6,000 ms median complete-case latency threshold was retired. Latency is informational, not a pass/fail acceptance criterion.

Complete-case latency includes provider requests, cooldown waits, validation and processing.

Zero validator rejections does not prove the absence of every possible semantic hallucination. Zero HTTP 429 responses demonstrates the observed result of this particular execution, not a universal guarantee against rate limits.

## 5.4 Evaluation Artifacts

```text
reports/eval_20261121_130243.json
reports/eval_20261121_130243.md
reports/checkpoints/eval_checkpoint_20261121_130243.json
```

Preserve these artifacts. Do not overwrite historical evaluation records.

---

# 6. INCOMPLETE, BROKEN, STUBBED OR UNVERIFIED CODE

| Component | File / Location | Status | Details |
|---|---|---|---|
| OpenAI adapter | `src/llm/client.py` — `_call_openai` | Live unverified | Unit-test coverage reported; successful live execution not established |
| Anthropic adapter | `src/llm/client.py` — `_call_anthropic` | Live unverified | Unit-test coverage reported; successful live execution not established |
| OpenRouter adapter | `src/llm/client.py` — `_call_openrouter` | Live unverified | Unit-test coverage reported; successful live execution not established |
| Gemini adapter | `src/llm/client.py` — `_call_gemini_interactions` | Live unverified | SDK installed, but current live operation not established |
| Groq rate limiter | `src/llm/client.py` — `GroqRateLimiter` | Implemented; design discrepancy to review | Verify token-bucket behaviour and HTTP retry handling against the approved simple cooldown design |
| CLI provider help | `analyze.py` — previously reported line 75 | Potential minor defect | Previous scan reported that help text omits Groq and OpenRouter. Confirm against current source |
| Scratch script | `Misc/limit.py` | Unverified / orphaned | OpenRouter account-limit script; not reported as part of the application or test suite |
| Investigator workflow | Not yet implemented | Planned | Menu-driven investigator review workflow is the next development task |
| YOLO module | Not yet implemented | Planned | Object detection and investigator confirmation workflow |
| OpenCV mapping module | Not yet implemented | Planned | Perspective rectification and evidence mapping |
| Timeline construction module | Not yet implemented | Planned | Structured chronology construction |
| Case context module | Not yet implemented as a complete production module | Planned | Production context construction from case records |
| Report generation module | Not yet implemented | Planned | Investigator-facing report generation |
| Final application UI | Not yet implemented | Planned | Final menu-driven interface |

## 6.1 Known Validator Limitations

The validator is defense-in-depth, not a semantic proof engine.

Its entity hallucination detection is heuristic and cannot guarantee that all natural-language claims are grounded.

A valid reference does not prove that the suggestion correctly interprets the referenced record.

The final semantic decision remains subject to investigator review.

## 6.2 Known Integration Boundaries

The current evaluation harness operates on JSON fixtures and the analysis pipeline.

It does not establish completed integration with:

- A production database.
- YOLO image detection.
- OpenCV mapping.
- A complete investigator review interface.
- Final report generation.

Do not describe these future modules as implemented merely because the project roadmap specifies them.

---

# 7. ENVIRONMENT AND CONFIGURATION

## 7.1 Environment Variables

The local `.env` file contains provider configuration and secrets. Never print, copy into reports, or commit actual credential values.

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | Selects the configured provider |
| `LLM_MODEL` | Selects the model identifier |
| `GROQ_API_KEY` | Groq authentication |
| `GROQ_COOLDOWN_SECONDS` | Optional Groq cooldown override; reported default is 20.0 seconds |
| `GEMINI_API_KEY` | Gemini authentication |
| `OPENAI_API_KEY` | OpenAI authentication |
| `ANTHROPIC_API_KEY` | Anthropic authentication |
| `OPENROUTER_API_KEY` | OpenRouter authentication |

Final production configuration:

```dotenv
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
GROQ_COOLDOWN_SECONDS=20.0
GROQ_API_KEY=<secret>
```

The actual key must never appear in documentation or Git.

Groq is finalized. Other provider variables are retained for optional adapter support, not as active production alternatives.

## 7.2 Installation

Create and activate a virtual environment if one is not already active.

Install the package and core dependencies:

```bash
pip install -e .
```

Install all declared optional provider dependencies:

```bash
pip install -e ".[all]"
```

## 7.3 Offline Verification Commands

Run the following from the repository root:

```bash
pytest -q
```

```bash
python scripts/check_fixtures.py
```

```bash
python scripts/check_refs.py
```

```bash
pyrefly check
```

## 7.4 Application Commands

Single-case analysis:

```bash
python analyze.py cases/C0.json
```

Live benchmark:

```bash
python evaluate.py --max-concurrency 1
```

Offline dry-run evaluation:

```bash
python evaluate.py --dry-run-llm
```

Do not run a live evaluation without explicit authorization.

---

# 8. OFFLINE VERIFICATION RESULTS

The executor ran the following checks in the active Python 3.14 environment before the merge.

## 8.1 Full Test Suite

Command:

```bash
pytest -q
```

Exit status: `0`

Result:

```text
146 passed, 1 warning in 30.83s
```

The warning was `PytestRemovedIn10Warning` from the installed AnyIO pytest plugin, concerning the renamed `CallSpec2` alias.

## 8.2 Fixture Schema Validation

Command:

```bash
python scripts/check_fixtures.py
```

Exit status: `0`

Result:

```text
[SUCCESS] All 13 case fixture(s) validated successfully.
```

All thirteen fixture files and their corresponding expected-result files passed Draft-07 schema validation.

## 8.3 Reference Resolution Validation

Command:

```bash
python scripts/check_refs.py
```

Exit status: `0`

Result:

```text
Reference validation PASSED: all 13 ref(s) across 13 cases resolved successfully.
```

## 8.4 Static Diagnostics

Last reported command:

```bash
pyrefly check src/ tests/
```

Exit status: `0`

Result:

```text
INFO 0 errors (1 suppressed, 2 warnings not shown)
```

The command actually executed was `pyrefly check src/ tests/`, not the shorter `pyrefly check`.

## 8.5 Verification Summary

| Check | Last reported result | Exit status |
|---|---|---:|
| Full pytest suite | 146 passed, 1 warning | 0 |
| Fixture validation | 13 fixtures passed | 0 |
| Reference validation | 13 references across 13 cases resolved | 0 |
| Pyrefly | 0 errors; 2 warnings not shown; 1 suppressed | 0 |

These results were obtained before the merge. They are not automatically post-merge verification results.

A post-merge verification run should establish that the current `main` branch still passes the required checks.

---

# 9. CI AND VERSION CONTROL

## 9.1 CI Workflow

File:

`.github/workflows/ci.yml`

The workflow runs on:

- Pushes to `main`.
- Pull requests targeting `main`.

The reported CI installation command is:

```bash
pip install -e ".[all]"
```

The workflow performs:

```bash
python scripts/check_fixtures.py
python scripts/check_refs.py
pytest -q
```

The required GitHub status check is:

`Build & Test`

The repository has branch protection requiring a pull request and the required status check before merging into `main`.

## 9.2 Merge Status

The feature branch has been merged into `main`, as confirmed by the user.

The previous implementation changes are therefore part of the merged development baseline.

However, the following details remain unverified:

- Current `main` HEAD commit hash.
- Whether the local working tree is clean.
- Whether the merge-triggered GitHub Actions run completed successfully.
- Whether the merged `main` branch passes the full verification suite.

Do not assume that a successful merge necessarily means the post-merge CI run passed.

## 9.3 Git Rules

- Do not commit secrets or `.env` files.
- Preserve existing reports and evaluation checkpoints.
- Do not overwrite historical evaluation artifacts.
- Do not stage, commit, push, merge or reset without explicit user authorization.
- Review the complete diff before staging.
- Use the established pull-request workflow for protected branches.
- Do not assume a dirty working tree is safe to discard.
- Treat `main` as the current development baseline unless the user explicitly establishes another branch.

---

# 10. ARCHITECTURAL CONSTRAINTS AND LOCKED DECISIONS

These decisions are established project requirements. Do not change them merely because another approach is available.

## 10.1 Role of the LLM

The LLM is a semantic reconciliation assistant.

It is not an autonomous investigator and must not:

- Decide guilt or innocence.
- Determine that a person committed a crime.
- Invent evidence.
- Override investigator decisions.
- Treat model-generated claims as verified facts.
- Modify original case records autonomously.
- Convert uncertainty into certainty.

All suggestions must be grounded in case-context records and accompanied by resolvable source references.

## 10.2 Case Context

- The LLM consumes structured JSON context.
- Images and image bytes are not sent to the LLM.
- Original source records remain distinct from derived descriptions.
- Observed, reported and inferred information must remain distinguishable.
- Uncertainty and conflicting accounts must be preserved.
- User-supplied case text is data, not system instructions.

## 10.3 Tier A and Tier B Separation

Tier A remains deterministic.

Tier B remains semantic and LLM-assisted.

Do not replace deterministic checks with LLM guesses or use the LLM to bypass the validator.

## 10.4 Production Provider

The production provider is finalized:

```text
Provider: Groq
Model: openai/gpt-oss-120b
```

Do not propose provider migration, repeat provider-selection experiments or change the production model without explicit authorization.

## 10.5 Investigator Authority

The investigator retains control over case decisions.

AI-generated suggestions are reviewable outputs, not automatic modifications to the underlying investigation.

Investigator review history must be stored separately from original LLM suggestions.

---

# 11. CURRENT PROJECT ROADMAP

The established development sequence is:

| Order | Module | Status |
|---:|---|---|
| 1 | LLM Analysis Module | Live evaluation and pre-merge offline verification completed; final implementation review and formal freeze pending |
| 2 | YOLO Module | Not implemented |
| 3 | OpenCV Module | Not implemented |
| 4 | Timeline Construction Module | Not implemented |
| 5 | Case Context Module | Not implemented as a complete production module |
| 6 | Report Generation Module | Not implemented |
| 7 | Integration Testing | Future |
| 8 | Final Menu-Based UI | Future |

Integration testing should be performed incrementally as modules are developed. Do not postpone all integration work until the end.

## 11.1 Next Planned Task: Prompt 14 — Investigator Interaction Workflow Prototype

The next planned task is the investigator-facing workflow prototype.

The goal is a menu-driven interaction model, not a chatbot.

The prototype should establish:

- Analysis operation selection.
- Display of generated findings.
- Display of empty-result states.
- Handling of partial-success and error states.
- Source-reference inspection.
- Investigator review decisions.
- Review history.
- Return-to-menu behaviour.
- A structured response envelope.
- Separation between immutable AI output and investigator review records.

The proposed response envelope is:

```json
{
  "module": "...",
  "operation_id": "...",
  "status": "completed | partial_success | failed",
  "data": {},
  "warnings": [],
  "errors": [],
  "available_actions": []
}
```

The application, not the LLM, controls `available_actions`.

The prototype should first use mocked interactions, followed by one controlled live integration test.

It must not expand into a full React interface or final application UI at this stage.

---

# 12. EXECUTOR OPERATING INSTRUCTIONS

The executor is responsible for repository inspection, code modifications, commands and verification when explicitly instructed.

The coordinator is responsible for technical reasoning, requirements, architecture, review and generating precise execution prompts.

The user retains final approval.

Follow these rules:

1. Inspect existing source code before proposing modifications.
2. Preserve established architecture and approved decisions.
3. Do not reopen settled decisions without concrete evidence of a defect or incompatibility.
4. Do not introduce new dependencies without a clear technical requirement.
5. Do not change fixtures, expected results, prompts, validator rules or evaluation scoring merely to improve benchmark scores.
6. Do not modify unrelated files.
7. Do not silently remove existing functionality.
8. Do not replace a completed feature with a stub or mock implementation.
9. Distinguish mocked tests from actual live-provider verification.
10. Run focused tests for the affected component, followed by the required offline verification suite when appropriate.
11. Report exact commands, outputs, exit statuses and changed file paths.
12. Identify known limitations and unverified behaviour.
13. Never expose secrets in output or documentation.
14. Never run live LLM API calls unless explicitly authorized.
15. Never stage, commit, push, merge or reset Git changes without explicit authorization.
16. Preserve evaluation reports and checkpoint artifacts.
17. Do not claim that a feature works merely because a class, function or file exists.
18. Do not invent test results, file contents or implementation details.

## 12.1 Required Execution Report

After implementation tasks, report:

- Objective completed.
- Exact files modified or created.
- Important implementation details.
- Tests and verification commands executed.
- Exact test results and exit statuses.
- Known defects or unresolved issues.
- Git working-tree status.
- Whether any live API calls were made.

Do not claim successful completion when verification has not been performed.

---

# 13. HANDBOOK AUTHORITY AND MAINTENANCE

This document is an implementation snapshot based on the last executor scan, supplied verification results and the user's confirmation that the feature branch has been merged into `main`.

It is not a replacement for the project requirements or approved architectural decisions.

Use the following authority distinction:

| Document | Authority |
|---|---|
| Coordinator Handbook | Project objectives, approved decisions, requirements, constraints and development history |
| Executor Codebase Handbook | Current repository structure, implementation status, dependencies and verification evidence |
| `PROJECT_BRIEF.md` | Detailed project requirements and established technical contracts |
| `full _roadmap.md` | Planned development sequence and implementation prompts |
| `PLAN.md` | Reconciled operational state, active tasks and decision/implementation ledger |

When documents disagree:

1. Preserve approved project requirements and decisions.
2. Inspect the actual source code to establish current implementation.
3. Identify the discrepancy explicitly.
4. Do not silently rewrite an approved requirement to match an accidental implementation deviation.
5. Obtain approval before changing a locked architectural decision.

Update this handbook when significant repository structure, dependencies, implementation status or verification results change.

## Current Baseline

- Feature branch `feature/live-gemini-evaluation` has been merged into `main`.
- The LLM Analysis Module completed its thirteen-fixture live Groq evaluation.
- The benchmark achieved Tier A recall of 1.00 and Tier B precision and recall of 1.00.
- The last reported offline verification was 146 passing tests, 1 warning, all 13 fixtures valid, all 13 references resolved and zero Pyrefly errors.
- The last verification results were obtained before the merge; post-merge CI and local verification remain unconfirmed.
- The production model remains `openai/gpt-oss-120b` through Groq.
- The rate-limiter implementation still requires reconciliation against the approved simple 20-second cooldown design.
- The next engineering task is the final LLM Analysis Module implementation review and formal freeze, followed by Prompt 14 — Investigator Interaction Workflow Prototype.