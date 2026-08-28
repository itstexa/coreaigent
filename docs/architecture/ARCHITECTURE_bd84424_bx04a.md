# Architecture Session — BX-04A abuse trends

`workflow` aggregates persisted BX-04 assessment rows on demand. The smallest
projection supports user/unit/system scopes, a configurable 7-day rolling view,
and default 30-day period (7/30/90 choices). Groups with fewer than five users
are omitted. If no BX-04 rows exist the response is `no_data/not_available`.
No streaming analytics, employee ranking, or notification channel is added.
