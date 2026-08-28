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
| Priority | Yes. Workflow persists an explainable deterministic `critical` / `high` / `normal` projection from configured safety/service-impact phrases. | `GET /cases` (ADMIN) | Yes, in the operator queue | It orders the queue only; it is not a model judgment, legal SLA, route override, or applicant-facing urgency decision. |
| Department routing | Yes. Routing is deterministic from the current classification/taxonomy state; Jamba cannot select the target. | `GET /cases/{case_id}/routing` | Yes | Routing is automatic; there is no public manual department-change endpoint. |
| Routing confidence (F9 MVP) | Derived in the UI from the authoritative F-02 confidence; classified routes show that score, fallback routes show `%0` with the reason. | Existing routing + case detail responses | Yes, in case overview and correspondence routing card | This is an explainable proxy, not a calibrated routing probability or self-training signal; calibration/dataset feedback remains future work. |
| Employee assignment (F2 first assignment) | Yes. Ordinary cases use least-open workload; a third same-topic petition or bounded aggression signal selects the active target-unit member with the strongest topic resolution rate, with deterministic fallbacks and an admin-visible explanation. | `GET /cases/{case_id}` assignment field (ADMIN variant) | Yes, in the case overview | Local seeded demo staff registry only; no external identity provider, staff CRUD, or manual reassignment yet. Resolution-rate calibration and human outcome events remain future work. USER responses omit staff identity. |
| Correspondence | Yes. Automatic F-04 start, optional idempotent manual start, current-result polling, local retrieval, and draft generation are implemented. | `POST` and `GET /cases/{case_id}/correspondence` | Yes | Generated content is a reviewable draft; it is not signed, approved, or dispatched. |
| Notifications | Yes. Two PostgreSQL notification records (`applicant`, `target_unit`) are generated independently. | Status via `GET /cases/{case_id}/routing`; role-filtered payloads via `GET /cases/{case_id}` | Yes | There is deliberately no SMTP/e-mail dispatch. `email_placeholder` remains null and the UI must label delivery as simulated/persisted only. |
| Case history / F0 trace | Ticket reference and immutable system state-transition actions are persisted; applicant notices and current workflow projection remain available. | `GET /cases/{case_id}`; ticket/action trace is ADMIN-only | Yes, in the detail history tab | Actions deliberately omit petition text, field values, drafts, notification payloads, staff identity, and assignment. |
| Similar past petitions / user F3 | Yes. A bounded same-validated-applicant projection scores normalized token overlap and records factual current resolution state. | `GET /cases/{case_id}/related-cases` (ADMIN) | Yes, in the case overview | No petition body, applicant identity value, staff/moderator, or assignment is returned; history is unavailable until an applicant field is validated. |
| Case listing / “assigned to me” | Case listing is implemented as an ADMIN-only server projection; F2 assignment is readable on the case detail projection. | `GET /cases` (ADMIN); `GET /cases/{case_id}` (ADMIN assignment) | Yes, as the operator queue and detail metric | It remains a complete queue, not an “assigned to me” filter; manual reassignment is deferred. |
| Human review completion | Yes, for `needs_review`, with ADMIN authorization, idempotency, and revision preconditions. | `POST /cases/{case_id}/review-completion` | Yes | This is demo ADMIN authorization, not production identity/RBAC. |
| Controlled learning feedback | Yes. Admin can explicitly save a completed, validated case as a PII-minimized dataset candidate; no automatic fine-tuning occurs. | `POST /cases/{case_id}/learning-feedback` | Yes, in AI Analizi | Dataset export, anonymization review, and model retraining remain separate future operations. |

## Runtime truth

- Base `compose.yaml` is a deterministic contract-mock stack, not real AI or
  durable business services.
- Real OCR intake, classification, validation, Jamba, correspondence, routing,
  notifications, and orchestration require the documented Compose overlays.
- Browser-facing fixed demo credentials must stay behind the local UI reverse
  proxy and must not be bundled into frontend JavaScript.
