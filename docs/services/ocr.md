# OCR (F-01 intake and normalization)

Read this when changing intake, text normalization, language detection, or the
intake outbox. Payload fields: `contracts/schemas/document-input.schema.json`
and `contracts/schemas/ocr-result.schema.json`.

## Responsibility

- Accept already-available document text (`sourceType: text | ocr`).
- Normalize it: CRLF/CR to LF, NFC, control and format characters stripped.
- Decide the document language deterministically (`tr`, `en`, or `unknown`),
  with no model call — this is the only place language is decided.
- Persist one immutable intake record per `documentId` with generated `caseId`
  and `workflowId`, plus one `process_document` durable outbox job.

## Does not own

- Image or PDF OCR. There is no binary upload and no OCR engine in this
  repository; the service normalizes text it is given.
- Classification, extraction, or any downstream decision.
- Retrying or consuming the outbox job it writes.

## Location

Implementation: `services/ocr/app.py` · Docker: `services/ocr/Dockerfile` ·
Overlay: `compose.ocr.yaml` (also defines the shared `postgres` service) ·
Tests: `tests/run_ocr_intake.py`, `tests/test_document_language.py`

## Inputs / outputs

- `POST /v1/ocr` — `document-input` → `ocr-result`
- `GET /health`, `GET /ready` (503 while PostgreSQL is unreachable)
- Errors: `standard-error` shape with `category` `validation` or `dependency`.

## Processing flow

1. Parse JSON; reject unknown fields, wrong `schemaVersion`, or a bad
   `sourceType` with HTTP 400.
2. Normalize the text; reject fewer than 40 normalized characters with 400.
3. `INSERT ... ON CONFLICT (document_id) DO NOTHING` into `intake_records`.
4. New row → also insert the `durable_outbox_jobs` row in the same transaction.
5. Existing row → compare the immutable fields; equal input replays the stored
   record (idempotent 200), changed input returns HTTP 409.
6. Return the stored projection: `caseId`, `workflowId`, normalized `text`,
   `language`, `ingestStatus: queued`.

## Failure behaviour

- Any `psycopg.Error` on the write path → HTTP 503, `retryable: true`.
- `/ready` returns 503 until `ensure_schema()` and `SELECT 1` succeed.
- Schema creation is idempotent DDL at first use, including
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS language`; there is no migration tool.

## Configuration

`DATABASE_URL` (required). Compose sets `MOCK_SERVICE: null` so the mock code
path cannot be reached in the overlay.

## Tests

`tests/run_ocr_intake.py --phase all` covers persistence, idempotent replay,
409 on changed input, the 39/40/41 character boundary, and the outbox row.
`--phase restart-create` / `--phase restart-verify` bracket a container restart.
`tests/test_document_language.py` pins the language rules.

## Related docs

- [`../data-flow.md`](../data-flow.md) — where intake sits in the lifecycle.
- [`classification.md`](classification.md) — the direct consumer.
- [`../development.md`](../development.md) — running the overlay and its phases.
