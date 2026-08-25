# CoreAIgent development harness

This repository starts with a contract-first local environment for the public-document workflow. It deliberately contains no business-service implementation: each team owns its implementation under `services/<service>/`.

Logical service names and addresses are permanent:

| Service | Address | Responsibility |
| --- | --- | --- |
| `ocr` | `http://ocr:8080` | document text extraction |
| `classification` | `http://classification:8080` | document type and classification |
| `validation` | `http://validation:8080` | missing information detection |
| `rag` | `http://rag:8080` | regulation/knowledge retrieval |
| `llm` | `http://llm:8080` | structured generation |
| `workflow` | `http://workflow:8080` | draft, routing and final workflow result |

The initial boundaries above are the only assumptions made from the competition workflow. The document flow is `ocr -> classification -> validation -> rag -> llm`. If the team chooses to merge or split one of them, change the corresponding contract before implementations are started.

## Quick start

Docker Desktop must be running. The current repository starts deterministic
contract mocks, so the quick start works before any real service implementation
exists.

```powershell
Copy-Item .env.example .env
docker compose up --build -d
.\scripts\coreaigent.ps1 test mock
```

`docker compose up --build -d` builds and starts all mock services. The test
command validates the contracts and runs the golden scenarios against them.

## Docker test commands

The mock suite is the baseline Docker verification for this repository. It
starts the six contract mocks, waits for their health checks, validates the
JSON Schemas, and runs all 58 golden scenarios end to end. It does not require
real service implementations or the image variables in `.env`.

Run these commands from the repository root on Linux, macOS, or Windows with
Docker Desktop/Compose v2 available:

```bash
# Validate the resolved Compose configuration.
docker compose config --quiet

# Build and start the OCR, classification, validation, RAG, LLM, and workflow mocks.
docker compose up --build -d

# Run schema checks, invalid-request checks, and the 58-scenario mock E2E suite.
docker compose --profile tests run --build --rm contract-tests --mode mock

# Inspect service health or follow logs when troubleshooting.
docker compose ps
docker compose logs --follow --tail 100

# Stop the local stack and remove its Compose resources.
docker compose down --volumes --remove-orphans
```

The PowerShell wrapper provides the equivalent mock test command on Windows:

```powershell
.\scripts\coreaigent.ps1 test mock
```

To run the real local Jamba `llm` service, use the GPU/cache overlay. This is
separate from the mock baseline:

```bash
export HF_CACHE_DIR=/media/serda/home_extra/hf-cache
docker compose -f compose.yaml -f compose.llm.yaml up --build -d llm
curl http://localhost:8085/health
curl http://localhost:8085/ready
```

The overlay builds `services/llm/Dockerfile`, uses the pinned
`linguai/Jamba2-3B-Turkish-SFT-v1` revision in `.env`, and keeps model weights
in the mounted HF cache. `/ready` remains
`503` until the GPU model is loaded.

To run the real PostgreSQL-backed OCR intake service, use its dedicated
development overlay. This replaces only `ocr`; the remaining services stay
deterministic mocks and must not be described as real implementations:

```bash
docker compose -f compose.yaml -f compose.ocr.yaml up --build -d
docker compose -f compose.yaml -f compose.ocr.yaml --profile tests run --build --rm --entrypoint python contract-tests /app/run_ocr_intake.py --phase all
docker compose -f compose.yaml -f compose.ocr.yaml down --volumes --remove-orphans
```

The second command verifies PostgreSQL persistence, equal-input idempotent
replay, changed-input HTTP 409, the 39/40/41 boundary, and the durable outbox.
For the restart predicate, run `--phase restart-create`, restart `ocr`, then
run `--phase restart-verify`. `scripts/coreaigent.ps1 dev ocr` and
`scripts/coreaigent.ps1 test development ocr` include the same overlay.

To run the real classification API and its durable PostgreSQL worker on top of
the real OCR intake, add the classification overlay. Classification is real in
this command; validation, RAG, LLM, and workflow remain deterministic mocks:

```bash
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml up --build -d
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml --profile tests run --build --rm --entrypoint python contract-tests /app/run_classification_intake.py
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml down --volumes --remove-orphans
```

The acceptance runner posts official-document text to real OCR, verifies the
evolved `POST /v1/classify` v3 response, and checks that the worker completes
the durable job only after writing the one current classification record. The
repository-owned `Demo Belediyesi` taxonomy returns `classified` only above
0.80; lower valid matches and no-match results remain `needs_review`.

To run the real PostgreSQL-backed F-03 validation service, retain the real OCR,
classification API, and durable worker, then add the validation overlay. This
CPU acceptance path injects the deterministic extractor explicitly; it tests
the real validation service and PostgreSQL persistence, but it is not a Jamba
inference run.

```bash
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.validation.yaml up --build -d
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.validation.yaml --profile tests run --build --rm --entrypoint python contract-tests /app/run_validation_intake.py
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.validation.yaml down --volumes --remove-orphans
```

To verify F-03 current state across a validation container restart, run
`/app/run_validation_intake.py --phase restart-create`, restart `validation`,
then run it again with `--phase restart-verify` before teardown.

In production extraction mode, set `EXTRACTOR_MODE=jamba` and run the real
`llm` Jamba overlay as well; validation calls its minimal `/generate` endpoint.
`/ready` reports 503 if PostgreSQL, the registry, or the configured Jamba
dependency is unavailable.

Pull requests run this same Docker mock suite automatically in GitHub Actions;
see [the PR workflow](.github/workflows/pr-contract-tests.yml).

When a real service implementation exists under `services/<service>/`, use the
following workflows:

```powershell
# After services/ocr/Dockerfile exists
.\scripts\coreaigent.ps1 dev ocr
.\scripts\coreaigent.ps1 test development ocr

# Local OCR, all other services pinned stable images
.\scripts\coreaigent.ps1 integration ocr
.\scripts\coreaigent.ps1 test integration ocr

# Every service uses its immutable real image
.\scripts\coreaigent.ps1 e2e
.\scripts\coreaigent.ps1 logs
.\scripts\coreaigent.ps1 reset
```

`dev <service>` starts the selected local implementation and contract-compatible deterministic mocks for all other application services. `integration <service>` keeps that local implementation but swaps the other services for the SHA-pinned images in `.env`. `e2e` uses only those images. Service hostnames never change.

Test scope is intentionally limited: service-owned unit tests, JSON Schema contract checks, the one-real-service development harness, local-plus-stable-image integration, and all-real E2E. Mock runs compare deterministic scenario results; real-image runs assert contracts and structural workflow properties rather than exact LLM strings.

Until an implementation Dockerfile exists, `dev` and `integration` stop with a clear message rather than presenting a mock as a real service. The useful first check today is `docker compose up --build -d` followed by `.\scripts\coreaigent.ps1 test mock`.

See [contracts/README.md](contracts/README.md), [docs/service-implementation.md](docs/service-implementation.md), and [docs/ci.md](docs/ci.md).
