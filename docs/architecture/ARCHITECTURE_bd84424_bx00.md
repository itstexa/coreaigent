# Architecture Session — BX-00 case action log

> Consumes approved BX-00 requirements in `docs/design/DESIGN_bd84424_extensions.md`.

## Boundary

`workflow` owns immutable SQL action records and authorized case-log reads.
Other services send a contract-bound internal event; no service accesses a
private table owned by another service.

### Entity: CaseActionLog

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `event_id` | UUID | identity | Primary key; generated once. |
| `case_id` | UUID | case identity | Required; existing case. |
| `action_type` | enum string | — | `state_change`, `assignment`, `petition_edit`, `attachment_change`, `spam_decision`, `view`, or `download`. |
| `actor` | string | principal | Required internal principal; never a bearer token. |
| `occurred_at` | timestamptz | UTC instant | Database-generated; immutable. |

**Invariants:** rows are append-only; event IDs and case/action values never
change; only a principal already allowed to read the case may read its log.

**Boundary Behavior:** unknown action type is rejected; missing/invalid case is
rejected; empty log returns an empty list; no deletion endpoint exists.

**Concurrency / Race-Scenario Analysis:** duplicate event IDs are idempotent;
concurrent inserts produce separate immutable events; reads may observe events
committed before the read transaction.

## Decision D-BX00-01: Log ownership

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Workflow-owned SQL table plus internal event contract | One case-authorized read projection; respects service boundaries. | Producers need event calls. | ✅ |
| Shared direct table writes from every service | Fewer HTTP calls. | Violates private-table boundary and couples schemas. | ❌ |
| New audit service | Strong isolation. | Extra service/topology for a small append-only feature. | ❌ |

**Why workflow:** it already owns case projection and access policy.
**Why not shared direct writes:** prohibited cross-service coupling.
**Why not new service:** unnecessary topology for current scope.

## Verification

Add contract/unit tests for allowed action enum, immutable insert/read,
unauthorized read, unknown-action rejection, and duplicate event ID replay.

## HTTP boundary

`workflow` exposes `GET /cases/{case_id}/action-log` for the existing USER and
ADMIN case-reader roles. Response shape is defined by
`contracts/schemas/case-action-log-result.schema.json`. Unknown cases return
`CASE_NOT_FOUND`; malformed IDs return `CASE_ID_INVALID`; no delete/update
endpoint exists. Initial producers append in the same workflow transaction for
correspondence start, review completion, and routing. Other services must later
publish a contract-bound event to this owner, never write this private table.
