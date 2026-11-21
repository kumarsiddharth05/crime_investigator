Yes. Now that the LLM Analysis Module has a defined role in the larger application, I would treat its remaining work as a separate, finite development track. We should not keep adding features indefinitely.

The module has two responsibilities to finish:

1. **Analytical reliability:** establish that the selected Groq model, production prompts, pipeline and validator work across all 13 fixtures.
2. **Investigator interaction:** establish that an investigator can operate the module through menus, receive understandable results, inspect sources and record decisions without using a chat interface.

After those are complete, we freeze the module and move to YOLO.

I recommend six remaining prompts, numbered 11–16 for continuity. Prompt 13 is conditional: we only issue it if the benchmark exposes defects. This avoids unnecessary implementation work.

# **Remaining LLM Analysis Module roadmap**

## **Six remaining prompts**

1. **Prompt 11 — Groq integration audit**

   Next

   Verify implementation, rate-limit handling, pacing, security and evaluation readiness. Read-only.
2. **Prompt 12 — Complete live evaluation**

   Run all 13 fixtures through the actual production pipeline and establish benchmark results.
3. **Prompt 13 — Targeted corrections**

   Fix defects exposed by evaluation, add regression tests and re-evaluate. Conditional.
4. **Prompt 14 — Investigator interaction prototype**

   Build a menu-based CLI to test the actual investigator workflow, JSON requests, results and review actions.
5. **Prompt 15 — Final module freeze**

   Documentation, contracts, final tests, reproducibility and release readiness.
6. **Prompt 16 — Git baseline and CI**

   Review changes, obtain authorization to commit, push, create PR and verify GitHub CI.

The final deliverable is not merely an LLM that returns JSON. It is a standalone analysis module that an investigator can operate, whose outputs can be traced to case records, and whose results can be reviewed and audited.

Below are the complete executor prompts. They are written to be issued sequentially. Do not issue the next prompt until the previous one has been reviewed and approved.

# **Complete executor prompt package**

# MASTER EXECUTION PLAN — LLM ANALYSIS MODULE COMPLETION

## Project context

Project: AI-Assisted Crime Scene Investigation and Evidence Analysis System.

Current branch: `feature/live-gemini-evaluation`.

Current selected LLM provider:

- Provider: Groq
- Model: `openai/gpt-oss-120b`
- Endpoint: `https://api.groq.com/openai/v1/chat/completions`

Current reported implementation status:

- Analysis pipeline implemented.
- Tier A deterministic checks implemented.
- Three Tier B semantic contradiction categories implemented.
- Seven-stage validator implemented.
- 13 evaluation fixtures implemented.
- Evaluation harness implemented.
- OpenAI, Gemini, Anthropic and OpenRouter adapters retained.
- Dedicated Groq adapter added.
- Groq 12-second pacing added.
- Investigator-facing CLI interaction workflow not yet implemented.
- Latest reported offline tests: 135 passed, 0 failed, 1 warning.
- Latest reported Groq median latency: 1.87 seconds in the tested sample.
- Complete 13-fixture live evaluation has not yet been established.

The objective is to finish the LLM Analysis Module before starting the YOLO module.

The LLM module must remain an independent subsystem. It receives structured case context, analyzes cross-source inconsistencies, returns validated suggestions and allows an investigator to review those suggestions.

It is not an autonomous investigator and must never determine guilt or independently establish facts.

## Permanent architectural constraints

1. Preserve the existing `case_context` schema.
2. Preserve stable dotted references such as `notes.N4`, `photos.P1.d3`, `timeline.T2` and `evidence.E1`.
3. Preserve all eight Tier A rules, A1–A8.
4. Do not reintroduce A9.
5. Preserve exactly three Tier B categories:
   - `spatial_inconsistency`
   - `timeline_contradiction`
   - `contextual_contradiction`
6. Do not introduce ambiguity, follow-up or semantic coverage-gap categories.
7. Preserve one analysis type per LLM invocation.
8. Preserve the existing validator and its seven checks.
9. Empty suggestions are valid.
10. Every suggestion must cite resolvable case-context references.
11. Never weaken grounding or validation requirements just to improve model recall.
12. Never allow the LLM to decide application navigation or investigator actions.
13. Preserve investigator control and auditability.
14. Do not send photographs, image bytes, image paths or base64 to the LLM.
15. Keep the evaluation harness independent of the future database and UI.
16. Never expose API keys or other secrets in logs or reports.

## Collaboration and execution rules

- Work only within the explicitly authorized prompt scope.
- Do not silently expand scope.
- Do not stage or commit files.
- Do not push branches or merge pull requests.
- Do not modify `.env` unless explicitly authorized.
- Do not make live API calls unless the current prompt explicitly authorizes them.
- Do not repeat failed API requests in uncontrolled loops.
- Report actual commands and results.
- Distinguish verified facts from assumptions.
- Preserve existing accepted functionality.
- Stop and report if an architectural conflict is discovered.
- Do not continue to the next prompt without coordinator approval.

---

# PROMPT 11 — FINAL GROQ INTEGRATION AUDIT

## Objective

Perform a read-only audit of the newly implemented Groq provider integration and its interaction with the existing analysis pipeline.

This is a diagnostic and verification task. No implementation changes are authorized.

## Files to inspect

At minimum:

- `src/llm/client.py`
- `src/llm/__init__.py`
- `src/analysis/pipeline.py`
- `evaluate.py`
- `analyze.py`
- `tests/test_client.py`
- `tests/test_pipeline.py`
- `tests/test_evaluate.py`
- `.gitignore`
- `.env.example`, if present.

Inspect additional files only when necessary to understand the implementation.

Do not print or expose `.env` credentials.

## A. Groq provider implementation

Verify:

1. `groq` is registered as a supported provider.
2. The endpoint is exactly:

   `https://api.groq.com/openai/v1/chat/completions`
3. The configured model is:

   `openai/gpt-oss-120b`
4. `GROQ_API_KEY` is correctly resolved.
5. Missing configuration produces a controlled configuration error.
6. Authentication errors are handled correctly.
7. HTTP 429 and other provider errors are mapped correctly.
8. Response parsing produces the internal structure expected by the validator.
9. JSON mode is configured correctly.
10. Existing OpenAI, Gemini, Anthropic and OpenRouter adapters remain functional.

Do not assume that compatibility with an OpenAI-style endpoint means every provider-specific behaviour is identical.

## B. Retry and transport behaviour

Verify:

- Application-level schema-repair attempts.
- HTTP transport retry behaviour.
- Behaviour on HTTP 429.
- Behaviour on HTTP 500 and other server failures.
- Behaviour on connection errors and timeouts.
- Whether any hidden retry layer can multiply API requests.

The evaluation harness must not silently repeat failed requests.

## C. Groq rate-limit pacing

Inspect the 12-second pacing implementation.

Determine:

- Where the delay is implemented.
- Whether it is applied only to Groq.
- Whether it affects calls across different cases.
- Whether it applies between analysis categories.
- Whether it is applied in both CLI and evaluation paths.
- Whether it is safe under concurrent execution.
- Whether it accounts for token-per-minute restrictions.
- Whether it can cause unnecessary delays.
- Whether the delay is included in complete-case latency measurement.

Do not assume that 12 seconds is sufficient simply because it was implemented.

## D. Latency measurement

The established evaluation target is median complete-case latency below 6000 ms.

Verify the actual measurement boundaries.

Report separately:

1. Provider request latency.
2. Validation and processing latency.
3. Pacing delay.
4. Complete-case wall-clock latency.

Do not exclude pacing or other real processing time from complete-case latency merely to make the metric pass.

If the current implementation makes the six-second target structurally incompatible with multi-category pacing, report that explicitly. Do not change the acceptance criterion without coordinator approval.

## E. Configuration and security

Verify:

- Dotenv loading from the CLI entry points.
- Environment-variable precedence.
- `.env` exclusion from Git.
- No hardcoded API keys.
- No secret leakage into reports.
- No unnecessary sensitive case data in logs.

## F. Offline verification

Run:

```
pytest -q
python scripts/check_fixtures.py
python scripts/check_refs.py
```

Expected reported baseline:

- 135 tests passing.
- 13 fixtures valid.
- 13 references valid.

Report actual differences rather than forcing the old expected count.

## Restrictions

- Read-only.
- No source modifications.
- No `.env` modifications.
- No API requests.
- No live evaluation.
- No staging or committing.

## Deliverable

Provide:

1. Exact files inspected.
2. Exact commands executed.
3. Results for sections A–E.
4. Offline test results.
5. Identified defects and risks.
6. Whether Prompt 12 can safely proceed.

Stop after the audit.

---

# PROMPT 12 — COMPLETE LIVE EVALUATION

## Objective

Evaluate the selected production model, `openai/gpt-oss-120b` through Groq, against all 13 established fixtures using the actual production pipeline and evaluation harness.

This is the first complete live evaluation of the selected model.

Prompt 11 must have been reviewed and approved before starting.

## Preconditions

Verify:

- `LLM_PROVIDER=groq`.
- `LLM_MODEL=openai/gpt-oss-120b`.
- `GROQ_API_KEY` is configured.
- The correct provider and model are active.
- No duplicate conflicting provider variables are active.
- The evaluation harness is functional.
- All 13 fixtures pass fixture validation.
- All references resolve.

Never print the API key.

If configuration is incorrect, stop without making an API request.

## Execution

Run:

```
python evaluate.py --max-concurrency 1
```

Use the existing production pipeline and validator.

Do not create a separate simplified evaluation path.

Do not bypass the semantic gate.

Do not bypass validation.

Do not modify fixtures or expected results.

Do not change prompts during the evaluation.

## Request discipline

This is one controlled benchmark run.

- Use concurrency 1.
- Respect existing Groq pacing.
- Do not launch duplicate evaluations.
- Do not automatically repeat the entire benchmark after an error.
- Stop and report if the provider returns persistent 429, authentication failure or configuration failure.
- Preserve partial diagnostic information if execution stops.

The evaluation may involve multiple API requests because each case can require multiple eligible analysis categories. Record the actual request count.

## Required metrics

Evaluate the established acceptance criteria:

| Metric                       | Acceptance criterion |
| ---------------------------- | -------------------- |
| Tier A recall                | 1.00                 |
| Tier B recall                | >= 0.85              |
| Tier B precision             | >= 0.85              |
| Hallucination/rejection rate | 0                    |
| Clean-case false positives   | 0                    |
| Median complete-case latency | < 6000 ms            |

Tier A precision remains informational, not an acceptance criterion.

Do not redefine any metric.

## Important interpretation rules

1. A reference resolving successfully does not prove semantic correctness.
2. A suggestion matching expected type and reference set does not automatically prove every statement is factually correct.
3. A rejected suggestion is not automatically a model hallucination; inspect the rejection reason.
4. A clean-case suggestion counts as a false positive according to the established evaluation logic.
5. Do not silently treat N/A metrics as passing.
6. Do not treat API errors as empty model responses.
7. Distinguish provider failures from model-quality failures.

## Latency reporting

Report:

- Per-request provider latency.
- Per-case complete wall-clock latency.
- Median complete-case latency.
- Pacing time.
- Total benchmark duration.

Pacing and real processing time must remain included in complete-case wall-clock latency.

If the complete-case target fails despite low individual provider latency, report the failure honestly.

## Output

Generate the existing JSON and Markdown evaluation reports.

Do not overwrite earlier reports.

Report:

1. Overall acceptance result.
2. All metrics.
3. Per-fixture results.
4. Per-category results.
5. False positives.
6. False negatives.
7. Rejected suggestions and reasons.
8. API errors.
9. Request and token counts.
10. Latency details.
11. Report file locations.
12. Whether Prompt 13 is required.

Do not modify source files.

Do not stage or commit.

Stop after producing the report.

---

# PROMPT 13 — TARGETED EVALUATION CORRECTIONS

## Objective

Correct only genuine defects demonstrated by Prompt 12.

This prompt is conditional. If Prompt 12 passes all acceptance criteria, skip Prompt 13 entirely.

## First step: classify failures

For each failure, determine whether it originates from:

- Provider or API behaviour.
- Incorrect model response.
- Prompt ambiguity.
- Semantic-gate eligibility.
- Validator defect.
- Fixture or expected-result defect.
- Evaluation metric implementation.
- Latency/pacing architecture.

Do not assume every failure is caused by the model.

## Correction requirements

For every confirmed defect:

1. Identify the root cause.
2. Identify the smallest responsible code or prompt component.
3. Propose the correction.
4. Explain possible regressions.
5. Implement only the approved correction.
6. Add a focused regression test.
7. Run the relevant test subset.
8. Run the complete offline suite.

## Permanent constraints

Do not:

- Remove validator checks to improve recall.
- Relax reference resolution.
- Permit invented references.
- Introduce new Tier B categories.
- Change ground truth to match model output without evidence.
- Convert empty results into findings.
- Suppress valid contradictions simply because the model has difficulty identifying them.
- Change acceptance criteria without explicit coordinator approval.

## Re-evaluation

After approved corrections:

- Re-run fixture validation.
- Re-run reference validation.
- Run all offline tests.
- Produce a new complete live evaluation only after explicit authorization.

Never overwrite the original benchmark.

Keep the original and corrected reports separately identifiable.

## Deliverable

Provide:

- Root-cause analysis.
- Modified files.
- Exact changes.
- Regression tests.
- Full offline test results.
- Remaining defects.
- Whether the engine meets acceptance criteria.

Stop after reporting.

---

# PROMPT 14 — INVESTIGATOR INTERACTION WORKFLOW PROTOTYPE

## Objective

Build a menu-driven CLI prototype that tests the LLM Analysis Module from an investigator's perspective.

This is not the final application UI.

The purpose is to prove that the existing analysis engine can be operated through structured menu selections rather than a conversational interface.

The prototype must reuse the existing production pipeline and `case_context` format.

## Architectural principle

The investigator interacts with the application.

The application constructs structured JSON requests.

The pipeline selects eligible analysis categories, constructs prompts, calls the LLM and validates the result.

The LLM returns suggestions.

The application presents those suggestions and offers deterministic investigator actions.

The LLM must never generate or control application navigation.

## A. Main menu

Implement a menu resembling:

```
================================================
       AI-ASSISTED CRIME SCENE ANALYSIS
================================================

1. Select Case
2. Run Complete Analysis
3. Run Spatial Inconsistency Analysis
4. Run Timeline Contradiction Analysis
5. Run Contextual Contradiction Analysis
6. View Previous Analysis
7. Review Findings
8. View Case Analysis History
9. Exit

Select an option:
```

The actual case must be selected or loaded through the existing supported case-loading mechanism.

Do not hardcode C4 as the only available case.

## B. Operation selection

Support:

- Complete analysis.
- Spatial inconsistency analysis.
- Timeline contradiction analysis.
- Contextual contradiction analysis.

A complete analysis means running the existing pipeline for all eligible analysis types.

Do not bypass the existing semantic gate.

Do not combine the three analysis types into a new single LLM call. Preserve the established one-analysis-type-per-invocation architecture.

## C. JSON request envelope

The UI/CLI layer should construct a request envelope similar to:

```
{
  "schema_version": "1.0",
  "request_id": "REQ001",
  "case_id": "C004",
  "operation": "analyze",
  "analysis_types": [
    "contextual_contradiction"
  ],
  "case_context": {}
}
```

This is an application-level interaction envelope.

The nested `case_context` must preserve the exact existing production schema.

Do not rename its fields or introduce an alternative representation.

If the existing pipeline API accepts arguments rather than this envelope, implement a thin request adapter. Do not unnecessarily refactor the pipeline.

Validate the operation and analysis type before executing.

Reject unsupported operations and categories with a clear error.

## D. Standard response envelope

Return a structured application response:

```
{
  "schema_version": "1.0",
  "request_id": "REQ001",
  "case_id": "C004",
  "module": "llm_analysis",
  "operation": "analyze",
  "status": "completed",
  "data": {
    "analysis_id": "AN001",
    "suggestions": []
  },
  "warnings": [],
  "errors": [],
  "available_actions": [
    "view_sources",
    "view_analysis_history",
    "return_to_menu"
  ]
}
```

The example is illustrative. Adapt the internal data to the actual production pipeline output.

Do not fabricate analysis IDs, findings or references.

The response must distinguish:

- `completed`
- `completed_with_warnings`
- `failed`

If the existing pipeline uses different internal statuses, map them consistently at the application boundary.

## E. Result states and menu behaviour

Implement separate presentation paths.

### State 1: Findings returned

Display:

- Finding number.
- Category.
- Severity.
- Description.
- Source references.
- Validation status, if available.

Offer actions:

- View source records.
- Mark as acknowledged.
- Mark as not relevant.
- Defer review.
- Return to results.
- Return to analysis menu.

Do not describe acknowledgement as confirmation of factual truth.

### State 2: Empty suggestions

Display:

"No contradictions were identified in the selected analysis category using the available case information."

Offer:

- Run another category.
- View analysis details.
- Return to menu.
- Return to case dashboard.

Never claim that no contradictions exist in the case.

### State 3: Partial completion

If some categories complete and others are ineligible or fail:

- Display completed categories.
- Display unavailable or failed categories.
- Explain the reason for each.
- Preserve successful results.
- Offer retry only for eligible failed operations.

Do not represent partial completion as complete success.

### State 4: Technical failure

Display a clear failure message.

Offer:

- Retry.
- View technical error details.
- Return to menu.

Do not represent a provider error as an empty successful result.

## F. Investigator review records

Keep model findings separate from investigator decisions.

Use a review structure similar to:

```
{
  "suggestion_id": "S001",
  "review_status": "deferred",
  "reviewed_by": "investigator_01",
  "reviewed_at": "2026-11-21T14:30:00",
  "comment": "Awaiting ownership verification."
}
```

Permitted review statuses:

- `pending`
- `acknowledged`
- `not_relevant`
- `deferred`

A `not_relevant` decision should require a reason.

An acknowledgement does not establish that the underlying claim is true.

Review records must not silently modify or delete the original model response.

Preserve analysis history.

If persistent database storage is not yet part of this module, use a clearly identified prototype persistence mechanism. Do not pretend temporary in-memory state is durable.

## G. Available actions

Generate available actions deterministically from application state.

The LLM must not decide which buttons or menu options appear.

For example:

- Before analysis: run analysis, select case, exit.
- After successful analysis: view sources, review findings, run another category, view history.
- After failure: inspect error, retry, return.
- After review: return to findings or menu.

Do not expose actions that are invalid for the current state.

## H. Testing strategy

First implement the interaction flow with mocked LLM responses.

Test:

1. Case selection.
2. Valid menu operations.
3. Invalid menu selections.
4. JSON request validation.
5. Correct pipeline dispatch.
6. Findings display.
7. Empty-result display.
8. Partial completion.
9. Technical failure.
10. Source-reference navigation.
11. Review status updates.
12. Mandatory dismissal reasons for `not_relevant`.
13. Analysis history.
14. Return navigation.
15. No fabricated results.
16. No LLM-controlled actions.
17. No accidental mutation of original findings.

Then test the same interaction path using the actual production pipeline and the selected Groq provider only after explicit authorization for live API usage.

Do not run repeated live requests during development.

## I. Scope restrictions

- No React frontend.
- No Flask or FastAPI integration unless already required by the existing architecture.
- No database migration.
- No YOLO changes.
- No OpenCV changes.
- No changes to the existing case-context schema.
- No changes to Tier A/Tier B semantics.
- No changes to the validator's grounding rules.
- No automatic acceptance of model findings.
- No staging or commits.

## Acceptance criteria

The investigator must be able to:

1. Select a case.
2. Select an analysis operation.
3. Submit a structured request.
4. Receive and understand the result.
5. Inspect the cited source records.
6. Record an independent review decision.
7. Return to the menu.
8. View prior analysis and review history.

All response states must behave correctly.

All existing tests must continue to pass.

## Deliverable

Provide:

- Interaction architecture.
- Menu flow.
- Request and response examples.
- Modified and new files.
- Test results.
- Sample CLI session.
- Known limitations.
- Confirmation that the production pipeline and case-context schema remain intact.

Stop after reporting.

---

# PROMPT 15 — FINAL LLM ANALYSIS MODULE FREEZE

## Objective

Prepare the LLM Analysis Module for a stable handover to the next project module: YOLO.

This is a final consolidation and verification milestone.

## A. Architecture verification

Confirm that the LLM module includes:

1. Structured case-context input.
2. Tier A deterministic analysis.
3. Semantic gating.
4. Three Tier B categories.
5. Category-specific prompts.
6. Provider abstraction.
7. Groq production configuration.
8. Response validation.
9. Reference grounding.
10. Severity validation.
11. Evaluation harness.
12. Audit and reporting.
13. Investigator interaction prototype.
14. Investigator review-state separation.

## B. Provider configuration

Document:

- Selected provider: Groq.
- Selected model: `openai/gpt-oss-120b`.
- Endpoint.
- Required environment variables.
- Authentication setup.
- Rate-limit considerations.
- Retry behaviour.
- Model replacement procedure.

Keep alternative provider adapters if they remain functional.

Do not remove them merely because Groq is the selected provider.

## C. Data contracts

Document:

- Existing `case_context` schema.
- Stable reference format.
- Analysis request envelope.
- Analysis response envelope.
- Finding structure.
- Investigator review record.
- Error and warning structure.

Clearly distinguish application-level interaction envelopes from the existing nested `case_context`.

## D. Analysis semantics

Document:

- A1–A8.
- Exactly three Tier B categories.
- Semantic-gate rules.
- Validator checks.
- Empty-result behaviour.
- Partial-result behaviour.
- Known hallucination-detector limitations.
- Investigator responsibilities.

## E. Evaluation documentation

Preserve:

- All 13 fixtures.
- Expected results.
- Evaluation scripts.
- Benchmark reports.
- Acceptance criteria.
- Actual model and provider configuration used for the successful evaluation.

A benchmark must be reproducible.

Do not label a failed or incomplete evaluation as passed.

## F. Testing

Run:

```
pytest -q
python scripts/check_fixtures.py
python scripts/check_refs.py
```

Run the appropriate CLI interaction tests.

Confirm that the final live evaluation report satisfies the acceptance criteria.

If any required acceptance criterion remains unmet, do not declare the module frozen.

## G. Module boundary

The LLM Analysis Module must not directly depend on:

- YOLO implementation internals.
- OpenCV implementation internals.
- React components.
- Browser state.
- Image bytes.
- Database-specific ORM models.

It should consume a validated structured context and return structured results.

The future Case Context Module will be responsible for generating that context from application data.

## Restrictions

- Do not introduce unrelated features.
- Do not redesign the project.
- Do not remove working provider adapters without authorization.
- Do not change established analysis semantics.
- Do not stage or commit.

## Deliverable

Produce a final module handover document containing:

1. Architecture.
2. Module responsibilities.
3. Input and output contracts.
4. Provider configuration.
5. Evaluation results.
6. Test results.
7. Known limitations.
8. Operational commands.
9. Integration requirements for future modules.
10. Explicit freeze readiness: PASS or FAIL.

Stop after reporting.

---

# PROMPT 16 — GIT BASELINE AND CI VERIFICATION

## Objective

Establish a clean, reproducible Git baseline for the completed LLM Analysis Module.

This prompt includes review and preparation. Actual staging, committing, pushing and merging require separate explicit user authorization.

## A. Repository inspection

Inspect:

```
git status
git branch --show-current
git diff --stat
git diff
git diff --check
```

Identify every modified, deleted, new and untracked file.

## B. Secret protection

Verify:

- `.env` is ignored.
- No API keys appear in source files.
- No API keys appear in test fixtures.
- No credentials appear in reports.
- No temporary diagnostic scripts are accidentally included.
- No scratch directories or unrelated files are included.

Do not print secret values.

## C. Scope review

Confirm that the changes belong to the completed LLM Analysis Module.

Do not include unrelated `Misc/` files or temporary diagnostic artifacts.

Do not restore intentionally deleted files.

## D. Test readiness

Verify the final offline suite and the successful benchmark report.

Check that CI uses the correct Python version and dependencies.

Confirm that the workflow does not require live API credentials for ordinary tests.

The CI pipeline should validate:

- Fixture structure.
- Reference resolution.
- Offline tests.

It should not make paid or free-tier model requests.

## E. Change proposal

Produce:

- Exact files proposed for staging.
- Exact files excluded.
- Proposed commit message.
- Current branch.
- Diff summary.
- CI expectations.

Do not stage files yet.

## F. Authorization gate

Stop and wait for the user to explicitly authorize staging and committing.

After authorization:

1. Stage only approved files.
2. Commit to `feature/live-gemini-evaluation`.
3. Push the feature branch.
4. Create a pull request to `main`.
5. Wait for the required `Build & Test` status check.
6. Report CI results.

Do not merge without explicit authorization.

## Final acceptance

The LLM Analysis Module is considered released when:

- The benchmark is accepted.
- The interaction prototype works.
- The final offline suite passes.
- The working tree changes are reviewed.
- The feature branch is pushed.
- The required CI check passes.
- The user authorizes the merge.

Do not claim release completion before these conditions are satisfied.

Stop at every authorization boundary.

---

# END OF MASTER EXECUTION PLAN

## **3. What the interaction prototype will prove**

There is a distinction worth emphasizing: your existing evaluation harness tests analytical correctness, but it does not fully test the investigator's experience. Prompt 14 closes that gap.

The final interaction flow should look like this:

**Select case**

C004

**Select operation**

Complete / Spatial / Timeline / Contextual

**Build JSON request**

Existing case_context + selected operation

**Analysis pipeline**

Tier A → semantic gate → LLM → validator

**Display result**

Findings / no findings / partial / error

**Investigator review**

View sources · Acknowledge · Not relevant · Defer

**Return to menu / View history**

The application, not the LLM, decides what actions are available after each response. That is a fundamental boundary.

## **4. When can we call the LLM module complete?**

These are the final release conditions:

| Requirement            | Completion condition                                   |
| ---------------------- | ------------------------------------------------------ |
| Analytical correctness | Full 13-fixture benchmark accepted                     |
| Deterministic checks   | A1–A8 verified                                         |
| Semantic analysis      | All three Tier B categories tested                     |
| Grounding              | References validated; hallucination criteria satisfied |
| Performance            | Complete-case latency meets the approved target        |
| User interaction       | Menu-driven workflow tested                            |
| Investigator control   | Review decisions stored separately from model findings |
| Reliability            | Offline tests and error-state tests pass               |
| Reproducibility        | Reports and configuration documented                   |
| Release                | Git baseline and CI verified                           |

One issue deserves special attention: the 12-second Groq pacing and the six-second complete-case latency requirement. We must resolve that honestly in Prompt 11. If pacing is included in the complete-case measurement and causes the target to fail, we cannot simply exclude it from the metric.

**My recommended immediate sequence is Prompt 11 → Prompt 12 → Prompt 13 if needed → Prompt 14 → Prompt 15 → Prompt 16.**

Once Prompt 16 is accepted and the module is released, we stop changing the LLM module except for genuine bugs or integration requirements. The next major development track becomes YOLO.

This gives you a defined finish line rather than an LLM module that keeps expanding while the rest of the project remains untouched.