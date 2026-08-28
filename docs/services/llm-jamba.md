# llm (Jamba)

Read this when you touch model serving, the generation endpoints, GPU lanes, or
offline model loading. Prompt construction and output guards are **not** here —
they live in [`workflow.md`](workflow.md).

## Responsibility

Serves the pinned local Jamba model behind two HTTP endpoints. It loads the
model, counts prompt tokens, enforces the generation deadline, and returns text.

## Does not own

- Prompt content, retrieval context assembly, citation checking, PII policy, or
  any decision about the case. It receives a prompt and returns a string.
- Model selection at runtime: the model id and revision are pinned.
- Persistence. It writes nothing to PostgreSQL.

## Location

| What | Path |
| --- | --- |
| Service | `services/llm/app.py` |
| CUDA image | `services/llm/Dockerfile`, `services/llm/requirements.txt` |
| GGUF image | `services/llm/Dockerfile.gguf`, `services/llm/requirements-gguf.txt` |
| Overlays | `compose.llm.yaml` (CUDA), `compose.llm.gguf.yaml` (GGUF host lane) |
| Host launcher for the GGUF lane | `scripts/jamba-gguf-server.ps1` |

## Model boundary

Pinned in `services/llm/app.py` and both overlays:

- `MODEL_ID` — `ai21labs/AI21-Jamba2-3B`
- `MODEL_REVISION` — `525c6c8e1d9f5bddedfbdc1dbb0ade2df84230c9`
  (a 40-hex commit, validated against `MODEL_REVISION_PATTERN`)
- `MAX_PROMPT_TOKENS` — 8192 input tokens
- `BACKENDS` — `transformers` | `llama_cpp`

`HF_HUB_OFFLINE` defaults to `1`: weights are read from the mounted cache
(`HF_HOME` / `HUGGINGFACE_HUB_CACHE`), never downloaded during a run.

## Two real lanes

| Lane | Overlay | Where the weights run |
| --- | --- | --- |
| In-container CUDA (reference) | `compose.llm.yaml` | `transformers` inside the container, `gpus: all` |
| Host llama.cpp / Vulkan | `compose.llm.gguf.yaml` | GGUF on the host, container is a thin adapter to `LLAMA_SERVER_URL` |

Use one or the other, never both. The GGUF lane exists because Docker Desktop
cannot pass a Radeon GPU into a Linux container. It is still the real model:
the adapter refuses to serve unless the host server reports the pinned
`GGUF_FILE`.

## Endpoints

| Endpoint | Shape | Purpose |
| --- | --- | --- |
| `GET /health` | model id, `model_loaded`, backend | liveness |
| `GET /ready` | 200 when loaded, otherwise a readiness error | gate |
| `POST /generate` | body must be **exactly** `{"prompt": "..."}` | model-native API |
| `POST /v1/generate` | `llm-request` → `llm-response` | the CoreAIgent contract |

`/v1/generate` is the contract boundary declared in
`contracts/http/manifest.json`; `/generate` is the narrower model API used by
runtime tests. `/v1/generate` appends `context` entries under a `Bağlam:`
heading before calling the model.

## Failure behaviour

`/generate`: `400 malformed_json`; `422` for a non-object body, a missing or
empty prompt, extra keys, a non-string prompt, or `prompt_too_long`;
`504 deadline_exceeded`; `500 empty_generation`; `500 generation_failed`;
readiness error while the model is loading.

`/v1/generate` maps the same conditions onto the standard error envelope:
`400 validation`, `503 dependency` (not ready, retryable),
`504 timeout` (retryable), `502 dependency` (empty or failed generation,
retryable).

Generation is a single serialized lane, so a bounded `MAX_NEW_TOKENS` default
keeps one runaway answer from blocking the queue.

## Configuration

Names only. `MODEL_ID`, `MODEL_REVISION`, `BACKEND`, `HF_HOME`,
`HUGGINGFACE_HUB_CACHE`, `HF_HUB_OFFLINE`, `MAX_NEW_TOKENS`, `TEMPERATURE`,
`GENERATION_DEADLINE_SECONDS`, `LLAMA_SERVER_URL`, `GGUF_FILE`,
`LLAMA_API_KEY`, `HF_CACHE_DIR`, `NVIDIA_VISIBLE_DEVICES`,
`NVIDIA_DRIVER_CAPABILITIES`.

`LLAMA_API_KEY` is empty by default: the host llama.cpp server is
**unauthenticated** unless the same value is set here and passed to the
launcher's `-ApiKey`. Treat the GGUF lane as a local development surface.

## Tests

`tests/test_jamba_service.py` (endpoint behaviour),
`tests/test_jamba_runtime.py` (runtime/loading),
`tests/run_llm_intake.py` (contract intake).

## Related docs

- [`workflow.md`](workflow.md) — F-04/F-05 caller and output guards
- [`validation.md`](validation.md) — optional Jamba field-extractor caller
- [`../development.md`](../development.md) — which lane to start
- [`../contracts.md`](../contracts.md) — `llm-request` / `llm-response`
