# Architecture Session — BX-07 citizen document draft

The existing citizen portal and `workflow` boundary own a temporary draft
projection. Local templates/configuration deterministically define document
type and mandatory fields; optional Jamba generation may fill prose but cannot
change required structure or claim legal authority. Submission remains the
existing F-01 intake path.

## Model and invariants

- Supported types are `petition/request`, `complaint`, and
  `information_request`.
- A draft has `draft_id`, `document_type`, editable structured fields/plain
  text, template version, and `temporary=true` until submitted.
- Missing mandatory fields reject submission but preserve the draft; unknown
  document types are rejected without creating a case.
- No signature, dispatch, PDF/DOCX export, or legal-finality claim is produced.
- Draft content is user-editable and deterministic formatting is authoritative;
  model prose is a suggestion only.

## Boundary behavior and concurrency

Empty/oversized text and malformed fields return 4xx. Draft updates use the
existing owner/session boundary; the latest draft version wins for the same
session. F-01 creates the durable case exactly once on submit, after which BX-05
owns edits and revision history.

## Technology choice

Reuse the frontend/API and local template JSON rather than adding a document
service or asynchronous queue. This keeps the MVP testable and preserves the
existing intake contract.
