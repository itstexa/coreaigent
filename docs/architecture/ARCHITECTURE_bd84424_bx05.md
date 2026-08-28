# Architecture Session — BX-05 case revision editing

> Consumes the approved BX-05 requirements in
> [`docs/design/DESIGN_bd84424_extensions.md`](../design/DESIGN_bd84424_extensions.md).
> The existing workflow PostgreSQL schema and contract boundaries remain the
> system of record; this session adds no service.

## Boundary and processing flow

`workflow` owns the case-scoped edit command and revision projection. The
command uses the existing case-reader authorization (the shared demo USER is
the owner surrogate until a per-user identity exists), then sends changed text
through the existing OCR/classification/validation contracts. Services do not
write one another's private tables.

```text
case reader + If-Match
  → workflow: validate state, create immutable revision snapshot
  → existing OCR → classification (when affected) → validation contracts
  → current case projection / existing workflow workers
```

The original revision and all previous correspondence, assignment, and action
events remain readable. A revision does not mutate an earlier document row.

## Data models

### Entity: CaseRevision

Traces to: BX-05 (approved design session).

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `case_id` | UUID | — | Required; stable case identity. |
| `revision` | positive integer | revision number | Required; starts at 1 and increases by exactly one for each accepted edit. |
| `parent_revision` | positive integer or null | revision number | Null only for the initial revision; otherwise the immediately previous current revision. |
| `document_id` | non-empty string | — | Required; immutable intake/document snapshot for this revision. |
| `actor_id` | non-empty string | — | Required; authenticated editor or system actor. |
| `created_at` | timestamp with timezone | UTC | Required; append timestamp, never rewritten. |
| `change_kind` | enum | — | `initial` or `petition_edit`. |

**Invariants**

- `(case_id, revision)` and `document_id` are unique.
- `current_case_states.revision` identifies the only current revision and is
  never lower than a retained revision.
- A successful edit has exactly one `petition_edit` action-log event and one
  immutable revision row.

**Boundary Behavior**

- Revision 1 is valid; revision 0, negative, gaps, and duplicate numbers are
  rejected.
- A missing case, actor, or edited content is rejected without creating a row.
- There is no truncation: text and structured values are passed through the
  existing contract limits; an over-limit request is rejected.

**Concurrency / Race-Scenario Analysis**

- Two edits using the same `If-Match` revision lock the current case row; one
  commits the next revision and the other receives `412 CASE_REVISION_CONFLICT`.
- A retried request with the same idempotency key returns its stored result;
  the unique case/revision constraint prevents a duplicate revision.

### Entity: RevisionContentSnapshot

Traces to: BX-05 approved scope decisions and BX-03A attachment handoff.

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `document_id` | non-empty string | — | Required; references the immutable intake snapshot. |
| `original_text` | UTF-8 string | Unicode scalar values | Required operational source for this revision; never overwritten. |
| `normalized_text` | UTF-8 string | Unicode scalar values | Required projection consumed by classification/validation. |
| `structured_fields` | JSON object | — | Required, possibly empty; only registry-known fields may be sent to validation. |
| `attachment_ids` | array of UUIDs | attachment references | May be empty; each referenced attachment is retained by the attachment owner. |

**Invariants**

- A snapshot is immutable after its revision is accepted; later edits create a
  new document/snapshot.
- Classification is not a writable snapshot field. It is a result produced by
  the classification contract from the changed content.
- An attachment change is represented by the new revision's attachment set;
  existing attachment metadata and binary storage are not rewritten.

**Boundary Behavior**

- Empty text follows the existing OCR/intake contract and is rejected there;
  an empty structured-field object and zero attachments are valid.
- Unknown structured field IDs and invalid attachment references reject the
  edit atomically.
- Attachments keep BX-03A's file/count/MIME limits; BX-05 adds no second limit.

**Concurrency / Race-Scenario Analysis**

- Snapshot insertion and the current-revision pointer update commit in one SQL
  transaction after the row lock; a failed downstream call leaves no partial
  current revision.
- A downstream retry is keyed by the new document/revision and existing
  contract idempotency rules, so it cannot replace a newer revision.

### Predicate: Editability and derived processing

Traces to: BX-05 Gherkin scenarios and OQ-178…OQ-181 resolutions.

- Editable directly: `draft`/`draft_prepared` and
  `waiting_for_information`/`waiting_for_user` projections.
- `review`/`needs_review` and `routed` accept an edit only as a new BX-05
  revision. A resolution mark or terminal `completed`/`closed` projection is
  immutable; no edit is accepted.
- Text, structured fields, and attachments are editable. Classification is
  never directly writable. If classification inputs changed, classification
  and routing are re-analyzed; the current owner is retained, SLA start is
  unchanged, priority may be recalculated, and prior correspondence is never
  rewritten.
- Prior revisions remain visible to authorized staff until ordinary case
  retention/deletion. Restore is not part of this slice.

**Boundary Behavior and concurrency**

- Missing `If-Match` is rejected with the existing precondition error; stale
  values return 412; terminal-state edits return a conflict and create no row.
- The edit decision and revision allocation happen under one case-row lock;
  workers observe either the old current revision or the committed new one,
  never a half-written snapshot.

### Predicate: Latest eligible training projection

Traces to: BX-01/BX-05 approved dataset decisions.

Training export selects only the newest revision that passes the existing
BX-01 eligibility/redaction gate and records that revision/document as
provenance. A superseded, not-yet-exported revision is excluded; model
retraining and unlearning are outside scope. The operational original remains
in SQL and is never included in the training projection.

## Technology / Design Decisions

### Decision D-BX05-01: Revision persistence

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Append-only relational revision rows plus JSON structured snapshot | Fits existing PostgreSQL, preserves queryable IDs, small schema change, transactionally locks current case | JSON fields need existing validation to interpret | ✅ |
| Event-sourced case stream | Strong history semantics and replay | New event model, replay machinery, and unnecessary topology | ❌ |
| Overwrite current document and keep a diff | Smallest write | Loses exact prior content and breaks audit/training provenance | ❌ |

**Why append-only SQL:** It is the smallest durable model compatible with the
existing case projection and the requirement that prior revisions remain visible.
**Why not event sourcing:** BX-05 needs history, not arbitrary replay; adding a
stream is overengineering. **Why not overwrite/diff:** It cannot guarantee an
exact immutable prior revision.

### Decision D-BX05-02: Re-analysis boundary

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Reuse OCR/classification/validation contracts and existing workers | Keeps ownership and schema rules in their current services | Adds asynchronous processing time | ✅ |
| Workflow writes classification/validation tables directly | Synchronous-looking implementation | Violates service boundaries and duplicates rules | ❌ |
| New revision-analysis service | Isolates future policy | New service, deployment, and contract for one flow | ❌ |

**Why contract reuse:** A revision is a new intake projection; existing
producers remain authoritative. **Why not direct table writes:** private-table
coupling would make races and schema evolution unsafe. **Why not a new service:**
no approved behavior requires another runtime boundary.

### Decision D-BX05-03: Edit concurrency

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Existing `If-Match` optimistic concurrency plus idempotency key | Matches current case mutations; prevents lost updates and duplicate retries | Caller must refresh after conflict | ✅ |
| Last-write-wins | Simple caller behavior | Silently discards another editor's petition changes | ❌ |
| Distributed lock service | Could coordinate across services | Extra dependency for a single PostgreSQL transaction | ❌ |

**Why optimistic concurrency:** The case row already supplies the durable lock
and ETag revision. **Why not last-write-wins:** It violates immutable-history
and user-intent guarantees. **Why not a lock service:** PostgreSQL is already
the authoritative durable store.

## Verification predicates for implementation

- Draft/waiting edit creates revision 2, preserves revision 1, and reruns
  validation.
- Review/routed edit creates a revision while old assignment and correspondence
  rows remain unchanged.
- A classification field in the edit body is rejected; changed text may cause
  reclassification.
- Resolution-marked/closed cases reject edits and create no revision.
- Exact stale `If-Match`, duplicate idempotency retry, and simultaneous edit
  cases are covered.
- Training export points to the latest eligible revision and omits operational
  original text.

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| — | None. The approved BX-05 requirements and existing case-state mapping are sufficient for this slice. | solution-architect | Resolved | — |
