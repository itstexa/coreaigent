# Implementation Log

Append one entry per implementation pass (one story per pass). This file is a
traceable history of completed and paused implementation work.

---

## Pass: 2026-08-17 — US-103 GPU and SSM-compatible runtime

**Branch:** `feature/llm-jamba-inference`
**Traces to:** `docs/design/DESIGN.md` (US-103 GPU and SSM-compatible
runtime), `docs/architecture/ARCHITECTURE.md` (RuntimeConfiguration,
RuntimeState, ModelLoaderPort; D-103–D-104)
**Approval basis:** Requirement Analysis and Solution Architecture were
approved by Serda on 2026-08-17 (see `docs/APPROVAL_LOG.md`).

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| The real service runs with an available NVIDIA GPU | ✅ Pass | Local RTX 4060 smoke with revision `6f8a29fe2c0a4fa2e0a8a0075525370619de8301`: `/health=200`, `/ready=200`, and two real Turkish `/generate` responses returned HTTP 200 |
| The configured Jamba/SSM runtime dependencies are incompatible | ✅ Pass | Controlled loader-failure test keeps `/health` live and `/ready` non-ready; image import probe plus Triton kernel JIT validated the pinned Mamba stack |
| Runtime configuration boundaries are enforced | ✅ Pass | `tests/test_jamba_runtime.py::test_reference_runtime_configuration_boundaries` |
| Real deployment uses persistent HF cache and GPU Compose reservation | ✅ Pass | `tests/test_jamba_runtime.py::test_compose_llm_overlay_reserves_gpu_and_persistent_hf_cache` |
| Real deployment preserves pinned model identity | ✅ Pass | `tests/test_jamba_runtime.py::test_real_overlay_requires_the_pinned_model_identity` |

### Predicates / Invariants Matched

| Entity/Predicate | Invariant / Boundary / Concurrency Rule | Verified By |
|---|---|---|
| `RuntimeConfiguration` | Exact model ID, full lowercase commit SHA, numeric bounds, and absolute cache path | Runtime boundary test plus `RuntimeConfig.validation_error()` |
| `RuntimeConfiguration` | Production does not silently fall back to CPU | `RealJambaLoader` CUDA guard and `gpu_unavailable` readiness test |
| `RuntimeConfiguration` | Model weights are read from persistent HF cache, not image layers | `compose.llm.yaml` volume and `HF_HOME` assertions; pinned cache verification found all 12 model files |
| D-104 runtime baseline | CUDA 12.1 / PyTorch 2.5.1 / pinned `mamba_ssm` and `causal-conv1d` imports | `services/llm/Dockerfile` build-time import probe; real Triton generation smoke |

### Open Questions Raised This Pass

| ID | Question | Status | Resolution |
|---|---|---|---|
| — | None. | — | All implementation details required by US-103 were covered by approved DESIGN/ARCHITECTURE decisions. |

### Deviations From Approved DESIGN/ARCHITECTURE

The host Docker daemon does not currently expose NVIDIA CDI (`--gpus all`
returns `failed to discover GPU vendor from CDI`). The GPU smoke therefore used
the equivalent explicit NVIDIA device/library injection; the production
Compose contract remains `gpus: all` and requires the NVIDIA Container Toolkit.

### Version Control Actions

- Branch: `feature/llm-jamba-inference`
- Verification image: `coreaigent/llm:jamba-us103`.
- Model revision: `6f8a29fe2c0a4fa2e0a8a0075525370619de8301`.
- Commits:
  - `ba8a92b test(llm): define Jamba runtime acceptance suite`
  - `3c6a9ef feat(llm): wire CUDA cache overlay for Jamba runtime`
  - This documentation commit.
- PR: Not opened.

---

## Pass: 2026-08-17 — US-102 Türkçe Jamba inference API

**Branch:** `feature/llm-jamba-inference`
**Traces to:** `docs/design/DESIGN.md` (US-102, Türkçe Jamba inference API),
`docs/architecture/ARCHITECTURE.md` (GenerateRequest, GenerateResponse,
ErrorEnvelope, RuntimeConfiguration, RuntimeState, ModelLoaderPort; D-102–D-106)
**Approval basis:** Requirement Analysis approved by Serda on 2026-08-17;
Solution Architecture approved by Serda on 2026-08-17 (see
`docs/APPROVAL_LOG.md`).

### Acceptance Criteria Coverage

| Scenario | Status | Test(s) |
|---|---|---|
| A loaded service generates text for a Turkish prompt | ✅ Pass | `tests/test_jamba_service.py::test_generate_returns_turkish_text_and_fixed_model_id` |
| A client checks the loaded service | ✅ Pass | `tests/test_jamba_service.py::test_health_reports_loaded_model_without_generating` |
| A process is alive but cannot accept inference | ✅ Pass | `tests/test_jamba_service.py::test_health_is_live_but_ready_rejects_without_gpu` |
| The service cannot accept generation while not ready | ✅ Pass | `tests/test_jamba_service.py::test_generate_returns_503_when_model_is_not_ready` |
| A generation request omits the required prompt | ✅ Pass | `tests/test_jamba_service.py::test_generate_rejects_missing_empty_and_wrong_type_prompts_with_422` |
| A client sends malformed JSON | ✅ Pass | `tests/test_jamba_service.py::test_generate_rejects_malformed_json_with_400` |
| Model generation raises an unexpected error | ✅ Pass | `tests/test_jamba_service.py::test_generation_failure_returns_500_json_error` |
| Sequential generation requests reuse the loaded model | ✅ Pass | `tests/test_jamba_service.py::test_loader_is_called_once_and_generation_is_serialized` |
| 1023/1024/1025 input-token boundary | ✅ Pass | `tests/test_jamba_service.py::test_prompt_token_limit_accepts_1023_and_1024_but_rejects_1025` |
| Model loading failure preserves liveness and reports not-ready | ✅ Pass | `tests/test_jamba_service.py::test_ready_reports_model_load_failure_without_killing_liveness` |

### Predicates / Invariants Matched

| Entity/Predicate | Invariant / Boundary / Concurrency Rule | Verified By |
|---|---|---|
| `GenerateRequest.prompt` | String-only, whitespace rejection, 422 validation, no generation on invalid input | Invalid/missing/type test and loader generation-count assertions |
| `GenerateRequest.prompt` token limit | 1023 and 1024 accepted; 1025 rejected without silent truncation | Boundary test with exact limit and ±1 token |
| `GenerateResponse` | Fixed model ID and generated text are returned | Turkish generation test exact body assertion |
| `ErrorEnvelope` | Stable nested JSON envelope and 400/422/500/503 mappings | Malformed, validation, readiness, load, and generation-error tests |
| `RuntimeState` | `/health` is liveness-only; `/ready` is 503 until inference is available | Health/readiness tests; health asserts no generation call |
| `ModelLoaderPort` | Startup loader call count is exactly one; requests never reload | Singleton lifecycle test |
| D-106 generation lane | Concurrent requests cannot overlap model generation | Concurrent request test asserts `max_active_generations == 1` |
| D-104 runtime | CUDA/PyTorch/Mamba wheels import in the built image | `docker build -f services/llm/Dockerfile ...` build-time import probe |

### Open Questions Raised This Pass

| ID | Question | Status | Resolution |
|---|---|---|---|
| — | None. | — | All implementation details required by US-102 were covered by approved DESIGN/ARCHITECTURE decisions. |

### Deviations From Approved DESIGN/ARCHITECTURE

None.

### Version Control Actions

- Branch: `feature/llm-jamba-inference`
- Commits:
  - `dea32d1 test(llm): define Jamba inference acceptance suite`
  - `6b8a3a9 feat(llm): add pinned Jamba inference service`
  - Documentation and shared pipeline-log update (this pass)
- PR: Not opened; pending human approval after final verification.
