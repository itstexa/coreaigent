# Architecture Session — US-110 F-05 routing and notifications

> Consumes approved [F-05 design](../design/DESIGN_8c16689_f05.md).

## Component boundary

F-05 extends `workflow` with a `routing-worker`. It has no client-owned start
operation. F-04 terminal publication inserts one durable F-05 job in the same
PostgreSQL transaction. A lease-safe reconciliation pass also finds complete
cases whose F-04 job/event was missed or is `not_requested`. The worker owns
routing and notification state; it does not send e-mail.

```text
F-04 completed / recovery scan
              |
              v
     routing_jobs (pending, leased)
              |
              v
       routing-worker
        |              |
        v              v
routing_operations   notification_jobs
  (immutable)         (applicant + unit)
                         |
                         v
                    llm /generate
                         |
                         v
              notification_records (PostgreSQL only)
```

## Entities

### Entity: RoutingOperation

Traces to: US-110.

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `routing_id` | UUID | routing identity | Primary key; server generated once. |
| `case_id` | UUID | case identity | Required; foreign key to current authoritative case. |
| `source_case_revision` | positive bigint | case revision | Required immutable revision. |
| `source_generation_id` | nullable UUID | F-04 generation identity | Required for event-triggered work; null only for reconciliation of `not_requested`. |
| `route_kind` | enum | — | `classified` or `fallback`. |
| `target_department_id`, `target_unit_id` | text | taxonomy stable IDs | Required active target snapshot. |
| `request_type_id` | text | taxonomy stable ID | Required classified request-type snapshot. |
| `routing_status` | enum | — | `routed` or `failed`; no partial routed state. |
| `routing_reason` | JSONB object | audit metadata | Server-built source status, recovery reason, and registry version; no bearer credential. |
| `routed_at`, `created_at` | timestamptz | UTC instant | Required database timestamps. |

**Invariants**

- `UNIQUE(case_id, source_case_revision)` permits exactly one logical route per
  revision, regardless of event/recovery races.
- `classified` uses the active current F-02 department/unit. `fallback` uses
  taxonomy IDs `diger` / `siniflandirilmamis`; it never uses an LLM-selected
  target.
- A route is immutable after `routed`; a later case revision creates a new
  operation rather than overwriting its history.

**Boundary behavior**

- A missing/invalid/non-classified F-02 chain, F-03 status other than
  `complete`, or inactive target produces no routing row and a completed
  rejected job audit.
- `review_required` and F-04 `not_requested` are fallback candidates only;
  `draft_ready` is a classified-target candidate.
- A routing job may be retried after its lease expires; malformed identifiers
  are rejected rather than coerced.

**Concurrency**

- Event and reconciliation workers use `FOR UPDATE SKIP LOCKED` plus the
  unique route key. The loser observes the existing route and completes as a
  replay.
- F-03 revision changes are checked under the locked current state row. A
  stale job cannot route a newer revision.

### Entity: NotificationRecord

Traces to: US-110.

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `notification_id` | UUID | notification identity | Primary key. |
| `routing_id` | UUID | routing identity | Required foreign key. |
| `audience` | enum | — | Exactly `applicant` or `target_unit`. |
| `generation_status` | enum | — | `queued`, `processing`, `completed`, or `failed`. |
| `payload` | JSONB object | structured notification | Null until completed; required title/body/audience/case reference after completion. |
| `model_id`, `model_revision` | nullable text | model provenance | Required after a Jamba invocation. |
| `attempt_count` | smallint | attempts | `0..2`; failed text is never published. |
| `error_code` | nullable stable token | — | Required only for `failed`. |
| `created_at`, `completed_at` | timestamptz | UTC instant | Database timestamps. |

**Invariants**

- `UNIQUE(routing_id, audience)` creates exactly one applicant and one
  target-unit notification record for a routed operation.
- A notification failure never mutates `RoutingOperation.routing_status`.
- Applicant payload includes only process-facing wording. Target-unit payload
  is built from the case fields and F-04 result accessible to that target
  audience; it contains no source data outside that authorized case.
- `payload` is persisted structured data only. `email_placeholder` is an
  optional null/not-configured field and performs no dispatch.

**Boundary behavior**

- Blank/non-object Jamba output or an output without non-blank exact `title`
  and `body` strings fails validation and is retryable once; no partial body is
  exposed. When those two exact fields are valid, server-owned structural
  recovery discards additional echoed model fields rather than publishing them.
- An inactive target prevents notification job creation because no route is
  committed.

**Concurrency**

- Claiming is lease-safe. A duplicate worker can only complete a row still in
  `processing` under its lease; terminal rows are immutable.

## Decisions

### Decision D-150: Durable event and reconciliation routing

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| PostgreSQL job/outbox plus reconciliation scan | Atomic with F-04, survives restart, repairs missed events. | Requires lease and uniqueness predicates. | ✅ |
| In-process F-04 function call | Low initial code volume. | Loses work on restart and cannot recover missed calls. | ❌ |
| External queue/broker | Independent dispatch scaling. | Adds an unapproved mandatory dependency. | ❌ |

**Why PostgreSQL:** it remains the approved authoritative source and already
hosts durable F-01/F-04 jobs.

**Why not in-process:** F-05 must not disappear when a container dies after
F-04 commits.

**Why not external queue:** Redis/Kafka/RabbitMQ are not required for this
initial implementation.

### Decision D-151: Fallback routing target

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Active demo taxonomy `diger` / `siniflandirilmamis` chain | Stable, auditable, user-approved Others/Uncategorized behavior. | Requires an explicit fallback taxonomy record. | ✅ |
| Reuse a classified unit for review work | No taxonomy addition. | Misrepresents an unreviewed case as belonging to that unit. | ❌ |
| Let Jamba choose a fallback unit | Flexible wording. | Violates authoritative routing rules. | ❌ |

**Why the fallback chain:** review/no-F-04 cases must route while remaining
visibly outside a normal department decision.

**Why not reuse or Jamba:** neither preserves the explicit categorization and
audit semantics required for review work.

### Decision D-152: Notification structured-output recovery

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Preserve only valid exact `title` and `body`; discard extra echoed fields | Handles real Jamba context echo without exposing it or inventing replacement text. | Does not recover missing/renamed required fields. | ✅ |
| Reject every object with an unknown member | Strict and simple. | Rejects a safe notification when the two authoritative display fields are already valid. | ❌ |
| Derive a notification from arbitrary model fields | Can recover more output variation. | Could publish invented or unauthorized context. | ❌ |

**Why exact-field recovery:** a real local Jamba run returned valid `title` and
`body` together with echoed `draft_text` and `validated_fields`. Keeping only
the two approved fields is deterministic redaction, not semantic generation.

**Why not strict rejection:** it turns harmless context echo into an avoidable
durable notification failure.

**Why not derive fields:** F-05 must not reinterpret an arbitrary model object
or expose fields outside the audience projection.

## Read boundary

`GET /cases/{case_id}/routing` is an authorized read-only workflow projection.
It exposes the current revision's routing status, target IDs/labels, route
kind, and applicant/unit notification generation states. It never exposes the
target-unit payload to an applicant audience; the existing case access model
determines which projection is available. There is no public F-05 POST.

## Architecture Open Questions

None. The notification output uses the already-approved local Jamba structured
generation and F-04 safety posture; external delivery remains deliberately
outside this boundary.
