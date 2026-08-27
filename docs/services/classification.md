# Classification (F-02 hierarchical classification)

Read this when changing taxonomy scoring, the classification response, or the
durable classification worker. Payload fields:
`contracts/schemas/classification-result.schema.json` (v3).

## Responsibility

- Score normalized document text against the repository-owned taxonomy and
  return the hierarchical target: request type → unit → department.
- Decide `classified` (score > 0.80) versus `needs_review` (lower score, or no
  match) and report the reason and evidence.
- Keep exactly one current classification record per document, written by a
  durable PostgreSQL worker that completes the intake outbox job.

## Does not own

- Field extraction or missing-information logic (that is `validation`).
- Routing the case to a unit — routing reads the taxonomy again in `workflow`.
- The document language decision (made once in `ocr`), though it scores the
  language-specific keyword lists independently of it.

## Location

Implementation: `services/classification/app.py` (API),
`services/classification/worker.py` (durable worker) ·
Taxonomy: `services/classification/taxonomy.json` ·
Docker: `services/classification/Dockerfile` · Overlay:
`compose.classification.yaml` (API + `classification-worker`) ·
Tests: `tests/test_classification_service.py`, `tests/test_semantic_classifier.py`,
`tests/run_classification_intake.py`

## Inputs / outputs

- `POST /v1/classify` — `ocr-result` → `classification-result`
- `GET /health`, `GET /ready`
- Errors: `standard-error`.

There is no case-level classification GET route; the current record is exposed
through the `workflow` case projection instead.

## Processing flow

1. Validate the incoming `ocr-result` envelope.
2. Load the versioned taxonomy (`taxonomyVersion`, currently
   `demo-belediyesi-v2`: 6 departments, 6 units, 10 request types).
3. Score every request type with the selected model (`CLASSIFIER_MODEL`,
   default `semantic-v3`; the frozen literal `keyword-v2` scorer still ships).
4. `semantic-v3` matches concept signal groups, token- and suffix-aware, with
   Turkish-correct case folding and ASCII folding, and requires
   `REQUIRED_SIGNALS` (default 3) distinct concepts.
5. Map the score through `status_for_score()` and attach the reason/evidence.
6. The worker leases a `pending` outbox job, classifies, upserts
   `current_classifications`, and only then marks the job `completed`.

## Failure behaviour

- Invalid request envelope → HTTP 400 `validation`.
- A lease expiring re-queues the job; the record upsert plus job completion are
  one transaction, so a crash never leaves two current classifications.
- Inactive taxonomy entries are not silently accepted downstream; routing
  rejects them (see [`workflow.md`](workflow.md)).

## Configuration

`DATABASE_URL`, `TAXONOMY_PATH` (`/app/taxonomy.json` in Compose),
`CLASSIFIER_MODEL`, `REQUIRED_SIGNALS`, `WORKER_POLL_SECONDS`,
`WORKER_LEASE_SECONDS`.

## Tests

`tests/run_classification_intake.py` posts real official-document text through
real OCR, checks the v3 response, and asserts the worker writes one current
record before completing the job. The two unit test files pin the scorers,
including Turkish orthography and threshold behaviour.

## Related docs

- [`ocr.md`](ocr.md) — producer · [`validation.md`](validation.md) — consumer.
- [`../data-flow.md`](../data-flow.md) — stage boundaries.
- `docs/tekno_agent_feature_pack/02_hierarchical_classification.md` — requirements.
