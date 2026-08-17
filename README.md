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
