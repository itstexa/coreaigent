# Design & Requirements Atlas

Central index of requirement-analysis output for this repository. Individual
sessions may split their work into `DESIGN_<commit-id>.md` files when this file
grows too large; every such file must be listed below.

## Linked Design Documents

| File | Scope / Topic | Started (commit) | Status |
|---|---|---|---|
| (this file) | Core; US-102 Jamba2-3B-Turkish Docker inference API | — | Active |

## Analysis Context

- Source request: [GitHub Issue #363](https://github.com/itstexa/coreaigent/issues/363),
  `[US-102] Jamba2-3B-Turkish Docker inference API oluştur`.
- The requested model identifier is `serda-dev/Jamba2-3B-Turkish`. Its model
  configuration declares `JambaForCausalLM`, `use_mamba_kernels: true`, and
  Transformers `4.57.6`.
- The local reference project `jamba-sft` uses CUDA 12.1 / PyTorch 2.5.1 and
  treats `mamba-ssm` plus `causal-conv1d` as preinstalled, compatibility-sensitive
  dependencies. Its inference loader uses `AutoModelForCausalLM`, sets
  `config.use_mamba_kernels`, and loads model artifacts once before serving.
- This repository currently has no implemented service directories. The Jamba
  implementation belongs to the existing fixed `llm` Compose service. Issue #363
  takes precedence over the previous `llm` endpoint shape, so its real API is
  `POST /generate`, not `/v1/generate`.
- Per `AGENTS.md`, any later Compose, contract, mock, scenario, or test change
  must run the documented Docker mock suite. A mock must not be presented as a
  real `jamba` service.

## User Stories

### US-102: Türkçe Jamba inference API

As a CoreAIgent demo operator
I want the fixed `llm` service to serve `serda-dev/Jamba2-3B-Turkish`
So that Turkish prompts can receive model-generated text without loading the
model for each request.

### US-103: GPU and SSM-compatible runtime

As an operator with an NVIDIA-capable Docker host
I want the Jamba service image to start with GPU access and compatible SSM
dependencies
So that the Jamba model can load and generate reliably in the demo runtime.

### US-104: Reproducible verification

As a maintainer
I want automated verification to distinguish deterministic API tests from
GPU/model smoke verification
So that routine tests remain runnable and the real Jamba integration is still
proved on suitable hardware.

### US-105: Operator documentation

As a demo operator
I want build, run, GPU, endpoint, and request examples documented
So that I can start and validate the real Jamba service without treating a mock
as an implementation.

## Gherkin Acceptance Criteria

Feature: Türkçe Jamba inference API

  Scenario: A loaded service generates text for a Turkish prompt
    Given the service process has loaded `serda-dev/Jamba2-3B-Turkish`
    When a client sends `POST /generate` with a JSON body containing a non-empty Turkish `prompt`
    Then it returns JSON containing `model` equal to `serda-dev/Jamba2-3B-Turkish`
    And it returns the generated text in `response`

  Scenario: A client checks the loaded service
    Given the model has finished loading in the service process
    When a client sends `GET /health`
    Then it returns JSON with `status` equal to `ok`
    And it returns `model` equal to `serda-dev/Jamba2-3B-Turkish`
    And it returns `model_loaded` equal to `true`

  Scenario: A process is alive but cannot accept inference
    Given the LLM process is running without an available GPU or ready model
    When a client sends `GET /health`
    Then it returns HTTP 200 without triggering generation
    When the client sends `GET /ready`
    Then it returns HTTP 503 with JSON error code `gpu_unavailable` or `model_not_ready`

  Scenario: The service cannot accept generation while not ready
    Given the LLM process has no available GPU or no loaded model
    When a client sends a valid `POST /generate` request
    Then it returns HTTP 503 with a JSON error response

  Scenario: A generation request omits the required prompt
    Given the service is running
    When a client sends `POST /generate` without a non-empty `prompt`
    Then the service rejects the request with a JSON error response
    And it does not invoke model generation

  Scenario: A client sends malformed JSON
    Given the service is running
    When a client sends malformed JSON to `POST /generate`
    Then it returns HTTP 400 with a JSON error response

  Scenario: Model generation raises an unexpected error
    Given the service is ready
    When model generation raises an unexpected error
    Then it returns HTTP 500 with a JSON error response

  Scenario: Sequential generation requests reuse the loaded model
    Given the model was loaded during service initialization
    When a client sends two sequential valid `POST /generate` requests to the same process
    Then both requests use the initialized model instance
    And the service does not load model weights again between those requests

Feature: GPU and SSM-compatible runtime

  Scenario: The real service runs with an available NVIDIA GPU
    Given a Docker host with a supported NVIDIA runtime and GPU access
    When the Jamba image is built and started with GPU access
    Then the service process can access the assigned GPU
    And it loads `serda-dev/Jamba2-3B-Turkish` with its required Jamba/SSM-compatible dependencies
    And `GET /health` reports that the model is loaded

  Scenario: The configured Jamba/SSM runtime dependencies are incompatible
    Given the image is built with a Jamba/SSM dependency combination that cannot load the model
    When the service starts
    Then it fails in a controlled, diagnosable way
    And it must not report `model_loaded` as `true`

Feature: Reproducible verification

  Scenario: CPU CI exercises API lifecycle behavior through an injected fake or tiny backend
    Given CPU-only CI is running the LLM service with an injected fake or tiny backend
    When its unit, contract, API, lifecycle, and Compose E2E tests run
    Then it verifies `/health`, a valid Turkish `/generate` request, and invalid-request JSON handling
    And it verifies that sequential requests do not trigger a second model load

  Scenario: GPU verification loads the pinned real model
    Given a GPU-capable verification environment with a pre-populated persistent HF cache
    When the GPU smoke test runs with the pinned `MODEL_ID` and `MODEL_REVISION`
    Then it verifies readiness and a real Turkish generation from Jamba2-3B-Turkish
    And it does not substitute a fake or tiny backend for the real-model result

Feature: Operator documentation

  Scenario: An operator follows the documented real-service workflow
    Given the repository documentation is available
    When an operator reads the Jamba service README
    Then it contains Docker build and run commands, GPU run instructions, endpoint descriptions, a curl request, and an example response

  Scenario: The documented environment cannot meet the selected runtime prerequisites
    Given the operator follows the Jamba service README on an unsupported or unprepared host
    When the operator starts the service or runs its verification command
    Then the documentation identifies the prerequisite and expected remediation
    And it does not claim that a deterministic mock is the Jamba inference service

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-102 | Is `services/jamba` a seventh, independently addressed Compose service, or must it replace/implement the existing fixed `llm` service? The issue specifies `/generate`; the current `llm` contract requires `/v1/generate` with a different request/response schema. | requirement-analysis | Resolved | Use the existing fixed `llm` Compose service. Issue #363 takes priority, therefore use `/generate`; a `services/llm/jamba/` internal folder is permitted but no separate Compose service is created. |
| OQ-103 | Must `GET /ready` be implemented in addition to Issue #363's `GET /health`? Repository service guidance requires both for real services, while the issue lists only `/health`. | requirement-analysis | Resolved | Implement both. `/health` reports only process liveness with HTTP 200 and must not generate. `/ready` returns 200 only after the model accepts inference; otherwise it returns 503. |
| OQ-104 | Is an NVIDIA GPU mandatory at runtime, or must a CPU fallback be supported? If GPU is mandatory, what JSON/health behavior is required when it is unavailable? | requirement-analysis | Resolved | Production targets CUDA. CPU mode is out of scope. Without a GPU, `/health` is 200 and `/ready` is 503 with `gpu_unavailable` or `model_not_ready`; CPU CI must not load the real model. |
| OQ-105 | Which exact CUDA, PyTorch, Transformers, `mamba-ssm`, and `causal-conv1d` versions/platforms are supported, and are optimized Mamba kernels mandatory or may a compatible fallback be used? The reference project marks these SSM packages as preinstalled and compatibility-sensitive. | requirement-analysis | Resolved | Derive and lock the Jamba dependency stack from `jamba-sft` and `mamba-cpt-tr`; direct use of those projects as compatibility references is required. |
| OQ-106 | What model revision must deployments use, and should Hugging Face weights be downloaded at image build time, container startup, or from a mounted persistent cache? | requirement-analysis | Resolved | Require `MODEL_ID=serda-dev/Jamba2-3B-Turkish` and a commit-SHA `MODEL_REVISION`, never `main`. Load at startup through a persistent HF cache volume pre-populated before competition/offline deployment; do not bake multi-GB weights into the image. |
| OQ-107 | Which generation controls and limits are public API contract: for example `max_new_tokens`, sampling parameters, maximum prompt size, timeout, concurrency, and response time? Issue #363 defines only `prompt`. | requirement-analysis | Resolved | The public request remains only `prompt`. Sampling controls are service configuration/environment values; caller/orchestrator owns request timeout and the model server owns concurrency. |
| OQ-108 | What HTTP status codes and JSON error shape are required for malformed JSON, empty/missing prompts, model-load failure, GPU unavailability, and generation failure? | requirement-analysis | Resolved | JSON errors use `{"error":{"code":"...","message":"..."}}`. Statuses: malformed JSON 400; missing/empty prompt 422; GPU unavailable, model-load failure, or not-ready 503; unexpected generation failure 500; server-side deadline, if configured, 504. |
| OQ-109 | How must “model is loaded only once” be observed by tests: an internal load counter, structured logs/metrics, or a test double around the loader? | requirement-analysis | Resolved | Test through an injected loader test double: startup followed by N generation requests must have `loader.call_count == 1`. Structured logging is optional and not a test contract. |
| OQ-110 | Which test tiers must be required in CPU-only CI versus GPU-equipped infrastructure, and may a test use a tiny/local fixture only for API wiring while clearly remaining distinct from real-model verification? | requirement-analysis | Resolved | CPU CI runs unit, contract, API, lifecycle/singleton, and Compose E2E with an injected fake/tiny backend. GPU CI/manual runs pinned real-model readiness and generation smoke; final E2E covers orchestrator → LLM → real model. |
