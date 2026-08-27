# Data Flow

Read this when you need to know what happens between two stages, who produces a
payload, and which contract governs it. Field definitions stay in
`contracts/schemas/`; the producer/consumer table is in
[`contracts.md`](contracts.md).

Every payload carries `schemaVersion`, `requestId`, and `documentId`;
`workflowId` is additionally required once workflow processing begins. Errors
use `standard-error` (nested `error` object for the case endpoints).

## Stage sequence

```text
text input
  → intake + normalization + language        (ocr)
  → taxonomy classification                  (classification)
  → field extraction + missing/invalid split (validation)
  → [supplemental information loop]          (validation, client-driven)
  → automatic correspondence start           (workflow orchestrator-worker)
  → regulation retrieval + draft generation  (workflow correspondence-worker + llm)
  → target unit routing + notifications      (workflow routing-worker + llm)
  → case projection reads                    (workflow API)
```

## Client → OCR

Producer: caller (`frontend/src/api.ts`, or a `tests/run_*_intake.py` runner).
Consumer: `services/ocr`.
Contract: `document-input` → `ocr-result`, `POST /v1/ocr`.
Meaning: normalized text plus `sourceType` (`text` or `ocr`) becomes a persisted
intake record with generated `caseId`/`workflowId`, a detected `language`, and a
`process_document` outbox job. Equal input replays idempotently; changed input
for the same `documentId` is HTTP 409.

## OCR → Classification

Producer: `services/ocr`. Consumer: `services/classification`.
Contract: `ocr-result` → `classification-result` (v3), `POST /v1/classify`.
Meaning: normalized text is scored against `services/classification/taxonomy.json`.
`classified` requires a score above 0.80; lower or unmatched results are
`needs_review`. The durable worker then writes exactly one current
classification record per document.

## Classification → Validation

Producer: `services/classification`. Consumer: `services/validation`.
Contract: `classification-result` → `validation-result` (v3), `POST /v1/validate`.
Meaning: the request type selects a field schema from
`services/validation/registry.json`; candidates are extracted (deterministic
rules or Jamba, per `EXTRACTOR_MODE`) and split into accepted, missing, and
invalid. The result carries a revision used for optimistic concurrency.

## Validation ↔ Client (supplemental loop)

Producer/consumer: caller ↔ `services/validation`.
Contract: `supplemental-information-request` → `validation-result`,
`PATCH /cases/{case_id}/supplemental-information`.
Meaning: the applicant supplies missing or corrected values. Bearer,
`Idempotency-Key`, and `If-Match` are preconditions; the response is the new
current validation state with a quoted `ETag`. The loop repeats until the
completion status is `complete`.

## Validation → Correspondence start (automatic)

Producer: `orchestrator-worker` (`services/workflow/orchestrator_worker.py`).
Consumer: `correspondence_generations` job row.
Contract: internal PostgreSQL job; the equivalent public entry is
`POST /cases/{case_id}/correspondence` → `correspondence-start-result`.
Meaning: a complete validation revision on a `classified` case creates the F-04
job — one initial attempt plus at most three retries after a 30-second cooldown.
Manual start exists for demos and is idempotent against the same revision.

## Correspondence generation

Producer: `correspondence-worker` (`services/workflow/worker.py`).
Consumers: `llm`, then the case correspondence projection.
Contracts: internal to `workflow`; the public read is
`GET /cases/{case_id}/correspondence` → `case-correspondence-result`. The
declared retrieval boundary is `rag-request` → `rag-result`.
Meaning: dense BGE-M3 retrieval over `services/workflow/corpus.json`
(top-5, cosine ≥ 0.60) selects citations; `services/workflow/correspondence.py`
applies the PII policy and builds the structured prompt; `llm` returns JSON that
is parsed, guarded (no unsourced legal claim, bounded lengths, citation subset),
and persisted as a reviewable draft. Retrieval failure or guard rejection sets
`result_status = review_required` rather than emitting an unsafe draft.

## Routing and notifications

Producer: `routing-worker` (`services/workflow/routing_worker.py`).
Consumer: case routing projection.
Contract: `GET /cases/{case_id}/routing` → `case-routing-result`.
Meaning: `services/workflow/routing.py` selects the target department/unit
deterministically from the taxonomy — the model cannot choose it — and falls back
to `diger` / `siniflandirilmamis` when the target is inactive or invalid. Jamba
then writes two notification records (`applicant`, `target_unit`) that are
persisted only; there is no dispatch, and `email_placeholder` stays null.

## Case reads

Producer: `services/workflow/app.py`. Consumer: `frontend`, acceptance runners.
Contracts: `GET /cases` → `case-list-result` (ADMIN only),
`GET /cases/{case_id}` → `case-status-result`,
`GET /cases/{case_id}/document` → `case-document`,
`POST /cases/{case_id}/review-completion` → `review-completion-result`.
Meaning: state is derived from current records, not stored as free text.
USER sees the case, its status, and applicant notices; ADMIN additionally sees
validated fields, operational context, and the target-unit notification. ADMIN
may complete a `needs_review` case idempotently, guarded by the case revision.
