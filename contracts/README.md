# API contracts

Schemas use JSON Schema Draft 2020-12. The intake graph is version `2.0`; the
evolved hierarchical `classification-result` and `validation-result` are
version `3.0`. The HTTP
manifest is the source of truth for endpoint, producer, and consumer. F-01
replaces the former document input with normalized `text` plus `sourceType`;
breaking changes require a new schema version and updates to both producer and
consumer tests.

| Boundary | Producer | Consumer | Request | Response |
| --- | --- | --- | --- | --- |
| OCR | OCR | classification/workflow | `document-input` | `ocr-result` |
| Classification | classification | validation/RAG/workflow | `ocr-result` | `classification-result` |
| Validation | validation | RAG/workflow | `classification-result` | `validation-result` |
| Retrieval | RAG | LLM/workflow | `rag-request` | `rag-result` |
| Generation | LLM | workflow | `llm-request` | `llm-response` |
| Workflow | workflow | client | `document-input` | `workflow-result` |

The manifest also records validation's case-level
`PATCH /cases/{case_id}/supplemental-information` request body. Its Bearer,
`Idempotency-Key`, and `If-Match` headers are HTTP preconditions; the response
is the same current `validation-result` v3 with a quoted `ETag` revision.

All payloads carry `schemaVersion`, `requestId`, and `documentId`. `workflowId` is additionally required once workflow processing begins. Errors use `standard-error`. Nullable fields are explicitly declared in their schemas.
