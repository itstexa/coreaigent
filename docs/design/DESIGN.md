# Design & Requirements Atlas

Central index of requirement-analysis output for this repository. Individual
sessions may split their work into `DESIGN_<commit-id>.md` files when this file
grows too large; every such file must be listed below.

## Linked Design Documents

| File | Scope / Topic | Started (commit) | Status |
|---|---|---|---|
| (this file) | Core; US-102–US-107 Jamba runtime, F-01 intake, and F-02 classification analysis | — | Active |
| [DESIGN_0df0ad1_f03.md](DESIGN_0df0ad1_f03.md) | US-108 F-03 information extraction and missing-information analysis | `0df0ad1` | Active |
| [DESIGN_0df0ad1_f04.md](DESIGN_0df0ad1_f04.md) | US-109 F-04 legislation recommendation, summary, and official correspondence analysis | `0df0ad1` | Active |
| [DESIGN_8c16689_f05.md](DESIGN_8c16689_f05.md) | US-110 F-05 final routing and audience-specific notifications | `8c16689` | Active — open decisions |
| [DESIGN_c207e52_f06.md](DESIGN_c207e52_f06.md) | US-111 F-06 orchestration and observable case state | `c207e52` | Active |
| [DESIGN_f38fa41_f08.md](DESIGN_f38fa41_f08.md) | US-112 F-08 Compose developer-mode dependency closure | `f38fa41` | Active |
| [DESIGN_a18aacd_f09.md](DESIGN_a18aacd_f09.md) | US-113 F-09 contract atlas stabilization for implemented case APIs | `a18aacd` | Active |
| [DESIGN_bd84424_f11.md](DESIGN_bd84424_f11.md) | US-114 local Turkish/English translation bridge and US-115 truthful competition UI | `bd84424` | Active |
| [DESIGN_bd84424_f00.md](DESIGN_bd84424_f00.md) | US-116 F0 case ticket and immutable system action trace | `bd84424` | Active |
| [DESIGN_bd84424_f08.md](DESIGN_bd84424_f08.md) | US-117 F8 explainable petition priority | `bd84424` | Active |
| [DESIGN_bd84424_f03a.md](DESIGN_bd84424_f03a.md) | US-118 same-applicant similar petition history | `bd84424` | Active |
| [DESIGN_bd84424_rag.md](DESIGN_bd84424_rag.md) | US-119 local hybrid legislation retrieval | `bd84424` | Active |
| [DESIGN_bd84424_f02a.md](DESIGN_bd84424_f02a.md) | US-120 F2 birim içi otomatik personel ataması | `bd84424` | Active |
| [DESIGN_bd84424_f02b.md](DESIGN_bd84424_f02b.md) | US-122 F2 tekrar/agresiflik sinyaline göre çözüm oranı odaklı atama | `bd84424` | Active — open decisions |
| [DESIGN_bd84424_learning_feedback.md](DESIGN_bd84424_learning_feedback.md) | US-123 admin-onaylı PII-minimized öğrenme adayı | `bd84424` | Active — OQ-184 open |
| [DESIGN_bd84424_f09.md](DESIGN_bd84424_f09.md) | US-121 F9 açıklanabilir yönlendirme güveni | `bd84424` | Active |

## Analysis Context

- Source request: [GitHub Issue #363](https://github.com/itstexa/coreaigent/issues/363),
  `[US-102] Jamba2-3B-Turkish Docker inference API oluştur`.
- The deployed model identifier is `ai21labs/AI21-Jamba2-3B`, the upstream
  base model. Its configuration declares `JambaForCausalLM`,
  `use_mamba_kernels: true`, and Transformers `4.57.6`. A locally fine-tuned
  checkpoint was evaluated and rejected on output quality, so the pinned
  identity is the upstream repository at revision
  `525c6c8e1d9f5bddedfbdc1dbb0ade2df84230c9`.
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
I want the fixed `llm` service to serve `ai21labs/AI21-Jamba2-3B`
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

### US-106: F-01 evrak intake kontratının repository uyumu

As a document-processing operator
I want text and OCR-origin evrakların tek, izlenebilir bir intake sınırında
normalize edilmesini
So that classification ve validation servisleri kaynak türüne göre farklı
kontratlar uygulamak zorunda kalmasın.

The existing `POST /v1/ocr` boundary will be changed for this intake flow; no
second intake endpoint is introduced. PostgreSQL is the authoritative source
of truth for original/normalized text and case/workflow state. A PostgreSQL
durable job/outbox is required for initial dispatch; Redis is not required.

### US-107: F-02 hiyerarşik evrak sınıflandırması

As a document-processing operator
I want normalized documents to receive one valid department, unit, and request
type classification from a versioned taxonomy
So that downstream extraction and routing can use stable authoritative IDs
without independently predicting the hierarchy.

F-02 evolves the existing `POST /v1/classify` boundary and its
`classification-result` contract; it does not introduce a second
classification endpoint. The repository will own a versioned `Demo Belediyesi`
taxonomy fixture. Classification confidence follows the repository's existing
`0..1` score convention: only a score strictly greater than `0.80` is
`classified`; `0.80` and lower is `needs_review`. PostgreSQL holds exactly one
current authoritative classification per case; historical results are not
retained. A durable worker must consume F-01's `process_document` outbox job,
run classification, persist the current result, and complete the job only
after the classification persistence succeeds.
The response never exposes a `topCandidates` collection: if multiple valid
chains are above `0.80`, it returns exactly the single chain with the highest
confidence. An exact confidence tie is broken deterministically by stable
taxonomy ID so one result is always selected.
A valid but low-confidence best chain is returned as provisional context with
`needs_review`; when no valid chain matches at all, the status is still
`needs_review` and all three hierarchy fields are `null`.

#### Remote branch reference check (2026-08-25)

- `origin/feature/rule-engine` (`c7486f1`) provides a dependency-free,
  deterministic baseline and a 20-record synthetic evaluation fixture. Its
  labels are flat `document_type` and `department`; it contains neither
  department → unit → request-type taxonomy records nor taxonomy versions.
  Its documented scores are keyword-coverage heuristics, explicitly not
  calibrated confidence/probabilities, and it has no PostgreSQL or outbox
  persistence.
- `origin/feature/rag-advanced-pipeline` (`076d542`) retains the existing
  flat classification contract/scenarios and adds RAG work, but does not
  define the F-02 taxonomy, confidence policy, authoritative classification
  persistence, or F-01-to-classification dispatch boundary.

These branches are useful reference material only. They do not decide the
open F-02 product and data-contract choices below, and the rule-engine fixture
cannot be represented as a complete F-02 taxonomy without an owner decision.

## Gherkin Acceptance Criteria

Feature: Türkçe Jamba inference API

  Scenario: A loaded service generates text for a Turkish prompt
    Given the service process has loaded `ai21labs/AI21-Jamba2-3B`
    When a client sends `POST /generate` with a JSON body containing a non-empty Turkish `prompt`
    Then it returns JSON containing `model` equal to `ai21labs/AI21-Jamba2-3B`
    And it returns the generated text in `response`

  Scenario: A client checks the loaded service
    Given the model has finished loading in the service process
    When a client sends `GET /health`
    Then it returns JSON with `status` equal to `ok`
    And it returns `model` equal to `ai21labs/AI21-Jamba2-3B`
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
    And it loads `ai21labs/AI21-Jamba2-3B` with its required Jamba/SSM-compatible dependencies
    And `GET /health` reports that the model is loaded

  Scenario: A host GPU that Docker cannot pass into a container serves the same model
    Given a Docker host whose GPU has no supported container runtime, such as an AMD Radeon on Windows
    And a host-native llama.cpp server that serves the pinned GGUF artifact with GPU offload
    When the Jamba service is started with `BACKEND=llama_cpp` and that server's URL
    Then `GET /ready` returns 200 and names `llama_cpp` as the backend that served the run
    And `POST /generate` returns model-generated Turkish text with the pinned `model` and `modelRevision`
    And the container reserves no GPU and holds no model weights

  Scenario: The upstream server is absent or serves a different artifact
    Given the Jamba service is configured with `BACKEND=llama_cpp` and a pinned `GGUF_FILE`
    When the host server is unreachable, or reports any file other than the pinned artifact
    Then `GET /health` returns 200 and `GET /ready` returns 503 with `model_not_ready`
    And it must not report `model_loaded` as `true`
    And it becomes ready again on its own once that server serves the pinned artifact

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
    Then it verifies readiness and a real Turkish generation from the pinned Jamba2-3B
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

Feature: F-01 evrak girdisi ve normalizasyon

  Scenario: Direct Turkish text is accepted through the updated intake contract
    Given a Turkish document with at least 40 characters
    When a client sends it to the updated `POST /v1/ocr` intake boundary with source type `text`
    Then the service persists the original and normalized text in PostgreSQL
    And it returns the document and case/workflow identity
    And downstream processing receives the normalized document without branching on source type

  Scenario: OCR-origin text uses the same normalized intake record
    Given OCR-origin Turkish text with at least 40 characters
    When a client sends it to the updated `POST /v1/ocr` intake boundary with source type `ocr`
    Then the service creates the same normalized intake record shape used for direct text
    And it preserves supplied source metadata for traceability

  Scenario: A duplicate document is replayed idempotently
    Given an intake request with a stable document identity was accepted
    When the same document is submitted again
    Then the service returns the existing document and case/workflow identity
    And it does not create a second case, workflow, or durable outbox job

  Scenario: Text below the minimum length is rejected
    Given a document containing 39 characters
    When a client sends it to the intake boundary
    Then the service returns a machine-readable validation error
    And it does not persist a case or create a durable outbox job

  Scenario: The exact minimum length is accepted
    Given a document containing exactly 40 characters
    When a client sends it to the intake boundary
    Then the service accepts it for normalization and durable processing

  Scenario: Pending work survives a container restart
    Given an accepted intake record has a pending durable outbox job
    When the intake container restarts before dispatch completes
    Then the document, case/workflow state, and pending job remain recoverable from PostgreSQL

Feature: F-02 hierarchical document classification

  Scenario: A document receives a valid taxonomy chain
    Given the loaded versioned `Demo Belediyesi` taxonomy contains a matching document example
    When classification runs for a normalized document
    Then it returns stable department, unit, and request-type identifiers with their display labels
    And the unit belongs to the returned department
    And the request type is allowed by the returned unit
    And the result identifies the taxonomy version

  Scenario: An invalid parent-child chain is never emitted
    Given a candidate unit or request type belongs to a different taxonomy parent
    When classification evaluates the candidate
    Then it does not return the invalid hierarchy as `classified`
    And it does not persist that hierarchy as the authoritative classification result

  Scenario: Confidence strictly above 0.80 auto-classifies
    Given a document whose valid best classification candidate has confidence 0.81
    When classification runs
    Then its status is `classified`
    And its persisted current classification contains the selected taxonomy chain

  Scenario: Multiple qualifying departments yield only the highest-confidence chain
    Given three valid taxonomy chains have confidence 0.81, 0.87, and 0.91
    When classification runs
    Then it returns exactly the 0.91 chain as `classified`
    And the response does not contain `topCandidates`

  Scenario: Confidence at or below 0.80 requires review
    Given a document whose valid best classification candidate has confidence 0.80 or lower
    When classification runs
    Then its status is `needs_review`
    And it returns the one valid best taxonomy chain as provisional context when one exists
    And no downstream automatic routing is triggered

  Scenario: No taxonomy match requires review without a hierarchy
    Given a document with no valid matching taxonomy chain
    When classification runs
    Then its status is `needs_review`
    And its department, unit, and request type are all null

  Scenario: A durable intake job completes classification end to end
    Given F-01 has committed a pending `process_document` outbox job for a normalized document
    And the versioned `Demo Belediyesi` taxonomy is available
    When the classification worker claims the job
    Then it runs the evolved existing classification boundary
    And it persists exactly one current authoritative classification result in PostgreSQL
    And it marks the outbox job completed only after that result is persisted

  Scenario: Reclassification replaces the current result without retaining history
    Given a case has one persisted current classification result
    When a later valid classification result is persisted for that case
    Then PostgreSQL exposes the later result as the only current authoritative result
    And it does not retain a historical classification-result record for the earlier result

  Scenario: An unavailable taxonomy does not produce invented labels
    Given the configured taxonomy cannot be loaded
    When the classification service receives a document
    Then it reports non-readiness or a controlled dependency failure
    And it does not return a fallback department, unit, or request type

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-102 | Is `services/jamba` a seventh, independently addressed Compose service, or must it replace/implement the existing fixed `llm` service? The issue specifies `/generate`; the current `llm` contract requires `/v1/generate` with a different request/response schema. | requirement-analysis | Resolved | Use the existing fixed `llm` Compose service. Issue #363 takes priority, therefore use `/generate`; a `services/llm/jamba/` internal folder is permitted but no separate Compose service is created. |
| OQ-103 | Must `GET /ready` be implemented in addition to Issue #363's `GET /health`? Repository service guidance requires both for real services, while the issue lists only `/health`. | requirement-analysis | Resolved | Implement both. `/health` reports only process liveness with HTTP 200 and must not generate. `/ready` returns 200 only after the model accepts inference; otherwise it returns 503. |
| OQ-104 | Is an NVIDIA GPU mandatory at runtime, or must a CPU fallback be supported? If GPU is mandatory, what JSON/health behavior is required when it is unavailable? | requirement-analysis | Resolved | GPU inference is mandatory and CPU inference stays out of scope. Two lanes are supported: `BACKEND=transformers` loads the pinned snapshot in-process on CUDA, and `BACKEND=llama_cpp` adapts a host-native llama.cpp server that offloads the pinned GGUF to a non-NVIDIA GPU (Vulkan) — the container itself reserves no GPU and holds no weights. Without a usable accelerator, `/health` is 200 and `/ready` is 503: `gpu_unavailable` for the CUDA lane, `model_not_ready` for an absent upstream server. CPU CI must not load the real model. |
| OQ-105 | Which exact CUDA, PyTorch, Transformers, `mamba-ssm`, and `causal-conv1d` versions/platforms are supported, and are optimized Mamba kernels mandatory or may a compatible fallback be used? The reference project marks these SSM packages as preinstalled and compatibility-sensitive. | requirement-analysis | Resolved | Derive and lock the Jamba dependency stack from `jamba-sft` and `mamba-cpt-tr`; direct use of those projects as compatibility references is required. |
| OQ-106 | What model revision must deployments use, and should Hugging Face weights be downloaded at image build time, container startup, or from a mounted persistent cache? | requirement-analysis | Resolved | Require `MODEL_ID=ai21labs/AI21-Jamba2-3B` and `MODEL_REVISION=525c6c8e1d9f5bddedfbdc1dbb0ade2df84230c9`, never `main`. The CUDA lane loads at startup through a persistent HF cache volume pre-populated before competition/offline deployment; the GGUF lane keeps the SHA-256-verified quantized artifact on the host next to the pinned llama.cpp build. Neither lane bakes multi-GB weights into the image. |
| OQ-107 | Which generation controls and limits are public API contract: for example `max_new_tokens`, sampling parameters, maximum prompt size, timeout, concurrency, and response time? Issue #363 defines only `prompt`. | requirement-analysis | Resolved | The public request remains only `prompt`. Sampling controls are service configuration/environment values; caller/orchestrator owns request timeout and the model server owns concurrency. |
| OQ-108 | What HTTP status codes and JSON error shape are required for malformed JSON, empty/missing prompts, model-load failure, GPU unavailability, and generation failure? | requirement-analysis | Resolved | JSON errors use `{"error":{"code":"...","message":"..."}}`. Statuses: malformed JSON 400; missing/empty prompt 422; GPU unavailable, model-load failure, or not-ready 503; unexpected generation failure 500; server-side deadline, if configured, 504. |
| OQ-109 | How must “model is loaded only once” be observed by tests: an internal load counter, structured logs/metrics, or a test double around the loader? | requirement-analysis | Resolved | Test through an injected loader test double: startup followed by N generation requests must have `loader.call_count == 1`. Structured logging is optional and not a test contract. |
| OQ-110 | Which test tiers must be required in CPU-only CI versus GPU-equipped infrastructure, and may a test use a tiny/local fixture only for API wiring while clearly remaining distinct from real-model verification? | requirement-analysis | Resolved | CPU CI runs unit, contract, API, lifecycle/singleton, and Compose E2E with an injected fake/tiny backend. GPU CI/manual runs pinned real-model readiness and generation smoke; final E2E covers orchestrator → LLM → real model. |
| OQ-111 | F-01 intake API mevcut `POST /v1/ocr`/`document-input` sınırını mı değiştirecek, yoksa `source_type` ve `text` alanları için yeni versioned bir intake boundary mi eklenecek? Mevcut kontrat `content`, `contentType`, `scenarioId` ve `source` kullanır. | requirement-analysis | Resolved | Existing `POST /v1/ocr` contract will be changed; no second intake endpoint is introduced. |
| OQ-112 | Aynı belge tekrar gönderildiğinde seçilecek davranış hangisidir: hangi identity anahtarıyla idempotent replay, yoksa conflict? | requirement-analysis | Resolved | Idempotent replay; a repeat must return the existing identity and must not create duplicate case, workflow, or durable job state. |
| OQ-113 | “Kullanılamayacak kadar kısa” metnin kesin minimum eşiği ve ölçüm birimi nedir? | requirement-analysis | Resolved | Minimum input length is 40 characters; 39 is rejected and 40 is accepted. |
| OQ-114 | Kabul edilen evrakın original/normalized metni ile queued state'i hangi persistence/queue bileşeninde tutulacak? Repository şu an shared infrastructure tanımlamıyor. | requirement-analysis | Resolved | PostgreSQL is the authoritative source of truth for original/normalized text and case/workflow state. Initial dispatch uses a PostgreSQL-backed durable job/outbox; Redis is optional future transient queue/cache infrastructure only. Container restarts must not lose a case or pending work. |
| OQ-115 | F-02 mevcut sabit `classification` / `POST /v1/classify` sınırını ve v2 `classification-result` şemasını mı değiştirecek, yoksa yeni bir logical service/endpoint mi gerektiriyor? | requirement-analysis | Resolved | Evolve the existing `POST /v1/classify` and `classification-result` contract; do not add a classification endpoint. |
| OQ-116 | Başlangıçta kullanılacak canonical taxonomy kaynağı ve kapsamı nedir: repository içi versioned demo fixture mı, sağlanacak resmi taxonomy verisi mi, yoksa başka bir owner-managed kaynak mı? Hangi department/unit/request-type kayıtları beklenir? | requirement-analysis | Resolved | Create a repository-owned, versioned demo taxonomy using a municipality as the example. |
| OQ-117 | Confidence threshold tam değeri nedir; değer altında `needs_review` ve `unclassified` arasındaki seçim kuralı ile top-candidate görünürlüğü ne olmalıdır? | requirement-analysis | Resolved | Existing contract score scale is `0..1`; only scores strictly greater than `0.80` are `classified`, and `0.80` or lower, including no match at `0.0`, is `needs_review`. Top-candidate visibility is tracked separately in OQ-120. |
| OQ-118 | Authoritative classification kaydı PostgreSQL'de nasıl versionlanmalı: bir case için tek mutable current result mı, yoksa taxonomy/model değişiminde historical sonuçlar da tutulmalı mı? | requirement-analysis | Resolved | PostgreSQL retains one current authoritative classification result per case; do not retain historical classification results. |
| OQ-119 | F-02 bu pass'te F-01 `process_document` durable outbox işini gerçekten dispatch edip classification çağrısını tamamlayacak mı, yoksa yalnız `classification` service/contract/state davranışı mı uygulanacak? | requirement-analysis | Resolved | Complete the working operation: consume F-01's durable job, run classification, persist the result, and complete the job end to end. |
| OQ-120 | `needs_review` sonucunda veya başarılı sınıflandırmada API `topCandidates` alanını döndürmeli mi; dönecekse aday sayısı ve görünürlük kuralı nedir? | requirement-analysis | Resolved | Do not return `topCandidates`. If multiple valid candidates are above `0.80`, return exactly one: the highest-confidence candidate. An exact tie is deterministically resolved by stable taxonomy ID. |
