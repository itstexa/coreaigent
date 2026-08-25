# Architecture Session — US-107 F-02 hierarchical classification

> Linked from [ARCHITECTURE.md](ARCHITECTURE.md). This session consumes the
> human-approved US-107 requirements in [DESIGN.md](../design/DESIGN.md).
> The suffix avoids colliding with the already-linked F-01 architecture session
> created from the same uncommitted base revision.

## Scope and component boundary

F-02 replaces the baseline mock at the existing `classification` hostname with
a real FastAPI API and adds a separate `classification-worker` process from the
same image. The worker consumes the F-01 PostgreSQL `process_document` outbox
job. It invokes the same classification application service exposed at
`POST /v1/classify`, then atomically upserts the current classification and
marks its job complete. No Redis, new classification endpoint, or external
municipal-system integration is introduced.

```text
POST /v1/ocr ──transaction──> intake_records + process_document(pending)
                                                |
                                                | FOR UPDATE SKIP LOCKED + lease
                                                v
                                  classification-worker (same image)
                                                |
                                                v
                                  classification core + Demo Belediyesi v1
                                                |
                                                v
                          current_classifications upsert + job completed
                                                |
                                                v
                           PostgreSQL authoritative current result only
```

## Data Models

### Entity: DemoMunicipalityTaxonomyV1

Traces to: US-107 (docs/design/DESIGN.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `taxonomyVersion` | literal string | taxonomy version | Required; initial value `demo-belediyesi-v1`. |
| `departments[].id` | lowercase slug string | stable identifier | Required; unique and immutable within the version. |
| `departments[].label` | UTF-8 string | Unicode code points | Required, non-empty Turkish display label. |
| `units[].id` | lowercase slug string | stable identifier | Required; unique and immutable within the version. |
| `units[].departmentId` | slug string | foreign-key identifier | Required; references a department in the same version. |
| `requestTypes[].id` | lowercase slug string | stable identifier | Required; unique and immutable within the version. |
| `requestTypes[].unitId` | slug string | foreign-key identifier | Required; references a unit in the same version. |
| `requestTypes[].keywords` | array of UTF-8 strings | matching phrases | Required; non-empty, distinct after scorer normalization. |
| `requestTypes[].documentType` | enum | legacy document kind | Required; one existing document-kind enum value for downstream compatibility. |

The committed `Demo Belediyesi` fixture contains at least the following valid
chains and matching concepts; it is synthetic demo data, not a claim about a
real municipality's organisation:

| Department | Unit | Request types / example concepts |
|---|---|---|
| Citizen Services | White Desk | address-change notice; information request |
| Information Technologies | Digital Services | e-signature incident; system-access incident |
| Financial Services | Revenue and Accrual | invoice processing; payment-objection |
| Zoning and Urbanism | Licence Services | licence application; licence-status enquiry |
| Municipal Police | Inspection | noise complaint; workplace-inspection report |

**Invariants** (must always hold true):

- A unit belongs to exactly one department and a request type belongs to
  exactly one unit in the same `taxonomyVersion`.
- IDs, parent references, and normalized keywords are unique; an invalid
  parent-child edge prevents the taxonomy from becoming ready.
- Fixture loading is read-only and versioned from the repository; request text
  never mutates taxonomy data.

**Boundary Behavior:**

- Min/Max: every request type has at least one keyword; labels and IDs are
  non-empty. The initial fixture has no implementation-imposed upper count.
- Empty/Null/Zero: an absent file, empty version, empty array, missing parent,
  or duplicate ID leaves the API non-ready and the worker must not complete a
  job from that taxonomy.
- Overflow/Truncation: taxonomy JSON is parsed in full and rejected on invalid
  shape; no label, keyword, or parent list is silently truncated.

**Concurrency / Race-Scenario Analysis:**

- API and worker load an immutable in-process snapshot after validation.
  Concurrent workers cannot see a partly parsed fixture. A new fixture version
  requires a process restart/deployment and therefore cannot change a running
  job's taxonomy snapshot.

### Entity: ClassificationResultV3

Traces to: US-107 (docs/design/DESIGN.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `schemaVersion` | literal string | protocol version | Required; exactly `3.0`. |
| `requestId`, `documentId`, `workflowId` | opaque strings | trace identities | Required, non-empty; copied from the OCR result. |
| `status` | enum | — | Required; `classified` or `needs_review`. |
| `department`, `unit`, `requestType` | nullable taxonomy-node object | stable taxonomy identity | A valid best provisional chain is returned when one exists; all three are null only when no chain matches. |
| `confidence` | decimal | ratio | Required; inclusive `0.0..1.0`. |
| `taxonomyVersion` | string | taxonomy version | Required for all non-error results. |
| `classifierVersion` | string | classifier implementation version | Required, non-empty. |
| `classificationReason` | UTF-8 string | Unicode code points | Required, bounded diagnostic explanation without source-text echo. |

`topCandidates` is deliberately absent. The result exposes exactly one chain:
among chains with confidence strictly greater than `0.80`, it selects the
largest score; exact score ties sort by stable request-type ID ascending.

**Invariants** (must always hold true):

- `classified` has all three taxonomy nodes, a valid parent chain, and
  `confidence > 0.80`.
- The selected unit's `departmentId` equals `department.id`; the selected
  request type's `unitId` equals `unit.id`.
- A result never returns a partial or cross-parent chain, and it never contains
  `topCandidates`.
- `needs_review` never triggers automatic routing, regardless of whether its
  best score is exactly `0.80` or lower.
- `needs_review` returns the one valid best provisional chain when a candidate
  exists; a no-match result has confidence `0.0` and all hierarchy nodes null.

**Boundary Behavior:**

- Min/Max: `0.80` is `needs_review`; `0.81` is `classified`; `0.0` and `1.0`
  are representable. Values outside `0..1` are invalid producer output.
- Empty/Null/Zero: a no-match score of `0.0` is `needs_review` with all three
  hierarchy nodes null. A non-null provisional chain must be complete and
  valid. Required trace/version fields may never be null.
- Overflow/Truncation: reason text has an implementation bound and is rejected
  rather than silently truncated if the bound is exceeded.

**Concurrency / Race-Scenario Analysis:**

- Candidate ordering is pure and deterministic for identical text plus
  taxonomy/classifier versions. Concurrent calls can calculate the same result
  safely; authoritative persistence is controlled by CurrentClassification.

### Entity: CurrentClassification

Traces to: US-107 (docs/design/DESIGN.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `document_id` | PostgreSQL `text` | document identity | Primary key and foreign key to `intake_records.document_id`. |
| `case_id` | PostgreSQL `uuid` | case identity | Required; must equal the referenced intake record's case. |
| `workflow_id` | PostgreSQL `uuid` | workflow identity | Required; must equal the referenced intake record's workflow. |
| `status` | PostgreSQL enum/text | — | Required; mirrors ClassificationResultV3 status. |
| `department_id`, `unit_id`, `request_type_id` | nullable PostgreSQL `text` | taxonomy identity | Store the best valid chain; all null only for a no-match result. |
| `department_label`, `unit_label`, `request_type_label` | nullable PostgreSQL `text` | Unicode code points | Must accompany their corresponding IDs. |
| `confidence` | PostgreSQL `numeric(4,3)` | ratio | Required; `0.000..1.000`. |
| `taxonomy_version`, `classifier_version` | PostgreSQL `text` | version | Required, non-empty. |
| `classification_reason` | PostgreSQL `text` | Unicode code points | Required, non-empty. |
| `updated_at` | PostgreSQL `timestamptz` | UTC instant | Required; database-generated. |

**Invariants** (must always hold true):

- At most one row exists for every document/case; the table is the PostgreSQL
  authoritative source for the current classification and retains no history.
- A `classified` row persists a valid complete chain with confidence `> 0.80`.
- A row's case/workflow IDs match `intake_records`; a mismatched identifier
  rolls back persistence.

**Boundary Behavior:**

- Min/Max: `numeric(4,3)` stores 0.000 through 1.000 exactly; out-of-range
  confidence, blank versions, or incomplete classified chain fail the write.
- Empty/Null/Zero: status and confidence are non-null. Hierarchy columns are
  all null only for a `needs_review` no-match result; `updated_at` is
  database-generated.
- Overflow/Truncation: long values fail database/validation constraints rather
  than being silently shortened.

**Concurrency / Race-Scenario Analysis:**

- `INSERT ... ON CONFLICT (document_id) DO UPDATE` replaces the one current
  row. A later successful reclassification wins; no historical row is created.
- The worker's upsert and outbox completion occur in one transaction, so a
  crash produces either neither commit or both commits. Reclaimed work can
  safely repeat the idempotent upsert.

### Entity: ProcessDocumentClaim

Traces to: US-106, US-107 (docs/design/DESIGN.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `job_id` | PostgreSQL `uuid` | job identity | Existing durable outbox primary key. |
| `document_id` | PostgreSQL `text` | document identity | Existing unique referenced intake record. |
| `state` | enum | — | Existing `pending`, `claimed`, or `completed`. |
| `attempt_count` | non-negative integer | attempts | Incremented on every successful claim. |
| `claimed_until` | nullable `timestamptz` | UTC instant | A finite worker lease; null only when unclaimed/completed. |

**Invariants** (must always hold true):

- Only one worker holds a non-expired claim for a job.
- A job becomes `completed` only in the same transaction that persists its
  CurrentClassification row.
- A worker failure, unavailable taxonomy, or failed classification leaves the
  job recoverable: it is returned to `pending` or is reclaimable after lease
  expiry; it is never marked `completed`.

**Boundary Behavior:**

- Min/Max: claim attempts start at zero and cannot be negative; lease duration
  is a positive worker configuration duration. There is no destructive retry
  ceiling in F-02 because pending work must survive restarts.
- Empty/Null/Zero: a null lease only represents an unclaimed/completed job;
  `document_id` and `state` are never null.
- Overflow/Truncation: increment overflow or invalid state transition aborts
  the transaction and preserves durable work rather than completing it.

**Concurrency / Race-Scenario Analysis:**

- Claim uses `FOR UPDATE SKIP LOCKED` over `pending` plus expired `claimed`
  rows. Multiple worker replicas never process a non-expired claim together.
- If a worker dies after classification but before its transaction commits, an
  expired lease allows reprocessing; the document-key upsert leaves one current
  result and the eventual completion happens once.

## Technology / Design Decisions

### Decision D-114: Evolve the existing classification contract

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Keep `POST /v1/classify`; upgrade `classification-result` and dependent consumers to v3 | Retains the fixed service/route while making the hierarchical breaking change explicit. | Mocks, schemas, scenarios, workflow adapters, and CI must migrate together. | ✅ |
| Add a new classification endpoint | Allows parallel shapes. | Violates the approved single-boundary decision. | ❌ |
| Add hierarchy fields to the v2 strict schema | Smallest textual edit. | Breaks v2 consumers without a distinguishable version. | ❌ |

**Why the first option:** It implements the approved existing-route evolution
and preserves a verifiable contract graph.

**Why not a new endpoint:** The operator explicitly rejected it.

**Why not mutate v2:** `additionalProperties: false` makes this a breaking
change; the version must advertise it.

### Decision D-115: Repository-owned JSON taxonomy fixture

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Versioned JSON fixture packaged with the classification image | Reproducible demo, reviewable IDs/parents/keywords, no extra runtime dependency. | Taxonomy edits require a build/deploy. | ✅ |
| PostgreSQL-managed taxonomy editor | Runtime updates and central administration. | Adds owner/editor/audit scope not requested for the demo. | ❌ |
| External municipal taxonomy API | Could later be authoritative. | No supplied API, availability risk, and makes the demo non-reproducible. | ❌ |

**Why the first option:** The approved source is a repository-owned demo
taxonomy, so a packaged versioned file is the smallest authoritative source.

**Why not a database editor:** The user requested a demo taxonomy, not a
taxonomy-management product.

**Why not an external API:** No authority or contract for one was supplied.

### Decision D-116: Deterministic taxonomy keyword classifier for the demo

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Normalized keyword/phrase scoring over the versioned fixture | Deterministic, offline, fast, and exactly testable at 0.80/0.81 boundaries. | Demo score is not a statistically calibrated ML confidence. | ✅ |
| Jamba-based classification | Richer semantic understanding. | GPU/model readiness couples document processing to optional heavy inference. | ❌ |
| Embedding/retrieval classifier | Potential semantic recall. | Adds model/index lifecycle and calibration work outside the approved demo scope. | ❌ |

**Why the first option:** F-02 requires a working, reproducible demo taxonomy
flow now; it does not mandate an ML classifier. `classifierVersion` makes the
demo scorer visible rather than representing it as calibrated probability.

**Why not Jamba:** It expands the durable pipeline's availability dependency
beyond the approved classification scope.

**Why not embeddings:** It requires an additional persistent index and a
calibration decision before a demo can run.

### Decision D-117: Separate durable worker, shared classification image

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| `classification` API plus `classification-worker` Compose service from one image | Isolates HTTP readiness from polling, supports crash recovery and safe horizontal workers. | Adds one process/service entry. | ✅ |
| FastAPI in-process background task | Fewer Compose entries. | Process restart can interrupt dispatch ownership and complicates lease recovery. | ❌ |
| OCR service dispatches classification synchronously | Fewer components. | Couples intake latency/availability to classification and defeats durable decoupling. | ❌ |

**Why the first option:** It is the smallest topology that executes the
approved durable outbox independently of intake and still shares one classifier
implementation.

**Why not a background task:** It cannot own durable worker lifecycle cleanly.

**Why not synchronous OCR dispatch:** It makes a successfully persisted intake
depend on downstream availability.

### Decision D-118: Transactional current-result completion

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Upsert CurrentClassification and update the claimed job to `completed` in one PostgreSQL transaction | Enforces no completed-without-result state and makes retry idempotent. | Requires the worker to own database writes. | ✅ |
| Persist result then complete job in separate transactions | Simpler individual statements. | Crash can leave a result with a forever-pending job. | ❌ |
| Mark complete before persistence | Shorter critical section. | Violates the explicit durability predicate and can lose work. | ❌ |

**Why the first option:** It directly satisfies the user's completion rule.

**Why not separate transactions:** Recovery would require a new reconciliation
policy that the atomic write avoids.

**Why not completion first:** A restart could lose the authoritative result.

### Decision D-119: Real-classification Docker/CI overlay

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Add a classification overlay on top of the existing OCR/PostgreSQL overlay, plus a dedicated acceptance runner and CI job | Tests real durable flow while retaining the required lightweight mock baseline. | Adds build time and a second real-service job. | ✅ |
| Replace classification in the baseline mock Compose file | One apparent topology. | Breaks deterministic baseline isolation and changes its purpose. | ❌ |
| Unit-test the worker only | Fast. | Does not prove Compose, PostgreSQL leases, or restart recovery. | ❌ |

**Why the first option:** It follows the repository's distinction between mock
contract verification and a real service implementation.

**Why not replace baseline mocks:** Mocks must remain clearly mocks.

**Why not unit tests alone:** The user asked for a fully working operation,
including durable execution.

### Decision D-120: Review-result representation

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Always return `needs_review`; include one valid provisional chain when it exists, otherwise all hierarchy fields are null | Gives reviewers useful context without routing on an unapproved result. | Consumers must treat populated review fields as provisional. | ✅ |
| Return `unclassified` when no chain matches | Distinguishes no-match from low confidence. | Contradicts the operator's decision to use `needs_review` below the threshold. | ❌ |
| Hide every provisional chain | Avoids displaying uncertainty. | Discards useful reviewer context explicitly requested by the operator. | ❌ |

**Why the first option:** It records the operator's two resolutions: no-match
is still `needs_review`, and a temporary valid best guess is useful to show.

**Why not `unclassified`:** The current chosen review workflow covers the
no-match case too.

**Why not hide all candidates:** A valid provisional hierarchy helps a human
reviewer, while the status prevents automatic routing.

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| AQ-107 | The approved F-02 feature still permits `unclassified` for no sufficient class, while the operator's threshold resolution says `0.80` and lower is `needs_review`. If no valid taxonomy chain matches at all (confidence 0.0), should v3 return `needs_review` or `unclassified`? | solution-architect | Resolved | Human operator: “needs to review” (2026-08-25). No-match is `needs_review`; `unclassified` is not emitted by v3. |
| AQ-108 | For a `needs_review` or `unclassified` result, should `department`, `unit`, and `requestType` expose the single best provisional chain, or must all three fields be `null` to avoid presenting an unapproved routing result? | solution-architect | Resolved | Human operator: “geçici tahmin varsa göstersin” (2026-08-25). Return the one valid best provisional chain; if no candidate exists, all three hierarchy fields are null. |
