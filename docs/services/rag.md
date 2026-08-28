# rag (retrieval)

Read this when you touch legislation retrieval, the corpus, citations, or the
`rag` contract. **Known inconsistency:** there is no `services/rag/` directory.
The `rag` boundary is a declared contract served by the mock, while real
retrieval runs in-process inside the `workflow` F-04 worker.

## Two things named "rag"

| | Contract boundary | Real retrieval |
| --- | --- | --- |
| Interface | `POST /v1/retrieve`, `rag-request` → `rag-result` | none; a Python function |
| Implementation | `mocks/server.py` (`SERVICE == "rag"`, line 153) | `services/workflow/worker.py` `retrieve()` (line 46) |
| Used by | the mock graph in `mocks/server.py` (line 175) | the F-04 correspondence worker |
| Runtime | any mock lane | `correspondence-worker` in `compose.workflow.yaml` |

So: a mock-lane E2E exercises the *contract*, and a real workflow lane exercises
the *retrieval*. They are not the same code path. Do not describe the mock
response as retrieval output.

## Responsibility (real path)

Given the case text plus its semantic fields, return the corpus passages the
draft is allowed to cite, with scores and source metadata.

## Does not own

- Prompt assembly, generation, or citation enforcement — those are in
  `services/workflow/correspondence.py`.
- Any HTTP surface of its own in the real lane.
- Embedding model serving as a separate process: the model is loaded
  **in-process** by the worker.

## Location

| What | Path |
| --- | --- |
| Retrieval function | `services/workflow/worker.py` (`retrieve`, `embedding_model`, `semantic_similarity`) |
| Hybrid rank core | `services/workflow/hybrid_retrieval.py` (adapted from `feature/autonomous-core-integration`'s `mevzuat-rag`) |
| Context building and thresholds | `services/workflow/correspondence.py` (`build_retrieval_context`) |
| Corpus | `services/workflow/corpus.json` |
| Contract mock | `mocks/server.py` |
| Schemas | `contracts/schemas/rag-request.schema.json`, `contracts/schemas/rag-result.schema.json` |

## Retrieval parameters

Constants in `services/workflow/correspondence.py`:

- `EMBEDDING_MODEL_ID` — `BAAI/bge-m3`, `EMBEDDING_DIMENSION` 1024
- `TOP_K` — 5, `MIN_COSINE_SIMILARITY` — 0.60
- `RETRIEVAL_CONFIG_VERSION` — `municipality-rag-v3-hybrid`
- Citation bounds: `MAX_CITATIONS`, `MAX_CITATION_EXCERPT_CHARACTERS`,
  `MAX_TOTAL_CITATION_EXCERPT_CHARACTERS`

The BGE-M3 revision is pinned in `services/workflow/worker.py`
(`BGE_MODEL_REVISION`, overridable by env) and loaded with
`local_files_only=True` — offline, no network fallback.

## Corpus shape

`services/workflow/corpus.json` holds `corpus_version`
(`demo-municipality-regulations-v1`) and `sources`; each source carries
`source_id`, `title`, `source_type`, `official_source_url` and `chunks`. Chunks
are flattened before scoring, so a chunk id is the unit a citation refers to.

The corpus is demo municipal regulation content, not a complete legislation
database. Treat `corpus_version` as the thing to bump when content changes:
it is stored on every generation row.

## Processing flow

1. The worker builds one query string from the request-type label, the case
   text and the semantic fields.
2. The corpus is loaded and every chunk is embedded together with the query in
   a single normalized `encode()` call.
3. Dense BGE-M3 ranks and local Turkish BM25 ranks are combined with reciprocal
   rank fusion (RRF), adapted from the supplied `mevzuat-rag` branch. The
   persisted citation `score` remains the BGE cosine score for contract
   compatibility; `rank_score` only changes selection order.
4. `build_retrieval_context` applies the threshold and top-K, and returns a
   source status plus the surviving chunks.
5. The draft may only cite `chunk_id` values that came back here; a citation
   outside that set is rejected by the F-04 guards.

## Failure behaviour

No network fallback, Qdrant dependency, or remote embedding service: if the local artifact is
missing, the worker raises and the leased job returns to `pending`. When
nothing clears `MIN_COSINE_SIMILARITY`, retrieval reports that as a source
status rather than inventing citations — the case ends up needing review
instead of getting an unsourced draft.

## Configuration

Names only: `BGE_MODEL_REVISION`, `HF_HOME` (both read by the workflow worker).

## Tests

`tests/test_correspondence_service.py` covers retrieval context and citation
rules; `tests/test_hybrid_retrieval.py` falsifies Turkish lexical scoring and
RRF integration; `tests/run_scenarios.py` exercises the mock `rag` contract boundary.

## Related docs

- [`workflow.md`](workflow.md) — the caller and the guard set
- [`llm-jamba.md`](llm-jamba.md) — what the retrieved context is fed into
- [`../contracts.md`](../contracts.md) — the `rag` boundary and its gap
