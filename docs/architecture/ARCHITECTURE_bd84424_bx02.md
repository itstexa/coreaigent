# Architecture Session — BX-02 unit assignment

> Consumes approved BX-02 requirements in
> `docs/design/DESIGN_bd84424_extensions.md`.

## Data model

`workflow` owns two small SQL tables in its existing PostgreSQL schema:

- `unit_personnel(person_id, unit_id, display_name)` — membership source;
- `case_assignments(assignment_id, case_id, source_case_revision, person_id,
  assigned_at)` — one immutable assignment per case revision.

No online/active flag, role, skill, leave, or separate personnel service exists
in this slice. A missing member leaves the route in a pending-assignment state;
override/reassignment semantics are deferred.

## Selection predicate

`services/workflow/assignment.py` filters members by the routed `unit_id`,
counts their assignments whose case state is not terminal (`completed` or
`failed`), finds the minimum count, and calls an injected random chooser over
the tied members. Production uses `random.choice`; tests inject a chooser so
the boundary is deterministic without changing behavior.

The assignment is inserted in the same routing transaction with a unique
`(case_id, source_case_revision)` constraint. A retry that sees the unique row
does not create a second assignment. Existing assignments are never rebalanced.

## API projection

`GET /cases/{case_id}/routing` adds nullable `assignee` (`id`, `name`) to the
routed response. Null means no unit member was available; no invented person
is returned. The existing USER/ADMIN case-reader access policy remains.

## Decision D-BX02-01

| Option | Choice | Why |
|---|---|---|
| New assignment service | No | No approved personnel source; extra topology. |
| Workflow SQL + pure selector | **Yes** | Fits existing route transaction and keeps rule testable. |
| Rebalancing scheduler | No | Explicitly outside approved scope. |

## Verification predicates

- only routed-unit members enter the candidate set;
- minimum open-case count always wins;
- tied minimums use the random chooser;
- no candidates returns no assignment without inventing a person;
- duplicate route/retry is idempotent for one case revision.
