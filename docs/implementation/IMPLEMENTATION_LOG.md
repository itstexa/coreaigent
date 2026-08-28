# Implementation Log

Append one entry per implementation pass (one story per pass). This file is a
traceable history of completed and paused implementation work.

---

## Pass: 2026-08-28 — BX-12 managed RAG corpus (paused)

**Branch:** `feature/managed-rag-corpus` (no commit requested).
**Traces to:** `docs/design/DESIGN_bd84424_rag_corpus.md` (BX-12) and
`docs/architecture/ARCHITECTURE_bd84424_rag_corpus.md`.
**Approval basis:** BX-12 requirements and its architecture were approved by
the human operator on 2026-08-28 before the new artifact-pin question arose.

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Source byte/type limits and deterministic chunks | In progress | `tests/test_rag_sources.py` tests 0 B, 10 MiB - 1, 10 MiB, 10 MiB + 1, MIME/suffix mismatch, empty text, and exact 3,000-character chunk boundaries. |
| Synchronous PDF/DOCX extraction and publication | Blocked | AQ-116: an offline, pinned PaddleOCR artifact is required before scanned-PDF extraction can be implemented. |

### Predicates / Invariants Matched

- The source byte boundary is exactly 1..10 MiB before OCR/storage work.
- Chunking is an ordered, lossless partition with a 3,000-character maximum.
- Candidate BGE vectors must be finite, exactly 1,024-dimensional, and L2-normalized within 0.001.

### Open Questions Raised This Pass

| ID | Question | Status | Resolution |
|---|---|---|---|
| AQ-116 | Which exact CPU-compatible PaddleOCR artifact and offline cache location are approved? | Open | — |

### Deviations From Approved DESIGN/ARCHITECTURE

None. No unpinned OCR model or network fallback was added.

### Meaningful-Test Review

- Tests exercise stated limits at the boundary and on each adjacent side.
- Expected values come from BX-12/BX-14, not from implementation output.
- Negative MIME, empty, malformed-vector, and zero-norm paths have specific assertions.

### Version Control Actions

- Created approved branch `feature/managed-rag-corpus`; no commit, push, or PR action requested.


## Pass: 2026-08-28 — BX-02 least-open-case unit assignment

**Branch:** `feature/case-action-log` (no commit requested).
**Traces to:** `docs/design/DESIGN_bd84424_extensions.md` (BX-02) and
`docs/architecture/ARCHITECTURE_bd84424_bx02.md`.
**Approval basis:** Requirement Analysis, Solution Architecture, and
Implementation approved by human operator on 2026-08-28.

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Unit member with lowest open-case count is selected | ✅ Pass | `tests/test_assignment.py` compares unequal loads. |
| Equal minimums are random-selected | ✅ Pass | Injected chooser test proves only tied minimum candidates are offered. |
| Non-unit/invalid personnel are excluded | ✅ Pass | Unit filter and invalid-ID tests. |
| No unit member produces no invented assignment | ✅ Pass | Explicit `None` result test; routing response exposes nullable `assignee`. |
| Assignment persists once per case revision | ✅ Pass | `case_assignments` unique `(case_id,source_case_revision)` constraint and route-worker insert. |

### Verification

- `python3 -m unittest tests/test_assignment.py tests/test_case_contracts.py tests/test_action_log.py tests/test_dlp.py` — 24 passed.
- `npm test` — 55 passed; `npm run build` — passed.
- Docker mock contract suite — `contracts and 58 golden scenarios are valid`; `58 mock scenario(s) passed`.

### Scope Boundary

No active/online signal, role/skill filter, rebalancing, or new personnel
service was added. No-person, manual override, and reassignment behavior stays
open as OQ-160.

---

## Pass: 2026-08-28 — BX-01 irreversible DLP training export

**Branch:** `feature/case-action-log` (no commit requested).
**Traces to:** `docs/design/DESIGN_bd84424_extensions.md` (BX-01) and
`docs/architecture/ARCHITECTURE_bd84424_bx01.md`.
**Approval basis:** all three pipeline stages approved by human operator on
2026-08-28.

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Name and T.C. Kimlik No are irreversibly redacted | ✅ Pass | `tests/test_dlp.py` checks document labels, dynamic validation names, placeholders, and source-value absence. |
| Original operational text is excluded | ✅ Pass | `case-training-export` strict schema has only redacted `text`; workflow projection never returns `original_text`. |
| Case access controls export | ✅ Pass | Workflow endpoint reuses `_role`; unknown/malformed cases use existing guards. |
| Export is auditable | ✅ Pass | Successful projection appends BX-00 `download` with `export_type=training_dataset`. |
| DLP cannot prove safe redaction | ✅ Pass | Non-text and missing dynamic-name spans fail closed with `DLP_REDACTION_FAILED`. |

### Verification

- `python3 -m unittest tests/test_dlp.py tests/test_action_log.py tests/test_case_contracts.py` — 19 passed.
- `npm test` — 55 passed; `npm run build` — passed.
- Docker mock contract suite — `contracts and 58 golden scenarios are valid`; `58 mock scenario(s) passed`.
- Compose config and `git diff --check` — passed.

### Scope Boundary

No legal basis, retention, external destination, bulk training pipeline, or
additional identifier class was invented. The endpoint is a case-scoped JSON
projection; source data remains operational-only.

---

## Pass: 2026-08-28 — BX-00 case action log

**Branch:** `feature/case-action-log` (no commit requested).
**Traces to:** `docs/design/DESIGN_bd84424_extensions.md` (BX-00) and
`docs/architecture/ARCHITECTURE_bd84424_bx00.md`.
**Approval basis:** Requirement Analysis, Solution Architecture, and
Implementation approved by human operator on 2026-08-28.

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Allowed action is recorded in immutable SQL shape | ✅ Pass | `tests/test_action_log.py` checks all seven enum values and `ON CONFLICT DO NOTHING` insert. |
| Unknown or empty action data is rejected | ✅ Pass | `tests/test_action_log.py` negative assertions. |
| Case reader can retrieve chronological log | ✅ Pass | `GET /cases/{case_id}/action-log`, strict contract schema, and mock projection. |
| Unknown/malformed case and unauthorized access remain rejected | ✅ Pass | Workflow route reuses `_case_uuid` and `_role` guards; boundary documented in architecture. |

### Predicates / Invariants Matched

- SQL rows are append-only; no update/delete endpoint is exposed.
- Duplicate deterministic worker event IDs are idempotent; concurrent events remain separate.
- Workflow owns persistence; routing/orchestration producers use the shared helper.
- USER and ADMIN retain existing case-reader visibility.

### Verification

- `python3 -m unittest tests/test_action_log.py tests/test_case_contracts.py` — 13 passed.
- `npm test` — 55 passed.
- `npm run build` — passed.
- `python3 -m py_compile ...` and `git diff --check` — passed.
- Full contract validator requires the repository test image's `jsonschema` dependency; host environment lacks it.

### Open Questions / Deviations

None for BX-00. Cross-service producers beyond workflow remain a future
contract event integration, as specified by the approved architecture.

---

## Pass: 2026-08-28 — BX-06 F-03 validation preview

**Branch:** Existing worktree; no branch, commit, push, or PR action. The
worktree contains unrelated operator-owned changes and no Git action was
requested or approved.
**Traces to:** `docs/design/DESIGN_bd84424_extensions.md` (BX-06) and
`docs/architecture/ARCHITECTURE_bd84424_bx06.md`
(`ValidationPreviewProjection`, D-BX06-01).
**Approval basis:** Requirement Analysis and Solution Architecture approved by
human operator on 2026-08-28 (see `docs/APPROVAL_LOG.md`).

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Current validation gaps appear in preview | ✅ Pass | `frontend/src/petition.test.ts` asserts the F-03 labels are preserved, including an invalid `invoice-attachment`; `PetitionForm` now projects both missing and invalid attachment fields. |
| Validation has no current result | ✅ Pass | `frontend/src/petition.test.ts` asserts `validationPreview(null)` returns `unavailable` with no fields. |

### Predicates / Invariants Matched

| Entity/Predicate | Invariant / Boundary / Concurrency Rule | Verified By |
|---|---|---|
| `ValidationPreviewProjection` | All labels come from F-03 `ValidationResultV3`; the browser does not infer a field. | Independent literal labels in the BX-06 test. |
| `ValidationPreviewProjection` | Null validation produces no preview entries. | Explicit null-result assertion. |
| Read-only projection | No preview write, retry, endpoint, persistence, or state-revision behavior is introduced. | `validationPreview` is a pure mapper; `PetitionForm` consumes its output only. |

### Open Questions Raised This Pass

| ID | Question | Status | Resolution |
|---|---|---|---|
| — | None. | — | Approved BX-06 scope fully specifies the in-flow preview. |

### Deviations From Approved DESIGN/ARCHITECTURE

None. The smallest fix extracts the already-existing client projection and
extends it to invalid attachment fields, which were previously omitted.

### Meaningful-Test Review

- Happy and negative paths: supplied current result and `null` result.
- Assertions are literal F-03 labels/status, not output copied from code.
- The mapping itself is exercised; no internal logic is mocked.
- No new numeric threshold exists; F-03 owns field cardinality limits.

### Version Control Actions

- No state-changing Git action. Existing unrelated worktree changes are
  preserved.

---

## Pass: 2026-08-25 — US-113 F-09 case API contract atlas

**Branch:** `feature/jamba-inference`.
**Traces to:** `docs/design/DESIGN_a18aacd_f09.md` (US-113) and
`docs/architecture/ARCHITECTURE_a18aacd_f09.md`.
**Approval basis:** Requirement Analysis and Solution Architecture approved by
Serda on 2026-08-25 (see `docs/APPROVAL_LOG.md`).

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Public case API atlas | ✅ Pass | `contracts/http/manifest.json` contains each implemented F-03–F-06 case route exactly once; `tests/test_case_contracts.py` rejects missing, duplicate, or mismatched records. |
| Lifecycle-safe F-04 reads | ✅ Pass | Strict `oneOf` schema separates `not_requested`, active, failed, and completed correspondence responses; failed results cannot include draft fields. |
| Role-safe case projection | ✅ Pass | Strict USER and ADMIN response branches prevent operational or target-unit fields from leaking into the USER view. |
| CI and UI handoff | ✅ Pass | Pull requests run the Python acceptance suite in addition to Compose checks; `docs/ui-api-guide.md` documents polling, mutations, roles, revisions, and rendering states. |
| Required mock Docker baseline | ✅ Pass | Exact README Compose sequence rebuilt services and passed `contracts and 58 golden scenarios are valid` and `58 mock scenario(s) passed`; stack was torn down. |
| Local CI-equivalent tests | ✅ Pass | Isolated Python 3.12 environment with Docker available completed 72 tests. Negative Jamba timeout/initialization logs were expected test fixtures. |

### Predicates / Invariants Matched

| Entity/Predicate | Invariant / Boundary / Concurrency Rule | Verified By |
|---|---|---|
| `CaseEndpointContract` | Every existing public case endpoint has one method/path/schema record; GET declares no request schema. | Manifest validator and F-09 contract tests. |
| `CorrespondenceCurrentResult` | Lifecycle payload is determined by `generation_status`; no stale or partial failed draft is legal. | Strict schema branch checks. |
| `CaseStatusResult` | USER and ADMIN projections are disjoint strict shapes while retaining opaque persisted notification payloads. | F-09 schema tests and workflow projection implementation. |
| Verification truthfulness | GPU/cache-dependent Jamba/BGE-M3 work is not represented as GitHub-hosted real inference. | CI and UI/runbook documentation. |

### Open Questions Raised This Pass

| ID | Question | Status | Resolution |
|---|---|---|---|
| — | None. | — | Existing implementations and approved F-03–F-06 contracts define all endpoint behavior. |

### Deviations From Approved DESIGN/ARCHITECTURE

None. The CI job and UI guide expose and verify the approved contracts without
altering endpoint behavior.

### Version Control Actions

- Pending this pass's final commit and push.

---

## Pass: 2026-08-25 — US-112 F-08 truthful local Compose modes

**Branch:** `feature/jamba-inference`.
**Traces to:** `docs/design/DESIGN_f38fa41_f08.md` (US-112) and
`docs/architecture/ARCHITECTURE_1b8477b_f08.md`.
**Approval basis:** Requirement Analysis and Solution Architecture approved by
Serda on 2026-08-25 (see `docs/APPROVAL_LOG.md`).

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Isolated mock baseline | ✅ Pass | Exact README sequence passed `docker compose config --quiet`, then `58 mock scenario(s) passed`; it is recorded as mock verification only. |
| Declarative local closures | ✅ Pass | `scripts/local-topologies.json` lists ordered OCR, classification, validation, workflow, and LLM closures. `tests/test_local_topologies.py` independently checks exact overlay order, Dockerfiles, missing-dependency declaration, and wrapper use. |
| Full real local Jamba mode | ✅ Pass | RTX 4060 host with cached Jamba/BGE-M3 ran `run_llm_intake.py`: `/ready`, real `/generate`, model identity, 40-character revision, and non-empty generation passed. |
| Real F-03 extraction | ✅ Pass | Full Compose topology with `compose.validation.jamba.yaml` ran `run_validation_intake.py --phase jamba`; actual Jamba extraction, deterministic TCKN validation, and PostgreSQL current row passed. |
| Real F-04/F-05/F-06 workflow | ✅ Pass | Full local runner passed `run_correspondence_intake.py` and `run_orchestration_intake.py`; it exercised OCR, classification worker, validation, BGE-M3, Jamba, durable PostgreSQL jobs, routing, notification, and case-state reads. |
| Jamba notification context echo | ✅ Pass | Real run exposed valid `title`/`body` plus extra echoed fields. `normalize_notification_output` now discards only extras; unit tests reject missing fields and the rerun completed both notification audiences. |

### Predicates / Invariants Matched

| Entity/Predicate | Invariant / Boundary / Concurrency Rule | Verified By |
|---|---|---|
| `LocalDevelopmentTopology` | `real_local` closures build every available local dependency and select a named non-mock runner. | Registry contract tests and Compose config validation. |
| Jamba prerequisite | Missing real GPU/model readiness is not substituted with an LLM mock. | `compose.llm.yaml` readiness dependency and real ready/generate test. |
| F-03 source of truth | Jamba semantic extraction does not replace deterministic TCKN validation; current result commits in PostgreSQL. | Jamba F-03 runner direct response and SQL assertion. |
| Notification recovery | Only exact non-blank title/body survive; additional model context is discarded, and missing/oversize output still fails. | `tests/test_routing_service.py` recovery/negative/boundary assertions and real F-05 rerun. |

### Open Questions Raised This Pass

| ID | Question | Status | Resolution |
|---|---|---|---|
| — | None. | — | OQ-150 and the existing real-model structural-oracle policy fully specified the implementation. |

### Deviations From Approved DESIGN/ARCHITECTURE

- F-05 D-152 records a narrowly-scoped structural recovery discovered by the
  real local run: extra model fields are discarded only when exact valid
  `title` and `body` already exist. This applies the approved structured-output
  recovery intent without deriving content from a different field.

### Version Control Actions

- Pending this pass's final verification and commit.

---

## Pass: 2026-08-25 — US-111 F-06 durable orchestration and case state

**Branch:** `feature/jamba-inference`.
**Traces to:** `docs/design/DESIGN_c207e52_f06.md` (US-111) and
`docs/architecture/ARCHITECTURE_5a9d17f_f06.md`.
**Approval basis:** Requirement Analysis and Solution Architecture approved by
Serda on 2026-08-25 (see `docs/APPROVAL_LOG.md`).

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Durable automatic F-04 start | ✅ Pass | `orchestrator-worker` derives a complete/classified current revision into a unique PostgreSQL `correspondence_start_jobs` row, then atomically writes one F-04 generation/job. The real Docker intake proves this without a client POST. |
| Initial plus three retry limit | ✅ Pass | `tests/test_orchestrator.py` asserts the exact 0/3/4/5 attempt boundaries; worker uses PostgreSQL lease and configurable 30-second cooldown. |
| Review hold and manual completion | ✅ Pass | Pure state tests reject automatic completion; real local intake reads USER/ADMIN projections, rejects USER completion with 403, and proves ADMIN replay-safe completion. |
| Review classification with no F-03 row | ✅ Pass | `tests/run_orchestration_intake.py` uses real OCR/classification/PostgreSQL and proves a `needs_review` case is projected while validation, F-04 starts and routes remain zero. |
| Persisted missing/invalid notice | ✅ Pass | Orchestrator inserts one `case_notifications` applicant record per current revision/kind and projects it from PostgreSQL; no external dispatch exists. |
| Current state layering and F-05 preservation | ✅ Pass | Mutable `current_case_states` never updates F-02/F-03/F-04/F-05 source records; F-05 routing/notifications remain separate and a manual completed review state is preserved for its revision. |
| Compose and contract baseline | ✅ Pass | Worker-only services disable inherited HTTP health checks; `docker compose config --quiet` and the documented mock suite passed all 58 scenarios. |

### Predicates / Invariants Matched

| Entity/Predicate | Invariant / Boundary / Concurrency Rule | Verified By |
|---|---|---|
| `CorrespondenceStartJob` | At most one automatic start per case revision; exactly four total F-04 attempts maximum; stale claims are lease-recoverable. | Unique `(case_id, source_case_revision)`, `FOR UPDATE SKIP LOCKED`, boundary tests. |
| `CurrentCaseState` | Derived state is a PostgreSQL layer; `review_required` cannot auto-complete; reviewer completion survives projection refresh for the same revision. | State derivation tests, reviewer endpoint, real local acceptance. |
| `CaseNotification` | One applicant display record per missing/invalid kind/revision; e-mail is a null placeholder. | Database unique constraint and worker insertion. |
| Demo access policy | Exactly one fixed USER token and one fixed ADMIN token; USER excludes internal/target payloads, ADMIN can complete review. | Projection tests and real HTTP assertions. |

### Open Questions Raised This Pass

| ID | Question | Status | Resolution |
|---|---|---|---|
| — | None. | — | All implementation details required by US-111 were covered by the approved design and architecture. |

### Deviations From Approved DESIGN/ARCHITECTURE

None.

### Version Control Actions

- Commit: `cfa574f feat(workflow): add durable case orchestration`.
- Pushed to `origin/feature/jamba-inference`.

---

## Pass: 2026-08-25 — US-110 F-05 final routing and notifications

**Branch:** `feature/jamba-inference`.
**Traces to:** `docs/design/DESIGN_8c16689_f05.md` (US-110) and
`docs/architecture/ARCHITECTURE_f84cffd_f05.md`.
**Approval basis:** Requirement Analysis and Solution Architecture approved by
Serda on 2026-08-25 (see `docs/APPROVAL_LOG.md`).

### Acceptance Criteria Coverage

| Scenario | Status | Test / Verification |
|---|---|---|
| Automatic exactly-once F-04 routing | ✅ Pass | F-04 completion atomically enqueues `routing_jobs`; `UNIQUE(case_id, source_case_revision)` protects the immutable route. The real acceptance runner asserts one route row. |
| Recovery of unrequested/missed work | ✅ Pass | `routing_worker.recover_once()` scans complete/classified current state and enqueues a lease-safe PostgreSQL reconciliation job. |
| Active classified/fallback target selection | ✅ Pass | `tests/test_routing_service.py` rejects `needs_review`, incomplete and inactive chains, and asserts `review_required`/`not_requested` select `diger` / `siniflandirilmamis`. |
| Separate persisted notifications | ✅ Pass | One `notification_records` row per `applicant` and `target_unit`; real Jamba/PostgreSQL acceptance verifies completed independent payloads and null e-mail placeholders. |
| Notification failure preserves routing | ✅ Pass | Route commit and notification jobs are separate transactions; a structured-output failure stores no partial payload and cannot mutate a routed operation. |
| Read-only UI projection | ✅ Pass | `GET /cases/{case_id}/routing` returns current revision route and notification states, never notification payload content. |

### Predicates / Invariants Matched

| Entity/Predicate | Invariant / Boundary / Concurrency Rule | Verified By |
|---|---|---|
| `RoutingOperation` | One immutable logical target per case revision; Jamba cannot select department/unit. | PostgreSQL unique key, taxonomy resolver, pure routing tests, real F-04→F-05 run. |
| `RoutingJob` | F-04 event and reconciliation are PostgreSQL leased durable work; a stale revision is rejected. | Atomic F-04 insert, `FOR UPDATE SKIP LOCKED` claim, worker revision check. |
| `NotificationRecord` | Applicant and target-unit payloads are separate; applicant cannot receive operational context; e-mail remains null placeholder. | Projection tests and real persisted-payload assertions. |
| Current read model | Previous revision routes are not returned as current after F-03 changes. | Current-revision lookup by `(case_id, revision)` in the authorized GET endpoint. |

### Open Questions Raised This Pass

| ID | Question | Status | Resolution |
|---|---|---|---|
| — | None. | — | All F-05 behavior was covered by the approved design and architecture. |

### Deviations From Approved DESIGN/ARCHITECTURE

None.

### Version Control Actions

- Commit: `feat(workflow): add durable final routing`.

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

---

## Pass: 2026-08-27 — US-102 prose `/v1/generate` prompt contract fix

**Traces to:** `services/llm/app.py`, `tests/test_jamba_service.py`,
`docs/analysis/JAMBA_PROMPT_FIX_REEVALUATION.md`
**Scope:** Existing LinguAI Jamba snapshot only; no model change, training,
dataset download, Golden Dataset change, or reference-model comparison.

### Implementation

- Added centralized `build_prose_admin_prompt()` with version
  `prose-admin-v2` and hash `f14a9079caccde36fb4410d6f0080ceae41705e6e89079569f0db001d590cf64`.
- Integrated validated `task` and context into `/v1/generate`.
- Kept raw `/generate` and F-03/F-04 structured workflows unchanged.
- Added tests proving task/context propagation, no expected-answer leakage, and
  raw structured prompt isolation.

### Verification

- Jamba service tests: `17/17 PASS`.
- CPU contract/service suite: `70/70 PASS`.
- Docker image build, `/ready`, and 58-case development contract runner:
  `PASS`.
- F-03 real Jamba extraction: `PASS`.
- F-04 real correspondence intake with structured guards: `PASS`.
- Golden re-evaluation: `58/58` schema-valid and non-empty; full metrics and
  raw artifact paths are recorded in the linked analysis report.

### Deviations / Open Questions

None. Action enum values were intentionally not inserted into the model-facing
prose prompt because a live trial showed enum echo; the evaluator-side action
taxonomy remains explicit in the report.

### Version Control Actions

- Branch/commit/PR: none; not requested by the operator.

## Pass: 2026-08-28 — BX-03 case history and similar cases

**Traces to:** approved BX-03 requirement and architecture sessions,
`services/workflow/app.py`, `services/workflow/similarity.py`, history/resolution
contracts, mock projection, and frontend history tab.

### Implementation

- Added deterministic same-classification, inclusive 30-day history projection
  with text/location/time signal labels.
- Persisted immutable per-reader resolution marks in workflow PostgreSQL and
  exposed idempotent reader marking; existing BX-00 view events provide viewers.
- Added strict history and resolution contracts, manifest routes, mock behavior,
  API client types, and a minimal panel view/action.

### Verification

- Pure Python checks: `30/30 PASS` (similarity, contracts, action log,
  assignment, DLP).
- Frontend: `55/55 PASS`; TypeScript/Vite build passed.
- Docker mock contract suite: `contracts and 58 golden scenarios are valid`;
  `58 mock scenario(s) passed`.

## Pass: 2026-08-28 — BX-04 abuse review signals

**Traces to:** approved BX-04 requirement/architecture, `services/workflow/abuse.py`,
the orchestrator assessment, moderation contracts, and workflow routes.

### Implementation

- Added configurable deterministic duplicate, burst, term, and bot-repeat
  signals with bounded 0.0–1.0 score and review threshold.
- Persisted case assessment in PostgreSQL; moderator/admin override requires a
  reason and emits `spam_decision`; citizens do not receive the judgement.

### Verification

- Abuse policy, strict contracts, and mock projection tests pass.
- Python compilation and Docker mock suite pass (`58/58` golden scenarios).

## Pass: 2026-08-28 — BX-04A abuse trends

- Added privacy-bounded daily flagged-rate aggregation with 7/30/90-day
  periods, unit/system scopes, user `no_data` behavior, and five-user minimum.
- Added `GET /moderation-trends`, strict contract, mock projection, and pure
  aggregation tests. No realtime analytics or notification channel added.

Verification: trend/policy/contract tests pass; Python compilation and
`git diff --check` pass.

## Pass: 2026-08-28 — BX-08 deterministic priority

- Added deterministic priority policy (`low`, `normal`, `high`, `urgent`) with
  default `normal`, configured deadline/waiting/request-type signals, and
  protection against sensitive-data-only escalation.
- Added case priority read and ADMIN override routes with mandatory reason;
  override is auditable and does not alter routing.
- Added strict contracts, mock behavior, and boundary tests.

## Pass: 2026-08-28 — BX-09 routing confidence feedback

- Added pure routing evaluation projection separating classifier confidence from
  correctness; configurable threshold marks low-confidence cases for review.
- Final accepted unit is treated as ground truth; evaluation remains separate
  from BX-01 training eligibility.
- Routing assignee projection and strict result contract preserve destination
  semantics while exposing the selected unit/person.

## Pass: 2026-08-28 — BX-11 Turkish text improvement

- Added deterministic Turkish whitespace/punctuation/readability suggestions
  with protected-span preservation and explicit unsupported-language handling.
- Added `/v1/normalize` contract/mock endpoint; original text is always returned
  unchanged and post-submit persistence remains BX-05's revision boundary.

### Deviations / Open Questions

No deviations for the approved slice.

## Pass: 2026-08-28 — BX-03A related attachments

**Traces to:** approved BX-03A requirement and architecture sessions,
`services/workflow/attachments.py`, attachment contracts, and workflow routes.

### Implementation

- Added deterministic request-type required-attachment rules and metadata-only
  object-storage registration.
- Enforced PDF/DOCX/JPG/JPEG/PNG, MIME/extension agreement, 10 MiB per file,
  and 10 files per case.
- Added manual/rule relations and non-authoritative similarity suggestions;
  submitted-state edits return `CASE_REVISION_REQUIRED` for BX-05.
- Persisted SQL metadata/relations and `attachment_change` action events.

### Verification

- Attachment policy and contract tests passed; Python compilation and
  `git diff --check` passed.
- Docker mock contract suite: `contracts and 58 golden scenarios are valid`;
  `58 mock scenario(s) passed`.

## Pass: 2026-08-28 — BX-05 case revision edit

- Added strict edit validation for text, structured fields, and attachment IDs;
  classification mutation is rejected.
- Added append-only PostgreSQL `case_revisions`, optimistic `If-Match` checks,
  terminal-state rejection, `petition_edit` action logging, and authorized
  revision reads.
- Existing assignment/SLA/correspondence records are not rewritten; revision
  payload provenance is retained for later eligibility filtering.

Verification: revision policy, contract, compilation, and mock-suite checks
pass; Docker mock suite remains the final integration gate.

## Pass: 2026-08-28 — BX-07 citizen document draft

- Added local deterministic templates for petition/request, complaint, and
  information-request documents.
- Added editable temporary draft endpoint `POST /v1/drafts` with mandatory
  field reporting and strict unsupported-type/size rejection.
- Deliberately excluded signing, dispatch, and PDF/DOCX generation.

Verification: focused draft/contract tests and Python compilation pass; Docker
mock suite is the integration gate.
