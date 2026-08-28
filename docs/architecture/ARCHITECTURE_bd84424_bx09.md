# Architecture Session — BX-09 routing confidence feedback

`workflow` owns a durable routing-evaluation projection over existing routing
and case-action records. The predicted unit and classifier confidence remain
distinct from correctness. A configurable confidence threshold sets
`needs_review=true` without blocking case creation or inventing a destination.

At moderator transfer/acceptance or final closure, the final accepted unit is
the authoritative ground truth. Store case-level `routing_correct` plus unit
and system aggregates. Feedback is visible in an authorized evaluation view,
but never enters BX-01 training automatically; only an anonymization/eligibility
pipeline may select it.

Rows are append-only per case decision; aggregate counts are derived. Concurrent
moderator decisions serialize on the case revision and the latest accepted
unit is authoritative. No new service, model, or routing destination is added.
