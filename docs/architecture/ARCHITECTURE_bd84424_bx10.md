# Architecture Session — BX-10 personnel dashboard

`workflow` derives bounded workload metrics from PostgreSQL case and assignment
projections. Authorized unit managers see their unit; admins see unit/system
aggregates. Citizens have no access. Supported periods are 7, 30, and 90 days;
default is 30 and refresh is page-load/query based.

Metrics are active (enabled+available), current open assignment load, completed
terminal cases, throughput, and resolution time. Case content, individual
employee ranking, and aggression-based scoring are never returned. Aggregates
are read-only and calculated from existing durable rows; no analytics service or
realtime channel is introduced.
