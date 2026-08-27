# Repository Map

Read this when you need to find a path or an entrypoint. It explains locations,
not behaviour — behaviour lives in [`architecture.md`](architecture.md) and the
`services/*.md` files.

## Root

| Path | Role |
| --- | --- |
| `AGENTS.md` | Agent entry point and context router. |
| `README.md` | Runnable commands for every Compose lane. |
| `compose.yaml` | Baseline mock stack, `frontend`, and the `contract-tests` profile. |
| `compose.<name>.yaml` | One overlay per real service or runtime lane. |
| `.env.example` | Image tags and pinned model identifiers; copy to `.env`. |
| `.github/workflows/pr-contract-tests.yml` | CI: unit tests, mock E2E, and the OCR/classification/validation overlays. |

## `services/`

Each directory is one deployable image: FastAPI `app.py`, `requirements.txt`,
`Dockerfile`, and its own data assets. Workers are separate `command:` entries
built from the same image.

| Path | Entrypoints | Data assets |
| --- | --- | --- |
| `services/ocr/` | `app.py` (`/v1/ocr`) | — |
| `services/classification/` | `app.py` (`/v1/classify`), `worker.py` | `taxonomy.json` |
| `services/validation/` | `app.py` (`/v1/validate`, `PATCH /cases/{id}/supplemental-information`) | `registry.json` |
| `services/workflow/` | `app.py` (case API), `worker.py`, `routing_worker.py`, `orchestrator_worker.py` | `corpus.json`, `f04_pii_policy.json` |
| `services/llm/` | `app.py` (`/generate`, `/v1/generate`), `Dockerfile`, `Dockerfile.gguf` | — |

Pure-logic modules with no I/O, safe to read alone:
`services/workflow/correspondence.py` (F-04 selection, PII, draft guards),
`services/workflow/routing.py` (F-05 target and notification rules),
`services/workflow/orchestrator.py` (F-06 state derivation).

There is no `services/rag/`; see [`services/rag.md`](services/rag.md).

## `contracts/`

| Path | Role |
| --- | --- |
| `contracts/http/manifest.json` | Endpoint, method, request and response schema per boundary. Source of truth. |
| `contracts/schemas/*.schema.json` | JSON Schema Draft 2020-12 payload definitions. |
| `contracts/README.md` | Boundary table, shared envelope, versioning policy. |

Map of which service uses which schema: [`contracts.md`](contracts.md).

## `mocks/` and `scenarios/`

`mocks/server.py` is a single stdlib HTTP server; `MOCK_SERVICE` selects which
contract it answers, and it replays `scenarios/golden-scenarios.json`
(58 scenarios, keyed by `scenarioId` or a `doc-`-prefixed `documentId`).
`mocks/Dockerfile` builds the shared mock image used by all six baseline
services.

## `tests/`

Runs in its own container (`tests/Dockerfile`, `contract-tests` Compose service,
profile `tests`).

| Path | Scope |
| --- | --- |
| `tests/validate_contracts.py` | Manifest/schema consistency, 58-scenario invariant. |
| `tests/run_scenarios.py` | Default entrypoint; mock or real scenario E2E (`--mode`). |
| `tests/run_ocr_intake.py` | F-01 acceptance, including restart durability phases. |
| `tests/run_classification_intake.py` | F-02 real API plus durable worker acceptance. |
| `tests/run_validation_intake.py` | F-03 acceptance (`--phase jamba`, restart phases). |
| `tests/run_correspondence_intake.py` | F-04/F-05 real closure acceptance. |
| `tests/run_orchestration_intake.py` | F-06 negative review path acceptance. |
| `tests/run_llm_intake.py` | Real Jamba contract acceptance. |
| `tests/test_*.py` | CPU unit tests (`python -m unittest discover -s tests`). |

## `frontend/`

`src/Root.tsx` chooses a surface from `src/router.ts`: `Landing.tsx` (`/`),
`PetitionForm.tsx` (`/dilekce`), `PetitionThanks.tsx`, and `App.tsx`
(`/panel*`). `src/api.ts` is the only HTTP client; `vite.config.ts` (dev) and
`nginx.conf` (container) define the proxy paths and inject demo tokens.
`frontend/dist/` is build output — never edit it.

## `docs/` and `design/`

`docs/00_README.md` indexes this layer. `docs/tekno_agent_feature_pack/` holds
F-01…F-09 requirements plus `acceptance/*.feature`;
`docs/architecture/` and `docs/design/` hold the decision sessions;
`docs/ui-api-guide.md`, `docs/ui-feature-matrix.md`, `docs/ci.md`, and
`docs/service-implementation.md` are standalone guides.
`design/stitch_smart_doc_ai_analysis_drafting/` contains exported UI mockups
(`code.html`, `screen.png`) that informed `frontend/`, and is not built.

## `scripts/` and `.agents/`

`scripts/coreaigent.ps1` wraps Compose (`dev`, `integration`, `e2e`, `test`,
`logs`, `reset`, `validate`); `scripts/local-topologies.json` registers each
verified local closure and its acceptance runner;
`scripts/jamba-gguf-server.ps1` launches the pinned host llama.cpp server.
`.agents/` holds agent skill definitions and `tools/approval.py`, covered by
`tests/test_approval_cli.py`; it is not part of the product runtime.
