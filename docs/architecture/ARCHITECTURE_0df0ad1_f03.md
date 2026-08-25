# Architecture Session — US-108 F-03 extraction and missing information

> Linked from [ARCHITECTURE.md](ARCHITECTURE.md). This session consumes the
> approved US-108 requirements in
> [DESIGN_0df0ad1_f03.md](../design/DESIGN_0df0ad1_f03.md).

## Scope and Component Boundary

`validation` remains the existing logical service. It evolves its existing
`POST /v1/validate` contract to F-03 validation-result v3 and additionally
hosts the separately addressed case-level endpoint
`PATCH /cases/{case_id}/supplemental-information`. It is not a new extraction
container or a hidden mode of the `/v1/validate` request.

```text
classification-result v3                 supplemental PATCH
        |                                      |
        v                                      v
POST /v1/validate                    validation service
        |                              |       |
        | documentId                   |       | caseId + If-Match + idempotency key
        v                              v       v
PostgreSQL: intake_records <--- current_validation_states ---> supplemental_replays
        |                                  |
        | normalized_text                | current only
        v                                  v
rule extractor + Jamba StructuredExtractorPort --> validation-result v3 + ETag
```

The service uses `documentId` from the existing classification result to read
the normalized text and case/workflow identity from PostgreSQL. The public
request shape therefore does not regain document text. Classification must be
`classified`; a `needs_review` result is rejected with non-retryable HTTP 409
and does not create F-03 state.

## Data Models

### Entity: RequestTypeSchemaDefinition

Traces to: US-108 (docs/design/DESIGN_0df0ad1_f03.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `requestTypeId` | string | stable taxonomy ID | Required; one of the ten IDs in F-02 `Demo Belediyesi` taxonomy. |
| `schemaVersion` | string | semantic version | Required; `demo-belediyesi-fields-v1`. |
| `fields` | ordered array of FieldDefinition | entries | Required; 1..8 definitions; unique `fieldId`. |

`FieldDefinition` contains `fieldId` (lowercase kebab-case string), Turkish
`label`, `required` (boolean), `kind`, and `validator`. `kind` is one of
`free-text`, `tckn`, `phone-tr`, `date`, `document-number`, `money-try`, or
`attachment`. Canonical stored values are UTF-8 strings; money uses a decimal
TRY string with two fractional digits, and attachment is `present`.

| Request type | Required field IDs | Optional field IDs |
|---|---|---|
| `adres-bildirimi` | `applicant-name`, `tckn`, `new-address` | `phone` |
| `bilgi-edinme` | `applicant-name`, `tckn`, `request-subject` | `phone` |
| `e-imza-arizasi` | `applicant-name`, `tckn`, `problem-description` | `phone` |
| `sistem-erisim-arizasi` | `applicant-name`, `tckn`, `problem-description` | `phone` |
| `fatura-islemi` | `supplier-name`, `invoice-number`, `invoice-date`, `invoice-amount`, `invoice-attachment`* | `phone` |
| `odeme-itirazi` | `applicant-name`, `tckn`, `payment-reference`, `objection-reason` | `phone` |
| `ruhsat-basvurusu` | `applicant-name`, `tckn`, `business-address`, `business-activity` | `application-attachment`* |
| `ruhsat-sorgusu` | `applicant-name`, `tckn`, `application-number` | `phone` |
| `gurultu-sikayeti` | `applicant-name`, `tckn`, `incident-address`, `incident-date`, `incident-description` | `phone` |
| `isyeri-denetimi` | `business-name`, `business-address`, `inspection-subject` | `document-number` |

The validators are exact: `tckn` accepts 11 ASCII digits only and applies the
Turkish TCKN tenth- and eleventh-digit checksums; `phone-tr` accepts a Turkish
mobile number written as `5XXXXXXXXX`, `05XXXXXXXXX`, or `+905XXXXXXXXX` and
stores `+905XXXXXXXXX`; `date` accepts `YYYY-MM-DD` or `DD.MM.YYYY`, rejects
impossible calendar dates, and stores ISO `YYYY-MM-DD`; `money-try` accepts a
positive decimal at two fractional digits; `attachment` accepts a valid
`sourceMetadata.attachments[]` AttachmentReference and stores only `present`.
The remaining kinds require a non-blank 1..4096 Unicode-code-point value after NFC
normalization; they are extracted by Jamba and may have request-type-specific
labels but no additional hidden validation.

**Invariants** (must always hold true):

- A field definition belongs to exactly one registry schema version and one
  request type; a field ID cannot occur twice in that schema.
- A required-field decision derives only from this registry, never from Jamba
  output or caller-provided field IDs.
- The registry is repository-owned JSON loaded atomically at startup; an
  invalid registry makes `/ready` return 503 and produces no fallback schema.

**Boundary Behavior:**

- Min/Max: every registry has 1..8 fields, and every field ID/label is
  non-empty; unsupported request type returns non-retryable HTTP 409.
- Empty/Null/Zero: empty definitions, duplicate IDs, or unrecognized `kind`
  fail readiness; an empty field value is not a usable value.
- Overflow/Truncation: values beyond 4096 code points are invalid, never
  truncated; an unrecognized registry version cannot be silently substituted.

**Concurrency / Race-Scenario Analysis:**

- The loaded registry is immutable for a process lifetime. Concurrent requests
  observe the same version; deployment of a new version is a controlled
  service restart, not an in-place mixed-schema update.

### Entity: AttachmentReference

Traces to: US-106, US-108 (docs/design/DESIGN.md;
docs/design/DESIGN_0df0ad1_f03.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `sourceMetadata.attachments` | JSON array | references | Optional at intake; 1..64 elements when present. |
| `attachmentId` | opaque string | external/ingestion attachment identity | Required per element; non-blank, maximum 128 Unicode code points. |
| `filename` | nullable UTF-8 string | display name | Optional; 1..255 Unicode code points when present. |
| `contentType` | nullable ASCII string | MIME type | Optional; 1..127 characters when present. |

**Invariants** (must always hold true):

- F-01 persists `sourceMetadata` verbatim as JSONB, so the accepted
  `attachments[]` reference is authoritative F-03 input for the same immutable
  document.
- An `attachment` field becomes accepted with canonical value `present` only
  when at least one well-formed AttachmentReference exists. Attachment IDs and
  filenames are not returned in ValidationResultV3.
- Missing `attachments` is absence and therefore `missing_information` for a
  required attachment field. A present but malformed `attachments` value is
  `invalid_information` with `attachment_missing` code.

**Boundary Behavior:**

- Min/Max: empty arrays, more than 64 entries, blank IDs, or overlong ID/name/
  MIME values are malformed attachment metadata; no value is truncated.
- Empty/Null/Zero: omitted `attachments` is allowed for F-01 but does not
  satisfy a later required F-03 attachment field; null elements are malformed.
- Overflow/Truncation: oversize/invalid metadata is rejected by F-03 without
  altering current accepted attachment state.

**Concurrency / Race-Scenario Analysis:**

- F-01's immutable-document replay rule prevents a later caller from changing
  source metadata for the same document. F-03 reads the persisted JSONB value
  in its validation transaction, so a supplemental PATCH cannot forge or
  replace attachment presence.

### Entity: ExtractedField

Traces to: US-108 (docs/design/DESIGN_0df0ad1_f03.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `fieldId` | string | registry field ID | Required; defined by the selected schema. |
| `label` | UTF-8 string | Turkish display text | Required; copied from registry, never model-generated. |
| `value` | UTF-8 string | canonical field value | Required for accepted fields; 1..4096 code points after normalization. |
| `confidence` | decimal | probability-like score | Required; inclusive range 0.000..1.000. |

**Invariants** (must always hold true):

- A public accepted field contains only canonical value and confidence; source
  span, raw evidence, extractor provenance, and raw PII evidence are absent.
- A deterministic or Jamba candidate becomes an accepted field only after the
  selected registry validator succeeds.
- If a valid current value exists and a later candidate is invalid, the valid
  current value remains stored; the new invalid candidate is reported without
  replacing it.

**Boundary Behavior:**

- Min/Max: confidence 0 and 1 are valid; values outside the closed interval
  reject the extractor result as a dependency/protocol failure.
- Empty/Null/Zero: empty/null candidate values are treated as absent; 0
  confidence is still a valid reported confidence for an accepted rule result.
- Overflow/Truncation: no field value is truncated; an oversize result is
  invalid and is not persisted.

**Concurrency / Race-Scenario Analysis:**

- Candidate extraction has no write authority. Only the current-state
  transaction decides whether it becomes the field's canonical value, so a
  stale extractor result cannot overwrite a later supplemental update.

### Entity: ValidationResultV3

Traces to: US-108 (docs/design/DESIGN_0df0ad1_f03.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `schemaVersion` | literal string | protocol version | Required; exactly `3.0`. |
| `requestId` | string | request correlation | Required, non-empty. |
| `documentId` | string | document identity | Required, non-empty. |
| `caseId` | UUID string | case identity | Required, maps to F-01 intake record. |
| `workflowId` | UUID string | workflow identity | Required, maps to F-01 intake record. |
| `requestTypeId` | string | taxonomy ID | Required, selected classified request type. |
| `schemaVersionUsed` | string | registry version | Required, `demo-belediyesi-fields-v1`. |
| `extractedFields` | array of ExtractedField | entries | Required; zero or more accepted current values. |
| `missingRequiredFields` | array of `{id,label}` | entries | Required; no duplicate IDs. |
| `invalidFields` | array of `{id,label,code}` | entries | Required; code is `tckn_checksum`, `phone_format`, `date_format`, `money_format`, `attachment_missing`, or `schema_rule`. |
| `completionStatus` | enum | — | Required; `complete`, `missing_information`, or `invalid_information`. |
| `userActionRequired` | boolean | — | Required; equals `completionStatus != complete`. |

**Invariants** (must always hold true):

- `complete` means both missing and invalid arrays are empty; every required
  registry field has one accepted current value.
- `missing_information` means at least one required field has no candidate or
  usable current value and no invalid candidate takes priority.
- `invalid_information` means at least one candidate is present but violates a
  schema validator. It takes priority over `missing_information` when both
  conditions occur.
- Display labels come only from the versioned registry. The result never
  exposes `topCandidates`, evidence spans, provenance, or raw source text.

**Boundary Behavior:**

- Min/Max: arrays may be empty; `requestId`, `documentId`, and IDs are
  non-empty; exactly one completion state is emitted.
- Empty/Null/Zero: no extracted fields with no invalid candidates produces
  `missing_information` if any required field exists; an empty optional field
  never blocks completion by itself.
- Overflow/Truncation: results exceeding schema limits are rejected before
  persistence; client-visible values are never silently shortened.

**Concurrency / Race-Scenario Analysis:**

- Re-running validation on unchanged current state returns the same canonical
  result and does not increment its revision. Validation serializes against a
  concurrent supplemental PATCH using the case row lock.

### Entity: CurrentValidationState

Traces to: US-108 (docs/design/DESIGN_0df0ad1_f03.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `case_id` | UUID | case identity | Primary key; exactly one row per case. |
| `document_id` | string | document identity | Required; unique and foreign-keyed to `intake_records`. |
| `workflow_id` | UUID | workflow identity | Required; copied from intake. |
| `request_type_id` | string | taxonomy ID | Required; must equal the classified current request type. |
| `schema_version` | string | registry version | Required. |
| `accepted_fields` | JSONB object | field-id → `{value,confidence}` | Required; current values only, keys must be registry fields. |
| `missing_fields` | JSONB array | `{id,label}` entries | Required; current result only. |
| `invalid_fields` | JSONB array | `{id,label,code}` entries | Required; current result only. |
| `completion_status` | enum | — | Required; same three ValidationResultV3 values. |
| `revision` | positive bigint | optimistic version | Required; starts at 1, increments exactly once per changed current state. |
| `updated_at` | timestamptz | UTC instant | Required; set by PostgreSQL. |

**Invariants** (must always hold true):

- PostgreSQL is the sole authoritative location for current F-03 values and
  result; no historical validation-result rows are retained.
- `case_id`, `document_id`, and `workflow_id` must agree with the intake and
  current-classification rows in the same transaction.
- `accepted_fields`, missing fields, invalid fields, completion status, and
  revision commit atomically. A `complete` row has empty missing/invalid arrays.

**Boundary Behavior:**

- Min/Max: revision starts at 1 and cannot be zero/negative; one row only per
  case/document; accepted field values obey the registry maximum.
- Empty/Null/Zero: accepted fields may be `{}` only for an incomplete case;
  missing/invalid arrays may be empty only as permitted by completion status.
- Overflow/Truncation: revision overflow is a PostgreSQL error and fails the
  request without mutation; JSON is validated before write and never trimmed.

**Concurrency / Race-Scenario Analysis:**

- `SELECT ... FOR UPDATE` on this row (or the intake row before its first
  creation) serializes validation and supplemental updates. The transaction
  compares the expected revision before it writes, eliminating lost updates.

### Entity: SupplementalInformationRequest

Traces to: US-108 (docs/design/DESIGN_0df0ad1_f03.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| path `case_id` | UUID string | case identity | Required; existing case with F-03 state. |
| `Authorization` | HTTP Bearer credential | — | Required; evaluated by CaseAccessPort; never persisted or logged. |
| `Idempotency-Key` | UUID string | replay identity | Required; one stable key per intended mutation. |
| `If-Match` | quoted positive integer | CurrentValidationState revision | Required; exact current ETag value. |
| body `fields` | JSON object | field-id → UTF-8 string | Required; 1..8 known field IDs; each non-blank and at most 4096 code points. |

**Invariants** (must always hold true):

- The endpoint is exactly `PATCH /cases/{case_id}/supplemental-information`;
  it is distinct from `/v1/validate`.
- A valid submitted value replaces that field's current accepted value; an
  invalid submitted value never erases a prior valid accepted value.
- The response is the post-request ValidationResultV3 and includes quoted
  `ETag` equal to its revision.

**Boundary Behavior:**

- Min/Max: a body has 1..8 known fields; empty, duplicate-after-normalization,
  unknown, or oversize fields produce HTTP 400 without mutation.
- Empty/Null/Zero: missing/malformed bearer credentials produce 401; omitted
  `Idempotency-Key` or `If-Match` produces 400 or 428 respectively; unknown
  case produces 404.
- Overflow/Truncation: malformed/non-positive/non-quoted revisions are 400;
  stale revision is 412; values are never truncated.

**Concurrency / Race-Scenario Analysis:**

- Same case + two current `If-Match` PATCHes: only one takes the row lock and
  commits; the other observes the changed revision and returns 412.
- Same key + identical method/path/body/case: replay ledger returns the first
  response without a second merge, validation, or revision change.
- Same key + different fingerprint: returns 409 without mutation.

### Entity: SupplementalReplay

Traces to: US-108 (docs/design/DESIGN_0df0ad1_f03.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `case_id` | UUID | case identity | Composite primary-key component. |
| `idempotency_key` | UUID | replay identity | Composite primary-key component. |
| `request_fingerprint` | SHA-256 lowercase hex string | content digest | Required; exact 64 characters over case, method, normalized body, and expected revision. |
| `response_status` | integer | HTTP status | Required; successful canonical response status. |
| `response_body` | JSONB object | ValidationResultV3 | Required; immutable canonical replay body. |
| `etag` | quoted positive integer | revision | Required; canonical replay ETag. |
| `created_at` | timestamptz | UTC instant | Required; PostgreSQL default. |

**Invariants** (must always hold true):

- This is a protocol replay ledger, not F-03 result history. It exists solely
  to implement the required idempotent PATCH behavior.
- A successful mutation and its replay record commit in the same transaction.
- A replay record never stores authorization credentials, source text, spans,
  provenance, or raw evidence.

**Boundary Behavior:**

- Min/Max: digest is exactly 64 lowercase hexadecimal characters and ETag is a
  quoted positive integer; only successful requests create records.
- Empty/Null/Zero: no record is created on 400/401/403/404/409/412; a missing
  replay record means a first execution.
- Overflow/Truncation: no response body is truncated; persistence failure
  fails the PATCH and rolls back state/replay record together.

**Concurrency / Race-Scenario Analysis:**

- Its unique composite key is acquired within the same case transaction. Two
  simultaneous identical first requests produce one mutation and one replay;
  the loser reads the canonical stored response.

### Entity: StructuredExtractorPort and CaseAccessPort

Traces to: US-108 (docs/design/DESIGN_0df0ad1_f03.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `StructuredExtractorPort.extract` | operation | invocation | Receives normalized text plus selected field definitions and returns typed candidate strings/confidence only. |
| `CaseAccessPort.allowed` | operation | boolean result | Receives bearer credential and case UUID; returns only allow/deny. |

**Invariants** (must always hold true):

- Rule extraction/validation runs locally before and after Jamba extraction;
  Jamba cannot choose field definitions or bypass validators.
- The real port invokes the existing `llm` service's Jamba runtime with a
  server-owned structured JSON prompt; it neither trusts model field IDs nor
  exposes prompt/evidence to the client.
- The access port never persists bearer credentials. An unavailable Jamba port
  yields controlled retryable dependency failure and does not turn fields into
  `missing_information`.

**Boundary Behavior:**

- Min/Max: candidate count cannot exceed the registry field count; confidence
  is 0..1; output containing unknown fields is rejected.
- Empty/Null/Zero: empty Jamba output is a dependency failure, not proof a
  field is missing; absent/invalid credential is denied before database lookup.
- Overflow/Truncation: overlong candidate values are rejected before any state
  mutation; prompts and responses use the LLM service's configured limits.

**Concurrency / Race-Scenario Analysis:**

- Extraction runs before the final row-lock transaction. The transaction
  rechecks revision/current values before persisting candidates, so slow Jamba
  work cannot overwrite a concurrent PATCH. Case authorization is evaluated on
  every PATCH, never cached in state.

## Technology / Design Decisions

### Decision D-130: Registry representation

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Versioned repository JSON alongside F-02 taxonomy | Reviewable, deterministic, no administration service, aligns with demo taxonomy. | Registry edits require deployment/restart. | ✅ |
| Owner-managed PostgreSQL registry | Runtime edits possible. | Requires an unapproved administration/authorship workflow and migration path. | ❌ |
| Hard-code fields in Python conditionals | Small first diff. | Versioning, validation, and review are opaque and duplicate taxonomy logic. | ❌ |

**Why the first option:** F-02 already establishes repository-owned versioned
demo data, and no owner-facing registry administration capability is approved.

**Why not PostgreSQL registry:** Runtime mutability has no approved governance
or operator workflow.

**Why not hard-coded conditionals:** They cannot safely act as the explicit,
versioned authoritative schema registry required by F-03.

### Decision D-131: Hybrid extraction boundary

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Deterministic extractors/validators plus Jamba StructuredExtractorPort | Validates TCKN/phone/date exactly while extracting semantic text fields. | Requires a Jamba dependency for semantic-field production. | ✅ |
| Jamba-only extraction and validation | One model interface. | Cannot provide deterministic checksum/format assurance requested for invalid values. | ❌ |
| Rules only | Fast and GPU-independent. | Cannot extract the approved semantic fields from natural Turkish documents. | ❌ |

**Why the first option:** It is the human-approved division of responsibility.

**Why not Jamba-only:** The TCKN and format examples require deterministic
validation independent of model confidence.

**Why not rules only:** The user explicitly assigned remaining semantic fields
to Jamba.

### Decision D-132: Validation topology and CI mode

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Real validation service with injected deterministic StructuredExtractorPort in CPU Docker/CI; real Jamba port in GPU smoke | Tests actual persistence, contracts, and concurrency without pretending a mock is real Jamba. | Requires a separate GPU smoke for semantic extraction. | ✅ |
| Require GPU Jamba for every Docker/CI test | Always exercises production model. | Makes ordinary CI hardware-dependent and slow. | ❌ |
| Use rules-only in production and CI | Simplifies deployment. | Violates the approved Jamba semantic extraction behavior. | ❌ |

**Why the first option:** It follows the existing Jamba test partition: a
clearly injected test double proves service behavior, while GPU smoke proves
the real model path.

**Why not GPU everywhere:** Repository baseline Docker verification is designed
to run without a GPU.

**Why not rules-only production:** It removes an explicitly required capability.

### Decision D-133: Supplemental endpoint placement

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Separate PATCH route hosted by validation service | Keeps state/extraction ownership local while honoring a distinct case-level API. | Validation container owns two public routes. | ✅ |
| New supplemental-information service/container | Strong isolation. | Adds an unapproved service topology and duplicate state coordination. | ❌ |
| Add supplemental fields to `POST /v1/validate` | One route. | Explicitly rejected; mixes analysis with user mutation. | ❌ |

**Why the first option:** The user requires a separate endpoint, not a separate
container; the same service owns the state it must atomically update.

**Why not a new service:** Cross-service transactional state would complicate
the authoritative current-state rule without approved benefit.

**Why not `/v1/validate`:** The user explicitly said not to put supplemental
information inside validation endpoint.

### Decision D-134: PostgreSQL concurrency and replay

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Row lock + `If-Match` revision + atomic idempotency replay ledger | Prevents lost updates and gives deterministic retry behavior. | Requires two current-state tables and transactional code. | ✅ |
| Last writer wins | Small implementation. | Silently loses a concurrent user update. | ❌ |
| Stateless PATCH without idempotency record | No replay storage. | Retries can reapply mutation and increment revision. | ❌ |

**Why the first option:** It implements the required ETag and idempotency-key
contract while keeping PostgreSQL authoritative.

**Why not last writer wins:** It conflicts with explicit revision preconditions.

**Why not stateless PATCH:** It cannot guarantee replay without repeated
validation/mutation.

### Decision D-135: Public extraction visibility

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Return canonical field values and confidence; omit evidence/provenance/spans | Supports review while avoiding unnecessary raw-source disclosure. | Less client-side explainability. | ✅ |
| Return confidence plus raw evidence/provenance/spans | Rich auditing UI. | The operator questioned client evidence exposure; adds PII disclosure. | ❌ |
| Return no confidence | Smallest response. | Discards the explicitly allowed confidence signal. | ❌ |

**Why the first option:** It directly records the operator's confidence-only
decision and keeps evidence internal.

**Why not raw evidence:** It is not needed by the client and increases PII
exposure.

**Why not omit confidence:** The operator explicitly allowed it in the public
result.

### Decision D-136: Attachment-presence source

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Versioned `sourceMetadata.attachments[]` references persisted by F-01 | Uses the approved current intake boundary and PostgreSQL source of truth without new upload topology. | Proves presence of an ingestion reference, not binary-content inspection. | ✅ |
| New attachment-upload/intake contract | Can validate/upload binaries directly. | Expands F-01 and Docker/CI contracts beyond the approved scope. | ❌ |
| Make all attachment fields optional | Avoids attachment metadata modelling. | Contradicts the required-invoice attachment demo requirement. | ❌ |

**Why the first option:** The operator approved `sourceMetadata.attachments[]`
as the authoritative reference and F-01 already preserves that metadata
idempotently in PostgreSQL.

**Why not a new upload contract:** No binary upload capability is required for
this F-03 pass.

**Why not optional attachment fields:** It would hide a missing mandatory
invoice/application attachment instead of asking the user to supply it.

## Contract Migration and Verification

- `validation-result` becomes schema `3.0`; its existing identity fields are
  retained and it adds case, request-type, extracted, missing, invalid, and
  completion data. `POST /v1/validate` keeps its path and continues accepting
  `classification-result` v3.
- The HTTP manifest retains `validation.path=/v1/validate` and adds validation
  `additionalEndpoints` metadata for the PATCH route and its header/body
  schemas. Contract validation must permit the explicit `/cases/{case_id}/...`
  route without weakening the existing `/v1/` service-route check.
- Add schemas for `supplemental-information-request` and its documented 400,
  401, 403, 404, 409, 412 error envelope behavior. The successful PATCH body
  is validation-result v3; its ETag is tested as a response header.
- Extend the existing deterministic mocks and all 58 golden scenarios only as
  necessary to preserve the mock baseline's scenario count and explicit mock
  identity. The real validation Docker overlay uses PostgreSQL plus the
  injected CPU test extractor; it is not called a real Jamba result.
- Real Jamba GPU smoke sends a field-schema constrained Turkish document to the
  real validation service and asserts Jamba-produced semantic fields still pass
  deterministic validation before current-state persistence.
- Tests must falsify: invalid TCKN checksum, invalid phone/date, absent versus
  invalid distinction, optional absence, current-only replacement, unchanged
  revalidation, 400/401/403/404/409/412 no-mutation paths, same-key replay,
  same-key conflict, and two concurrent revision updates.

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| AQ-109 | The current F-01 text intake has no authoritative attachment reference, yet the approved demo registry includes invoice/application attachment fields. Should attachment presence come from a versioned `sourceMetadata` reference, a new intake/upload contract, or should those F-03 fields be optional until an attachment capability is approved? | solution-architect | Resolved | Human operator confirmed `sourceMetadata.attachments[]` as the authoritative attachment reference (2026-08-25). |
