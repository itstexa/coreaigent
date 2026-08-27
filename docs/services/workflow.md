# workflow

Read this when you touch correspondence drafting (F-04), department routing (F-05),
case state and the case API (F-06), or any of the three durable workers.
For the retrieval half of F-04 see [`rag.md`](rag.md); for the generation call see
[`llm-jamba.md`](llm-jamba.md).

## Responsibility

- Owns the **case API** the UI talks to: case list, case detail, correspondence,
  routing, document, review completion.
- Owns **F-04**: turning a completed validation state into an official draft
  (retrieval → prompt → Jamba → deterministic guards → stored generation).
- Owns **F-05**: choosing the destination department/unit and writing the
  notification text.
- Owns **F-06**: deriving case state from the rows other services wrote, and
  starting F-04 automatically when a case becomes eligible.

## Does not own

- Text intake and normalization (`ocr`), taxonomy scoring (`classification`),
  missing-field logic and the supplemental loop (`validation`).
- Model serving. It calls the `llm` service over HTTP; it never loads Jamba.
- Any UI rendering. It returns JSON only.
- Routing decided by a model: the destination is computed in `routing.py`
  from the stored taxonomy chain.

## Location

| What | Path |
| --- | --- |
| API | `services/workflow/app.py` (routes at lines 295–531) |
| F-04 logic and guards | `services/workflow/correspondence.py` |
| F-04 worker | `services/workflow/worker.py` |
| F-05 logic | `services/workflow/routing.py` |
| F-05 worker | `services/workflow/routing_worker.py` |
| F-06 derivation | `services/workflow/orchestrator.py` |
| F-06 worker | `services/workflow/orchestrator_worker.py` |
| Retrieval corpus | `services/workflow/corpus.json` |
| PII policy | `services/workflow/f04_pii_policy.json` |
| Taxonomy copy used for routing | `TAXONOMY_PATH` (see Configuration) |
| Container | `services/workflow/Dockerfile`, overlay `compose.workflow.yaml` |

## Endpoints

Declared in `contracts/http/manifest.json` under `additionalEndpoints`.

| Method + path | Auth | Notes |
| --- | --- | --- |
| `GET /cases` | ADMIN | `limit`/`offset`/`state`/`q`; 401, 403 |
| `GET /cases/{case_id}` | access | Case detail with derived state |
| `POST /cases/{case_id}/correspondence` | access | `Idempotency-Key` + `If-Match`; body must be empty or `{}` |
| `GET /cases/{case_id}/correspondence` | access | Generation result or status |
| `GET /cases/{case_id}/routing` | access | F-05 result |
| `GET /cases/{case_id}/document` | access | Stored document view |
| `POST /cases/{case_id}/review-completion` | ADMIN | `Idempotency-Key` + `If-Match`; only `needs_review` cases |

Client generation input is refused on purpose: `POST .../correspondence`
returns `REQUEST_BODY_INVALID` for any non-empty body, so the prompt is
always built server-side from stored, validated fields.

## Processing flow

1. `orchestrator_worker` polls, re-derives every current case with
   `derive_case_state`, and upserts `current_case_states`. A pass that changes
   nothing leaves `updated_at` alone.
2. When `next_start_action` says a case is eligible, the same worker enqueues
   F-04 itself (1 initial attempt + retries up to `MAX_F04_START_ATTEMPTS`,
   with a cooldown between attempts).
3. `POST /cases/{id}/correspondence` (or that automatic start) inserts a
   `correspondence_generations` row plus a leased job and returns `202` with
   `generation_status: "queued"`.
4. `worker.py` claims the job, embeds the case text with BGE-M3 in-process,
   retrieves top-`TOP_K` corpus passages above `MIN_COSINE_SIMILARITY`, builds
   the prompt, and calls `JAMBA_URL`.
5. The model answer passes the deterministic guards in `correspondence.py`:
   PII policy, no unsourced legal claim, bounded summary/draft/excerpt lengths,
   citations a subset of what was retrieved, `correspondence_type` from
   `CORRESPONDENCE_TYPES`.
6. `routing_worker.py` maps the stored classification chain to a department and
   unit and writes the notification, falling back to `FALLBACK_DEPARTMENT_ID` /
   `FALLBACK_UNIT_ID` when the chain is missing.
7. Notifications are persisted only; nothing is sent to an external system.

## Failure behaviour

- All handlers answer `503 POSTGRES_UNAVAILABLE` on `psycopg.Error`.
- Concurrency: `428` when `If-Match` is missing, `412 CASE_REVISION_CONFLICT`
  when it is stale, `409 IDEMPOTENCY_KEY_REUSED` when a key returns with a
  different request fingerprint; a matching replay returns the stored response.
- `409 CASE_NOT_READY_FOR_CORRESPONDENCE` when validation is not `complete`
  (the response carries `case_state` and `completion_status`).
- `409 CASE_NOT_REVIEWABLE` when review completion targets a case that is not
  `needs_review`. `404 CASE_NOT_FOUND` when no state row exists.
- A worker exception releases the lease back to `pending`, so the job is
  retried rather than lost. A guard rejection is a recorded failure, not a
  crash: the case ends in `needs_review` with an error code.

## Configuration

Names only — values live in `compose.workflow.yaml` and the environment.

`DATABASE_URL`, `TAXONOMY_PATH`, `JAMBA_URL`, `JAMBA_TIMEOUT_SECONDS`,
`BGE_MODEL_REVISION`, `HF_HOME`, `WORKER_POLL_SECONDS`,
`WORKER_LEASE_SECONDS`, `F04_RETRY_COOLDOWN_SECONDS`,
`CASE_ACCESS_TOKEN`, `CASE_ADMIN_TOKEN`.

The two tokens are fixed demo credentials, not authentication — see
[`../development.md`](../development.md).

## Tests

`tests/test_correspondence_service.py`, `tests/test_routing_service.py`,
`tests/test_orchestrator.py`, `tests/test_case_contracts.py`,
`tests/test_case_list_projection.py`, `tests/run_orchestration_intake.py`,
`tests/run_correspondence_intake.py`.

## Related docs

- [`../data-flow.md`](../data-flow.md) — where these stages sit in the lifecycle
- [`../contracts.md`](../contracts.md) — case endpoint contracts
- [`validation.md`](validation.md) — the state this service waits for
