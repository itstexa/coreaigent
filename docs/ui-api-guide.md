# UI API Guide

This is the implemented demo API guide for a UI, not a production login/RBAC
design. Local Compose browser ports are OCR `8081`, classification `8082`,
validation `8083`, LLM `8085`, and workflow `8086`.

## Demo access

| Role | Header | Visibility |
| --- | --- | --- |
| USER | `Authorization: Bearer f03-demo-token` | Current case, correspondence/routing status, applicant notices. |
| ADMIN | `Authorization: Bearer f06-demo-admin-token` | USER view plus operational fields, target routing and target-unit notice. |

Never put these fixed demo tokens in a production UI bundle.

## UI sequence

```text
submit document → poll case → missing/invalid? → PATCH supplemental fields
                     │                                │
                     └────────────── poll case ◀──────┘
                                      │
                         show correspondence and routing status
                                      │
                         ADMIN may complete needs_review
```

F-06 starts F-04 automatically after F-03 becomes complete. The frontend must
not provide F-04 with a prompt, department, request type, extracted fields or
correspondence type; backend PostgreSQL state is authoritative.

## Endpoints

| Endpoint | Role | Request | UI result |
| --- | --- | --- | --- |
| `POST /v1/ocr` | demo public | F-01 document-input v2 | Queues a case/workflow; retain returned IDs. |
| `GET /cases/{case_id}` | USER/ADMIN | Bearer header | Primary polling projection. ADMIN adds operational context. |
| `PATCH /cases/{case_id}/supplemental-information` | USER | `{ "fields": { "field-id": "value" } }`, Bearer, UUID `Idempotency-Key`, quoted `If-Match` | F-03 result v3 plus `ETag`; on `412`, reload before retry. |
| `POST /cases/{case_id}/correspondence` | authorized | Empty/`{}`, Bearer, UUID key, quoted `If-Match` | Optional manual F-04 start: `202 queued`, `409` not ready, `412` stale. |
| `GET /cases/{case_id}/correspondence` | USER/ADMIN | Bearer header | `not_requested`, `queued`, `processing`, `completed`, or `failed`; never a prior revision. |
| `GET /cases/{case_id}/routing` | USER/ADMIN | Bearer header | `not_routed` or current route and notification states. |
| `POST /cases/{case_id}/review-completion` | ADMIN | Empty body, Bearer, UUID key, quoted `If-Match` | Only `needs_review` becomes `completed`; USER gets `403`. |

## Rendering rules

- `missing_information`: show `missingRequiredFields`; no usable value exists.
- `invalid_information`: show `invalidFields`; a value exists but is invalid.
- `needs_review`: provisional classification is only a hint. Never auto-complete.
- `queued`/`processing`: show progress; do not issue a second start request.
- `no_relevant_source` + `review_required`: label the draft as unverified legal source.
- `failed` correspondence contains no draft; do not show stale content.

## Revisions and data visibility

Persist the last quoted `ETag` and send it as `If-Match` unchanged. Generate
one UUID per intended mutation and reuse it only for the identical retry. USER
responses deliberately exclude validated values, draft context and target-unit
payloads; never reconstruct them from browser state.
