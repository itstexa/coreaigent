# Architecture Session — BX-03A attachments

> Consumes the approved BX-03A requirements in
> `docs/design/DESIGN_bd84424_extensions.md`.

## Data model

`workflow` keeps attachment metadata in the existing PostgreSQL database:

- `case_attachments` stores case, attachment type, filename, MIME, byte size,
  opaque object-storage key, and creation time;
- `case_attachment_relations` stores manual, deterministic-rule, or
  `similarity_suggestion` pairs. Suggestions are explicitly non-authoritative.

Binary content is not copied into PostgreSQL. `storage_key` points to the
configured object/file storage adapter. Malware scanning is a production
integration point; it is not a demo dependency.

## Policy

`services/workflow/attachment_rules.json` owns request-type required attachment
types. The policy is deterministic and is never delegated to an LLM. Accepted
files are PDF, DOCX, JPG/JPEG, or PNG; MIME and extension must agree, a file is
at most 10 MiB, and a case contains at most 10 files (inclusive boundaries).

The pure policy module validates metadata, computes missing required types, and
offers filename-token similarity suggestions. A suggestion is only returned to
the caller; it never inserts an authoritative relation.

## Lifecycle and API

`GET /cases/{case_id}/attachments` returns current metadata, missing required
types, persisted relations, and suggestions to an existing case reader.
`POST /cases/{case_id}/attachments` registers an object-storage object and
persists its metadata plus an optional explicit relation. It writes the BX-00
`attachment_change` event. Mutation is allowed only for draft and waiting-for-
information states (including the repository's `draft_prepared` and
`waiting_for_user` names). Submitted states return `CASE_REVISION_REQUIRED`;
BX-05 owns the new revision path. Object keys are never returned by the read
projection.

## Verification predicates

- unsupported extensions, MIME mismatch, invalid names/keys, and 10 MiB + 1
  byte are rejected;
- exactly 10 MiB and exactly 10 case files are accepted;
- required types are selected by request type and missing values are explicit;
- manual/rule relations are authoritative; similarity suggestions are not;
- submitted case mutation does not alter current state and directs callers to
  BX-05 revision handling;
- only case readers receive attachment metadata.

## Decision

No new service, upload protocol, database, ML model, or malware dependency is
introduced. The API registers an object already placed in file/object storage;
the storage adapter can later add streaming upload and AV scanning without
changing the case projection.
