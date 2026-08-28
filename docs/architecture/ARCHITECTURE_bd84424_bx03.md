# Architecture Session — BX-03 case history and similar cases

> Consumes the approved BX-03 requirement slice in
> `docs/design/DESIGN_bd84424_extensions.md`.

## Boundary and ownership

`workflow` owns the case-scoped history projection because it already owns the
case state, action log, and case-reader authorization. The feature reuses the
existing PostgreSQL database and does not create a per-user database, a new
service, or an identity/ownership model.

## Data model

`case_resolution_marks(case_id, actor, marked_at)` stores immutable reader marks
with a `(case_id, actor)` primary key. A case is resolved when one or more rows
exist. The existing `case_action_logs` `view` events provide the viewer list for
similar cases; no second viewer table is introduced.

The history query joins the current case projection, intake record, and current
classification. It considers candidates with the same request type created in
the inclusive interval `[current_created_at - 30 days, current_created_at]`.
The pure `similar_case` predicate also reports text, classification, location,
and time signals, while the acceptance decision requires same classification
and a non-negative age of at most 30 days. It does not use a model or a hidden
similarity score.

## API projection

- `GET /cases/{case_id}/history` returns current resolution marks and permitted
  similar-case summaries, including state, classification, resolution actors,
  viewer actors, and signal labels.
- `POST /cases/{case_id}/resolution-mark` accepts only an empty body or `{}`.
  It is idempotent per current case-reader principal and returns the persisted
  actor/time. Every case reader uses the existing USER/ADMIN access guard.

The response shapes are defined by
`contracts/schemas/case-history-result.schema.json` and
`contracts/schemas/case-resolution-mark-result.schema.json`.

## Invariants and race handling

- A caller without case access cannot read history or create a mark.
- A mark never deletes or overwrites another actor's mark; the primary key makes
  retries safe.
- History never exposes candidates outside the same-classification, 30-day
  window, and it excludes the current case itself.
- View logging is append-only through BX-00. A history read records the current
  reader as a `view` event; later readers of that case appear as its viewers.
- All state and history reads are transactional; an unavailable database maps
  to the existing `POSTGRES_UNAVAILABLE` envelope.

## Decision D-BX03-01

| Option | Choice | Why |
|---|---|---|
| Separate per-user history database | No | Conflicts with the approved shared case-access model. |
| Workflow SQL projection + pure predicate | **Yes** | Smallest boundary; deterministic and testable. |
| Embedding/model similarity or background index | No | Not required by the approved same-classification/30-day rule. |
| Mutable single resolved flag | No | Multiple reader marks and audit visibility are required. |

## Verification predicates

- exact 30-day boundary is included; day 31 and different classifications are excluded;
- text and location differences are reported as signal labels without changing
  the approved threshold;
- any permitted reader can mark once, and every permitted reader sees the mark;
- an unauthorized reader receives an authorization error and changes no state;
- retrying the same mark does not create a duplicate row or action event.
