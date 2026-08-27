# AGENTS.md

Read this file first, then load **only** the documents that
[Context Routing](#context-routing) names for your task. Do not read the whole
`docs/` tree.

## Project

CoreAIgent is a contract-first local system for Turkish public-document
(evrak) intake and official correspondence, built for the TEKNOFEST Türkçe
Yapay Zeka Dil Ajanları Yarışması 1st scenario. A citizen petition or official
document enters as text, is classified against a municipality taxonomy, checked
for missing/invalid information, enriched with local regulation retrieval,
turned into a reviewable official draft by a local Jamba model, routed to a
target unit, and exposed as a durable case projection over HTTP.

The repository ships **two runtime realities**. Base `compose.yaml` is a
deterministic contract-mock stack of six services; real PostgreSQL- and
model-backed implementations live under `services/` and are enabled only by
explicit Compose overlays. Never describe a mock run as a real one, and never
describe a partial overlay closure as full E2E.

Feature IDs `F-01`…`F-09` are used repository-wide and are the fastest way to
locate requirements; see `docs/tekno_agent_feature_pack/`.

## Repository Map

Details: [`docs/repository-map.md`](docs/repository-map.md)

- `services/` — real service implementations (`ocr`, `classification`, `validation`, `workflow`, `llm`). There is no `services/rag/`; see [Services](#services).
- `contracts/` — JSON Schema payloads plus the HTTP manifest; the cross-service source of truth.
- `mocks/` — one deterministic stdlib HTTP mock (`mocks/server.py`) serving every contract, selected by `MOCK_SERVICE`.
- `scenarios/golden-scenarios.json` — the fixed 58-scenario golden dataset the mock stack replays.
- `tests/` — schema validation, unit tests, and the real-overlay acceptance runners (`run_*_intake.py`).
- `frontend/` — React/TypeScript citizen portal and operator panel, served by nginx with the demo-token reverse proxy.
- `compose*.yaml` — base mock stack plus one overlay per real service or runtime lane.
- `scripts/` — PowerShell wrapper (`coreaigent.ps1`), host llama.cpp launcher, and the local dependency-closure registry.
- `docs/` — this documentation layer plus requirement, architecture, and design records.
- `design/` — exported Stitch UI mockups (HTML + PNG); reference material, not built code.
- `.agents/` — agent skill definitions and the approval CLI; unrelated to product runtime.

## Services

Logical service names, hostnames and ports are permanent. In-cluster every
service listens on `:8080`; host ports are `ocr` 8081, `classification` 8082,
`validation` 8083, `rag` 8084, `llm` 8085, `workflow` 8086, `frontend` 3000.

### ocr — F-01 intake and normalization

Path: `services/ocr/` · Overlay: `compose.ocr.yaml`
Purpose: accepts already-available text (`sourceType: text|ocr`), normalizes it,
decides the document language, and persists the intake record plus a durable
outbox job. It performs no image/PDF OCR.
Read: [`docs/services/ocr.md`](docs/services/ocr.md)

### classification — F-02 hierarchical classification

Path: `services/classification/` · Overlay: `compose.classification.yaml`
Purpose: scores normalized text against the repository-owned taxonomy and runs a
durable PostgreSQL worker that writes one current classification record.
Read: [`docs/services/classification.md`](docs/services/classification.md)

### validation — F-03 extraction and missing-information detection

Path: `services/validation/` · Overlays: `compose.validation.yaml`, `compose.validation.jamba.yaml`
Purpose: extracts candidate fields (deterministic or Jamba extractor), separates
missing from invalid information, and owns the case-level supplemental-information
patch with optimistic revisions.
Read: [`docs/services/validation.md`](docs/services/validation.md)

### workflow — F-04/F-05/F-06 correspondence, routing, case state

Path: `services/workflow/` · Overlay: `compose.workflow.yaml`
Purpose: local BGE-M3 regulation retrieval, structured Jamba draft generation,
deterministic unit routing, notification records, the case projection API, and
three durable workers (`worker.py`, `routing_worker.py`, `orchestrator_worker.py`).
Read: [`docs/services/workflow.md`](docs/services/workflow.md)

### llm — F-07 local Jamba inference

Path: `services/llm/` · Overlays: `compose.llm.yaml` (CUDA), `compose.llm.gguf.yaml` (host llama.cpp)
Purpose: serves the pinned `ai21labs/AI21-Jamba2-3B` snapshot behind a minimal
`/generate` endpoint and the contract `/v1/generate`.
Read: [`docs/services/llm-jamba.md`](docs/services/llm-jamba.md)

### rag — retrieval boundary, mock-only

Path: none. The `rag` contract exists and the mock serves it, but real retrieval
runs inside `services/workflow/worker.py` (BGE-M3 over `services/workflow/corpus.json`).
Read: [`docs/services/rag.md`](docs/services/rag.md)

### frontend — citizen portal and operator panel

Path: `frontend/`
Purpose: `/` landing, `/dilekce` petition portal, `/panel*` operator surfaces;
one API client for both mock and real modes, demo tokens injected by the proxy.
Read: [`docs/services/frontend.md`](docs/services/frontend.md)

## Critical Data Flow

Details: [`docs/data-flow.md`](docs/data-flow.md)

```text
frontend (/dilekce, /panel)
  → POST /v1/ocr           ocr             intake record + durable outbox job
  → POST /v1/classify      classification  one current classification record
  → POST /v1/validate      validation      accepted / missing / invalid fields
  → PATCH /cases/{id}/supplemental-information   (only while incomplete)
  → orchestrator-worker    workflow        auto-starts F-04 on a complete revision
  → correspondence-worker  workflow        BGE-M3 retrieval → llm /generate → draft
  → routing-worker         workflow        target unit + two notification records
  → GET /cases, /cases/{id}, /cases/{id}/correspondence|routing|document
```

The declared base contract graph is `ocr -> classification -> validation -> rag
-> llm`. The real overlay keeps the public `rag` contract shape but performs
retrieval inside `workflow` before calling `llm`.

## Contracts Are Source of Truth

Before changing any service boundary, inspect:

- `contracts/http/manifest.json` — endpoint, method, request and response schema per boundary.
- `contracts/schemas/*.schema.json` — JSON Schema Draft 2020-12 payloads.
- `contracts/README.md` — boundary table, shared envelope, and versioning rules.

Do not infer request/response structure from implementation when a contract
exists, and do not restate schema fields in Markdown — link the schema file.
Intake-graph payloads are `schemaVersion` 2.0; `classification-result` and
`validation-result` are 3.0. Producer/consumer map:
[`docs/contracts.md`](docs/contracts.md).

## Context Routing

Load the listed files, in order, and nothing else unless the task forces it.

**F-01 / OCR intake or normalization**
1. [`docs/services/ocr.md`](docs/services/ocr.md)
2. `contracts/schemas/document-input.schema.json`, `contracts/schemas/ocr-result.schema.json`
3. `services/ocr/app.py`, `tests/run_ocr_intake.py`

**F-02 / classification or taxonomy**
1. [`docs/services/classification.md`](docs/services/classification.md)
2. `contracts/schemas/classification-result.schema.json`, `services/classification/taxonomy.json`
3. `services/classification/app.py`, `services/classification/worker.py`

**F-03 / extraction, missing information, supplemental patch**
1. [`docs/services/validation.md`](docs/services/validation.md)
2. `contracts/schemas/validation-result.schema.json`, `contracts/schemas/supplemental-information-request.schema.json`, `services/validation/registry.json`
3. `services/validation/app.py`, `tests/run_validation_intake.py`

**F-04 correspondence, F-05 routing, F-06 case state**
1. [`docs/services/workflow.md`](docs/services/workflow.md)
2. `contracts/schemas/case-*.schema.json`, `contracts/schemas/correspondence-start-result.schema.json`, `contracts/schemas/review-completion-result.schema.json`
3. the matching module only: `correspondence.py` + `worker.py` (F-04), `routing.py` + `routing_worker.py` (F-05), `orchestrator.py` + `orchestrator_worker.py` (F-06)

**Retrieval corpus / RAG boundary**
1. [`docs/services/rag.md`](docs/services/rag.md)
2. `services/workflow/corpus.json`, `contracts/schemas/rag-request.schema.json`, `contracts/schemas/rag-result.schema.json`

**F-07 / Jamba or LLM runtime**
1. [`docs/services/llm-jamba.md`](docs/services/llm-jamba.md)
2. `services/llm/app.py`, `compose.llm.yaml` or `compose.llm.gguf.yaml`
3. `tests/test_jamba_runtime.py`, `tests/test_jamba_service.py`

**Any cross-service contract change**
1. [`docs/contracts.md`](docs/contracts.md)
2. `contracts/http/manifest.json` plus the affected `contracts/schemas/*.json`
3. the producer and consumer service docs
4. `tests/validate_contracts.py`, `tests/run_scenarios.py`, `mocks/server.py`

**F-08 / Docker, Compose, E2E, or a mock-vs-real question**
1. [`docs/development.md`](docs/development.md)
2. `compose.yaml` plus the specific overlay, `scripts/local-topologies.json`
3. `.github/workflows/pr-contract-tests.yml`

**Frontend / UI-backend integration**
1. [`docs/services/frontend.md`](docs/services/frontend.md)
2. `docs/ui-api-guide.md`, `docs/ui-feature-matrix.md`
3. `frontend/src/api.ts`, `frontend/vite.config.ts`, `frontend/nginx.conf`

**Adding a new service**
1. [`docs/architecture.md`](docs/architecture.md), `docs/service-implementation.md`
2. `contracts/http/manifest.json`, `scripts/local-topologies.json`
3. an existing overlay as the pattern (`compose.classification.yaml`)

**Requirements or acceptance criteria for a feature**
1. `docs/tekno_agent_feature_pack/README.md`, then the single `0N_*.md` file
2. `docs/tekno_agent_feature_pack/acceptance/*.feature`

## Development Rules

Repository-verified rules only. Commands and rationale:
[`docs/development.md`](docs/development.md).

- Services communicate over the contract boundary, never through another service's internals or private database tables.
- Logical service names, hostnames and ports are permanent; an overlay swaps the implementation behind a name.
- A boundary change starts in `contracts/`, then producer, consumer, mock, and tests. A breaking change requires a new schema version.
- Baseline verification for changes to Compose files, contracts, mocks, scenarios, or test code is the Docker mock suite in [README.md](README.md#docker-test-commands): `docker compose up --build -d`, then `docker compose --profile tests run --build --rm contract-tests --mode mock`.
- `dev`, `integration`, and `e2e` require real implementations or the SHA-pinned images in `.env`. A mock must never be presented as a real service, and an incomplete closure is reported as `mixed_local`, not E2E.
- Every real overlay depends on the PostgreSQL service defined in `compose.ocr.yaml`; durable state lives in PostgreSQL, not in service memory.
- `CASE_ACCESS_TOKEN` (USER) and `CASE_ADMIN_TOKEN` (ADMIN) are fixed demo tokens, not authentication. They stay behind the frontend reverse proxy and out of browser bundles.
- Model artifacts are pinned by revision or SHA-256 digest and load offline (`HF_HUB_OFFLINE=1`); do not add an unpinned or network-fallback model path.
- The golden dataset must stay at exactly 58 scenarios — `tests/validate_contracts.py` asserts it.
- Notifications are persisted records only; there is no SMTP/e-mail dispatch. Generated correspondence is a reviewable draft, never signed or dispatched.

## Source of Truth

```text
Contract / Schema   →   Implementation   →   Tests   →   Docs
```

When documentation contradicts code, the contract and implementation win. Do not
silently assume the document is correct: update the outdated document as part of
the change. Keep the requirement, architecture, contract, and implementation
layers distinct — cross-reference them instead of copying content between them.

## Documentation Index

This navigation layer, read on demand per [Context Routing](#context-routing):

- [`docs/00_README.md`](docs/00_README.md) — documentation map: which file answers which question.
- [`docs/architecture.md`](docs/architecture.md) — service boundaries, orchestration, persistence, runtime modes.
- [`docs/repository-map.md`](docs/repository-map.md) — path-level navigation and entrypoints.
- [`docs/data-flow.md`](docs/data-flow.md) — request lifecycle stage by stage with its contract.
- [`docs/contracts.md`](docs/contracts.md) — contract map: producer, consumer, purpose, source path.
- [`docs/development.md`](docs/development.md) — Compose modes, one-real-service model, tests, CI.
- `docs/services/*.md` — one file per service boundary.

Pre-existing records, indexed here rather than rewritten:

- [README.md](README.md) — runnable commands for every Compose lane.
- [`contracts/README.md`](contracts/README.md) — contract versioning rules.
- [`docs/tekno_agent_feature_pack/`](docs/tekno_agent_feature_pack/) — F-01…F-09 requirements and acceptance features (Turkish).
- [`docs/architecture/`](docs/architecture/) — architecture atlas and per-feature architecture sessions.
- [`docs/design/`](docs/design/) — design/requirements atlas and per-feature design sessions.
- [`docs/service-implementation.md`](docs/service-implementation.md) — replacing a mock with a real service.
- [`docs/ci.md`](docs/ci.md) — CI wiring · [`docs/ui-api-guide.md`](docs/ui-api-guide.md) — demo API guide · [`docs/ui-feature-matrix.md`](docs/ui-feature-matrix.md) — backend/UI capability matrix.
- [`docs/implementation/IMPLEMENTATION_LOG.md`](docs/implementation/IMPLEMENTATION_LOG.md), [`docs/APPROVAL_LOG.md`](docs/APPROVAL_LOG.md) — process history, not a source of truth for current behavior.

## Known inconsistencies

- `README.md` ("Web UI") and `docs/ui-feature-matrix.md` state that there is no public case-list endpoint, but `GET /cases` is declared in `contracts/http/manifest.json`, implemented ADMIN-only at `services/workflow/app.py:307`, and consumed by `frontend/src/api.ts:642`. Contract and implementation are current; those two documents are outdated on this point.
- This documentation layer lives in the existing `docs/` directory. The checkout is on a case-insensitive filesystem, so `Docs/` and `docs/` are the same directory and a separate `Docs/` tree cannot exist alongside it.
