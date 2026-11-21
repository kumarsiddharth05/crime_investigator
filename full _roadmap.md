# MASTER PROJECT ROADMAP
## AI-Assisted Crime Scene Investigation and Evidence Analysis System

## 1. Roadmap Objective

This document defines the development sequence for the complete AI-Assisted Crime Scene Investigation and Evidence Analysis System.

The project is developed as a collection of independent modules with explicit responsibilities and integration contracts.

The roadmap distinguishes:

- Completed and verified work.
- Current development.
- Planned modules.
- Future integration.
- Verification and release milestones.

A planned feature must not be described as implemented. A mocked integration test must not be described as successful real-model execution.

The objective is to develop the system incrementally while preserving the existing verified implementation.

---

# 2. Current Project Position

| Module | Name | Status |
|---|---|---|
| 1 | LLM Analysis Engine | Frozen and verified |
| 2 | YOLO Detection and Evidence Management | Architecture proposed; Y0 pending |
| 3 | Spatial Mapping | Planned |
| 4 | Timeline Reconstruction | Planned |
| 5 | Case Context and Persistence | Planned |
| 6 | Report Generation | Planned |
| 8 | Investigator Application Interface | Planned |

Module 7 is not currently defined in the approved architecture. Do not create a Module 7 implementation task without an approved specification.

## 2.1 Completed milestone — Module 1

Module 1 is frozen.

Its completed responsibilities include:

- Structured case-context input.
- Tier A deterministic rules A1–A8.
- Three Tier B semantic contradiction categories.
- Semantic eligibility gate.
- Category-specific LLM prompts.
- Multi-provider LLM abstraction.
- Selected Groq production configuration.
- Seven-stage response validator.
- Reference grounding.
- Analysis execution and audit persistence.
- Investigator interaction workflow prototype.
- Thirteen-fixture live evaluation.
- Offline test and integration verification.

The latest handover reports 163 passing tests, 13 valid fixtures, 13 successfully resolved fixture references, and a completed live evaluation.

The exact verification environment, benchmark artifacts, provider configuration, and known limitations are recorded in the Module 1 handover.

**Module 1 is not an active development track.** Reopen it only for a demonstrated defect, a genuine integration incompatibility, or an explicitly approved requirement.

---

# 3. Development Strategy

The remaining system should be developed in dependency-aware stages.

The broad sequence is:

```text
MODULE 1 — LLM ANALYSIS
        |
        | FROZEN
        v
MODULE 2 — YOLO DETECTION
        |
        v
MODULE 3 — SPATIAL MAPPING
        |
        v
MODULE 4 — TIMELINE RECONSTRUCTION
        |
        v
MODULE 5 — CASE CONTEXT AND PERSISTENCE
        |
        +-------------------------+
        |                         |
        v                         v
MODULE 1 — ANALYSIS          MODULE 6 — REPORTING
        |                         |
        +------------+------------+
                     |
                     v
            MODULE 8 — APPLICATION
```

This is the broad development dependency direction, not a requirement to finish every module completely before beginning the next.

Each module should establish and verify its own contracts. Integration should occur incrementally where dependencies permit.

## 3.1 Engineering principles

1. Preserve the frozen Module 1 implementation.
2. Build new modules under their own `src/` packages.
3. Inspect the actual repository before implementation.
4. Reuse existing contracts instead of inventing parallel formats.
5. Keep original source material immutable.
6. Separate machine output from investigator decisions.
7. Keep persistence ownership centralized in Module 5.
8. Use offline stubs for ordinary automated tests.
9. Do not introduce dependencies without inspecting compatibility.
10. Update `PLAN.md` at significant milestones.
11. Document verified behavior, not intended behavior, in executor handovers.
12. Keep module boundaries explicit.

---

# 4. Module 2 — YOLO Detection and Evidence Management

**Current status: Architecture proposed. Y0 is the next task.**

## 4.1 Objective

Build a computer-vision subsystem that ingests crime-scene photographs, performs pretrained YOLO object detection, records candidate detections, generates annotated previews, and supports investigator-controlled evidence management.

The core distinction is:

**Detection candidate ≠ confirmed evidence.**

The model identifies potential objects. The investigator reviews them. The system records both the machine prediction and the human decision.

## 4.2 Target architecture

Initial package:

```text
src/yolo/
├── __init__.py
├── __main__.py
├── models.py
├── store.py
├── detector.py
├── preview.py
├── service.py
├── exporter.py
└── exceptions.py
```

This structure is subject to Y0 repository inspection.

### Core entities

| Entity | Responsibility |
|---|---|
| `PhotoRecord` | Original photograph and integrity metadata |
| `DetectionRun` | Model and inference execution provenance |
| `DetectionCandidate` | Machine-generated object prediction |
| `EvidenceRecord` | Investigator-managed evidence item |
| `ReviewEvent` | Append-only investigator decision history |

## 4.3 Implementation stages

### Y0 — Read-only pre-design inspection

**Status: NEXT**

Objective: establish the actual repository constraints before implementation.

Inspect:

- Existing case-context JSON Schema.
- Representative case fixtures.
- Reference resolver.
- Tier A implementation.
- Module 1 pipeline and workflow conventions.
- Python packaging and import configuration.
- Existing image and file-storage dependencies.
- Python and installed package versions.
- Hardware and model compatibility.
- Existing tests and verification conventions.
- Current `PLAN.md` and handbooks.

Required outputs:

1. Exact schema mapping.
2. Exact reference-resolution behavior.
3. Actual A1, A2, A3, and A8 implementation behavior.
4. Existing storage and workflow conventions.
5. Dependency and hardware report.
6. Model candidates and compatibility findings.
7. Proposed internal data contracts.
8. Final `src/yolo/` architecture.
9. Integration risks.
10. Recommended Y1 implementation scope.

Restrictions:

- Read-only.
- No source changes.
- No dependency installation.
- No model downloads.
- No schema changes.
- No Git operations.

**Y0 exit condition:** Coordinator reviews the inspection report and approves the implementation specification.

### Y1 — Data contracts and immutable photo storage

Objective: establish the data foundation.

Implement:

- Internal data models.
- Photo ingestion.
- Image validation.
- SHA-256 calculation.
- Immutable original storage.
- Stable photo and detection identifiers.
- JSON/JSONL persistence.
- Append-only audit infrastructure.
- Safe file-path handling.
- Atomic writes where appropriate.

Required tests:

- Valid and invalid image ingestion.
- Missing and corrupt image handling.
- Original-file overwrite prevention.
- SHA-256 integrity.
- Identifier uniqueness.
- Restart-safe identifier allocation.
- Case isolation.
- Persistence and recovery behavior.

**Y1 exit condition:** original photographs are safely stored and their identity and integrity can be verified across application restarts.

### Y2 — Detector backend and model abstraction

Objective: introduce pretrained YOLO inference without coupling the entire application to Ultralytics.

Implement:

- Detector backend interface.
- Deterministic stub backend.
- Lazy-loaded Ultralytics backend.
- Detector configuration.
- Prediction extraction.
- Detection-run provenance.
- Structured inference errors.

Model selection must consider:

- Existing Python and PyTorch compatibility.
- Available CPU/GPU resources.
- Target-class vocabulary.
- Weight availability.
- Licensing.
- Performance requirements.

No custom training or fine-tuning in this stage.

Offline tests must not download weights or require network access.

**Y2 exit condition:** the detector abstraction works with deterministic stub predictions, and the real backend is isolated behind the same interface.

### Y3 — Image preparation and annotated previews

Objective: ensure predictions and visualizations remain geometrically consistent with the original photographs.

Implement:

- Image preparation.
- EXIF orientation handling.
- Dimension tracking.
- Resize and letterbox metadata.
- Bounding-box coordinate transformations.
- Boundary validation.
- Preview rendering.
- Separate preview storage.

Authoritative detection coordinates must refer to the original photograph.

Do not assume the bounding-box centre is a physical floor-contact point.

**Y3 exit condition:** coordinate tests pass and preview generation never modifies the original photograph.

### Y4 — Detection orchestration and candidate lifecycle

Objective: connect image ingestion, model inference, prediction processing, and persistence.

Implement:

- Detection-run orchestration.
- Candidate generation.
- Stable detection references.
- Empty-result handling.
- Rerun handling.
- Run-status recording.
- Failure handling.
- Prediction provenance.

A successful run producing zero candidates must be distinguishable from a failed run.

A rerun must not silently overwrite the original predictions from an earlier run.

**Y4 exit condition:** the complete mocked photograph-to-detection workflow passes integration tests.

### Y5 — Investigator review and evidence management

Objective: implement the human-in-the-loop review and evidence lifecycle.

Implement:

- Confirmation.
- Dismissal with mandatory non-empty reason.
- Append-only review events.
- Controlled review corrections.
- Promotion of confirmed detections.
- Multi-photo and multi-detection evidence associations.
- Manual evidence creation.
- Evidence revision history.
- Duplicate association prevention.

Rules:

- All candidates begin as `unreviewed`.
- No confidence threshold automatically confirms a candidate.
- Unreviewed and dismissed candidates cannot be promoted.
- Similar-looking objects are not automatically merged.
- Manual evidence does not require a YOLO prediction.
- Previous review decisions remain auditable.

**Y5 exit condition:** all valid and invalid review transitions are tested, and evidence can be managed independently of raw detector predictions.

### Y6 — Case-context exporter and Module 1 integration

Objective: make Module 2 outputs compatible with the existing analysis engine.

Implement:

- Case-context projection.
- Exact field mapping.
- Schema validation.
- Detection reference validation.
- Evidence relationship validation.
- Relevant Tier A integration tests.
- Module 1 pipeline compatibility tests.

Verify against the actual implementation of:

- `schemas/case_context.schema.json`
- `src/analysis/refs.py`
- `src/analysis/tier_a.py`
- `src/analysis/pipeline.py`

Specific attention:

- A1: unreviewed candidates.
- A2: dismissed candidates with missing reasons.
- A3: note/object-class/evidence relationships.
- A8: confirmed evidence without map positions.

Module 2 must not modify the frozen Module 1 source code to accommodate its internal models.

**Y6 exit condition:** exported context passes the actual schema, reference resolver, and relevant Module 1 integration tests.

### Y7 — CLI and controlled real-model inference

Objective: provide an initial operational interface and verify actual model execution.

Implement:

- Deterministic CLI.
- Photograph registration.
- Detection execution.
- Candidate listing.
- Investigator review.
- Evidence promotion.
- Manual evidence creation.
- Case-context export.
- Integrity verification.
- History inspection.

The CLI must call the service layer. Business logic must not exist exclusively in menu handlers.

Run offline tests independently of real model execution.

A real pretrained-model smoke test requires explicit authorization if it involves installing dependencies or downloading weights.

Record:

- Model and weight identifier.
- Inference settings.
- Input image dimensions.
- Detected candidates.
- Bounding-box coordinates.
- Preview output.
- Runtime.
- Original-image SHA-256 before and after processing.

**Y7 exit condition:** offline tests pass and one controlled real-model inference succeeds with verified image integrity.

### Y8 — Model evaluation, documentation and freeze

Objective: complete Module 2 verification and prepare downstream integration.

Evaluate a documented, controlled set of representative photographs.

Measure:

- Per-class precision.
- Per-class recall.
- False positives.
- False negatives.
- Detection workload per photograph.
- Confidence distribution.
- Inference latency.

A small validation set is an engineering baseline, not proof of general forensic accuracy.

Produce:

- `docs/YOLO_MODULE_HANDOVER.md`
- Updated `PLAN.md`
- Updated Executor Handbook.
- Model configuration and provenance.
- Evaluation report.
- Test report.
- Integration contract.
- Known limitations.
- Final freeze verdict.

**Y8 exit condition:** all approved acceptance criteria are supported by verification evidence, the complete project test suite passes, and the handover accurately reflects the implementation.

## 4.4 Module 2 acceptance criteria

| ID | Requirement |
|---|---|
| M2-01 | Dedicated `src/yolo/` package |
| M2-02 | Module 1 remains untouched |
| M2-03 | Original photographs immutable |
| M2-04 | SHA-256 integrity verification |
| M2-05 | Pretrained detector backend |
| M2-06 | Model provenance recorded |
| M2-07 | Stable detection references |
| M2-08 | Original-image coordinate accuracy |
| M2-09 | Separate annotated previews |
| M2-10 | Every candidate starts unreviewed |
| M2-11 | Investigator-controlled confirmation |
| M2-12 | Mandatory dismissal reason |
| M2-13 | Append-only review history |
| M2-14 | Confirmed detection promotion |
| M2-15 | Manual evidence creation |
| M2-16 | Multi-photo evidence association |
| M2-17 | Evidence revision history |
| M2-18 | Schema-valid case-context export |
| M2-19 | Module 1 reference and Tier A compatibility |
| M2-20 | Module 3 geometric integration readiness |
| M2-21 | Module 5 persistence integration readiness |
| M2-22 | Offline automated test suite |
| M2-23 | Controlled real-model inference |
| M2-24 | Documented model evaluation |
| M2-25 | Complete handover and updated project records |

---

# 5. Module 3 — Spatial Mapping

**Status: PLANNED**

## 5.1 Objective

Develop a subsystem that represents and reconstructs spatial relationships between crime-scene photographs, scene geometry, and evidence locations.

## 5.2 Expected responsibilities

- Scene coordinate-system definition.
- Image-to-scene geometric relationships.
- Physical reference-point handling.
- Floor-plan or scene-plane representation.
- Evidence positioning.
- Investigator-adjustable spatial anchors.
- Spatial relationship calculations.
- Spatial summaries compatible with the case-context contract.

## 5.3 Dependencies

Module 3 consumes suitable outputs from Module 2:

- Original photograph references.
- Original image dimensions.
- Bounding boxes.
- Detection references.
- Investigator-provided anchor points where supported.

Module 3 owns spatial transformations and physical-position calculations.

## 5.4 Development stages

The detailed implementation plan must be created after inspecting the actual image inputs, available calibration assumptions, and intended scene geometry.

Expected stages:

1. Read-only inspection and geometric design.
2. Coordinate-system and scene models.
3. Image geometry and reference-point handling.
4. Spatial transformation and mapping.
5. Evidence-position integration.
6. Case-context exporter.
7. Controlled spatial verification.
8. Documentation and freeze.

## 5.5 Completion conditions

- Coordinate systems are explicitly defined.
- Spatial transformations are tested.
- Physical reference points are traceable.
- Evidence positions are not fabricated.
- Investigator adjustments are preserved.
- Exported data satisfies the approved case-context contract.
- Integration with Module 2 and Module 5 is verified.

---

# 6. Module 4 — Timeline Reconstruction

**Status: PLANNED**

## 6.1 Objective

Create structured temporal records from investigator-provided and other approved case information.

## 6.2 Expected responsibilities

- Event records.
- Event descriptions.
- Time expressions.
- Source references.
- Temporal normalization where justified.
- Uncertainty preservation.
- Event ordering.
- Timeline validation.
- Case-context export.

## 6.3 Development stages

1. Read-only inspection of the existing timeline contract.
2. Event data-model design.
3. Event ingestion and source tracking.
4. Temporal normalization and uncertainty handling.
5. Ordering and validation.
6. Case-context exporter.
7. Module 1 integration tests.
8. Documentation and freeze.

## 6.4 Completion conditions

- Timeline entries follow the existing schema.
- Every required source is preserved.
- Missing and uncertain timestamps are represented honestly.
- Temporal normalization is deterministic and tested.
- Module 1 can consume the resulting timeline.
- No unsupported event or timestamp is fabricated.

---

# 7. Module 5 — Case Context and Persistence

**Status: PLANNED**

## 7.1 Objective

Build the central persistence and case-context assembly subsystem.

Module 5 owns the eventual durable case state.

## 7.2 Responsibilities

- SQLite database design.
- Case and record persistence.
- Photo metadata and storage references.
- Detection and evidence relationships.
- Investigator review history.
- Spatial records.
- Timeline records.
- Case-level data validation.
- Reference integrity.
- Schema-version handling.
- Case-context construction.
- Context-size and token-budget management.
- Data migration.

## 7.3 Architectural boundary

The database model must remain distinct from the public `case_context` JSON representation.

Module 1 continues to receive validated structured context. It must not become coupled to SQLite or ORM internals.

Module 2's prototype JSON/JSONL store should be replaceable by the Module 5 persistence implementation without rewriting its business logic.

## 7.4 Development stages

1. Read-only inspection of existing module data contracts.
2. Database and entity relationship design.
3. SQLite schema and migration foundation.
4. Persistence adapters for module records.
5. Case-level relationship and reference integrity.
6. Case-context assembly.
7. Schema validation and token budgeting.
8. Integration with Modules 1–4.
9. Migration, recovery, and persistence tests.
10. Documentation and freeze.

## 7.5 Completion conditions

- Persistent case data is reliable.
- Module relationships are preserved.
- References resolve.
- Data migrations are controlled.
- Case context validates against the shared schema.
- Module 1 consumes the generated context without database dependencies.
- Existing module behavior remains intact.

---

# 8. Module 6 — Report Generation

**Status: PLANNED**

## 8.1 Objective

Generate structured, traceable investigator-facing reports from the system's validated records.

## 8.2 Responsibilities

- Report structure and templates.
- Case metadata presentation.
- Evidence summaries.
- Photograph and preview inclusion.
- Spatial and timeline information.
- Tier A deterministic findings.
- Tier B validated suggestions.
- Investigator review decisions.
- Source references.
- Generation metadata and provenance.

## 8.3 Important presentation rules

Reports must distinguish:

- Original source records.
- Machine-generated detections.
- Investigator-confirmed detections.
- Manually created evidence.
- Deterministic structural findings.
- LLM-generated validated suggestions.
- Investigator review decisions.

A model-generated suggestion must never be presented as an established forensic conclusion.

## 8.4 Development stages

1. Report requirements and document structure.
2. Input-contract inspection.
3. Report data model.
4. ReportLab generation.
5. Image and evidence presentation.
6. Finding and review-state presentation.
7. Output validation and regression tests.
8. Documentation and freeze.

## 8.5 Completion conditions

- Reports are generated from structured records.
- Source references remain traceable.
- Machine and investigator outputs are clearly distinguished.
- Missing information is not fabricated.
- PDF generation is deterministic where practical.
- Report output is tested against representative cases.

---

# 9. Module 8 — Investigator Application Interface

**Status: PLANNED**

## 9.1 Objective

Integrate the completed modules into a coherent investigator-facing application.

## 9.2 Responsibilities

- Case dashboard.
- Case selection and navigation.
- Photograph ingestion and viewing.
- Detection review.
- Evidence management.
- Spatial visualization.
- Timeline visualization.
- Analysis execution.
- Finding review.
- Report generation.
- Application-controlled actions.
- User identity and permission integration when implemented.

## 9.3 Architectural principles

- UI components must not duplicate backend business logic.
- Module contracts remain the integration boundaries.
- The application controls navigation and available actions.
- The LLM cannot generate or control application actions.
- Investigator decisions are recorded through explicit application operations.
- UI state must not silently mutate original case records.

## 9.4 Development stages

1. UI architecture and workflow design.
2. Backend integration-contract inspection.
3. Case dashboard and navigation.
4. Photograph and detection review.
5. Evidence management.
6. Spatial and timeline visualization.
7. Analysis and finding review.
8. Report integration.
9. End-to-end application verification.
10. Documentation and release.

The specific frontend framework and API architecture should be confirmed during this module's design stage rather than assumed in advance.

---

# 10. Cross-Module Integration Milestones

Individual modules must be verified before being treated as integrated.

| Milestone | Integration | Expected result |
|---|---|---|
| I1 | Module 2 → Module 1 | YOLO outputs produce valid case-context records consumed by the frozen analysis engine |
| I2 | Module 2 → Module 3 | Detection geometry and investigator anchors are usable for spatial mapping |
| I3 | Module 3 → Module 5 | Spatial records persist and export correctly |
| I4 | Module 4 → Module 5 | Timeline records persist and export correctly |
| I5 | Modules 2–4 → Module 5 | Complete case context can be assembled and validated |
| I6 | Module 5 → Module 1 | Persisted cases can be analyzed through the existing interface |
| I7 | Modules 1–5 → Module 6 | Structured case information can produce traceable reports |
| I8 | Modules 1–6 → Module 8 | Investigator can operate the integrated application |

These milestones require their own tests and reports. Successful completion of an individual module does not automatically establish successful system-wide integration.

---

# 11. Project-Wide Quality Gates

Every module should pass the applicable quality gates.

## 11.1 Architecture gate

- Responsibilities are defined.
- Existing module boundaries are respected.
- Shared contracts are inspected.
- No unnecessary dependencies are introduced.
- No unauthorized changes to frozen modules.

## 11.2 Implementation gate

- Typed and validated internal models where appropriate.
- Explicit error handling.
- Deterministic business logic.
- Safe persistence behavior.
- Clear separation of I/O and business logic.
- No hidden external service dependencies in core operations.

## 11.3 Testing gate

- Unit tests.
- Invalid-input tests.
- Failure-path tests.
- Integration tests.
- Regression tests.
- Offline verification.

## 11.4 Documentation gate

- Module handover.
- Data contracts.
- Architecture and responsibility boundaries.
- Operational instructions.
- Verification commands and results.
- Known limitations.
- Updated `PLAN.md`.

## 11.5 Release gate

A module is ready for freeze only when its approved acceptance criteria have evidence.

A module's freeze status must be explicitly recorded as PASS or FAIL.

---

# 12. Project-Wide Exclusions and Future Scope

The current approved architecture does not establish the following capabilities:

- Automated determination of guilt.
- Automated identification of suspects.
- Facial recognition.
- Autonomous forensic conclusions.
- Legally certified chain-of-custody management.
- Automated forensic laboratory analysis.
- Custom YOLO training.
- Predictive criminal profiling.

These must not be introduced as assumed features of the existing project.

Potential future capabilities require separate design, legal and technical assessment, and explicit approval.

---

# 13. Current Execution Plan

Only the current authorized stage should be executed.

| Order | Task | Status |
|---|---|---|
| 1 | Preserve and maintain Module 1 freeze | Completed |
| 2 | Consolidate Module 2 architecture | Completed as proposed design |
| 3 | Execute Module 2 Y0 read-only inspection | Next |
| 4 | Review Y0 findings and approve final contracts | Pending |
| 5 | Implement Module 2 Y1–Y8 sequentially | Pending |
| 6 | Freeze and hand over Module 2 | Pending |
| 7 | Design and implement Module 3 | Future |
| 8 | Design and implement Module 4 | Future |
| 9 | Design and implement Module 5 | Future |
| 10 | Integrate and verify Modules 1–5 | Future |
| 11 | Design and implement Module 6 | Future |
| 12 | Design and implement Module 8 | Future |
| 13 | Perform full-system verification and release | Future |

Do not begin later stages merely because they appear in this document. Their implementation requires the relevant design and execution approval.

---

# 14. Immediate Next Task — Module 2 Y0

The next executor task is:

**MODULE 2 — STAGE Y0: READ-ONLY PRE-DESIGN INSPECTION**

The executor must inspect the real repository and produce an evidence-based report covering:

1. Exact case-context schema.
2. Exact reference resolver behavior.
3. Exact Tier A A1, A2, A3, and A8 implementation.
4. Existing workflow and storage conventions.
5. Python packaging and import conventions.
6. Installed dependencies and hardware.
7. Suitable pretrained model candidates.
8. Proposed Module 2 internal data contracts.
9. Integration requirements and risks.
10. Final Y1 implementation recommendation.

Restrictions:

- No implementation.
- No source modifications.
- No dependency installation.
- No model downloads.
- No schema changes.
- No Module 1 modifications.
- No `PLAN.md` or handbook modifications.
- No Git operations.

The report must distinguish verified facts, assumptions, and recommendations.

After review, the coordinator will approve the final Module 2 design and prepare the Y1 execution prompt.

---

# 15. Roadmap Maintenance Rules

This document describes the approved development direction. It is not a record of every implementation detail or every executor command.

Maintain the following separation:

- **PROJECT_BRIEF.md:** stable architecture, responsibilities, and contracts.
- **full_roadmap.md:** development stages and dependencies.
- **PLAN.md:** current state, active task, decisions, evidence, and next step.
- **COORDINATOR_HANDBOOK.md:** architectural decision history.
- **EXECUTOR_HANDBOOK.md:** verified repository facts and implementation conventions.
- **Module handover documents:** implementation details, tests, contracts, and limitations.

When a significant implementation milestone is completed, update the relevant roadmap and `PLAN.md` with the verified result.

Do not mark a task complete based solely on an executor's intention or a proposed design.

Do not rewrite historical decisions merely to make the current architecture appear cleaner. Preserve the distinction between what was originally planned, what was implemented, what was verified, and what was later changed.

---

# END OF MASTER PROJECT ROADMAP