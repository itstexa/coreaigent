# Contracts

Read this before changing anything that crosses a service boundary. It maps
contracts to producers, consumers, and source paths. **Field definitions are not
repeated here** — open the schema file.

- Endpoint/method/schema source of truth: `contracts/http/manifest.json`
- Payload definitions: `contracts/schemas/<name>.schema.json`
- Versioning policy: [`../contracts/README.md`](../contracts/README.md)
- Per-stage meaning: [`data-flow.md`](data-flow.md)

Draft 2020-12. Intake-graph payloads are `schemaVersion` 2.0; the hierarchical
`classification-result` and `validation-result` are 3.0. All payloads carry
`schemaVersion`, `requestId`, `documentId`; `workflowId` once workflow
processing begins.

## Boundary endpoints

| Endpoint | Service | Request | Response |
| --- | --- | --- | --- |
| `POST /v1/ocr` | ocr | `document-input` | `ocr-result` |
| `POST /v1/classify` | classification | `ocr-result` | `classification-result` |
| `POST /v1/validate` | validation | `classification-result` | `validation-result` |
| `POST /v1/retrieve` | rag | `rag-request` | `rag-result` |
| `POST /v1/generate` | llm | `llm-request` | `llm-response` |
| `POST /v1/workflows/document` | workflow | `document-input` | `workflow-result` |

## Case endpoints

| Endpoint | Service | Request | Response |
| --- | --- | --- | --- |
| `PATCH /cases/{case_id}/supplemental-information` | validation | `supplemental-information-request` | `validation-result` |
| `GET /cases` | workflow | — | `case-list-result` |
| `GET /cases/{case_id}` | workflow | — | `case-status-result` |
| `GET /cases/{case_id}/document` | workflow | — | `case-document` |
| `POST /cases/{case_id}/correspondence` | workflow | `empty-object` | `correspondence-start-result` |
| `GET /cases/{case_id}/correspondence` | workflow | — | `case-correspondence-result` |
| `GET /cases/{case_id}/routing` | workflow | — | `case-routing-result` |
| `POST /cases/{case_id}/review-completion` | workflow | `empty-object` | `review-completion-result` |
| `POST /cases/{case_id}/learning-feedback` | workflow | `empty-object` | `learning-feedback-result` |

Error response for every boundary: `standard-error`. The case endpoints return it
with a nested `error` object (`services/workflow/app.py:nested_error`).

HTTP preconditions are part of the contract but not of the schemas: Bearer token
on every case route, `Idempotency-Key` and `If-Match` on the supplemental patch
and review completion, and a quoted `ETag` revision on the responses.

## Producer and consumer per contract

| Contract | Produced by | Consumed by | Purpose |
| --- | --- | --- | --- |
| `document-input` | caller / frontend | ocr, workflow | Normalized text plus `sourceType` and optional source metadata. |
| `ocr-result` | ocr | classification, workflow | Persisted intake record projection with detected language. |
| `classification-result` | classification | validation, rag, workflow | Hierarchical request type, department/unit target, status and score. |
| `validation-result` | validation | rag, workflow, frontend | Accepted, missing, and invalid fields with the current revision. |
| `supplemental-information-request` | frontend / runner | validation | Applicant-supplied values for missing or invalid fields. |
| `rag-request` | classification trace | rag | Retrieval query for the declared retrieval boundary. |
| `rag-result` | rag | llm, workflow | Retrieved excerpts and citations. |
| `llm-request` | workflow / runner | llm | Generation task, prompt, and retrieved context. |
| `llm-response` | llm | workflow | Structured generation output. |
| `workflow-result` | workflow | client | Final workflow projection (draft, department, status). |
| `case-status-result` | workflow | frontend, runners | Role-projected current case state. |
| `case-list-result` | workflow | frontend (ADMIN) | Paged operator queue with filters. |
| `case-document` | workflow | frontend (ADMIN) | Source document text and metadata for one case. |
| `correspondence-start-result` | workflow | frontend, runners | Accepted F-04 start against a case revision. |
| `case-correspondence-result` | workflow | frontend, runners | Current draft, summary, type, and regulation suggestions. |
| `case-routing-result` | workflow | frontend, runners | Target unit decision and notification status. |
| `review-completion-result` | workflow | frontend (ADMIN) | Idempotent completion of a `needs_review` case. |
| `learning-feedback-result` | workflow | frontend (ADMIN) | PII-minimized, human-approved learning candidate reference; it does not fine-tune a model. |
| `empty-object` | — | workflow | Explicit empty request body for the two POST case actions. |
| `standard-error` | every service | every caller | Uniform error envelope. |

## Changing a contract

1. Edit `contracts/schemas/*.schema.json` and, if the endpoint shape changes,
   `contracts/http/manifest.json`.
2. Update the producer, then every consumer named above.
3. Update `mocks/server.py` so the mock still answers the contract.
4. Run `tests/validate_contracts.py` and the mock suite; update
   `tests/run_scenarios.py` assertions and the affected `run_*_intake.py` runner.
5. A breaking change requires a new `schemaVersion` and updates to both producer
   and consumer tests (`contracts/README.md`).

`tests/validate_contracts.py` enforces the structural rules: every manifest
schema exists, boundary paths start with `/v1/`, case endpoints are `/cases` or
`/cases/{case_id}...`, GET endpoints declare no request body, no duplicate
endpoint identity, every schema compiles, and `schemaVersion` stays in
`{2.0, 3.0}`.

## Gaps worth knowing

- `POST /v1/workflows/document` (`workflow-result`) and the whole `rag` boundary
  are served by `mocks/server.py` only. The real `workflow` overlay implements the
  case API instead, and real retrieval happens inside
  `services/workflow/worker.py`. See [`services/rag.md`](services/rag.md).
- Real responses carry `X-CoreAIgent-Implementation: real`; mocks carry `mock`.
  `tests/run_scenarios.py` asserts this, which is how a mock cannot silently pass
  as an implementation.
- `README.md` and `docs/ui-feature-matrix.md` predate `GET /cases` and still
  describe it as unavailable; the manifest and `services/workflow/app.py` are
  current.
