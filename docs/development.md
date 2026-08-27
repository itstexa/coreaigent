# Development

Read this for Compose modes, the one-real-service development model, and
verification. Exact command lines per lane live in
[`../README.md`](../README.md); replacing a mock with a real service is
[`service-implementation.md`](service-implementation.md); CI wiring is
[`ci.md`](ci.md).

## Two realities

`compose.yaml` starts six deterministic contract mocks (one image,
`MOCK_SERVICE` selects the contract) plus the frontend. It needs no real
implementation, no GPU, and no image tags in `.env`. Real implementations are
opt-in through overlays, and PostgreSQL only exists once `compose.ocr.yaml` is
included.

Never report a mock run as a real one. Mock responses carry
`X-CoreAIgent-Implementation: mock`, real ones carry `real`, and
`tests/run_scenarios.py` asserts the expected value per service.

## Mock baseline (default verification)

```bash
docker compose config --quiet
docker compose up --build -d
docker compose --profile tests run --build --rm contract-tests --mode mock
docker compose down --volumes --remove-orphans
```

This is the required check for changes to Compose files, contracts, mocks,
scenarios, or test code. It validates the schemas and replays all 58 golden
scenarios plus the mock case-UI contract. `.\scripts\coreaigent.ps1 test mock`
is the PowerShell equivalent.

## One-real-service development model

A developer can run their own service for real while every other service stays a
deterministic mock. `tests/run_scenarios.py --mode development --local <service>`
asserts `real` for the selected service and `mock` for the rest, so a partial
closure cannot be presented as E2E.

Verified closures are registered in `scripts/local-topologies.json` — compose
files, local services, and the acceptance runner per topology:

| Topology | Real services | Acceptance runner |
| --- | --- | --- |
| `ocr` | ocr | `run_ocr_intake.py --phase all` |
| `classification` | ocr, classification | `run_classification_intake.py` |
| `validation` | ocr, classification, llm, validation | `run_validation_intake.py --phase jamba` |
| `workflow` | ocr, classification, llm, validation, workflow | `run_correspondence_intake.py` |
| `llm` / `llm-gguf` | llm | `run_llm_intake.py` |
| `workflow-gguf` | same as `workflow`, GGUF lane | `run_correspondence_intake.py` |

`scripts/coreaigent.ps1 dev <service>` and `test development <service>` resolve
that closure. The wrapper prints `real_local` for a complete closure and
`mixed_local` when an implementation is genuinely missing.

## Overlay composition rules

- Overlays are additive and order-sensitive; every real overlay transitively
  needs `compose.ocr.yaml` for PostgreSQL.
- `compose.llm.yaml` (CUDA, in-container weights) and `compose.llm.gguf.yaml`
  (host llama.cpp server) are mutually exclusive.
- `compose.validation.yaml` runs the deterministic extractor;
  `compose.validation.jamba.yaml` switches it to the real Jamba extractor and
  makes `validation` depend on a healthy `llm`.
- `compose.workflow.yaml` adds the `workflow` API plus `correspondence-worker`,
  `routing-worker`, and `orchestrator-worker` from the same image.
- `compose.integration.yaml` replaces every service with a SHA-pinned image from
  `.env`; `dev`/`integration`/`e2e` refuse to run without them.

Service hostnames and ports never change between modes; see
[`architecture.md`](architecture.md#runtime-modes) for the mode list.

## Tests

| Layer | How to run |
| --- | --- |
| CPU unit tests | `python -m unittest discover -s tests -p 'test_*.py'` (needs `tests/requirements.txt`, `fastapi`, `httpx`) |
| Schema + dataset invariants | `tests/validate_contracts.py` (also called by the scenario runner) |
| Mock scenario E2E | `contract-tests --mode mock` |
| Real acceptance per feature | the `run_*_intake.py` runner for the topology |
| Frontend | `cd frontend && npm test && npm run build` |

Real-image runs assert contracts and structural workflow properties, not exact
LLM strings. Mock runs compare deterministic scenario results.

Restart-durability checks are explicit phases: run
`run_ocr_intake.py --phase restart-create`, restart the container, then
`--phase restart-verify` (same pattern for `run_validation_intake.py`).

## Configuration

Copy `.env.example` to `.env`. Names only — never commit values:

- Image tags: `OCR_IMAGE`, `CLASSIFICATION_IMAGE`, `VALIDATION_IMAGE`, `RAG_IMAGE`, `LLM_IMAGE`, `WORKFLOW_IMAGE`.
- Model pinning: `MODEL_ID`, `MODEL_REVISION`, `HF_HUB_OFFLINE`, `HF_CACHE_DIR`; GGUF lane adds `LLAMA_SERVER_URL`, `GGUF_FILE`, `LLAMA_API_KEY`.
- Generation budget: `MAX_NEW_TOKENS`, `TEMPERATURE`, `JAMBA_TIMEOUT_SECONDS`, `GENERATION_DEADLINE_SECONDS`.
- Demo tokens: `CASE_ACCESS_TOKEN` (USER), `CASE_ADMIN_TOKEN` (ADMIN) — set in the overlays, not authentication.
- Service-local: `DATABASE_URL`, `TAXONOMY_PATH`, `EXTRACTOR_MODE`, `WORKER_POLL_SECONDS`, `F04_RETRY_COOLDOWN_SECONDS`, `BGE_MODEL_REVISION`.

## CI

`.github/workflows/pr-contract-tests.yml` runs on every pull request: Python
unit tests, Compose config validation, the mock E2E suite, the OCR overlay
(including a real container restart), the classification durable-worker overlay,
and the validation current-state overlay with its restart fixture. GPU lanes are
not exercised in CI.
