# API contracts

Schemas use JSON Schema Draft 2020-12 and version `1.0`. The HTTP manifest is the source of truth for endpoint, producer, and consumer. A breaking change requires a new schema version and an update to both producer and consumer tests.

| Boundary | Producer | Consumer | Request | Response |
| --- | --- | --- | --- | --- |
| OCR | OCR | classification/workflow | `document-input` | `ocr-result` |
| Classification | classification | validation/RAG/workflow | `ocr-result` | `classification-result` |
| Validation | validation | RAG/workflow | `classification-result` | `validation-result` |
| Retrieval | RAG | LLM/workflow | `rag-request` | `rag-result` |
| Generation | LLM | workflow | `llm-request` | `llm-response` |
| Workflow | workflow | client | `document-input` | `workflow-result` |

All payloads carry `schemaVersion`, `requestId`, and `documentId`. `workflowId` is additionally required once workflow processing begins. Errors use `standard-error`. Nullable fields are explicitly declared in their schemas.
