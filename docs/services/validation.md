# Validation (F-03 extraction and missing-information detection)

Read this when changing field extraction, the missing/invalid split, or the
supplemental-information patch. Payload fields:
`contracts/schemas/validation-result.schema.json` (v3) and
`contracts/schemas/supplemental-information-request.schema.json`.

## Responsibility

- Select the required field set for the classified request type from
  `services/validation/registry.json`.
- Extract candidate values from the normalized text, either with deterministic
  rules or through Jamba structured extraction (`EXTRACTOR_MODE`).
- Split the outcome into accepted, missing, and invalid fields, and derive a
  completion status (`complete`, `missing_information`, `invalid_information`).
- Own the case-level supplemental loop: an authorized, idempotent, revision-guarded
  `PATCH` that produces the next current validation state.

## Does not own

- Deciding the request type (that is `classification`).
- Correspondence, routing, notifications, or case state (that is `workflow`).
- Serving the model: it calls the `llm` service's minimal `/generate` endpoint.

## Location

Implementation: `services/validation/app.py` · Field registry:
`services/validation/registry.json` (8 request-type schemas) · Docker:
`services/validation/Dockerfile` · Overlays: `compose.validation.yaml`
(deterministic extractor), `compose.validation.jamba.yaml` (real Jamba
extractor, requires a healthy `llm`) · Tests:
`tests/test_validation_service.py`, `tests/run_validation_intake.py`

## Inputs / outputs

- `POST /v1/validate` — `classification-result` → `validation-result`, with a
  quoted `ETag` revision.
- `PATCH /cases/{case_id}/supplemental-information` —
  `supplemental-information-request` → `validation-result`.
- `GET /health`, `GET /ready`.

## Processing flow

1. `POST /v1/validate` loads the intake record joined to the current
   classification `FOR UPDATE`.
2. Missing record → 404. Not `classified`, or a request type absent from the
   registry → 409 (not eligible for extraction).
3. Extract candidates: deterministic rule/label matching, or a Jamba prompt whose
   response must parse as one JSON object. Extraction uses the document language
   recorded at intake.
4. Validate each value by kind (for example TCKN checksum) and classify it as
   accepted, missing, or invalid.
5. Persist the new current validation state and return it with the new revision.
6. `PATCH` requires Bearer `CASE_ACCESS_TOKEN`, a UUID `Idempotency-Key`, and a
   quoted `If-Match` revision; 1-8 non-blank field values, each ≤ 4096 characters,
   with IDs known to the registry.
7. A replayed `Idempotency-Key` returns the stored response; the same key with a
   different payload fingerprint is 409. A stale `If-Match` is 412, a missing one
   is 428.

## Failure behaviour

- `/ready` is 503 when the registry failed to load, `EXTRACTOR_MODE` is not
  `deterministic`/`jamba`, or the Jamba dependency is unset.
- Jamba unavailable or unparseable → HTTP 503 `dependency`, `retryable: true`.
- PostgreSQL unavailable → 503 `dependency`.
- Errors on the case route use the nested-error shape of `standard-error`.

## Configuration

`DATABASE_URL`, `CASE_ACCESS_TOKEN`, `EXTRACTOR_MODE`
(code default `jamba`; `compose.validation.yaml` sets `deterministic`),
`JAMBA_URL` (default `http://llm:8080/generate`), `JAMBA_TIMEOUT_SECONDS`
(65 s for CUDA, widened for CPU).

## Tests

`tests/run_validation_intake.py` covers the real overlay: current-state
persistence, the supplemental replay contract, and `--phase restart-create` /
`--phase restart-verify` across a container restart. `--phase jamba` is the real
extractor run. `tests/test_validation_service.py` pins field evaluation and the
missing/invalid split on CPU.

## Related docs

- [`classification.md`](classification.md) — producer.
- [`workflow.md`](workflow.md) — consumer; a complete revision triggers F-04.
- [`llm-jamba.md`](llm-jamba.md) — the extractor dependency.
- [`../data-flow.md`](../data-flow.md) — the supplemental loop in context.
