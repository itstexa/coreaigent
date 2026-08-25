# Architecture Session — US-111 F-06 orchestration and case state

> Consumes approved [F-06 design](../design/DESIGN_c207e52_f06.md).

## Component boundary

`orchestrator-worker` is a third process in the existing `workflow` image. It
observes PostgreSQL current records, creates durable F-04-start operations and
updates a separate current case projection. It does not reimplement F-01..F-05
logic, call an external broker, or send e-mail. F-04 and F-05 retain their
existing immutable generations/routes and job records.

```text
F-01..F-05 current PostgreSQL records
                 |
                 v
       orchestrator-worker / leases
        |                 |
        v                 v
 current_case_states   correspondence-start jobs
        |                 |
        +-- case_notifications (PostgreSQL only)
```

## Entities

### Entity: CurrentCaseState

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `case_id` | UUID | case identity | Primary key; exactly one mutable row. |
| `revision` | positive bigint | F-03 revision | Current source revision. |
| `state` | enum | — | `received`, `normalized`, `classified`, `needs_review`, `extracting`, `waiting_for_user`, `ready_for_processing`, `draft_prepared`, `routed`, `notification_pending`, `completed`, or `failed`. |
| `completed_steps` | JSONB string array | step IDs | Current derived/completed steps; no duplicate item. |
| `last_error_code` | nullable text | stable error token | Required for `failed`, otherwise null. |
| `updated_at` | timestamptz | UTC instant | PostgreSQL update instant. |

**Invariants:** it layers over rather than overwrites F-02/F-03/F-04/F-05;
`review_required` never automatically becomes `completed`; a current
`needs_review` can become `completed` only through the admin completion
operation.

**Boundary behavior:** unknown source combinations become `failed` with a
stable error rather than a synthetic completed state. A case has one current
row, and a newer F-03 revision replaces only this projection's revision.

**Concurrency:** the worker locks the current validation row and upserts this
row in the same transaction. A stale job cannot write a newer revision.

### Entity: CorrespondenceStartJob

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `job_id` | UUID | job identity | Primary key. |
| `case_id`, `source_case_revision` | UUID, positive bigint | case/revision | Unique pair; one automatic F-04 start per revision. |
| `state` | enum | — | `pending`, `claimed`, `waiting`, `completed`, `failed`. |
| `attempt_count` | integer | starts | `0..4`: one initial start plus at most three retries. |
| `next_attempt_at`, `claimed_until` | nullable timestamptz | UTC instant | Cooldown/lease; both null after terminal state. |
| `error_code` | nullable text | stable error token | Required only for terminal failure. |

**Invariants:** a successful automatic start creates/reuses exactly one F-04
generation of its source revision; a terminal failed job creates no F-05
route. `F04_RETRY_COOLDOWN_SECONDS` defaults to 30 and must be positive.

**Boundary behavior:** attempt four is the terminal retry; attempt five is
never issued. A missing/non-complete/non-classified state completes/rejects
the start job without calling Jamba.

**Concurrency:** `FOR UPDATE SKIP LOCKED` plus the unique pair prevents
duplicate F-04 starts; a lease-expired claim is reclaimed after restart.

### Entity: CaseNotification

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `notification_id` | UUID | notification identity | Primary key. |
| `case_id`, `source_case_revision` | UUID, positive bigint | case/revision | Required current source reference. |
| `audience` | enum | — | `applicant` only for F-06 missing/invalid notifications. |
| `kind` | enum | — | `missing_information` or `invalid_information`. |
| `payload` | JSONB object | structured display data | Required server-built field summary and `email_placeholder: null`. |
| `created_at` | timestamptz | UTC instant | Database-generated. |

**Invariants:** `UNIQUE(case_id, source_case_revision, audience, kind)` makes
notification insertion idempotent. It is separate from F-05 routing
`notification_records` and never dispatches e-mail.

**Boundary behavior:** an empty missing/invalid field summary is rejected;
notifications are display records, not an F-04 readiness bypass.

**Concurrency:** locked state evaluation and the unique key make repeats read
the existing record rather than create duplicate applicant messages.

### Entity: DemoAccessPolicy

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `CASE_ACCESS_TOKEN` | Bearer token | demo USER credential | Required configured secret; maps to one `USER` principal. |
| `CASE_ADMIN_TOKEN` | Bearer token | demo ADMIN credential | Required configured secret; maps to one `ADMIN` principal. |
| role | enum | — | `USER` or `ADMIN`; no login/session/provider. |

**Invariants:** USER receives no target-unit payload or internal F-04 context;
ADMIN receives the demo operational projection and may complete review. This
is explicitly non-production demo authorization.

**Boundary behavior:** missing/wrong token is 401; USER reviewer completion is
403; a malformed UUID is 400 before authorization-dependent reads.

**Concurrency:** reviewer completion locks the current state and F-03 revision;
an idempotent replay returns the original response, while a stale If-Match is
412.

## Decisions

### D-160: F-04 automatic start durability

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| PostgreSQL start job with lease/cooldown | Restart-safe, bounded retries, idempotent revision scope. | Additional table/worker loop. | ✅ |
| In-process F-03 callback | Small code path. | Loses starts on crash and cannot cooldown retry. | ❌ |
| External broker | Decoupled dispatch. | Unapproved required dependency. | ❌ |

**Why PostgreSQL:** matches the authoritative source and existing durable jobs.
**Why not callback:** it cannot guarantee recovery. **Why not broker:** no
approved operational need.

### D-161: Demo authorization

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Two fixed Bearer tokens | Testable minimal USER/ADMIN separation. | Not production identity/RBAC. | ✅ |
| Login/provider integration | Real identity lifecycle. | Outside demo scope. | ❌ |
| No authorization | Lowest code size. | Cannot enforce the requested projections. | ❌ |

## HTTP contract

- `GET /cases/{case_id}` requires USER or ADMIN. It returns current state,
  completed steps, last error, updated time, validation status, routing status
  and applicant notifications. ADMIN additionally receives classification,
  correspondence and target-unit notification payloads.
- `POST /cases/{case_id}/review-completion` requires ADMIN, an empty body,
  `Idempotency-Key` UUID and quoted current `If-Match`. It returns current
  case state. USER receives 403; any state other than `needs_review` receives
  409 `CASE_NOT_REVIEWABLE` without mutation.

## Architecture Open Questions

None.
