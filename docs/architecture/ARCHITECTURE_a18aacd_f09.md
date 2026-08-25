# Architecture Session — US-113 F-09 case API contract atlas

> Consumes approved [F-09 design](../design/DESIGN_a18aacd_f09.md).

## Entity: CaseEndpointContract

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `service` | service-id string | — | Existing manifest service only: `validation` or `workflow`. |
| `method` | HTTP method enum | — | `GET`, `POST`, or `PATCH` as implemented. |
| `path` | URI-template string | — | One implemented `/cases/{case_id}` path; no new route. |
| `request` | schema-id string or null | — | Null only for a bodyless GET; POST/PATCH references a strict schema. |
| `response` | schema-id string | — | Existing JSON Schema Draft 2020-12 schema. |

**Invariants:** Every public case route in `validation`/`workflow` has exactly
one manifest record. A record never changes the route's implementation or
authorization; it documents the existing boundary.

**Boundary behavior:** GET has no request body schema. Correspondence POST and
review POST accept only `{}`/empty body per their existing handlers. Unknown
endpoint method, unknown schema id, or duplicate service/method/path tuple is
a contract-validation error.

**Concurrency:** Schema validation is read-only. Runtime concurrency remains
owned by the existing PostgreSQL replay/If-Match routes.

## Entity: CorrespondenceCurrentResult

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `case_id` | UUID string | — | Required every branch. |
| `case_revision` | positive integer | revisions | Required every branch. |
| `generation_status` | enum | — | Exactly `not_requested`, `queued`, `processing`, `completed`, or `failed`. |
| branch payload | discriminated JSON object | — | Determined solely by `generation_status`. |

**Invariants:** `not_requested` has `result: null`; queued/processing contain
no generation result; failed contains an error code and no draft; completed
contains the current generation's approved F-04 fields/citations only.

**Boundary behavior:** `case_revision >= 1`; citation count is `0..5`; summary
and draft maximums remain 600/6000 characters. No response branch silently
accepts fields from another lifecycle branch.

**Concurrency:** The schema is a snapshot contract; existing current pointer
and revision rules prevent old generation output from becoming current.

## Decision D-173: Manifest coverage and lifecycle unions

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Add one manifest record per implemented route and strict `oneOf` result schemas | Prevents endpoint drift and validates lifecycle-specific fields. | More schema definitions. | ✅ |
| Keep only the legacy service-to-service routes | Smaller manifest. | Hides approved public case APIs from CI and consumers. | ❌ |
| Use one permissive object for all case results | Fewest schema lines. | Allows partial drafts and mixed lifecycle fields. | ❌ |

**Why one record and strict unions:** F-03–F-06 already define concrete
routes and state-specific outputs; the contract atlas must make them testable.

**Why not legacy-only:** it is the F-09 mismatch found in the repository.

**Why not permissive:** it defeats the requested contract stabilization.

## Architecture Open Questions

None. F-03–F-06 implementations and acceptance tests define the exact route
and branch shapes being recorded.
