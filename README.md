# CoreAIgent development harness

This repository starts with a contract-first local environment for the public-document workflow. It deliberately contains no business-service implementation: each team owns its implementation under `services/<service>/`.

Logical service names and addresses are permanent:

| Service | Address | Responsibility |
| --- | --- | --- |
| `ocr` | `http://ocr:8080` | document text extraction |
| `analysis` | `http://analysis:8080` | document analysis/classification/extraction |
| `rag` | `http://rag:8080` | regulation/knowledge retrieval |
| `llm` | `http://llm:8080` | structured generation |
| `workflow` | `http://workflow:8080` | draft, routing and final workflow result |

The initial boundaries above are the only assumptions made from the competition workflow. If the team chooses to merge or split one of them, change the corresponding contract before implementations are started.

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
