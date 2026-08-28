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
- Owns **F0**: a local ticket reference and immutable system-only state-action
  trace for every projected case.
- Owns **F8**: an explainable, local priority projection from configured
  safety/service-impact phrases; it orders the ADMIN queue but never changes a
  route, SLA, or administrative decision.
- Owns **F2**: assigning each current routed case revision using workload
  balancing, with topic-resolution priority for third same-topic or bounded
  aggression-signal cases, and a durable unassigned fallback.

## Does not own

- Text intake and normalization (`ocr`), taxonomy scoring (`classification`),
  missing-field logic and the supplemental loop (`validation`).
- Jamba serving. It calls the `llm` service over HTTP; it never loads Jamba.
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
| F0 ticket/action storage and read projection | `services/workflow/app.py`, `orchestrator_worker.py` |
| Retrieval corpus | `services/workflow/corpus.json` |
| Turkish/English bridge | `services/workflow/translation.py` |
| Offline translation-cache bootstrap | `services/workflow/prepare_translation_models.py` |
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
| `GET /cases/{case_id}/related-cases` | ADMIN | Bounded same-applicant similar-history projection |
| `GET /cases/{case_id}` | ADMIN | Includes the F2 assignment projection; USER responses omit it |
| `POST /cases/{case_id}/review-completion` | ADMIN | `Idempotency-Key` + `If-Match`; only `needs_review` cases |

Client generation input is refused on purpose: `POST .../correspondence`
returns `REQUEST_BODY_INVALID` for any non-empty body, so the prompt is
always built server-side from stored, validated fields.

## Processing flow

1. `orchestrator_worker` polls, re-derives every current case with
   `derive_case_state`, evaluates its original text against the repository-owned
   F8 rule table, and upserts `current_case_states`. `critical` (100), `high`
   (70), and `normal` (40) are visible to ADMIN and sort the queue first; a pass
   that changes nothing leaves `updated_at` alone.
2. When `next_start_action` says a case is eligible, the same worker enqueues
   F-04 itself (1 initial attempt + retries up to `MAX_F04_START_ATTEMPTS`,
   with a cooldown between attempts).
3. `POST /cases/{id}/correspondence` (or that automatic start) inserts a
   `correspondence_generations` row plus a leased job and returns `202` with
   `generation_status: "queued"`.
4. `worker.py` claims the job, embeds the case text with BGE-M3 in-process and
   fuses that local dense rank with Turkish lexical BM25 rank using RRF,
   retrieving top-`TOP_K` evidence-bearing corpus passages. Turkish
   human-readable prompt values pass through the pinned offline translation
   bridge before the English Jamba prompt; returned human-readable fields pass
   back through the bridge before persistence. Structured identifiers and
   citation IDs never cross this boundary.
5. The model answer passes the deterministic guards in `correspondence.py`:
   PII policy, no unsourced legal claim, bounded summary/draft/excerpt lengths,
   citations a subset of what was retrieved, `correspondence_type` from
   `CORRESPONDENCE_TYPES`.
6. `routing_worker.py` maps the stored classification chain to a department and
   unit, creates the F2 assignment for that unit, and writes the notification,
   falling back to `FALLBACK_DEPARTMENT_ID` / `FALLBACK_UNIT_ID` when the chain
   is missing.
7. Notifications are persisted only; nothing is sent to an external system.
8. An F-06 state insert or meaningful state/revision change appends one F0
   `state_projected` action in the same PostgreSQL transaction. No-op polling
   writes neither a new state timestamp nor a new action.

## Failure behaviour

- All handlers answer `503 POSTGRES_UNAVAILABLE` on `psycopg.Error`.
- Concurrency: `428` when `If-Match` is missing, `412 CASE_REVISION_CONFLICT`
  when it is stale, `409 IDEMPOTENCY_KEY_REUSED` when a key returns with a
  different request fingerprint; a matching replay returns the stored response.
- `409 CASE_NOT_READY_FOR_CORRESPONDENCE` when validation is not `complete`
  (the response carries `case_state` and `completion_status`).
- `409 CASE_NOT_REVIEWABLE` when review completion targets a case that is not
  `needs_review`. `404 CASE_NOT_FOUND` when no state row exists.
- A missing/offline-unavailable translation model is a worker exception: its
  leased job returns to `pending` and is retried; it never silently sends a
  Turkish prompt to Jamba.
- A worker exception releases the lease back to `pending`, so the job is
  retried rather than lost. A guard rejection is a recorded failure, not a
  crash: the case ends in `needs_review` with an error code.
- `case_action_log` rejects `UPDATE` and `DELETE` at the database boundary.
  ADMIN case detail reads its safe, bounded projection; USER responses do not
  contain the ticket or action data.

## F0 local ticket trace

Every projected case has one stable `CA-XXXXXXXX` local ticket reference. The
immutable action rows record only actor `system`, state, revision, completed
feature IDs, error code, and timestamp. They never contain the petition,
accepted values, generated draft, or notification payload. This is not an
external ticketing integration. F2 assignment is a separate ADMIN-only
workload projection and never appears in this action trace.

## F2 first assignment

`staff_members` and `case_assignments` are durable PostgreSQL tables. The local
competition registry contains two demo staff records per taxonomy unit. After a
route is inserted, the routing worker serializes choices per unit and persists
one row for the current case revision. Ordinary cases choose the least-loaded
active member (oldest `assigned_at`, then stable ID). For a third validated
petition by the same comparison-safe applicant in the same `request_type_id`,
or when bounded Turkish/English aggression markers produce an elevated/high
signal, the worker
first compares active staff by completed-topic assignments / all-topic
assignments. Topic resolution rate is followed by topic volume, open workload,
recency, and stable ID as deterministic tie-breakers. If no candidate has topic
history, it falls back to least-open workload. The persisted `selection_reason`
contains only policy, counters, level, and topic metrics; it never contains
applicant identity or petition text. If no active member exists, it inserts
`unassigned` so the route and case remain visible to ADMIN. When orchestration
reaches `completed`, an assigned row becomes `completed`. Staff CRUD, external
identity/RBAC, and manual reassignment are deliberately outside this slice.

## F8 explainable priority

F8 is intentionally not Jamba inference: the local rules in `orchestrator.py`
match normalized Turkish phrases in critical-safety first, then service-impact
order. Every case retains a `level`, numeric `score`, and human-readable rule
reason in the ADMIN list projection. A text with no configured phrase remains
`normal`; a critical phrase always wins over a high phrase. This is queue order
only, never a legal urgency classification or an automatic routing change.

## Controlled learning feedback

An ADMIN can promote a completed case whose validation is `complete` through
`POST /cases/{case_id}/learning-feedback`. The workflow stores one current
revision candidate with deterministic PII minimization: `redact` validated
fields become typed placeholders, `exclude` fields are omitted, and the text
is scanned for residual TCKN, phone, e-mail, and IBAN patterns. Repeating the
promotion returns the existing candidate. This is a dataset collection
boundary, not automatic fine-tuning or model publication; export and retraining
must perform a separate approval/review step.

## User F3 same-applicant history

`GET /cases/{id}/related-cases` is an ADMIN-only read projection, not a new
user database. It compares only cases with the same validated applicant field
(`applicant-name`, `business-name`, or `supplier-name`) and keeps candidates
whose normalized token overlap is at least 20%. It returns at most five records
with date, current state, resolved (`completed`) flag, score, and title — never
petition bodies, identity values, generated drafts, staff, or assignment data.
“Past moderators” remains unavailable until an authenticated employee model
exists.

## Configuration

Names only — values live in `compose.workflow.yaml` and the environment.

`DATABASE_URL`, `TAXONOMY_PATH`, `JAMBA_URL`, `JAMBA_TIMEOUT_SECONDS`,
`BGE_MODEL_REVISION`, `HF_HOME`, `WORKER_POLL_SECONDS`,
`WORKER_LEASE_SECONDS`, `F04_RETRY_COOLDOWN_SECONDS`,
`CASE_ACCESS_TOKEN`, `CASE_ADMIN_TOKEN`.

The two tokens are fixed demo credentials, not authentication — see
[`../development.md`](../development.md).

## Turkish output bridge (F11)

The workflow image carries two local Marian models in the same mounted
Hugging Face cache as BGE-M3. They are fetched deliberately once with
`HF_HUB_OFFLINE=0` and every normal runtime has `HF_HUB_OFFLINE=1`:

- `Helsinki-NLP/opus-mt-tc-big-tr-en` at
  `2261c8fc7b1af59caee87f8ff0ecf3fbccfe8391`
- `Helsinki-NLP/opus-mt-tc-big-en-tr` at
  `e539fc16a8a1a0ea5950eb339b595bfcce990e90`

Both models are CC-BY-4.0; include Helsinki-NLP attribution in a competition
delivery. Bootstrap them from the workflow image with
`HF_HUB_OFFLINE=0 python prepare_translation_models.py`, then return the
environment to offline mode. This is deliberately an in-process workflow
boundary, not a seventh HTTP service: it avoids a new public contract and
keeps the local CPU dependency in the worker that needs it.

## Tests

`tests/test_correspondence_service.py`, `tests/test_routing_service.py`,
`tests/test_orchestrator.py`, `tests/test_case_contracts.py`,
`tests/test_case_list_projection.py`, `tests/run_orchestration_intake.py`,
`tests/run_correspondence_intake.py`, `tests/test_document_language.py`.

## Related docs

- [`../data-flow.md`](../data-flow.md) — where these stages sit in the lifecycle
- [`../contracts.md`](../contracts.md) — case endpoint contracts
- [`validation.md`](validation.md) — the state this service waits for
