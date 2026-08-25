# Approval Log

> Single file shared by the entire pipeline (`requirement-analysis`,
> `solution-architect`, and future stages). Exactly one active entry exists at
> a time, regardless of stage. Update it in place as decisions accumulate.

## Active Entry

- **Status**: Approved
- **Stage**: Implementation
- **Session Started**: 2026-08-25
- **Related Doc(s)**: approved `docs/design/DESIGN_c207e52_f06.md`; approved `docs/architecture/ARCHITECTURE_5a9d17f_f06.md`; `docs/implementation/IMPLEMENTATION_LOG.md`; `services/workflow/`; `tests/test_orchestrator.py`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Implements F-06 durable orchestration, case-state projection, PostgreSQL applicant notices, and demo USER/ADMIN read/completion endpoints.
  - Verifies both real local Jamba/BGE-M3/PostgreSQL flow and the required mock Docker baseline.
- **Open Questions Resolved This Session**:
  - None; all F-06 implementation decisions are covered by the approved design and architecture.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

---

## History

### Implementation — US-110 F-05 final routing and notifications

- **Status**: Approved
- **Stage**: Implementation
- **Session Started**: 2026-08-25
- **Related Doc(s)**: approved `docs/design/DESIGN_8c16689_f05.md`; approved `docs/architecture/ARCHITECTURE_f84cffd_f05.md`; `docs/implementation/IMPLEMENTATION_LOG.md`; `services/workflow/`; `tests/test_routing_service.py`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Implements F-05 PostgreSQL routing/job/notification entities, recovery, and current-revision read projection.
  - Verifies automatic F-04 routing plus real local BGE-M3/Jamba/PostgreSQL acceptance and the required mock baseline.
- **Open Questions Resolved This Session**:
  - None.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Implementation — US-109 F-04 regulation retrieval and official correspondence

- **Status**: Approved
- **Stage**: Implementation
- **Session Started**: 2026-08-25
- **Related Doc(s)**: approved `docs/design/DESIGN_0df0ad1_f04.md`; approved `docs/architecture/ARCHITECTURE_0df0ad1_f04.md`; `docs/implementation/IMPLEMENTATION_LOG.md`; `services/workflow/`; `tests/test_correspondence_service.py`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Implements US-109 F-04 regulation retrieval and official-correspondence generation as one ATDD pass.
  - Adds independently falsifiable threshold, PII, structured-output, size-limit, and no-source legal-claim coverage before HTTP/durable worker wiring.
- **Open Questions Resolved This Session**:
  - None.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Solution Architecture — US-109 F-04 regulation retrieval and official correspondence

- **Status**: Approved
- **Stage**: Solution Architecture
- **Session Started**: 2026-08-25
- **Related Doc(s)**: approved `docs/design/DESIGN_0df0ad1_f04.md`; `docs/architecture/ARCHITECTURE.md`; `docs/architecture/ARCHITECTURE_0df0ad1_f04.md`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Extends F-03's current case row with an F-04 pointer and revision-safe immutable generation/job/replay models.
  - Selects PostgreSQL leased worker, dynamic BGE-M3 corpus retrieval, PII projection, structured Jamba output, current-result semantics, and no-source guard.
  - Defines F-04 contracts, Docker/CI acceptance strategy, and updates Jamba capacity for the approved F-04 token budget.
- **Open Questions Resolved This Session**:
  - AQ-110 through AQ-114 — retrieval configuration/threshold, residual PII pipeline, budgets, no-current GET, and no-source guard.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Requirement Analysis — US-109 F-04 regulation retrieval and official correspondence

- **Status**: Approved
- **Stage**: Requirement Analysis
- **Session Started**: 2026-08-25
- **Related Doc(s)**: `docs/design/DESIGN.md`; `docs/design/DESIGN_0df0ad1_f04.md`; `docs/tekno_agent_feature_pack/04_legislation_and_official_correspondence.md`; `docs/tekno_agent_feature_pack/acceptance/f04_official_correspondence.feature`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Establishes F-04's dependency on F-02 current classification and F-03 `complete` validation state, separation of retrieval from Jamba draft generation, and prohibition on automatic external sending/approval.
  - Defines asynchronous case-level start/read, authorization, revision precondition, principal-scoped replay, local versioned corpus/citations, no-source review behavior, immutable generation history, PostgreSQL durable jobs, PII placeholders, structured output, retry, and F-03-not-ready rejection.
  - Resolves dynamic corpus policy and current terminal GET result shape from the feature-pack contract, extending only the approved lifecycle/source/result/citation fields.
- **Open Questions Resolved This Session**:
  - OQ-130 through OQ-138 — F-04 boundary, corpus/citations, no-source result, status/type model, immutable history/durable jobs, Jamba PII/structured output, not-ready behavior, dynamic corpus policy, and terminal result shape.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Implementation — US-108 F-03 information extraction and missing information

- **Status**: Approved
- **Stage**: Implementation
- **Session Started**: 2026-08-25
- **Related Doc(s)**: approved `docs/design/DESIGN_0df0ad1_f03.md`; approved `docs/architecture/ARCHITECTURE_0df0ad1_f03.md`; `docs/implementation/IMPLEMENTATION_LOG.md`; `services/validation/`; `compose.validation.yaml`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Implements the F-03 v3 validation-result contract, ten-type Demo Belediyesi field registry, hybrid rule/Jamba extraction boundary, PostgreSQL current-only validation state, and no-evidence public response.
  - Implements the separately addressed supplemental PATCH route with Bearer access, quoted ETag preconditions, PostgreSQL row locking, atomic idempotent replay, stale-revision protection, and retained prior valid values.
  - Adds real OCR/classification/worker/validation Docker acceptance, validation restart durability, CI wiring, runbooks, contract-compatible mocks, and the required 58-scenario baseline verification.
- **Open Questions Resolved This Session**:
  - None; all implementation questions were resolved by the approved F-03 design and architecture.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Solution Architecture — US-108 F-03 information extraction and missing information

- **Status**: Approved
- **Stage**: Solution Architecture
- **Session Started**: 2026-08-25
- **Related Doc(s)**: approved `docs/design/DESIGN.md`; approved `docs/design/DESIGN_0df0ad1_f03.md`; `docs/architecture/ARCHITECTURE.md`; `docs/architecture/ARCHITECTURE_0df0ad1_f03.md`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Models the versioned ten-request-type registry, hybrid rule/Jamba extraction, current-only PostgreSQL validation state, public confidence-only result, and exact missing/invalid predicates.
  - Selects a real validation service with an injected CPU test extractor, real Jamba GPU smoke, and a separate PATCH route hosted by the validation service.
  - Specifies the supplemental request headers/body, row-lock plus revision concurrency, idempotent replay ledger, error/no-mutation behavior, and contract/CI evolution.
  - Defines F-01-persisted `sourceMetadata.attachments[]` as the authoritative attachment-presence reference for required F-03 attachment fields.
- **Open Questions Resolved This Session**:
  - AQ-109 — use F-01-persisted `sourceMetadata.attachments[]` for attachment presence.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Requirement Analysis — US-108 F-03 information extraction and missing information

- **Status**: Approved
- **Stage**: Requirement Analysis
- **Session Started**: 2026-08-25
- **Related Doc(s)**: `docs/design/DESIGN.md`; `docs/design/DESIGN_0df0ad1_f03.md`; `docs/tekno_agent_feature_pack/03_information_extraction_missing_info.md`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Defines US-108's evolved existing validation boundary, versioned Demo Belediyesi registry scope, hybrid deterministic/Jamba extraction, PostgreSQL current-only authority, and the separate supplemental-information endpoint boundary.
  - Defines `missing_information` as absence of every usable required value and `invalid_information` as a present but schema-invalid value; both block F-04/F-05 final processing.
  - Defines public confidence-only output, PostgreSQL text lookup by document ID, and the supplemental PATCH contract with Bearer authorization, idempotency, ETag revision, and controlled error behavior.
- **Open Questions Resolved This Session**:
  - OQ-121 through OQ-129 — validation evolution, registry, hybrid extraction, current-only persistence, supplemental boundary, invalid distinction, public confidence, PostgreSQL text lookup, and PATCH contract.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Implementation — US-107 F-02 hierarchical classification

- **Status**: Approved
- **Stage**: Implementation
- **Session Started**: 2026-08-25
- **Related Doc(s)**: approved `docs/design/DESIGN.md` (US-107); approved `docs/architecture/ARCHITECTURE.md`; `docs/architecture/ARCHITECTURE_0df0ad1_f02.md`; `docs/implementation/IMPLEMENTATION_LOG.md`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Implements the versioned `Demo Belediyesi` taxonomy, hierarchical v3 classification API, PostgreSQL current-result table, and a separately running durable worker.
  - Updates the v3 contract boundary, mock compatibility layer, real OCR/classification/worker Docker overlay, CI job, and runbooks while retaining the mock baseline.
  - Verifies the strict score threshold, provisional/no-match review behavior, deterministic ties, taxonomy validation, and atomic persistence-before-completion with real PostgreSQL.
- **Open Questions Resolved This Session**:
  - None; all implementation details were previously approved.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Solution Architecture — US-107 F-02 hierarchical classification

- **Status**: Approved
- **Stage**: Solution Architecture
- **Session Started**: 2026-08-25
- **Related Doc(s)**: approved `docs/design/DESIGN.md` (US-107); `docs/architecture/ARCHITECTURE.md`; `docs/architecture/ARCHITECTURE_0df0ad1_f02.md`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Models the versioned `Demo Belediyesi` taxonomy, hierarchical v3 classification result, PostgreSQL current-result table, and claimed durable-job lifecycle.
  - Selects a deterministic demo scorer, a separate durable worker using the real classification image, atomic current-result/job completion, and a real-classification Docker/CI overlay while retaining the mock baseline.
  - Defines `needs_review` for both low-confidence and no-match results; valid provisional chains are shown, while no-match hierarchy fields are null.
- **Open Questions Resolved This Session**:
  - AQ-107 — a no-match result is `needs_review`; v3 does not emit `unclassified`.
  - AQ-108 — expose the valid best provisional chain; use null hierarchy fields when no candidate exists.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Requirement Analysis — US-107 F-02 hierarchical classification

- **Status**: Approved
- **Stage**: Requirement Analysis
- **Session Started**: 2026-08-25
- **Related Doc(s)**: `docs/design/DESIGN.md`; `docs/tekno_agent_feature_pack/02_hierarchical_classification.md`; `docs/tekno_agent_feature_pack/acceptance/f02_classification.feature`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Evolves the existing classification contract, adds a repository-owned versioned `Demo Belediyesi` taxonomy, and completes F-01 durable outbox-to-classification processing.
  - Uses `> 0.80` for `classified`, `<= 0.80` for `needs_review`, one current PostgreSQL result, and one highest-confidence chain without `topCandidates`.
- **Open Questions Resolved This Session**:
  - OQ-115 through OQ-120 — existing contract evolution, demo taxonomy, confidence/status threshold, current-only persistence, end-to-end durable execution, and one highest candidate.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Implementation — US-106 F-01 intake and durable state

- **Status**: Approved
- **Stage**: Implementation
- **Session Started**: 2026-08-25
- **Related Doc(s)**: approved `docs/design/DESIGN.md` (US-106); approved `docs/architecture/ARCHITECTURE_0df0ad1.md`; `docs/implementation/IMPLEMENTATION_LOG.md`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Implements the real `ocr` service with PostgreSQL-authoritative intake state and transactional durable outbox.
  - Migrates the repository contract graph, mocks, scenarios, and LLM adapter to schema `2.0`.
  - Adds real OCR/PostgreSQL Docker development and PR CI verification while retaining the mock-only baseline.
- **Open Questions Resolved This Session**:
  - None; all implementation details were specified in the approved design and architecture.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Solution Architecture — US-106 F-01 intake and durable state

- **Status**: Approved
- **Stage**: Solution Architecture
- **Session Started**: 2026-08-25
- **Related Doc(s)**: approved `docs/design/DESIGN.md` (US-106); `docs/architecture/ARCHITECTURE.md`; `docs/architecture/ARCHITECTURE_0df0ad1.md`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Upgrades the existing `POST /v1/ocr` contract graph to schema `2.0`; no second intake route is added.
  - Uses the existing required `documentId` as the idempotency key: equal immutable input replays the canonical result without duplicate state or jobs; changed immutable input is rejected with a non-retryable HTTP 409 error and no mutation.
  - Persists immutable original/normalized text, case/workflow identity, and one durable PostgreSQL outbox job atomically; recovery is database-driven after restart.
  - Applies source-safe NFC/control-character normalization and validates the exact 40-code-point minimum.
  - Adds PostgreSQL only to the real OCR development topology, leaving the baseline Docker mock contract suite deterministic and infrastructure-light.
- **Open Questions Resolved This Session**:
  - AQ-106 — operator chose rejection without mutation for changed input reusing a persisted `documentId`.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Requirement Analysis — US-106 F-01 intake with resolved requirements

- **Status**: Approved
- **Stage**: Requirement Analysis
- **Session Started**: 2026-08-25
- **Related Doc(s)**: `docs/design/DESIGN.md`; `docs/tekno_agent_feature_pack/01_document_intake.md`; `docs/tekno_agent_feature_pack/acceptance/f01_intake.feature`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Requirement-analysis update for US-106 after human resolutions to OQ-111–OQ-114.
  - Changes the existing `POST /v1/ocr` contract rather than adding an intake endpoint.
  - Defines idempotent replay, 40-character validation, PostgreSQL authoritative persistence, durable outbox, and restart recovery acceptance behavior.
- **Open Questions Resolved This Session**:
  - OQ-111 — change the existing intake contract.
  - OQ-112 — idempotent replay with no duplicate state or job.
  - OQ-113 — 40-character minimum.
  - OQ-114 — PostgreSQL source of truth plus durable job/outbox and restart recovery.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Requirement Analysis — US-106 F-01 intake scope before Open Question resolutions

- **Status**: Approved
- **Stage**: Requirement Analysis
- **Session Started**: 2026-08-25
- **Related Doc(s)**: `docs/design/DESIGN.md`; `docs/tekno_agent_feature_pack/01_document_intake.md`; `docs/tekno_agent_feature_pack/acceptance/f01_intake.feature`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Requirement-analysis pass for the first feature-pack delivery unit: F-01 document intake and normalization (US-106).
  - Recorded the mismatch between F-01's proposed input shape and the repository's fixed `document-input`/`/v1/ocr` boundary.
- **Open Questions Resolved This Session**:
  - None; OQ-111 through OQ-114 were subsequently resolved in the active requirement-analysis update.
- **Approved By**: Serda
- **Approval Date**: 2026-08-25

### Implementation — US-103 GPU and SSM-compatible runtime

- **Status**: Approved
- **Stage**: Implementation
- **Session Started**: 2026-08-17
- **Related Doc(s)**: `docs/design/DESIGN.md` (approved input); `docs/architecture/ARCHITECTURE.md`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Implementation pass: US-103 GPU and SSM-compatible runtime for the existing `llm` service.
  - Places Jamba in the existing `llm` Compose service and changes the real-service route to `/generate` per Issue #363 priority.
  - Defines liveness/readiness, singleton loader, serialized inference, error-envelope, cache/revision, and CUDA/SSM runtime predicates.
  - Selects the reference-derived CUDA 12.1 / PyTorch 2.5.1+cu121 / Mamba compatibility baseline with GPU smoke validation.
  - Selects a FastAPI/Uvicorn API process and a CPU-test-double/GPU-real-model verification split.
- **Pass Status**: Complete; branch `feature/llm-jamba-inference`
- **Open Questions Resolved This Session**:
  - OQ-102 — fixed `llm` service and `/generate` route.
  - OQ-103 — `/health` liveness plus `/ready` readiness semantics.
  - OQ-104 — CUDA-only production behavior and no-real-model CPU CI.
  - OQ-105 — reference-derived dependency compatibility strategy.
  - OQ-106 — pinned revision and persistent HF-cache model acquisition.
  - OQ-107 — minimal public prompt API and server-side generation configuration.
  - OQ-108 — HTTP status/error envelope mapping.
  - OQ-109 — loader test double as singleton proof.
  - OQ-110 — CPU CI/GPU smoke/final E2E verification split.
- **Approved By**: Serda
- **Approval Date**: 17.08.2026

### Requirement Analysis — US-102 Jamba2-3B-Turkish Docker inference API

- **Status**: Approved
- **Stage**: Requirement Analysis
- **Session Started**: 2026-08-17
- **Related Doc(s)**: `docs/design/DESIGN.md`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - GitHub Issue #363 / US-102 analysis, model identity, API, Docker/GPU,
    model-once lifecycle, error, test, and README scope.
  - OQ-102–OQ-110 were resolved by the human operator before architecture.
- **Open Questions Resolved This Session**:
  - OQ-102 through OQ-110 — resolutions recorded in `docs/design/DESIGN.md`.
- **Approved By**: Serda
- **Approval Date**: 17.08.2026 - 0555AM

### Implementation — US-102 Türkçe Jamba inference API

- **Status**: Approved
- **Stage**: Implementation
- **Session Started**: 2026-08-17
- **Related Doc(s)**: `docs/design/DESIGN.md`, `docs/architecture/ARCHITECTURE.md`, `docs/implementation/IMPLEMENTATION_LOG.md`
- **Requested By**: human operator
- **Decisions / Scope Covered**:
  - Implemented the fixed `llm` Jamba API, singleton loader, readiness/error behavior, and CUDA/SSM image.
  - Verified 10 US-102 acceptance tests, the runtime image build, GPU-unavailable health behavior, and the repository's 58-scenario mock suite.
- **Approved By**: Serda
- **Approval Date**: 17.08.2026
