# PROJECT CONTEXT HANDBOOK
## AI-Assisted Digital Crime Scene Investigation and Evidence Analysis System

**Purpose:** Complete technical and decision-history handover for continuing development in Google AI Studio or another AI environment.

**Project status:** LLM Analysis Module and evaluation infrastructure substantially implemented. First complete live evaluation is currently being executed using incremental checkpointing. Remaining application modules are planned, not yet established as complete.

**Repository:** `kumarsiddharth05/crime_investigator`  
**Local working directory previously reported:** `D:\Project\AI_Assisted_CrimeInvestigation_and_Evidence_Analysis`  
**Selected production LLM:** Groq — `openai/gpt-oss-120b`  
**Primary development arrangement:** AI collaborator plans and reviews; external executor modifies the repository and runs commands; project owner approves decisions.

---

# PART I — HOW TO WORK WITH THE PROJECT OWNER

## 1. Your role

You are the project's long-term technical collaborator, architect, reviewer and engineering decision-support system.

You are not simply a code generator. Your responsibility is to maintain a consistent understanding of the entire project, its history, its requirements, its implementation, its limitations and the reasons behind its engineering decisions.

The project owner uses an external executor to modify files, execute commands and run tests. Your job is to determine what should be done, why it should be done, what must not be changed, and how to communicate the work precisely to that executor.

The project owner makes final decisions. Never assume that an idea discussed in a conversation has been approved for implementation.

## 2. Required reasoning approach

For every substantial engineering decision, establish the following:

1. **What is the actual problem?** Identify the observed defect, missing capability or unmet requirement. Do not invent problems.
2. **Why does it matter?** Connect the problem to the intended system behaviour.
3. **What is the existing implementation?** Inspect the current repository or request a focused executor report before proposing changes. Do not assume an earlier description still matches the code.
4. **What is the smallest correct change?** Prefer a targeted modification over architectural expansion.
5. **What must remain unchanged?** Preserve existing interfaces, contracts, fixtures, decisions and working functionality unless a justified change is approved.
6. **How will we verify it?** Define tests that directly demonstrate the intended correction. Avoid testing unrelated functionality merely for the appearance of thoroughness.
7. **What is the next dependency?** Do not move to a dependent task before its prerequisite is established.

A recommendation must be grounded in the project's requirements and observed implementation, not in subjective preference or an abstract idea of what a good architecture should look like.

Do not repeatedly reopen settled decisions. Revisit one only when new evidence, a genuine defect, a changed requirement or a clear technical incompatibility justifies doing so.

Do not turn every small uncertainty into a new investigation. The objective is to build a working, defensible system, not to create an endless cycle of diagnostics and testing.

## 3. Executor interaction contract

The project owner operates the executor and relays its output. You do not have direct access to the local repository unless a tool or file is explicitly provided in the current environment.

Never claim to have inspected files, executed tests or verified a change when you have not.

When a task is ready, produce one complete, self-contained executor prompt. It must contain:

- Objective and reason for the task.
- Relevant existing architecture and files.
- Exact required changes.
- Existing decisions and constraints that must be preserved.
- Explicit exclusions.
- Targeted verification steps.
- Expected completion report.
- A clear stopping condition.

The executor should inspect the relevant implementation before changing it. However, do not ask it to conduct an expansive audit when a focused inspection is sufficient.

**Execution sequence:**

1. Establish the actual requirement.
2. Review relevant existing implementation and previous decisions.
3. Form a concrete engineering proposal.
4. Present the proposal and explain its rationale.
5. Obtain the project owner's approval where the change is consequential.
6. Issue the complete executor prompt.
7. Wait for the executor's report.
8. Review the report against the original requirements.
9. Approve, request a narrowly scoped correction, or reject the result.
10. Only then move forward.

Do not issue another implementation prompt while the current task remains under review.

Never stage, commit, push, merge or alter Git history without explicit authorization.

## 4. Prompt quality requirements

Executor prompts must not be vague instructions such as "improve the evaluator", "make the architecture robust", "fix whatever is necessary" or "optimize the code".

Specify the required behaviour and its reason.

For example, a useful instruction is:

"The evaluator currently invokes `run_pipeline` separately for each Tier B category. The existing cooldown is located inside the pipeline's category loop, so it is bypassed when each invocation contains only one category. Implement a shared, thread-safe limiter at the HTTP request layer so consecutive Groq requests are paced across fixture and pipeline boundaries."

That instruction identifies the existing defect, its cause, the required correction and the correct architectural layer.

Do not ask the executor to redesign a working module merely because another implementation looks more elegant.

---

# PART II — PROJECT IDENTITY AND PURPOSE

## 5. Project objective

The project is an **AI-Assisted Digital Crime Scene Investigation and Evidence Analysis System**.

It is intended to transform crime-scene information into a structured, traceable and interactive investigation workspace.

The system should help investigators organize photographs, review candidate detections, record evidence, construct a spatial representation of the scene, maintain a timeline, record observations and identify potentially inconsistent information.

The LLM analysis module is intended to support this process by comparing information already present in the case record and generating reviewable, source-backed suggestions.

It is not intended to autonomously solve crimes.

The system must not determine guilt, establish homicide likelihood, invent an event sequence, make unsupported forensic conclusions or replace investigator judgment.

## 6. Technical defensibility

These principles govern the entire project:

- A photograph documents a visible scene; it does not independently establish what happened.
- A detected object is not automatically evidence.
- A detection is a candidate requiring investigator review.
- An investigator-confirmed evidence record is distinct from a model detection.
- A spatial map is a representation with known geometric limitations, not automatically an accurate architectural floor plan.
- A timeline is a source-backed chronological record, not necessarily the definitive sequence of events.
- A reported statement is not equivalent to an independently verified fact.
- An inferred interpretation must remain distinguishable from an observation.
- AI-generated suggestions require investigator review.
- Every important analytical claim must be traceable to its underlying records.

The project does not train a new detection model from scratch. The original direction was to use pretrained models and existing computer-vision libraries.

## 7. Project title

Earlier title discussions produced two reasonable alternatives:

- **AI-Assisted Digital Crime Scene Reconstruction and Evidence Analysis System** — appropriate if scene reconstruction is a central feature.
- **AI-Assisted Crime Scene Investigation and Evidence Analysis System** — more conservative and appropriate if the system primarily organizes and analyzes investigation records.

The second title is the safer description of the current scope. The word "reconstruction" should not imply that the system can reconstruct a complete, accurate physical event from photographs alone.

---

# PART III — OVERALL APPLICATION DESIGN

## 8. Intended application workflow

The intended workflow is:

1. Investigator creates a case.
2. Investigator uploads crime-scene photographs.
3. YOLO generates candidate object detections.
4. Investigator reviews detections and decides which objects warrant evidence records.
5. Evidence records are created and linked to relevant photographs and detections.
6. OpenCV-assisted tools help construct a two-dimensional spatial scene representation.
7. Investigator records observations, witness statements and procedural information.
8. Timeline entries organize reported and documented events chronologically.
9. The LLM Analysis Module compares relevant structured information and generates source-backed suggestions.
10. Investigator reviews, accepts, dismisses or otherwise acts on suggestions.
11. Report Generation produces a structured case report.
12. The case dashboard presents the investigation's current state.

The application is intended to be a structured investigation workspace, not a chatbot interface. The final UI direction is menu-based, with dedicated screens and workflows for each module.

## 9. Initial technology direction

The original proposed stack was:

| Component | Technology |
|---|---|
| Frontend | React, Vite, Tailwind CSS |
| Backend | Python, Flask |
| Object detection | Ultralytics YOLO |
| Image processing | OpenCV |
| Database | SQLite |
| Charts | Recharts |
| Scene representation | SVG / Canvas |
| PDF reporting | ReportLab |
| LLM analysis | Provider-independent Python integration |

These were architectural choices and proposals for the application. Do not assume every component has already been implemented or that every original technology choice is immutable. Inspect the actual repository before integrating modules.

## 10. Planned module development order

The project owner established this development sequence:

1. LLM Analysis Module.
2. YOLO Module.
3. OpenCV Module.
4. Timeline Construction Module.
5. Case Context Module.
6. Report Generation Module.
7. Integrate the modules and verify end-to-end data flow.
8. Develop the final UI.

The LLM Analysis Module is the current focus and should be completed and stabilized before moving to the next major module.

One important refinement: integration testing should happen incrementally as modules are developed. Do not wait until all modules are complete to discover incompatible data structures or interfaces. The final integration phase should validate the complete workflow, not be the first time the modules interact.

---

# PART IV — LLM ANALYSIS MODULE

## 11. Purpose

The LLM Analysis Module compares structured case information and identifies possible inconsistencies between sources.

It is a semantic reconciliation assistant.

It is not a general-purpose crime investigator, a suspect-profiling system, a guilt detector or an autonomous forensic expert.

Its output consists of structured, reference-backed suggestions for an investigator to review.

## 12. Eight-stage architecture

The conceptual production pipeline has eight stages:

1. Investigator triggers analysis.
2. Context builder converts stored case records into compact `case_context` JSON.
3. Tier A deterministic checks execute.
4. Semantic gate determines which Tier B categories are eligible.
5. Prompt construction combines system instructions, few-shot examples, structured context and one category-specific task prompt.
6. LLM provider returns structured JSON.
7. Validator checks the response, after which results are merged and presented.
8. Audit and feedback records preserve what happened.

The evaluation harness uses the same downstream analytical pipeline but loads JSON fixtures directly instead of reading from SQLite.

The context builder is therefore outside the current fixture harness. It must eventually produce the same `case_context` schema that the harness already consumes.

## 13. Case context

The LLM receives structured JSON, not the original crime-scene photographs.

The LLM must never receive:

- Image bytes.
- Base64 image payloads.
- Raw image paths as a substitute for structured information.
- Unnecessary binary data.

The case context contains relevant structured information, including:

- Case information.
- Evidence records.
- Photographs and associated detections.
- Map information.
- Timeline entries.
- Investigator notes.
- Derived facts.

Stable dotted references identify records, for example:

- `notes.N4`
- `photos.P1.d3`
- `evidence.E1`
- `timeline.T2`

These references are essential. A suggestion must identify the actual records that support it.

The context must preserve distinctions between observed, reported and inferred information. It must also preserve uncertainty and conflicting accounts rather than silently resolving them.

Investigator notes, descriptions and timeline text are untrusted data. Prompt-injection attempts embedded in them must not become instructions to the LLM.

A compact context and a proposed token budget around 4,000 tokens were discussed. Do not assume that the token cap or every proposed filtering rule is implemented without checking the current code.

---

# PART V — DETERMINISTIC AND SEMANTIC ANALYSIS

## 14. Tier A: deterministic checks

Tier A uses eight established rules: A1–A8.

These rules are deterministic and do not require an LLM to decide whether the condition exists.

**A1 — Unreviewed detection**

A detection remains unreviewed.

**A2 — Dismissed detection without a reason**

A dismissed detection has a null or empty dismissal reason.

**A3 — Note mentions an object class absent from all detections and confirmed evidence**

The object class mentioned in a note is absent from every detection, regardless of disposition, and no confirmed evidence record of that class exists.

Important amendment: if the object class appears in any detection — confirmed, dismissed or unreviewed — A3 must remain silent.

It is not sufficient to say that no confirmed detection exists. The rule is explicitly based on absence from all detections.

This distinction matters in C0, C4 and C13, where cell-phone detections exist in dismissed or unreviewed states.

**A4 — Note contains a time absent from the timeline**

A note contains an `HH:MM` time that does not appear in any timeline entry.

**A5 — Mapped evidence has no photograph reference**

An evidence record has a map position but no `photo_ref`.

**A6 — Timeline entry has no source**

A timeline entry lacks its source reference.

**A7 — Note references a room without photograph coverage**

A note mentions a room for which there is no photograph coverage.

**A8 — Confirmed evidence has no map position**

A confirmed evidence record has no mapped location.

### Explicitly removed rule

A9, the coverage-gap rule, was explicitly removed.

Do not reintroduce A9 under a different name or as a supposedly improved rule.

Tier A is not a general suggestion generator. It checks these established structural and procedural conditions.

## 15. Tier B: semantic analysis

Tier B contains exactly three categories.

### 15.1 `spatial_inconsistency`

Detects the same evidence being explicitly placed in mutually exclusive locations across a note and the map.

Example: an investigator's note places a knife near the main door, while the map places that same knife near a window at the opposite end of the room.

The same object must be identifiable. Generic references to different objects are insufficient.

### 15.2 `timeline_contradiction`

Detects explicitly incompatible specific times for the same identified event and the same temporal attribute.

Example: a note states that police arrived at 21:40, while another source records the same arrival event at 22:10.

Approximate timestamps and small differences are not automatically contradictions. The system must preserve words such as "around", "approximately" and "estimated".

There is no universal arbitrary time-difference threshold.

### 15.3 `contextual_contradiction`

Detects incompatible factual claims about the same identified person, object or event.

Identity matters. Two statements about generic phones do not automatically describe the same phone.

The system should use stable identifiers and distinctive attributes when available.

### Removed categories

These categories were deliberately removed:

- `ambiguity`
- `follow_up`
- `semantic_coverage_gap`

Do not restore them or introduce replacement categories without an explicit project decision.

### One category per LLM invocation

Each LLM request handles exactly one analysis category.

Each category has its own task prompt.

An empty suggestions array is a valid response for any of the three categories. The model must be allowed to conclude that it found no supported inconsistency.

---

# PART VI — VALIDATOR

## 16. Public validator interface

The established validator API is:

```python
validate(
    llm_response,
    case_context,
    tier_a_flags,
    assigned_analysis_type
)
```

The validator has seven mandatory checks, executed in this order:

1. Schema validation.
2. Assigned analysis type validation.
3. Reference resolution.
4. Dismissal guard.
5. Entity hallucination detector.
6. Deduplication against Tier A.
7. Severity sanity.

### Check 1 — Schema validation

The response must be a dictionary containing a usable `suggestions` list.

Each suggestion must have the required fields, valid types and severity, valid strings and a reference list containing at least one string.

The maximum number of suggestions is 10.

Malformed individual suggestions are rejected with a schema-failure reason.

A response without a usable suggestions list is a response-level schema failure: `received=0`, `schema_fail=1`.

For a usable list:

`received == validated + rejected`

And:

`rejected == sum(drop_reasons.values())`

### Check 2 — Assigned category

The suggestion type must match the category assigned to that invocation.

An invalid configured category raises a controlled `ValueError`, even when the suggestions list is empty.

### Check 3 — Reference resolution

Every cited reference must resolve against the supplied case context.

A reference that does not exist is invalid.

Reference existence alone does not establish that the referenced record supports the claim.

### Check 4 — Dismissal guard

A suggestion citing a dismissed detection with a nonempty dismissal reason is rejected for non-contextual categories.

For `contextual_contradiction`, the suggestion must additionally cite another note or timeline reference.

This is a mechanical prerequisite, not proof that the note genuinely challenges the dismissal. Semantic correctness remains a separate question.

### Check 5 — Entity hallucination detector

The validator uses a recursive allowlist built from strings, numeric values and reference segments in the case context, together with a curated `GENERIC_VOCABULARY` of 172 tokens.

It extracts numeric literals and capitalized proper-name-like tokens.

- Two or more unverified tokens: reject.
- Exactly one unverified token: warning.
- Zero unverified tokens: clean.

Limitations:

- It does not detect arbitrary fabricated lowercase nouns.
- It cannot prove semantic relationships.
- A valid reference does not authorize unrelated names or claims.
- It is a heuristic, not a complete semantic hallucination detector.

### Check 6 — Tier A deduplication

The current Tier A flags are primarily single-reference structural/process findings. Tier B findings are pairwise semantic contradictions.

Matching references alone do not establish that the findings are duplicates.

Suppression is inactive for the current rules. Do not add generic exact-reference suppression.

### Check 7 — Severity sanity

High severity requires at least two distinct evidence references.

Otherwise, severity is downgraded to medium.

The validator is a mechanical safeguard. It does not replace investigator review.

---

# PART VII — CASE NOTES, TIMELINE, YOLO AND OPENCV

## 17. Case Notes Module

Case Notes should support:

- Investigator observations.
- Witness statements.
- Evidence descriptions.
- Investigator actions.
- Procedural records.
- Interpretations.

Each note should preserve the distinction between observed, reported and inferred information.

Important fields and concepts:

- Author/source.
- Event time versus recorded time.
- References to photographs, evidence and other case records.
- Verification status.
- Revision history.

Notes should not be silently overwritten. Changes should preserve an audit trail.

## 18. Timeline Construction Module

The timeline is a chronological representation of recorded and reported events.

It is not an automatic definitive reconstruction of what happened.

The planned structure includes:

- Event ID.
- Description.
- Category.
- Event date and time.
- Time precision.
- Source/reference.
- People.
- Location.
- Verification status.
- Recorded-by and recorded-at information.
- Revision history.

It must preserve uncertainty and conflicting accounts.

Do not force approximate times into exact timestamps. Do not invent missing events. Do not silently resolve conflicting sources.

The timeline should be traceable to its source records.

## 19. YOLO Module

YOLO is intended to generate candidate detections from uploaded photographs.

It does not independently establish that an object is forensic evidence.

The intended behaviour is:

- Candidate detection.
- Investigator review.
- Confirmation, dismissal or unreviewed status.
- Dismissal reason.
- Evidence creation through investigator action.
- Traceability to original photographs.

Important decisions:

- Original photographs remain immutable.
- Annotated previews are stored separately.
- A detection is not an evidence record.
- An evidence item can link to multiple photographs and detections.
- A manual evidence-add path must exist for objects YOLO misses.
- Store model version, configuration and confidence threshold.
- A dismissal requires a reason.
- YOLO cannot establish ownership, forensic significance, chain of custody or whether a crime occurred.

The investigator, not the model, determines which detected objects become evidence records.

## 20. OpenCV spatial mapping

The initial mapping approach is a two-dimensional representation of a visible planar floor region.

The proposed technical process:

1. Identify four suitable points on the visible floor plane.
2. Use `cv2.getPerspectiveTransform`.
3. Apply `cv2.warpPerspective`.
4. Use `cv2.perspectiveTransform` for coordinate conversion.
5. Place evidence markers through investigator-selected positions.

This does not create a complete architectural floor plan.

### Calibration modes

Two concepts were distinguished:

- Relative rectification: produces a perspective-corrected representation without claiming real-world physical dimensions.
- Dimension-calibrated mapping: uses known physical measurements to establish a measurable scale.

Do not claim actual metric dimensions without calibration.

### Evidence placement

The investigator should select evidence positions on the rectified map.

A bounding-box bottom-center point can provide a rough initial estimate, but it is not automatically a reliable physical floor coordinate.

Elevated objects cannot be projected onto the floor using the same homography without additional geometric information.

### Data preservation

Store:

- Original photograph.
- Selected points.
- Homography.
- Dimensions.
- Calibration mode.
- Mapping method.
- Mapping status.

### Known limitations

- Planar-surface assumption.
- Occlusion.
- Floor visibility.
- Lens distortion.
- Manual point-selection errors.
- Elevated objects.
- Perspective and geometric uncertainty.

### UI direction

The mapping interface should provide:

- Original and rectified views.
- Interactive point selection.
- Preview and reset.
- Zoom and pan.
- Evidence markers.
- Calibration labels.

### Additional techniques discussed

SIFT/ORB feature detection, BF/FLANN matching, `findHomography` with RANSAC and image stitching were discussed as possible later techniques.

They are not mandatory requirements for the initial mapping implementation.

The recommended first approach remains a controlled, investigator-assisted planar transformation. More advanced reconstruction techniques should be justified by an actual requirement rather than added pre-emptively.

COLMAP was also mentioned as a possible later option, not a current requirement.

---

# PART VIII — EVALUATION FIXTURES

## 21. Fixture inventory

The established evaluation set contains 13 fixtures:

`C0, C1, C2, C3, C4, C5, C6, C7, C10, C11, C12, C13, C14`

C8 and C9 were deleted. They must not be restored.

The fixtures cover positive contradictions, clean cases, borderline cases, dismissed detections, uncertainty and spatial differences.

### Important fixture decisions

**C0**

- N3 no longer says "from her bag".
- Expected Tier A: A1 on `photos.P1.d3` and A6 on `timeline.T2`.
- No A3.
- Option 4 added `photos.P1.d4`, a dismissed cell-phone detection with confidence 0.77.
- P1.d3 remains unreviewed.
- D4 is a detection, not evidence.
- N3 describes Device D1 as a pink smartphone with a cracked screen, reported missing by the victim and not belonging to anyone at the residence.
- Expected Tier B contextual contradiction cites `notes.N3` and `photos.P1.d4`.

**C2**

A genuine spatial contradiction: the note places a knife near the main door, while the map places it near the window at the far end opposite the door.

**C3**

A genuine timeline contradiction:

- Note says police arrived at 21:40.
- T1 witness report says 21:40.
- T2 officer record says 22:10.
- The records refer to the same event.
- Expected Tier A is empty.
- Expected Tier B category is `timeline_contradiction`.
- Timeline date is 15 January 2026, synchronized with `incident_window`.

**C4**

Uses the same identified device D1:

- N4 says a pink smartphone with a cracked screen was observed on the kitchen counter.
- N4 says it does not belong to the victim.
- The victim's own white iPhone remains missing from her bag.
- P1.d3 is a dismissed cell-phone detection with confidence 0.83.
- Its reason identifies D1 as the victim's own device, accounted for.
- `rooms_covered` includes kitchen to avoid A7.

**C5**

A clean case with a footprint-toward-window note and no photograph reference. It should not produce a semantic coverage-gap suggestion. A9 has been removed.

**C11**

A clean borderline spatial case: note says knife near main door; map position is approximately 1.2 metres from the door.

**C12**

A clean borderline timeline case:

- Note says a sound was heard around 21:00.
- Timeline says approximately 21:05.
- A4 must not fire.
- Approximate wording must be preserved.

**C13**

A clean contextual case. The same identified D1 appears in a note and a dismissed detection, both consistent that it is victim-owned and accounted for. No contradiction should be generated.

**C14**

A second genuine spatial contradiction:

- E1 is a laptop.
- Photograph P1.
- Confirmed detection d1.
- Note places the laptop on a study desk next to a printer.
- Map places it near the balcony door, on the opposite side of the study.
- Expected category: `spatial_inconsistency`.

The remaining fixture expectations and exact JSON should be read from the current repository. This handbook is not a substitute for the fixture files.

## 22. Fixture philosophy

Fixtures are designed to test both positive and negative behaviour.

A model that produces suggestions for every case is not performing well. Clean cases must be able to return no suggestions.

Borderline cases exist to prevent over-detection.

A model must not be rewarded for inventing contradictions, treating approximate times as exact, or conflating similar objects.

Do not modify expected fixture results merely to make a model pass.

---

# PART IX — EVALUATION HARNESS

## 23. Purpose

The evaluation harness measures the actual production analytical pipeline using controlled fixtures.

It is not a separate mock implementation of the production analysis logic.

The evaluator uses:

```python
run_pipeline(case_context, config, case_id=case_id)
```

The harness dynamically discovers the 13 fixtures.

For each case, it evaluates the expected distinct Tier B categories. Clean fixtures are evaluated against all three categories.

## 24. Execution modes

The evaluator supports:

- Dry-run mode using `PipelineConfig(dry_run_llm=True)`.
- Stub mode using `StubLLMTransport` injected through `LLMClient` and `client_factory`.
- Live mode using `LLMClient()`.

The live mode must exercise the real provider adapter and production pipeline.

Do not bypass the semantic gate, prompt construction, validator or matching logic to obtain a better benchmark score.

## 25. Matching and scoring

Established matching logic:

- Tier A: match by rule and `about_ref`.
- Tier B: match by category and exact reference set, order-insensitive.
- Matching is one-to-one.
- Soft expected entries that are missed are not false negatives.
- A matched soft expected entry receives a bonus but is not a false positive.
- A validated Tier B suggestion on a clean fixture is a false positive.
- Zero-denominator metrics should be reported as N/A rather than silently marked PASS, except the existing rejection 0/0 case, which is reported as zero with an explanation.

The evaluator records:

- True positives.
- False positives.
- False negatives.
- Precision.
- Recall.
- Per-category results.
- Per-fixture results.
- Validator rejections and drop reasons.
- Provider errors.
- Request counts.
- Token usage.
- Latency.

## 26. Acceptance criteria and interpretation

The original internal analytical criteria are:

| Metric | Target |
|---|---:|
| Tier A recall | 1.00 |
| Tier B recall | >= 0.85 |
| Tier B precision | >= 0.85 |
| Clean-case false positives | 0 |

Tier A precision is informational.

These are internal fixture-benchmark criteria. They are not proof of real-world forensic reliability.

A 13-fixture benchmark is a controlled regression test, not a statistically representative evaluation of every possible crime-scene scenario.

### Important metric correction

The earlier evaluator used the name `hallucination_rate` for:

`rejected / received`

This measures validator rejection frequency. It does not directly measure actual model hallucination.

A validator can reject a structurally invalid suggestion, a type mismatch, an unresolved reference or a severity issue. Those are not all hallucinations.

The correct interpretation is **validator rejection rate**, with individual rejection reasons examined separately.

Do not claim that every rejected suggestion is a hallucination.

Do not impose a zero validator-rejection requirement without a justified reason. The current Prompt 12.2 document still contains a zero-valued "Hallucination/rejection rate" acceptance row, despite also instructing the executor not to classify every validator rejection as a hallucination. This is a known inconsistency requiring review after the current evaluation. Do not silently change the established scoring implementation.

### Latency

The original evaluation design included a median complete-case latency threshold of 6,000 ms.

The project owner subsequently decided to retire this threshold as a pass/fail criterion.

Latency remains important to measure, but analytical reliability is the priority.

Report separately:

- Individual provider request latency.
- Complete-case wall-clock latency.
- Cooldown time.
- Total benchmark duration.

Complete-case latency includes all required category requests, cooldown, validation and processing.

Do not confuse model inference latency with the time an investigator waits for the entire analysis to complete.

---

# PART X — LLM PROVIDERS AND MODEL SELECTION HISTORY

## 27. Provider-independent architecture

The LLM integration was designed to support multiple providers without making the analytical pipeline dependent on a particular SDK or API.

The provider adapters include:

- OpenAI.
- Gemini.
- Anthropic.
- OpenRouter.
- Groq.

The selected provider is configured through environment variables.

The Groq adapter uses an OpenAI-compatible HTTP interface through `httpx`; a Groq-specific SDK is not required.

The purpose of this architecture is to preserve the analytical engine while allowing the model provider to change.

## 28. Gemini history

The initial Gemini model was `gemini-2.5-flash`.

Live requests returned 404 errors indicating that the model was no longer available to new users. This did not provide evidence about model quality.

A migration to Gemini 3.x Flash was attempted. The requests returned 429 errors associated with the free-tier 20 requests/day quota.

The user reviewed the Google AI Studio quota dashboard.

Gemini remains an optional provider adapter. It was not selected as the production model for the live evaluation.

The SDK used was `google-genai`, not `google-generativeai`.

The SDK retry behaviour was investigated. The intended configuration was:

```python
retry_options={"attempts": 1}
```

For the Interactions API, the intended settings included:

```python
timeout=20.0
automatic_continuation=False
```

These decisions were made to prevent hidden SDK retries and uncontrolled request behaviour.

## 29. OpenRouter history

A dedicated OpenRouter provider was implemented.

Endpoint:

`https://openrouter.ai/api/v1/chat/completions`

It shares the OpenAI-compatible transport while retaining its own provider configuration.

`max_attempts` was added to the LLM call interface and validated strictly. Booleans, floats, strings, zero and negative values are rejected rather than silently accepted.

Mocked tests cover HTTP errors and connection failures.

A candidate model, `google/gemma-4-26b-a4b-it:free`, returned a 429 originating from Google AI Studio's shared upstream provider pool.

The response identified:

- Provider: Google AI Studio.
- `is_byok: false`.
- `limit_source: upstream_provider_shared_pool`.

This was not evidence that the user's OpenRouter account quota had been exhausted.

Other tested models:

| Model | Observed result |
|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 200; 12.45 seconds; clean exact match; retained as a backup candidate |
| `nvidia/nemotron-3.5-super-vl:free` | 200; 14.13 seconds; rejected |
| `dots-studio/dots-3-note-preview:free` | 200; 32.46 seconds; warning on `determine`; rejected |
| Gemini 3 Flash Preview | 200; 6.64 seconds; clean; limited 20 RPD quota |
| Groq GPT-OSS 120B | 200; positive limited sample; selected |

These are historical smoke-test observations, not a comparable comprehensive benchmark.

## 30. Groq selection

The selected production configuration is:

```env
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
```

Endpoint:

`https://api.groq.com/openai/v1/chat/completions`

The configuration uses `GROQ_API_KEY`, with the existing fallback mapping to `LLM_API_KEY`.

The model was selected after limited positive tests and practical provider availability considerations.

Previously observed performance figures varied substantially. One early limited sample suggested approximately 1.87 seconds, while a later diagnostic request took 21,070 ms. These numbers are not a reliable benchmark median.

Do not make claims about a fixed Groq latency based on those samples.

The historical free-tier limits discussed were 1,000 requests/day and 8,000 tokens/minute. These should be verified against the actual account and current provider limits rather than treated as permanent guarantees.

---

# PART XI — GROQ PACING AND CURRENT LIVE EVALUATION

## 31. Why the benchmark became a problem

The first full live benchmark attempted to process all 13 fixtures through the actual pipeline.

The evaluator was found to require approximately 29 category requests because clean fixtures also require all three Tier B categories to be checked.

The execution environment terminated the run at its 10-minute limit.

A separate diagnostic request succeeded but took approximately 21.07 seconds. That was one request, not a representative median.

The earlier pacing implementation used an 8-second delay, later discussed as 12 seconds in an audit. It was located in the category loop in `src/analysis/pipeline.py`:

```python
if idx > 0 and getattr(active_client.config, "provider", "") == "groq":
    time.sleep(12.0)
```

This was insufficient because it only applied between categories within one pipeline invocation.

The evaluator calls `run_pipeline` separately for each category. Each invocation contains one category, so the internal loop starts at index zero and bypasses the cooldown.

It also did not coordinate requests across fixture boundaries or separate pipeline invocations.

Concurrency greater than one would introduce additional risks.

The project owner decided that the solution should be simple and conservative rather than introducing a complex token-bucket system.

## 32. Current Prompt 12.2

The current executor prompt is titled:

**PROMPT 12.2 — CHECKPOINTED COMPLETE LIVE EVALUATION**

Its requirements are:

1. Implement incremental checkpointing in the existing evaluator.
2. Save each completed fixture's complete evaluation result immediately.
3. Preserve Tier A/Tier B results, rejected suggestions, drop reasons, API errors, request counts, token usage and latency.
4. Resume completed work without repeating completed API requests.
5. Associate checkpoints with provider, model, prompts, fixtures and evaluation configuration.
6. Stop if a checkpoint does not match the current configuration.
7. Preserve earlier reports and checkpoints.
8. Apply a minimum 20-second cooldown between consecutive Groq HTTP requests.
9. Put pacing at the LLM client/transport layer.
10. Apply it across pipeline invocations and fixture boundaries.
11. Keep it simple and thread-safe.
12. Keep concurrency exactly one.
13. Run all 13 fixtures using the actual production pipeline.
14. Preserve existing evaluation matching and scoring.
15. Measure provider latency, complete-case latency, cooldown time and total duration separately.
16. Generate the existing JSON and Markdown reports.
17. Do not modify fixtures, expected results, prompts, gates, validators or matching rules to improve scores.
18. Do not stage, commit or push.

Execution command:

```powershell
python evaluate.py --max-concurrency 1
```

The evaluation may span multiple execution sessions. Each session must resume from a verified checkpoint.

### Current task status

The project owner has stated that the executor is performing the tests.

**Do not assume the evaluation has completed. Do not start another evaluation. Do not issue a new implementation prompt until the executor's report has been received and reviewed.**

### Known inconsistency in Prompt 12.2

The prompt currently contains:

`Hallucination/rejection rate | 0`

as an acceptance criterion.

Elsewhere it says not to classify every validator rejection as a model hallucination.

This needs to be reconciled after the active task. The metric should not be misrepresented as actual hallucination rate. The project owner has already been advised that validator rejection is diagnostic and should be examined by reason.

The prompt also contains the phrase "an six-second response target", a grammatical typo. It does not affect execution.

The six-second latency threshold has been explicitly retired. Latency remains informational.

---

# PART XII — IMPLEMENTATION AND TEST HISTORY

## 33. Major completed work

### Validator and references

Implemented:

- `PROJECT_BRIEF.md`
- `src/analysis/refs.py`
- `scripts/check_refs.py`
- `src/analysis/tier_a.py`
- `src/analysis/validator.py`
- `tests/test_validator.py`

The validator's seven-check design and reference-resolution behaviour were reviewed and corrected.

Generic exact-reference Tier A suppression was removed.

Severity counts distinct evidence references.

### Pipeline and CLI

Implemented:

- `src/analysis/pipeline.py`
- `src/analysis/__init__.py`
- `analyze.py`
- `tests/test_pipeline.py`

The pipeline executes Tier A, semantic gating, category-specific LLM calls, validation and audit logging.

It supports sanitized context hashing and a CLI.

Semantic-gate refinements include:

- Contextual eligibility requires at least two relevant factual records across notes, timeline, detections and evidence.
- Spatial eligibility requires meaningful spatial claims, not merely two notes or object mentions.
- Timeline eligibility requires at least two time-bearing records across notes and timeline.
- Spatial patterns require locative prepositions and known location nouns.
- Spatial modifiers are bounded and exclude clause-forming terms.
- Contextual eligibility does not require a dismissed detection or a particular note/timeline combination.

The exact current implementation must be inspected before any modification.

### Evaluation harness

Implemented:

- `evaluate.py`
- `tests/test_evaluate.py`
- README evaluation documentation.

The harness uses the production pipeline and supports dry-run, stub and live modes.

It dynamically discovers the 13 fixtures.

### Provider integration

Implemented provider-independent support for:

- OpenAI.
- Gemini.
- Anthropic.
- OpenRouter.
- Groq.

OpenRouter has a dedicated adapter.

Groq uses the OpenAI-compatible HTTP transport.

### CI dependency fix

The GitHub Actions workflow was updated to install optional provider dependencies:

```yaml
pip install -e ".[all]"
```

A test failure had occurred because `tests/test_client.py` imported `google.genai.errors.APIError` even when the optional Google SDK was not installed.

The fix included:

- A fallback mocked APIError class in the test.
- `pytest.importorskip("google.genai")` for SDK-specific constructor tests.
- Moving the Google SDK import inside the actual client-construction path.
- Installing all optional SDK dependencies in CI.

### Historical test results

The project passed several progressively larger test suites. These are historical results, not proof of the current working tree's state:

| Stage | Reported result |
|---|---|
| Prompt 2.7 | 14 passed, 1 skipped |
| Prompt 3 validator development | 27 passed |
| Prompt 5 pipeline | 72 passed, 1 warning |
| Prompt 6 evaluator | 96 passed, 1 warning |
| OpenRouter integration | 131 passed, 1 warning |
| Prompt 11 offline suite | 136 passed, 1 warning |
| CI dependency-fix verification | 136 passed, 1 warning; simulated missing Google module subset 57 passed, 2 skipped |

Fixture and reference checks repeatedly reported 13 fixtures and 13 refs at later stages.

These figures must not be treated as the current test status. Always use the latest executor report.

---

# PART XIII — GIT AND CI

## 34. Repository

GitHub repository:

`kumarsiddharth05/crime_investigator`

GitHub Actions workflow:

`.github/workflows/ci.yml`

The workflow runs on pushes and pull requests targeting `main`.

It uses Python 3.11 and runs:

```bash
pip install -e ".[all]"
python scripts/check_fixtures.py
python scripts/check_refs.py
pytest -q
```

## 35. Branch protection

A direct push to `main` was rejected with GH013 because branch protection requires a pull request and the `Build & Test` status check.

The intended workflow is:

1. Work on a feature branch.
2. Review the diff.
3. Stage only approved changes.
4. Commit.
5. Push the feature branch.
6. Create a pull request targeting `main`.
7. Wait for CI.
8. Review the PR.
9. Merge only after approval and successful checks.

The user previously accepted this PR workflow.

A later audit reported:

- Branch: `feature/live-gemini-evaluation`
- Commit: `6b86f8a CI resolve`

However, the latest CI status could not be established because `gh run list` returned exit code 1.

An earlier CI run tested an older commit, `d3edef83ff66628fb18b29874f0998abfe9e3976`, and passed its checks. That does not establish that the latest changes passed CI.

Do not claim the latest CI is green without evidence.

## 36. Git discipline

The project owner wants manual Git control.

Do not automatically stage, commit or push.

Review `.gitignore`, `.env`, tracked files and staged diffs before any Git operation.

The `Misc/` directory was intended to be excluded. If already tracked, the proposed removal from Git tracking was:

```bash
git rm -r --cached Misc/
```

The local files should remain intact.

The `.env` and `.env.*` patterns are excluded in `.gitignore`. Credentials must never be placed in committed source files or reports.

The file `llm context.txt` was deliberately deleted. Do not restore it.

---

# PART XIV — FUTURE DEVELOPMENT ROADMAP

## 37. Next major module: YOLO

After the LLM module and its live evaluation have been reviewed and stabilized, move to the YOLO module.

The objective is to create a reliable candidate-detection workflow, not to claim forensic intelligence.

Start by inspecting the existing repository and identifying what is already implemented. Establish the current data contracts before writing new code.

The module must preserve original photographs, create separate annotated previews, store detection metadata and support investigator review.

Manual evidence creation must remain possible.

## 38. OpenCV module

Build the controlled planar mapping workflow described earlier.

Do not expand immediately into complex 3D reconstruction or image stitching.

First demonstrate that an investigator can select points, rectify a visible floor plane, place evidence markers and understand the calibration limitations.

## 39. Timeline module

Build source-backed event records with explicit time precision, uncertainty, verification and revision history.

The timeline must support conflicting accounts without forcing an artificial resolution.

## 40. Case Context module

Build the production context builder that converts database records into the exact structured context schema used by the LLM pipeline.

This module is particularly important because the current evaluation harness loads fixtures directly.

The integration must preserve stable references and ensure the production context has the same meaning and structure as the evaluated context.

## 41. Report Generation module

Generate structured, traceable case reports.

Reports should distinguish:

- Original observations.
- Reported statements.
- Confirmed evidence.
- Candidate detections.
- Investigator decisions.
- Timeline records.
- Spatial representations and their limitations.
- LLM-generated suggestions.
- Investigator review outcomes.

AI-generated material must never be presented as an independently established fact.

Report generation should use a structured document workflow and preserve source references.

## 42. Integration

Integration should verify that the modules exchange consistent records and references.

Important integration boundaries:

- Uploaded photograph → YOLO detection.
- Detection → investigator review.
- Investigator decision → evidence record.
- Evidence and photograph → spatial mapping.
- Notes and timeline → case context.
- Case context → LLM analysis.
- LLM output → validator and investigator review.
- All relevant case records → report generation.

The final integration phase should test the complete case workflow, including failure conditions and incomplete data.

## 43. Final UI

The user wants a menu-based application, not a chat-based application.

The interface should provide dedicated workflows for case management, photographs, detections, evidence, mapping, notes, timeline, AI analysis and reports.

The interface should make investigator decisions explicit and visible.

Avoid hiding important system states behind conversational interactions.

---

# PART XV — PROJECT-WIDE NON-NEGOTIABLES

## 44. Preserve established constraints

The following are explicit project constraints:

- No autonomous guilt determination.
- No unsupported forensic claims.
- No fabricated facts or evidence.
- No inference that a detection automatically represents evidence.
- No inference that a photograph establishes event sequence.
- No claim of accurate 3D geometry from a single photograph.
- No automatic resolution of conflicting witness statements.
- No conversion of approximate times into exact times.
- No speculative follow-up suggestions.
- No reintroduction of removed Tier B categories.
- No reintroduction of A9.
- No restoration of C8 or C9.
- No restoration of `llm context.txt`.
- No silent overwriting of investigator records.
- No unnecessary architectural redesign.
- No fixture manipulation to improve model scores.
- No bypassing the actual production pipeline during live evaluation.
- No unapproved Git operations.

## 45. What matters more than theoretical sophistication

The project owner wants a technically defensible, reliable end-to-end demonstration.

Prefer a small feature that works and can be explained over a sophisticated feature that cannot be validated.

Do not introduce distributed infrastructure, unnecessary abstractions, complicated concurrency systems, token-bucket frameworks or advanced reconstruction methods without an actual requirement.

A simple architecture with clearly defined data contracts is preferable to an elaborate architecture that is difficult to maintain.

---

# PART XVI — HOW TO CONTINUE FROM THIS HANDBOOK

## 46. First actions for the new AI collaborator

Do not immediately start changing code.

First, acknowledge and internalize the project purpose, current architecture, settled decisions and active evaluation state.

The project owner should provide the latest executor report for Prompt 12.2 when it becomes available.

Then:

1. Review the evaluation report and checkpoint state.
2. Determine whether all 13 fixtures completed.
3. Review analytical metrics separately from provider failures.
4. Examine validator rejection reasons rather than treating them all as hallucinations.
5. Confirm the actual Groq pacing behaviour and complete-case latency.
6. Identify only genuine outstanding defects.
7. Present a concise technical conclusion.
8. Propose the next necessary step based on the agreed roadmap.

Do not start YOLO implementation until the owner has reviewed the LLM evaluation and agreed that the module is ready to freeze.

## 47. Repository verification before future work

This handbook describes the project's known state as of 21 November 2026. It is a historical and architectural handover, not a live repository inspection.

Before any future implementation prompt, ask the executor for a focused inspection of the relevant files, current branch, working-tree state and existing tests.

Do not assume that file contents, branch names, test counts or configuration values have remained unchanged.

---

# FINAL INSTRUCTION TO THE AI COLLABORATOR

Treat this handbook as the project's accumulated context and decision history.

Your objective is not to agree with every previous decision blindly. Your objective is to preserve the reasoning behind those decisions, identify genuine defects when evidence appears, and make changes only when they serve the actual project requirements.

When something is unclear, distinguish between:

- An established requirement.
- An approved engineering decision.
- An implemented behaviour.
- A historical observation.
- A proposal that has not been approved.
- An unresolved issue.

Never present one category as another.

Maintain continuity across long conversations. When context becomes too large, create updated handover documents that preserve decisions, implementation status, unresolved issues and the reasons behind them.

Above all, **do not make the project owner repeatedly explain the same architecture, constraints or decisions.** The accumulated context is part of the engineering work and must be treated accordingly.


# PROJECT STATUS UPDATE — PROMPT 12.2 COMPLETE
## Live Evaluation of Groq `openai/gpt-oss-120b`
**Date:** 21 November 2026  
**Status:** Live evaluation completed; analytical acceptance criteria passed.  
**Next planned task:** Prompt 14 — Investigator Interaction Workflow Prototype.

## 1. Evaluation Completion

The first complete live evaluation of the selected production model was successfully completed.

| Configuration | Value |
|---|---|
| Provider | Groq |
| Model | `openai/gpt-oss-120b` |
| Evaluation mode | Actual production pipeline |
| Fixtures | All 13 |
| HTTP requests | 29 |
| Concurrency | 1 |
| Groq cooldown | 20 seconds between consecutive requests |
| Checkpointing | Atomic per-fixture and category-level checkpointing |
| Total benchmark duration | 762.49 seconds |
| Total tokens | 83,746 |

The evaluator completed all 13 fixtures without reported API errors or HTTP 429 responses.

## 2. Analytical Results

<badge color="success">PASS — Fixture acceptance criteria</badge>

| Metric | Result | Acceptance criterion |
|---|---:|---:|
| Tier A recall | 1.00 (3/3) | 1.00 |
| Tier A precision | 1.00 | Informational |
| Tier B recall | 1.00 (5/5) | >= 0.85 |
| Tier B precision | 1.00 | >= 0.85 |
| Clean-case false positives | 0 | 0 |
| Validator rejections | 0/5 | Diagnostic |
| API errors | 0 | No provider failures |

All five hard-expected Tier B findings were matched:

- 2 `contextual_contradiction`
- 2 `spatial_inconsistency`
- 1 `timeline_contradiction`

All three expected Tier A findings were detected.

No false positives were recorded across the seven clean fixtures: C5, C6, C7, C10, C11, C12 and C13.

No suggestions were rejected by the validator. The individual rejection counters were all zero.

## 3. Latency and Operational Results

| Metric | Result |
|---|---:|
| Median provider request latency | 22,626.6 ms |
| Minimum provider request latency | 538.6 ms |
| Maximum provider request latency | 72,102.9 ms |
| Median complete-case latency | 66,208.4 ms |
| Minimum complete-case latency | 1,655.4 ms |
| Maximum complete-case latency | 106,852.1 ms |
| Total cooldown wait | 425.21 seconds |
| Total benchmark duration | 762.49 seconds |

The former 6,000 ms median complete-case latency acceptance threshold was explicitly retired.

Latency remains informational and must not be labelled as a failed acceptance criterion.

Complete-case latency includes provider calls, cooldown, validation and processing. It represents the time required to complete the case analysis, not just model inference time.

The 20-second transport-layer cooldown produced zero observed rate-limit errors during this evaluation. This is a successful result for this execution, not a guarantee against all future provider rate limits.

## 4. Evaluation Artifacts

The executor reported the following paths:

- JSON report: `reports/eval_20261121_130243.json`
- Markdown report: `reports/eval_20261121_130243.md`
- Archived checkpoint: `reports/checkpoints/eval_checkpoint_20261121_130243.json`

These files should be preserved. Do not overwrite previous evaluation reports or checkpoints.

## 5. Reporting Qualifications

The report originally labelled the validator rejection metric as "Hallucination / Rejection Rate".

For future documentation, distinguish these concepts:

- Validator rejection rate: 0/5.
- Hallucination detector flags: 0.
- Independently adjudicated semantic hallucination rate: not separately established.

Zero validator rejections is a positive result, but it does not prove that every possible semantic hallucination was absent.

Similarly, zero HTTP 429 responses demonstrates that the limiter worked during this run, not that 20 seconds guarantees compliance with every possible TPM restriction.

The report also labelled the informational latency result as `FAIL`. This is inconsistent with the approved retirement of the six-second acceptance threshold. It should be interpreted as informational, not as an analytical failure.

## 6. Remaining Verification

The executor reported running the following offline verification commands:

```bash
pytest -q
python scripts/check_fixtures.py
python scripts/check_refs.py
pyrefly check
```

However, the final report did not include their actual outputs or exit statuses.

A focused read-only request is still required to obtain:

- Exact pytest result.
- Fixture validation result.
- Reference validation result.
- Pyrefly result.
- Confirmation that checkpoint/resumption tests passed.
- Confirmation that the working tree and evaluation artifacts remain intact.

Do not launch another live evaluation. Do not repeat completed API requests.

This is a reporting and verification requirement, not a reason to redesign the evaluator.

## 7. Prompt 13 Decision

Prompt 13 was intended as a conditional analytical correction stage if Prompt 12 identified confirmed defects.

The live evaluation identified no analytical defects requiring correction.

Therefore:

**Prompt 13 is skipped.**

Do not create unnecessary analytical changes merely to complete a numbered prompt.

## 8. LLM Analysis Module Status

The live evaluation has demonstrated that the selected model can satisfy the established analytical criteria across all 13 fixtures using the actual production pipeline.

The LLM Analysis Module is eligible for formal freeze after the remaining offline verification results are confirmed.

A freeze means:

- No further routine prompt or model changes.
- No unnecessary validator or semantic-gate redesign.
- No repeated provider-selection experiments.
- Only genuine bug fixes or necessary integration changes are permitted.
- Existing fixtures and expected results remain preserved.

The evaluation is a successful controlled fixture benchmark, not proof of general real-world forensic reliability.

## 9. Next Task — Prompt 14: Investigator Interaction Workflow Prototype

After the remaining verification is confirmed and the LLM module is frozen, proceed to Prompt 14.

The next task transitions from analytical correctness to investigator-facing workflow.

The prototype must preserve the separation between AI analysis and investigator decisions.

The established direction is:

- Menu-driven application workflow, not a chatbot.
- Investigator triggers analysis.
- Existing case context is passed into the analysis module.
- LLM suggestions are returned as structured findings.
- Findings are displayed with their source references.
- Investigator decisions are stored separately from original LLM suggestions.
- Review decisions retain an audit history.
- The application controls available actions.
- The LLM does not autonomously modify case records or decide the investigation outcome.

The response envelope previously discussed is:

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

The prototype should account for completed, empty, partial-success and failed analysis states.

Begin with mocked interactions and use one controlled live integration test after the workflow is verified.

## 10. Development Roadmap After Prompt 14

The established module sequence remains:

1. LLM Analysis Module — live evaluation completed; pending final offline verification and formal freeze.
2. YOLO Module.
3. OpenCV Module.
4. Timeline Construction Module.
5. Case Context Module.
6. Report Generation Module.
7. Integration testing.
8. Final menu-based UI.

Integration testing should continue incrementally while modules are built. Do not postpone all integration work until the final phase.

## 11. Coordinator Instructions

The next AI collaborator must:

- Preserve this evaluation result as an established milestone.
- Obtain the missing offline verification output without repeating the live evaluation.
- Avoid reopening settled LLM architecture decisions without evidence of a defect.
- Formally freeze the LLM module after verification.
- Proceed to Prompt 14 only after reviewing the current repository state.
- Inspect existing implementation before proposing changes.
- Produce focused, self-contained executor prompts.
- Preserve the project's established requirements and data contracts.
- Never stage, commit, push or merge without explicit authorization.

**Milestone conclusion:** The selected Groq model completed the first full 13-fixture live evaluation and achieved 1.00 Tier A recall, 1.00 Tier B precision and recall, and zero clean-case false positives. The project can now transition from model evaluation to the investigator interaction workflow once the outstanding offline verification results are confirmed.