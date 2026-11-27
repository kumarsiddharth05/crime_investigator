# AI-Assisted Crime Scene Investigation and Evidence Analysis System

An investigator-oriented system for organizing crime-scene information, detecting visual objects, managing evidence, reconstructing spatial and temporal relationships, and identifying potential contradictions across case records.

The system combines deterministic processing, computer vision, structured data management, and LLM-assisted analysis. Investigative decisions remain strictly under human control.

## Project Status

| Component | Status | Contract Reference |
|---|---|---|
| **Module 1 — LLM Analysis Engine** | **FROZEN & VERIFIED** | [docs/LLM_MODULE_HANDOVER.md](docs/LLM_MODULE_HANDOVER.md) |
| **Module 2 — YOLO Detection & Evidence Management** | **FROZEN & VERIFIED** | [docs/YOLO_MODULE_HANDOVER.md](docs/YOLO_MODULE_HANDOVER.md) |
| **Module 3 — Spatial Mapping** | **NEXT** (OpenCV Planar Spatial Mapping) | [full _roadmap.md](full%20_roadmap.md) |
| Module 4 — Timeline Reconstruction | Planned | [full _roadmap.md](full%20_roadmap.md) |
| Module 5 — Case Context and Persistence | Planned | [full _roadmap.md](full%20_roadmap.md) |
| Module 6 — Report Generation | Planned | [full _roadmap.md](full%20_roadmap.md) |
| Module 8 — Investigator Application Interface | Planned | [full _roadmap.md](full%20_roadmap.md) |

*Module numbering follows the existing project roadmap. Module 7 is not currently defined in the approved module structure.*

## 4-Document Architecture

The project operates under a concise 4-document governance model:

| Document | Role |
|---|---|
| [README.md](README.md) | Permanent entry point, project status, core principles, and repository layout |
| [full _roadmap.md](full%20_roadmap.md) | Complete multi-module roadmap, sequence, and cross-module completion criteria |
| [PROJECT_BRIEF.md](PROJECT_BRIEF.md) | Active module specification (currently **Module 2 — YOLO Detection & Evidence Management**) |
| [PLAN.md](PLAN.md) | Living operational record, verified facts, active milestones, and decision ledger |
| [docs/LLM_MODULE_HANDOVER.md](docs/LLM_MODULE_HANDOVER.md) | Permanent frozen contract specification for Module 1 |
| [docs/YOLO_MODULE_HANDOVER.md](docs/YOLO_MODULE_HANDOVER.md) | Permanent frozen contract specification for Module 2 |

## Architecture

The project is organized as independent modules under `src/`:

- **LLM Analysis (`src/analysis/`, `src/llm/`, `src/workflow/`):** Deterministic structural checks and validated semantic contradiction analysis. (Module 1 — Frozen).
- **YOLO Detection (`src/yolo/`):** Candidate object detection, investigator review, and evidence management. (Module 2 — Frozen).
- **Spatial Mapping:** Spatial reconstruction and evidence positioning. (Module 3 — Next).
- **Timeline Reconstruction:** Structured event and temporal analysis. (Module 4 — Planned).
- **Case Context and Persistence:** Centralized database and structured context assembly. (Module 5 — Planned).
- **Report Generation:** Traceable report generation. (Module 6 — Planned).
- **Application Interface:** Integrated investigator desktop workflow. (Module 8 — Planned).

Modules communicate through defined data contracts (`schemas/case_context.schema.json`) rather than depending directly on one another's internal implementations.

## Repository Structure

```text
project/
├── src/
│   ├── analysis/          # Module 1 — rules engine, validator, pipeline (frozen)
│   ├── llm/               # Module 1 — multi-provider client, rate limiter (frozen)
│   ├── workflow/          # Module 1 — request/response envelopes, store, adapter (frozen)
│   └── yolo/              # Module 2 — candidate detection, review, evidence (frozen)
│
├── schemas/               # Shared data contracts (case_context.schema.json)
├── cases/                 # Case fixtures (C0–C7, C10–C14) and evaluation baselines
├── tests/                 # Automated test suites
├── scripts/               # Verification utilities (check_fixtures.py, check_refs.py)
├── reports/               # Evaluation and benchmark reports
├── docs/                  # Permanent module handover documents
│   ├── LLM_MODULE_HANDOVER.md
│   └── YOLO_MODULE_HANDOVER.md
│
├── PLAN.md                # Living operational record
├── PROJECT_BRIEF.md       # Active module specification (transitions to Module 3 next)
├── README.md              # Project entry point
└── full _roadmap.md       # Master roadmap
```

## Existing Module Baselines

The frozen modules maintain verified baselines:

- **Module 1 (LLM Analysis):** 163 passing tests, 13 valid case fixtures, 13 resolved references, 0 Pyrefly errors, live Groq evaluation completed (1.00 Tier A recall, 1.00 Tier B precision/recall). See [docs/LLM_MODULE_HANDOVER.md](docs/LLM_MODULE_HANDOVER.md).
- **Module 2 (YOLO Detection & Evidence Management):** 47 passing tests, 210 full project tests, 0 Pyrefly errors, verified CPU inference with `yolov8n.pt`, pure-stdlib EXIF parsing, separate Pillow previews, Draft-07 case context export, and verified Module 1 integration. See [docs/YOLO_MODULE_HANDOVER.md](docs/YOLO_MODULE_HANDOVER.md).

## Development Principles

1. Investigator decisions remain strictly authoritative.
2. Machine-generated detections are candidates, not established evidence.
3. Original photographs and source records remain immutable and read-only.
4. Every finding must be traceable to its source records via dotted references.
5. Modules communicate through explicit schema contracts without cross-module coupling.
6. Automated tests must execute completely offline without live external services.
7. Model outputs must pass validation gates before presentation.
8. No module independently determines guilt, intent, or criminal responsibility.

## Current Development Focus

- **Current Status:** Module 1 (LLM Analysis) & Module 2 (YOLO Detection & Evidence Management) are **FROZEN & VERIFIED**.
- **Next Active Module:** **Module 3 — OpenCV Planar Spatial Mapping**.
