# Architecture Session — BX-01 DLP training export

> Consumes the approved BX-01 requirement slice in
> `docs/design/DESIGN_bd84424_extensions.md`.

## Boundary and ownership

`workflow` owns a case-scoped `GET /cases/{case_id}/training-export` read
projection. It reuses the existing case-reader authorization and intake record;
no new service, database, bulk pipeline, or training job is introduced.

The response contains only redacted normalized text, stable document/case IDs,
and redaction markers. Original text and raw accepted values stay in the
operational SQL tables and are never copied into the export response.

## DLP projection

`services/workflow/dlp.py` performs deterministic, document-specific span
redaction:

- every 11-digit numeric span is replaced by `<ANON_TCKN>`;
- accepted validation values for name fields (`*-name`) are replaced by
  `<ANON_NAME>` using exact document spans;
- labelled name lines (`Ad Soyad`, `Başvuru sahibi`, `İsim`) are marked when a
  value is present;
- replacements are applied from right to left, preserving unrelated text;
- overlapping/invalid spans or non-text input fail closed with a DLP error.

No reverse map or pseudonym key exists. The replacement is irreversible.

## Response and access invariants

The contract is `contracts/schemas/case-training-export.schema.json`. USER and
ADMIN may read only an existing case's redacted projection. Missing/invalid
case IDs, unknown cases, and unauthorized callers return the existing nested
case errors. An empty text export is valid; raw source text is never a legal
response field.

Successful exports append a BX-00 `download` action with
`details.export_type="training_dataset"`; failed DLP checks append nothing.

## Verification

Pure tests cover name/TC redaction, unchanged unrelated text, overlap/input
rejection, empty text, and absence of the original value. Contract tests cover
the strict response shape and manifest route. Docker mock verification remains
mock-only.

## Decision D-BX01-01

| Option | Choice | Why |
|---|---|---|
| New DLP/training service | No | No approved pipeline or legal policy; extra topology. |
| Workflow projection + pure redactor | **Yes** | Smallest case-authorized export and reusable existing SQL boundary. |
| Shared raw export table | No | Would duplicate or expose operational PII. |
