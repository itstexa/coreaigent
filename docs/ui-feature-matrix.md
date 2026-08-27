# CoreAIgent UI Feature Matrix

This matrix records the repository state observed before the Web UI implementation.
It distinguishes implemented public behavior from product goals so the UI does not
invent data or imply capabilities that the backend does not provide.

| Feature | Backend implementation | Public API | UI can integrate | Gap / boundary |
| --- | --- | --- | --- | --- |
| Case creation | Yes. Real OCR intake persists `intake_records` with generated case/workflow UUIDs and a durable outbox job. | `POST /v1/ocr` | Yes | The public request accepts normalized text or OCR-origin text, not a binary file. |
| Document upload | Partial. Intake accepts `sourceType: text\|ocr`, `text`, and optional attachment metadata. | `POST /v1/ocr` | Yes, as text/OCR text | There is no multipart/PDF/image upload or OCR engine endpoint. The UI must not claim a binary was uploaded or OCR was executed. |
| OCR / normalization | Partial. The `ocr` service normalizes already available text and preserves source metadata. | `POST /v1/ocr` | Yes | Actual image/PDF OCR is out of scope in the current repository. |
| Classification | Yes. A versioned taxonomy, public classifier, and PostgreSQL durable worker are implemented. | `POST /v1/classify` | Yes | There is no case-level classification GET route; the UI may retain the real submission response locally, while the ADMIN case projection exposes stable IDs only. |
| Information extraction | Yes, within validation. Deterministic/Jamba candidate extraction and current accepted fields are implemented. | `POST /v1/validate` | Yes | The orchestration demo requires the UI/runner to call validation after classification; extraction is not a separate endpoint. |
| Validation | Yes. Missing and invalid information are distinct, with optimistic revision and idempotent supplemental updates. | `POST /v1/validate`; `PATCH /cases/{case_id}/supplemental-information` | Yes | Supplemental fields are text values only; attachment completion is represented by intake metadata, not browser binary upload. |
| Priority | No authoritative priority field, enum, rule, or endpoint was found. | No | No | The UI must show priority as unavailable, never calculate or infer it. |
| Department routing | Yes. Routing is deterministic from the current classification/taxonomy state; Jamba cannot select the target. | `GET /cases/{case_id}/routing` | Yes | Routing is automatic; there is no public manual department-change endpoint. |
| Employee assignment | No employee entity, workload model, assignee field, or assignment endpoint was found. | No | No | The UI must not fabricate employees or an assignment action. Target unit is the narrowest supported destination. |
| Correspondence | Yes. Automatic F-04 start, optional idempotent manual start, current-result polling, local retrieval, and draft generation are implemented. | `POST` and `GET /cases/{case_id}/correspondence` | Yes | Generated content is a reviewable draft; it is not signed, approved, or dispatched. |
| Notifications | Yes. Two PostgreSQL notification records (`applicant`, `target_unit`) are generated independently. | Status via `GET /cases/{case_id}/routing`; role-filtered payloads via `GET /cases/{case_id}` | Yes | There is deliberately no SMTP/e-mail dispatch. `email_placeholder` remains null and the UI must label delivery as simulated/persisted only. |
| Case history | Partial. Current state, revision, completed feature steps, last error, update time, notices, and current routing/correspondence are public. | `GET /cases/{case_id}` plus correspondence/routing GETs | Yes, as a current lifecycle timeline | There is no immutable public audit-event/history list with actor timestamps for every transition. |
| Case listing / “assigned to me” | No public collection route or assignee model exists. | No | Partial, browser-local recent-case index only | The UI can remember case IDs created/opened in this browser and re-fetch each authoritative projection. It must not describe this as a server-side inbox. |
| Human review completion | Yes, for `needs_review`, with ADMIN authorization, idempotency, and revision preconditions. | `POST /cases/{case_id}/review-completion` | Yes | This is demo ADMIN authorization, not production identity/RBAC. |

## Runtime truth

- Base `compose.yaml` is a deterministic contract-mock stack, not real AI or
  durable business services.
- Real OCR intake, classification, validation, Jamba, correspondence, routing,
  notifications, and orchestration require the documented Compose overlays.
- Browser-facing fixed demo credentials must stay behind the local UI reverse
  proxy and must not be bundled into frontend JavaScript.

