# CoreAIgent development harness

This repository provides a contract-first local environment for the
public-document workflow. The base Compose file is intentionally a deterministic
mock baseline; local PostgreSQL-backed implementations live under
`services/ocr`, `services/classification`, `services/validation`,
`services/workflow`, and `services/llm` and are enabled only by their explicit
overlays.

Logical service names and addresses are permanent:

| Service | Address | Responsibility |
| --- | --- | --- |
| `ocr` | `http://ocr:8080` | document text extraction |
| `classification` | `http://classification:8080` | document type and classification |
| `validation` | `http://validation:8080` | missing information detection |
| `rag` | `http://rag:8080` | regulation/knowledge retrieval |
| `llm` | `http://llm:8080` | structured generation |
| `workflow` | `http://workflow:8080` | draft, routing and final workflow result |

The base contract graph is `ocr -> classification -> validation -> rag -> llm`.
The real F-04/F-05/F-06 implementation keeps the public `rag` contract intact
but runs local BGE-M3 retrieval and durable workflow work inside the `workflow`
overlay before calling `llm`. If the team changes a public boundary, it must
change the corresponding contract first.

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
The Web UI is available at `http://localhost:3000` and clearly labels this
baseline as deterministic mock mode.

## Web UI

`frontend/` contains the TypeScript product interface for the implemented case
contracts. It uses one API client for both mock and real-service Compose modes:

- text or pre-extracted OCR text intake through `POST /v1/ocr`;
- classification and validation through the existing v3 contracts;
- authorized case, correspondence, and routing polling;
- optimistic/idempotent supplemental information and review completion;
- reviewable correspondence drafts, regulation references, routing, and
  persisted-only notification status.

The browser never receives the fixed local demo bearer tokens. The local
frontend reverse proxy adds the USER or ADMIN demo credential for the exact
case route being called. This is still a demo access model, not production
authentication.

The repository has no public case-list endpoint, assignee model, employee
assignment endpoint, or priority contract. The UI therefore keeps only a
browser-local index of case IDs it created/opened and re-fetches each selected
case from the backend. It explicitly marks priority and personnel assignment
as unavailable instead of deriving them. See
[`docs/ui-feature-matrix.md`](docs/ui-feature-matrix.md) for the audited
backend/UI capability matrix.

For frontend-only development while the Compose services are already running:

```powershell
cd frontend
npm install
npm run dev
```

The development server opens on `http://localhost:5173` and proxies to the
documented host ports. Production verification is:

```powershell
cd frontend
npm test
npm run build
```

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

To run the real local Jamba `llm` service, pick the lane that matches the host
GPU. Both lanes serve the same pinned `ai21labs/AI21-Jamba2-3B` snapshot behind
the same HTTP contract, and both are separate from the mock baseline. Use one
overlay or the other, never both.

**NVIDIA lane (`compose.llm.yaml`)** — weights load in-process on CUDA:

```bash
export HF_CACHE_DIR=/media/serda/home_extra/hf-cache
docker compose -f compose.yaml -f compose.llm.yaml up --build -d llm
curl http://localhost:8085/health
curl http://localhost:8085/ready
```

The overlay builds `services/llm/Dockerfile`, uses the pinned `MODEL_ID` and
`MODEL_REVISION` from `.env`, and keeps model weights in the mounted HF cache.
`/ready` stays `503` until the GPU model is loaded.

**GGUF lane (`compose.llm.gguf.yaml`)** — for hosts whose GPU Docker cannot pass
into a Linux container, such as an AMD Radeon on Windows. A host-native
llama.cpp Vulkan server holds the weights and the container only adapts it, so
the image ships no torch and reserves no GPU. Start the host server first:

```powershell
.\scripts\jamba-gguf-server.ps1 -Root D:\coreaigent
```

The script downloads the pinned llama.cpp build and the pinned Q8_0 GGUF,
verifies both SHA-256 digests, refuses to serve an unpinned artifact, and then
serves `ai21labs/AI21-Jamba2-3B` on `http://0.0.0.0:8090`. It binds all
interfaces because containers reach it through `host.docker.internal`, and
llama-server has no authentication by default: keep the Windows firewall profile
on Private, or pass `-ApiKey <secret>` and set the same value as `LLAMA_API_KEY`
for the container. Then bring the lane up:

```bash
docker compose -f compose.yaml -f compose.llm.gguf.yaml up --build -d llm
curl http://localhost:8085/ready
```

The adapter refuses to start against a server that is loaded with any file other
than the pinned `GGUF_FILE`, and re-attaches on its own if the host server is
restarted, so start order between the two does not matter.

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

F-04 correspondence and the automatic F-05 route/notification flow run in the
same real PostgreSQL overlay. F-06 adds an `orchestrator-worker`: a complete
F-03 revision creates its own durable F-04 start job (one initial attempt plus
at most three 30-second cooldown retries), and PostgreSQL keeps the current
case projection. `CASE_ACCESS_TOKEN` is the sole demo `USER` token and
`CASE_ADMIN_TOKEN` the sole demo `ADMIN` token; this is intentionally not a
production login/RBAC system. F-04 completion creates a durable routing job;
the routing worker persists the target decision and two notification records
only—there is no external e-mail dispatch. This command uses the local pinned
Jamba and BGE-M3 artifacts, rather than a mock response:

```bash
export HF_CACHE_DIR=/media/serda/home_extra/hf-cache
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.llm.yaml -f compose.validation.yaml -f compose.validation.jamba.yaml -f compose.workflow.yaml up --build -d
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.llm.yaml -f compose.validation.yaml -f compose.validation.jamba.yaml -f compose.workflow.yaml --profile tests run --build --rm --entrypoint python contract-tests /app/run_llm_intake.py
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.llm.yaml -f compose.validation.yaml -f compose.validation.jamba.yaml -f compose.workflow.yaml --profile tests run --build --rm --entrypoint python contract-tests /app/run_validation_intake.py --phase jamba
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.llm.yaml -f compose.validation.yaml -f compose.validation.jamba.yaml -f compose.workflow.yaml --profile tests run --build --rm --entrypoint python contract-tests /app/run_correspondence_intake.py
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.llm.yaml -f compose.validation.yaml -f compose.validation.jamba.yaml -f compose.workflow.yaml --profile tests run --build --rm --entrypoint python contract-tests /app/run_orchestration_intake.py
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.llm.yaml -f compose.validation.yaml -f compose.validation.jamba.yaml -f compose.workflow.yaml down --volumes --remove-orphans
```

The full-local command overrides the CPU-only deterministic F-03 extractor
with the real Jamba extractor. It calls real OCR, classification, validation,
BGE-M3, Jamba, PostgreSQL workers, `GET /cases/{case_id}`, and
`GET /cases/{case_id}/routing`. It verifies automatic F-04 start, one
current-revision route, the active `diger` / `siniflandirilmamis` fallback for
`review_required`, USER/ADMIN response projections, idempotent reviewer
completion, and separately persisted applicant/target-unit Jamba
notifications. The second runner is the negative F-02 review path: it proves
no validation, F-04 start, or route is created while the case remains readable
from PostgreSQL. These are not the mock baseline.

On a host without an NVIDIA GPU, swap `-f compose.llm.yaml` for
`-f compose.llm.gguf.yaml` in every command above and start
`scripts/jamba-gguf-server.ps1` first; the closure is registered as
`workflow-gguf` in `scripts/local-topologies.json`. `HF_CACHE_DIR` is unused in
that lane because the host server owns the weights.

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

`dev <service>` and `test development <service>` resolve the selected
service's full local dependency closure from
[`scripts/local-topologies.json`](scripts/local-topologies.json), then run its
named real acceptance runner. The wrapper prints `real_local` for a complete
closure or `mixed_local` when an implementation is genuinely unavailable; the
latter is never presented as full E2E. `integration <service>` keeps one local
implementation but swaps the other services for SHA-pinned images in `.env`.
`e2e` uses only those images. Service hostnames never change.

Test scope is intentionally limited: service-owned unit tests, JSON Schema contract checks, the one-real-service development harness, local-plus-stable-image integration, and all-real E2E. Mock runs compare deterministic scenario results; real-image runs assert contracts and structural workflow properties rather than exact LLM strings.

Until an implementation Dockerfile exists, `dev` and `integration` stop with a clear message rather than presenting a mock as a real service. The useful first check today is `docker compose up --build -d` followed by `.\scripts\coreaigent.ps1 test mock`.

See [contracts/README.md](contracts/README.md), [docs/service-implementation.md](docs/service-implementation.md), [docs/ci.md](docs/ci.md), and the [UI API guide](docs/ui-api-guide.md).
