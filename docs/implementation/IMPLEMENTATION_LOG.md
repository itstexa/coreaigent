# Implementation Log

Append one entry per implementation pass (one story per pass). This file is a
traceable history of completed and paused implementation work.

---

## Pass: 2026-08-25 — US-108 F-03 information extraction and missing information

**Branch:** Existing `feature/jamba-inference` worktree; no branch, commit, or
PR action was taken because the worktree already contains operator-owned
changes and no Git action was requested.
**Traces to:** `docs/design/DESIGN_0df0ad1_f03.md` (US-108),
`docs/architecture/ARCHITECTURE_0df0ad1_f03.md`
(ValidationResultV3, CurrentValidationState, SupplementalReplay; D-130–D-135)
**Approval basis:** Requirement Analysis and Solution Architecture approved by
Serda on 2026-08-25 (see `docs/APPROVAL_LOG.md`).

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Versioned ten-type registry and hybrid boundary | ✅ Pass | `services/validation/registry.json`; real service uses rule validators and Jamba `/generate` in production mode. CPU overlay explicitly injects `EXTRACTOR_MODE=deterministic`; it is not presented as Jamba. |
| TCKN, phone, date, text, and attachment boundaries | ✅ Pass | `tests/test_validation_service.py`: valid/invalid TCKN, phone formats, possible/impossible dates, 4095/4096/4097 field boundary, and persisted attachment reference behavior. |
| Jamba cannot replace rule-owned fields | ✅ Pass | Unit test rejects a Jamba result containing `tckn`; only semantic fields may be model-produced. |
| Missing and invalid are distinct | ✅ Pass | Unit test asserts invalid takes status priority while a distinct required field remains missing; Docker acceptance asserts missing completion and invalid phone completion. |
| Optional absence does not block completion | ✅ Pass | Unit test asserts optional phone absence yields `complete`. |
| Current-only authoritative state | ✅ Pass | Real PostgreSQL acceptance asserts one current validation row, merged fields, ETag revisions, and retained valid phone after an invalid replacement attempt. |
| Supplemental PATCH concurrency/replay | ✅ Pass | Docker runner asserts Bearer access, quoted ETag, idempotent exact replay, reused-key conflict, stale-revision 412, and no state mutation on stale request. |
| Needs-review classification cannot create F-03 state | ✅ Pass | Docker runner obtains a persisted `needs_review`, receives 409 from validation, and asserts zero validation rows. |
| Validation restart durability | ✅ Pass | `restart-create`, validation-container restart, and `restart-verify` retain current missing state, revision `1`, and accepted TCKN. |
| Evolved mock contract remains valid | ✅ Pass | Documented Docker mock suite validates schemas and passes all 58/58 golden mock scenarios. |

### Predicates / Invariants Matched

| Entity/Predicate | Invariant / Boundary / Concurrency Rule | Verified By |
|---|---|---|
| `ValidationResultV3` | Public values/confidence only; no evidence, provenance, raw source, or `topCandidates`; `missing_information` and `invalid_information` are separate. | Schema, unit tests, and real Docker acceptance response assertions. |
| `CurrentValidationState` | PostgreSQL has exactly one mutable current row per case; a no-change revalidation preserves its revision. | PostgreSQL row assertions and restart verification. |
| `SupplementalReplay` | Equal request replays the canonical response; changed request under same key conflicts; a stale ETag cannot mutate. | Real Docker PATCH acceptance sequence. |
| `AttachmentReference` | Persisted `sourceMetadata.attachments[]` is the only attachment-presence authority and public output exposes only `present`. | Unit attachment tests and validator implementation. |
| Jamba boundary | Production mode calls the real LLM service's `/generate`; an unavailable/malformed structured result is retryable dependency failure. | Service implementation and readiness/error path. CPU acceptance deliberately uses injected deterministic extraction. |

### Open Questions Raised This Pass

| ID | Question | Status | Resolution |
|---|---|---|---|
| — | None. | — | All implementation details required by US-108 were covered by approved design and architecture. |

### Deviations From Approved DESIGN/ARCHITECTURE

None. The CPU test path uses the approved deterministic StructuredExtractorPort
injection; real Jamba GPU inference remains a separately identified GPU smoke
environment and is not claimed by these CPU Docker results.

### Version Control Actions

- No branch, commit, push, or PR was created. The existing worktree had
  unrelated operator-owned changes, and no explicit Git action approval was
  given.

---

## Pass: 2026-08-25 — US-107 F-02 hierarchical classification

**Branch:** Existing `feature/jamba-inference` worktree; no branch, commit, or
PR action was taken because the worktree already contains operator-owned
changes and no Git action was requested.
**Traces to:** `docs/design/DESIGN.md` (US-107),
`docs/architecture/ARCHITECTURE_0df0ad1_f02.md` (DemoMunicipalityTaxonomy,
ClassificationResultV3, CurrentClassification, claimed durable-job lifecycle;
D-120 and D-121)
**Approval basis:** Requirement Analysis and Solution Architecture approved by
Serda on 2026-08-25 (see `docs/APPROVAL_LOG.md`).

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Strict confidence boundary | ✅ Pass | `tests/test_classification_service.py` asserts 0.799 and 0.800 are `needs_review`; 0.801 is `classified`. |
| A valid chain yields exactly one hierarchy | ✅ Pass | Unit test checks department/unit/request type and absence of `topCandidates`. |
| Valid low-confidence chain is provisional | ✅ Pass | Unit and real PostgreSQL test assert the 0.800 chain with `needs_review`. |
| No match is review with null hierarchy | ✅ Pass | Unit and real PostgreSQL test assert `needs_review`, all hierarchy values null, and 0.0. |
| Equal scores are deterministic | ✅ Pass | Unit test asserts lexical stable taxonomy-ID tie resolution. |
| Invalid taxonomy cannot be classified | ✅ Pass | Unit test rejects an invalid parent reference before scoring. |
| Existing HTTP boundary evolves to v3 | ✅ Pass | `run_classification_intake.py` posts a real OCR response to `POST /v1/classify` and asserts v3 response shape. |
| Durable F-01 → F-02 completion | ✅ Pass | Real OCR/PostgreSQL/worker runner asserts `current_classifications` persistence before outbox job `completed`. |
| Baseline mock contract remains valid | ✅ Pass | Documented Docker mock suite: schema validation and 58/58 mock scenarios. |

### Predicates / Invariants Matched

| Entity/Predicate | Invariant / Boundary / Concurrency Rule | Verified By |
|---|---|---|
| `DemoMunicipalityTaxonomy` | Parent IDs are valid; request-type IDs and keywords are unique. | Taxonomy validation unit test; startup loader. |
| `ClassificationResultV3` | One selected hierarchy only; status is `classified` only for score `> 0.80`; no-match is null hierarchy. | Unit boundary, tie, low-score, and no-match tests. |
| `CurrentClassification` | One current record per document, no history; result and job completion commit atomically. | PostgreSQL upsert and direct SQL assertions in `run_classification_intake.py`. |
| `DurableOutboxJob` | A worker claims with a lease and processes one persisted F-01 job; completion follows persistence. | Real Docker acceptance runner. |
| Mock baseline | The F-02 v3 mock boundary stays compatible with the remaining v2 mock graph. | 58/58 documented mock scenarios. |

### Open Questions Raised This Pass

| ID | Question | Status | Resolution |
|---|---|---|---|
| — | None. | — | All implementation details required by US-107 were covered by approved design and architecture. |

### Deviations From Approved DESIGN/ARCHITECTURE

None.

### Version Control Actions

- No branch, commit, push, or PR was created. The existing worktree had
  unrelated operator-owned changes, and no explicit Git action approval was
  given.

---

## Pass: 2026-08-25 — US-106 F-01 intake and durable state

**Branch:** Existing `feature/jamba-inference` worktree; no branch, commit, or
PR action was taken because the worktree already contains operator-owned
changes and no Git action was requested.
**Traces to:** `docs/design/DESIGN.md` (US-106),
`docs/architecture/ARCHITECTURE_0df0ad1.md` (IntakeRequestV2, IntakeRecord,
DurableOutboxJob, IntakeResultV2; D-108–D-113)
**Approval basis:** Requirement Analysis and Solution Architecture approved by
Serda on 2026-08-25 (see `docs/APPROVAL_LOG.md`).

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Direct Turkish text is accepted and normalized | ✅ Pass | `tests/run_ocr_intake.py --phase all` checks exact original/normalized text and response values against real PostgreSQL. |
| OCR-origin text has the same normalized shape and preserved metadata | ✅ Pass | `tests/run_ocr_intake.py --phase all` asserts `source_type=ocr` and the JSONB metadata row. |
| 39, 40, and 41 character boundary | ✅ Pass | `tests/run_ocr_intake.py --phase all` asserts 39 rejects with no rows/jobs while 40 and 41 accept. |
| Equal replay is idempotent | ✅ Pass | `tests/run_ocr_intake.py --phase all` asserts stable case/workflow IDs and exactly one intake/outbox row. |
| Changed immutable input is rejected | ✅ Pass | `tests/run_ocr_intake.py --phase all` independently changes text, metadata, source type, and correlation ID; every request returns non-retryable HTTP 409 without mutation. |
| Pending work survives OCR restart | ✅ Pass | `tests/run_ocr_intake.py --phase restart-create`, `docker compose ... restart ocr`, and `--phase restart-verify`. |
| Baseline mock contract remains valid | ✅ Pass | Documented `docker compose` mock suite: schema validation and 58/58 mock scenarios. |
| One-real-service development flow remains valid | ✅ Pass | OCR/PostgreSQL overlay: 58/58 development scenarios with only OCR real. |
| LLM adapter accepts the changed shared contract version | ✅ Pass | `tests/test_jamba_service.py`: 14/14 tests in the Jamba runtime image. |

### Predicates / Invariants Matched

| Entity/Predicate | Invariant / Boundary / Concurrency Rule | Verified By |
|---|---|---|
| `IntakeRecord` | Original/normalized text, generated case/workflow IDs, and `queued` state persist in PostgreSQL. | Direct SQL assertions in `tests/run_ocr_intake.py`. |
| `DurableOutboxJob` | Exactly one `pending` job is created in the same transaction as a new intake; replay adds none. | Record/job count assertions and restart verification. |
| `IntakeRequestV2.text` | 39 rejects; 40 and 41 accept after NFC/control-character normalization; no truncation. | Boundary assertions in `tests/run_ocr_intake.py`. |
| D-109 / D-113 | Equal immutable input replays; changed immutable input returns HTTP 409 and cannot overwrite state. | Independent changed-field assertions in `tests/run_ocr_intake.py`. |
| D-111 / D-112 | PostgreSQL is the durable source; mock baseline has no PostgreSQL dependency. | Restart acceptance sequence and the documented 58-scenario mock suite. |

### Open Questions Raised This Pass

| ID | Question | Status | Resolution |
|---|---|---|---|
| — | None. | — | All implementation details required by US-106 were covered by approved design and architecture. |

### Deviations From Approved DESIGN/ARCHITECTURE

The legacy 58 golden scenarios contain 40 texts shorter than F-01's 40-character
minimum. `tests/run_scenarios.py` appends a deterministic test-only explanatory
suffix to those request bodies; F-01's real 39/40/41 rejection tests remain
unchanged. This preserves legacy scenario identities while exercising only
valid v2 intake requests.

### Version Control Actions

- No branch, commit, push, or PR was created. The existing worktree had
  unrelated operator-owned changes, and no explicit Git action approval was
  given.

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
