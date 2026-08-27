# Architecture Atlas

Central index of solution-architecture output for this repository. This design
consumes the human-approved Jamba and feature-pack requirements in
[docs/design/DESIGN.md](../design/DESIGN.md).

## Linked Architecture Documents

| File | Scope / Topic | Started (commit) | Status |
|---|---|---|---|
| (this file) | `llm` service / Jamba2-3B-Turkish inference | — | Active |
| [ARCHITECTURE_0df0ad1.md](ARCHITECTURE_0df0ad1.md) | US-106 F-01 intake, PostgreSQL state, durable outbox, contract v2 | 0df0ad1 | Active |
| [ARCHITECTURE_0df0ad1_f02.md](ARCHITECTURE_0df0ad1_f02.md) | US-107 F-02 hierarchical classification, demo taxonomy, durable worker, contract v3 | 0df0ad1 | Active |
| [ARCHITECTURE_0df0ad1_f03.md](ARCHITECTURE_0df0ad1_f03.md) | US-108 F-03 extraction, validation, current PostgreSQL state, and supplemental PATCH contract | 0df0ad1 | Active |
| [ARCHITECTURE_0df0ad1_f04.md](ARCHITECTURE_0df0ad1_f04.md) | US-109 F-04 regulation retrieval, immutable correspondence history, durable jobs, and structured Jamba draft | 0df0ad1 | Active |
| [ARCHITECTURE_f84cffd_f05.md](ARCHITECTURE_f84cffd_f05.md) | US-110 F-05 automatic routing, notification records, and PostgreSQL recovery | f84cffd | Active |
| [ARCHITECTURE_5a9d17f_f06.md](ARCHITECTURE_5a9d17f_f06.md) | US-111 F-06 orchestration, current state, demo access, and recovery | 5a9d17f | Active |
| [ARCHITECTURE_1b8477b_f08.md](ARCHITECTURE_1b8477b_f08.md) | US-112 F-08 truthful local Compose dependency closure and real local verification | 1b8477b | Active |
| [ARCHITECTURE_a18aacd_f09.md](ARCHITECTURE_a18aacd_f09.md) | US-113 F-09 public case API manifest and strict result schemas | a18aacd | Active |

## Scope and Component Boundary

Issue #363 is implemented by the existing fixed Compose service `llm`, not by
a seventh `jamba` service. The public real-service route is `POST /generate`;
it supersedes the prior `/v1/generate` route in this repository's LLM contract.
The Jamba runtime may live under `services/llm/jamba/`, but its Docker image,
Compose hostname, and orchestration dependency remain `llm`.

```text
CoreAIgent caller / workflow
        |
        | HTTP http://llm:8080/generate
        v
LLM API process ── health/readiness state machine ── ModelLoader (one instance)
        |                                              |
        |                                              v
        └────────────────── serialized inference ── Jamba2-3B-Turkish
                                                       |
                                           pinned HF revision in cache volume
```

## Data Models

### Entity: GenerateRequest

Traces to: US-102 (docs/design/DESIGN.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `prompt` | UTF-8 JSON string | Unicode scalar values | Required; must satisfy the resolved non-empty-prompt policy and the active server token capacity before inference. |

**Invariants** (must always hold true):

- A request reaching the model has exactly one validated `prompt` string.
- Generation controls are not accepted in this public request object.

**Boundary Behavior:**

- Min/Max: a missing or empty prompt returns HTTP 422; the F-04-capable server
  maximum is 8192 rendered Jamba input tokens.
- Empty/Null/Zero: missing, null, or empty values do not invoke the loader or
  model and return HTTP 422.
- Overflow/Truncation: the service must not silently truncate a prompt; a
  prompt beyond the active token limit is rejected before generation.

**Concurrency / Race-Scenario Analysis:**

- Concurrent valid requests are independently validated, then enter the single
  generation lane defined by Decision D-106. Invalid requests never acquire it.

### Entity: GenerateResponse

Traces to: US-102 (docs/design/DESIGN.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `model` | string | Hugging Face repository ID | Required; exact value `ai21labs/AI21-Jamba2-3B`, whichever lane served the run. |
| `modelRevision` | 40 lowercase hexadecimal string | Hugging Face commit identity | Required successful-response provenance for F-04 generation persistence. |
| `response` | UTF-8 JSON string | Unicode scalar values | Required; generated completion text. |

**Invariants** (must always hold true):

- A successful response always identifies the fixed model ID and loaded pinned
  revision.
- The `response` value is produced by the one loaded model instance, not a
  deterministic mock in a real-model verification tier.

**Boundary Behavior:**

- Min/Max: response length is governed by server-side generation configuration;
  F-04 permits at most 1800 generated tokens.
- Empty/Null/Zero: `model` and `response` are never null; the behavior of a
  zero-token model completion is pending AQ-103.
- Overflow/Truncation: the generation configuration, rather than request
  fields, limits output; no client-supplied sampling override exists.

**Concurrency / Race-Scenario Analysis:**

- Each response is bound to its own request and its own completed generation;
  the serialization lock prevents token/state interleaving between requests.

### Entity: ErrorEnvelope

Traces to: US-102, US-103 (docs/design/DESIGN.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `error` | object | — | Required for every non-2xx API result described below. |
| `error.code` | string | — | Required, machine-readable, non-empty; `gpu_unavailable` and `model_not_ready` are required readiness codes. |
| `error.message` | UTF-8 JSON string | Unicode scalar values | Required, non-empty, operator-readable; never contains model weights, tokens, or secrets. |

**Invariants** (must always hold true):

- Error bodies have exactly the envelope shape `{ "error": { "code": "...",
  "message": "..." } }`.
- `GET /health` is liveness-only: an unavailable model does not turn its
  process-liveness result into an error response.
- HTTP status mapping is fixed: malformed JSON 400; missing/empty prompt 422;
  unavailable GPU, load failure, or not-ready state 503; unexpected generation
  failure 500; configured server-side deadline expiry 504.

**Boundary Behavior:**

- Min/Max: `code` and `message` must be non-empty; model output is never
  included in an error body.
- Empty/Null/Zero: missing `error`, code, or message is an implementation
  defect; internal exceptions become a complete 500 envelope.
- Overflow/Truncation: diagnostic messages are bounded by implementation
  logging policy without exposing secret or model data.

**Concurrency / Race-Scenario Analysis:**

- A readiness transition concurrent with a request is resolved at the point the
  request enters the generation lane: if the model is not ready it gets 503;
  otherwise its generation completes or returns its mapped failure.

### Entity: RuntimeConfiguration

Traces to: US-102, US-103, US-105 (docs/design/DESIGN.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `MODEL_ID` | string | Hugging Face repository ID | Required; exactly `ai21labs/AI21-Jamba2-3B`. |
| `MODEL_REVISION` | string | Git commit SHA hexadecimal characters | Required; exactly 40 lowercase hexadecimal characters; `main` is prohibited. |
| `HF_HOME` | absolute POSIX path string | filesystem path | Required; inside the persistent, writable Hugging Face cache volume. |
| `max_new_tokens` | positive integer | tokens | Server configuration only; default/range pending AQ-103. |
| `temperature` | number | — | Server configuration only; default/range pending AQ-103. |
| `top_p` | number | probability | Server configuration only; default/range pending AQ-103. |
| `server_deadline` | positive duration or disabled | milliseconds | Server configuration only; default pending AQ-103. |
| `BACKEND` | enumerated string | — | Required; `transformers` (in-process CUDA) or `llama_cpp` (host llama.cpp server). Any other value leaves the service not ready. |
| `LLAMA_SERVER_URL` | absolute http(s) URL string | — | Required and only meaningful when `BACKEND=llama_cpp`; a bare host:port is invalid. |
| `GGUF_FILE` | string | file name | Required when `BACKEND=llama_cpp`; must end in `.gguf` and must equal the artifact the upstream server reports. |
| `LLAMA_API_KEY` | string | — | Optional bearer credential for the upstream server; never logged and never returned in a response. |

**Invariants** (must always hold true):

- The loader receives both `MODEL_ID` and `MODEL_REVISION`; it never loads the
  mutable `main` revision.
- The image contains runtime code and dependencies but not multi-GB model
  weights; the pinned artifact is read through the mounted cache.
- Exactly one lane is configured per process: `transformers` reserves a CUDA
  device, `llama_cpp` reserves none and holds no weights. Neither lane can
  silently fall back to CPU inference inside the container.
- The `llama_cpp` lane refuses to start when the upstream server reports any
  file other than the pinned `GGUF_FILE`, so a swapped artifact cannot be
  served as the pinned model.

**Boundary Behavior:**

- Min/Max: absent/invalid model ID, SHA, or cache path leaves the service not
  ready and produces 503; numeric generation bounds are pending AQ-103.
- Empty/Null/Zero: blank configuration values are invalid; zero is invalid for
  `max_new_tokens` and for any enabled deadline.
- Overflow/Truncation: configuration parsing rejects values outside approved
  numeric ranges instead of clamping them.

**Concurrency / Race-Scenario Analysis:**

- Configuration is read once during initialization and immutable for that
  process lifetime; replica coordination is deployment-level, not in-process.

### Entity: RuntimeState

Traces to: US-102, US-103 (docs/design/DESIGN.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `process_alive` | boolean | — | True while the HTTP process accepts liveness probes. |
| `gpu_available` | boolean | — | True only when the configured accelerator is usable: the assigned CUDA device for `transformers`, or a reachable upstream llama.cpp server for `llama_cpp`. |
| `model_loaded` | boolean | — | True only after pinned model and tokenizer load successfully. |
| `accepting_inference` | boolean | — | True only after the model is ready to enter the generation lane. |
| `readiness_code` | nullable string | — | Null when ready; otherwise at least `gpu_unavailable` or `model_not_ready`. The `llama_cpp` lane reports `model_not_ready` for an absent upstream server, because no local GPU is expected. |
| `backend` | enumerated string | — | Reported by `/health` and `/ready`; names the lane that actually served the process, never a lane that was merely configured. |

**Invariants** (must always hold true):

- `accepting_inference` is true only if `gpu_available` and `model_loaded` are
  both true.
- `/health` returns HTTP 200 whenever `process_alive` is true and never calls
  `generate`.
- `/ready` returns HTTP 200 exactly when `accepting_inference` is true;
  otherwise it returns HTTP 503 with an ErrorEnvelope.

**Boundary Behavior:**

- Min/Max: state fields are unitless booleans; readiness has no partial success.
- Empty/Null/Zero: before startup completes, `model_loaded` and
  `accepting_inference` are false; an absent CUDA device uses
  `gpu_unavailable` and an absent upstream server uses `model_not_ready`.
- Overflow/Truncation: invalid state combinations are prevented by lifecycle
  transition rules.

**Concurrency / Race-Scenario Analysis:**

- Startup publishes `accepting_inference=true` only after the loader succeeds.
  Concurrent `/ready` probes observe either 503-before-publication or
  200-after-publication, never a false ready result.
- Failed loading keeps the process live but non-ready; it does not retry per
  request.

### Entity: ModelLoaderPort

Traces to: US-102, US-104 (docs/design/DESIGN.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `load(config)` | operation | invocation | Creates tokenizer/model artifacts from RuntimeConfiguration during startup only. |
| `generate(prompt)` | operation | invocation | Available only after successful load and only inside the generation lane. |
| `load_call_count` | non-negative integer | invocations | Test-double observable; must equal 1 after startup and any number of requests in one process. |

**Invariants** (must always hold true):

- Production binds this port to one of two real pinned-Jamba loaders: the
  in-process CUDA loader or the HTTP adapter in front of the host llama.cpp
  server. CPU CI explicitly injects a fake or tiny backend.
- Only the HTTP adapter may be loaded again after a failed start, because a
  reachability change is cheap to re-probe while reloading a CUDA checkpoint
  costs minutes; `load_call_count` still counts exactly one load per attached
  upstream server.
- A request never calls `load`; startup owns the one valid load transition.

**Boundary Behavior:**

- Min/Max: exactly one successful or failed startup load attempt is permitted
  for a process lifetime; `load_call_count > 1` fails the lifecycle test.
- Empty/Null/Zero: a null/failed loader result yields non-ready state, not a
  partially initialized model.
- Overflow/Truncation: no request count changes the singleton rule.

**Concurrency / Race-Scenario Analysis:**

- The process initializes before publishing readiness. Concurrent initial
  requests receive 503 until initialization completes, not competing load calls.

## Technology / Design Decisions

### Decision D-102: Service identity and public route

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Implement Jamba inside existing `llm` at `/generate` | Keeps fixed hostname and follows Issue #363 priority. | Prior LLM manifest/schema and callers must migrate from `/v1/generate`. | ✅ |
| Create an independent `jamba` Compose service | Isolates model API. | Violates the operator decision and adds topology. | ❌ |
| Keep `/v1/generate` | Avoids contract migration. | Conflicts with authoritative Issue #363. | ❌ |

**Why the first option:** It is the explicit operator decision.

**Why not an independent `jamba` service:** The operator explicitly rejected a
new Compose service.

**Why not `/v1/generate`:** It preserves an older repository contract over the
issue named authoritative by the operator.

### Decision D-103: Pinned artifact acquisition

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Startup load from persistent HF cache using model ID + full SHA | Deterministic artifact, reusable offline cache, small image. | Needs cache warming before deployment. | ✅ |
| Download mutable `main` at startup | Simple first run. | Non-deterministic and unsuitable offline. | ❌ |
| Download weights during image build | Self-contained image. | Multi-GB image and revision changes require rebuild. | ❌ |

**Why the first option:** It directly implements the selected offline-ready,
revision-pinned deployment model.

**Why not mutable `main`:** It cannot guarantee that the verified artifact is
the artifact deployed.

**Why not image-baked weights:** It contradicts the explicit persistent-cache
requirement.

### Decision D-104: CUDA/SSM runtime compatibility baseline

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Lock reference CUDA 12.1/PyTorch 2.5.1+cu121/Mamba stack and GPU-smoke it | Reuses the known baseline: `mamba-ssm 2.2.4`, `causal-conv1d 1.5.0.post8`, model-compatible Transformers 4.57.6. | CUDA image and GPU verification lane are required. | ✅ |
| Float PyTorch, Transformers, and Mamba versions | Could receive fixes automatically. | Reintroduces the SSM ABI/runtime risk the reference projects isolate. | ❌ |
| Use an unvalidated non-Transformers serving engine | May offer throughput features. | Not the requested/reference loading path; no approved compatibility evidence. | ❌ |

**Why the first option:** The supplied projects use the CUDA 12.1 / PyTorch 2.5.1
family and pin Mamba packages; the model configuration requires Transformers
4.57.6. Image build and GPU smoke verify imports and real load.

**Why not floating versions:** Mamba and `causal-conv1d` are compiled,
compatibility-sensitive packages.

**Why not another serving engine:** The requirement is known Jamba loading, not
an unverified serving architecture.

### Decision D-105: HTTP implementation

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| FastAPI application with Uvicorn process | Explicit JSON validation/error mapping and testable health/readiness routes. | Adds two small dependencies. | ✅ |
| Python standard-library HTTP server | No framework dependency. | Manual validation/errors/lifecycle integration. | ❌ |
| Reuse repository mock server | Existing route scaffolding. | Deterministic mock behavior cannot be real Jamba. | ❌ |

**Why the first option:** The real service needs typed request/error boundaries
while retaining a small `app.py` implementation.

**Why not the standard library:** It turns required API validation into custom
boilerplate without improving model integration.

**Why not the mock server:** `AGENTS.md` prohibits presenting a mock as real.

### Decision D-106: One model instance and serialized inference

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Load once at startup and guard `generate` with one in-process lock | Meets singleton requirement and prevents concurrent GPU generation/state contention. | Requests queue behind active inference. | ✅ |
| Reload model per request | Stateless handler. | Violates Definition of Done and makes latency/VRAM unacceptable. | ❌ |
| Ungated concurrent calls on one model | Potential higher throughput. | No approved batching/scheduling policy and risks GPU pressure. | ❌ |

**Why the first option:** The reference inference server guards generation with a
lock and the operator assigned concurrency to the model server.

**Why not per-request loading:** It directly violates the approved lifecycle.

**Why not ungated concurrency:** It chooses capacity/scheduling policy before a
batching design exists.

### Decision D-107: Verification partition

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| CPU CI uses injected fake/tiny loader; GPU lane runs pinned real-model smoke; final real E2E | Fast standard CI plus direct proof of actual model. | Needs GPU-capable execution. | ✅ |
| CPU CI loads real Jamba | One uniform test mode. | Contradicts CUDA scope and makes runners load the model. | ❌ |
| CPU CI labels a mock as real service | Fast. | Misrepresents behavior and violates repository guidance. | ❌ |

**Why the first option:** It is the approved verification strategy and makes
singleton proof observable through a test double.

**Why not real Jamba on CPU CI:** CPU real-model loading is outside approved
production mode.

**Why not relabel a mock:** A fake/tiny loader is an explicit test fixture, not
a claimed real Jamba result.

## Architecture Open Questions

| AQ         | Karar                                                                                          | Açıklama                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ---------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **AQ-102** | **CLOSED — string zorunlu, whitespace-only yasak, max 8192 rendered input token.**             | `prompt` JSON string olmak zorunda. `null`, number, boolean, array, object → `422 invalid_prompt_type`. `prompt.strip()` boşsa → `422 empty_prompt`. String otomatik olarak trim/normalize edilmez; yalnızca validation için whitespace kontrolü yapılır. Rendered chat template tokenization sonrasında **8192 token'dan büyük prompt reddedilir** → `422 prompt_too_long`. HTTP tarafında ayrıca kaba DoS koruması için örn. **64 KiB request-body limiti** konabilir ama public semantic limit token sayısıdır. |
| **AQ-103** | **CLOSED — `256 / 0.7 / 0.9 / 60s`; F-04 output capacity max 1800.**                            | Server-only defaults: `max_new_tokens=256`, `temperature=0.7`, `top_p=0.9`, `generation_deadline_seconds=60`. Allowed config ranges: `max_new_tokens 1..1800`, `temperature 0.0..2.0`, `top_p >0.0..1.0`, deadline `5..120 s`. F-04 deployment profile uses at most **1800** output tokens; request body cannot change controls. **Zero-token completion success değildir**; model EOS'u hemen üretir veya decode sonrası boş çıktı kalırsa `500 empty_generation`. |
| **AQ-104** | Production modeli `ai21labs/AI21-Jamba2-3B`, sabit revision ise `525c6c8e1d9f5bddedfbdc1dbb0ade2df84230c9` olarak çözülmüştür. İki lane aynı modeli sunar: CUDA hostlarında safetensors snapshot'ı (`BACKEND=transformers`), NVIDIA GPU'su olmayan hostlarda ise host üzerinde çalışan llama.cpp Vulkan sunucusundaki pinned Q8_0 GGUF (`BACKEND=llama_cpp`). Cache warming ve offline artifact doğrulama politikası her iki lane için de geçerlidir; GGUF artifact'ı SHA-256 ile doğrulanır. | **Resolved** |
