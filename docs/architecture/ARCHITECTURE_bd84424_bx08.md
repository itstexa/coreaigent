# Architecture Session — BX-08 deterministic priority

Priority is a workflow projection calculated from versioned local policy. The
allowed values are `low`, `normal`, `high`, and `urgent`; absent qualifying
signals default to `normal`. Request type, deadline, verified urgency, and
waiting time may contribute; sensitive data and unverified user wording cannot
raise priority alone.

The projection stores level, policy version, reason, calculated time, and an
optional human override. Moderator/admin overrides require a non-empty reason
and append an existing action-log event. Priority changes queue order and an
optional SLA target only; routing destination and assignment are unchanged.

Calculation is deterministic and idempotent for a case revision. Concurrent
overrides serialize on the case row; the latest authorized override wins and
is auditable. No predictive model, escalation, or notification pipeline is
introduced.
