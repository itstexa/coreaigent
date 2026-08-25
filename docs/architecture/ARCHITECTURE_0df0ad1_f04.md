# Architecture Session — US-109 F-04 regulation retrieval and official correspondence

> Linked from [ARCHITECTURE.md](ARCHITECTURE.md). This session consumes the
> approved requirements in [DESIGN_0df0ad1_f04.md](../design/DESIGN_0df0ad1_f04.md).

## Scope and component boundary

F-04 adds the case-level correspondence API to the existing logical
`workflow` boundary and runs a separate `correspondence-worker` process from
the same image. `workflow` owns the start/read protocol, authorization,
case-revision precondition, immutable generation history, and the current
generation pointer. It does not own taxonomy selection, field extraction, or
model serving.

`validation` remains the authoritative owner of F-03's current validation
state. Its `current_validation_states.revision` is the case revision used by
F-04: F-03 is the only approved operation that can advance it. F-04 extends
that current case row with its nullable current-generation pointer; it does
not create a competing case-revision counter or retain a second F-03 history.

The active F-04 retrieval configuration is repository-owned and versioned as
`municipality-rag-v1`: `BAAI/bge-m3` dense 1024-dimensional vectors, L2
normalization, cosine similarity, `top_k = 5`, and
`min_cosine_similarity = 0.60`. This is configuration/data, not a
request-type conditional in application code. A calibrated change requires a
new retrieval configuration version and its benchmark record.

```text
POST /cases/{case_id}/correspondence
  | authorization + replay + quoted If-Match + F-03 complete
  | one PostgreSQL transaction
  v
current_validation_states  <- current_correspondence_generation_id
        |                              |
        |                              +-- correspondence_generations (immutable history)
        |                                           |
        +------------------------ correspondence_generation_jobs (pending)
                                                    |
                              FOR UPDATE SKIP LOCKED + renewable lease
                                                    v
                                       correspondence-worker
                                      /          |            \
                       normalized text + F-03    |             \-- local corpus / semantic RAG
                       values -> PII projection  |                    -> citation-owned chunks
                                                  v
                                            llm /generate
                                                  |
                                  JSON schema + citation validation
                                                  |
                             resolve validated placeholders and atomically
                             terminalize generation + current pointer
```

The browser need not sequence F-03 and F-04; a workflow/orchestrator normally
starts F-04. The public POST accepts no semantic input. The local corpus is
the only retrieval source; no F-04 component makes an internet request.

## Data models

### Entity: CorrespondenceStartRequest

Traces to: US-109 (docs/design/DESIGN_0df0ad1_f04.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `case_id` | UUID | case identity | Required path value; must name a case the authenticated principal may access. |
| `Authorization` | Bearer credential | credential | Required HTTP header; used only by CaseAccessPort and never persisted. |
| `Idempotency-Key` | UUID | replay identity | Required header; canonical UUID syntax. |
| `If-Match` | quoted positive bigint | case revision | Required header, exactly `"<decimal>"`; weak/wildcard ETags are invalid. |
| body | absent or JSON object | — | An absent body or exactly `{}` is accepted; no other member or value is accepted. |

**Invariants** (must always hold true):

- Case semantics—prompt, request type, department, extracted fields, and
  correspondence type—are read only from authoritative PostgreSQL state.
- Authorization is evaluated before a replay, state lookup, or result read;
  a bearer credential is never copied into a generation, job, or replay row.
- A first successful start creates exactly one generation and exactly one
  durable job in the same transaction and returns HTTP 202.

**Boundary Behavior:**

- Min/Max: revision is in `1..9223372036854775807`; exactly zero JSON members
  are allowed; a UUID has its standard 128-bit representation.
- Empty/Null/Zero: an omitted/blank credential, key, or If-Match is rejected
  before any database write. `{}` is valid; `null`, `[]`, and semantic JSON
  members are HTTP 400 request errors.
- Overflow/Truncation: overlong/malformed headers and a bigint overflow are
  rejected, never coerced or truncated.

**Concurrency / Race-Scenario Analysis:**

- After access is allowed, the start transaction locks the current validation
  row. It reads/reuses an exact replay first, then compares a first execution's
  expected revision and readiness under that lock. Two distinct keys for the
  same current revision may create two explicitly requested immutable
  generations; each has its own job.
- An exact existing replay is returned even when a later F-03 mutation has
  made that old revision non-current. Same principal/case/key with a different
  revision or request fingerprint is HTTP 409 `IDEMPOTENCY_KEY_REUSED`; a new
  key with a stale revision is HTTP 412 `CASE_REVISION_CONFLICT`.

### Entity: CurrentCaseCorrespondenceState

Traces to: US-108, US-109 (docs/design/DESIGN_0df0ad1_f03.md;
docs/design/DESIGN_0df0ad1_f04.md)

This is an additive extension of the existing one-row-per-case
`current_validation_states` table, not a parallel source of truth.

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `case_id` | UUID | case identity | Existing primary key. |
| `revision` | positive bigint | case revision | Existing F-03 optimistic revision and sole F-04 If-Match value. |
| `completion_status` | enum | — | Existing `complete`, `missing_information`, or `invalid_information`. |
| `current_correspondence_generation_id` | nullable UUID | generation identity | New nullable foreign key to `correspondence_generations.generation_id`. |
| `updated_at` | timestamptz | UTC instant | Existing database-managed current-state timestamp. |

**Invariants** (must always hold true):

- An F-04 start is eligible only when `completion_status = complete` at the
  locked `revision`. Otherwise it returns the specified HTTP 409 error with
  `case_state: waiting_for_user`; it does not change this row or call Jamba.
- A non-null pointer identifies at most one generation whose `case_id` and
  `source_case_revision` equal this row's case and revision. It may identify
  queued, processing, completed, or failed work.
- Every changed F-03 current state increments `revision` as already specified
  by F-03 and atomically clears this pointer. Old generations remain history;
  an old worker can never repoint a newer case revision.

**Boundary Behavior:**

- Min/Max: a pointer is one UUID or null; revision remains positive and is
  never assigned by F-04.
- Empty/Null/Zero: null means this revision has no F-04 generation yet; it is
  not a synthetic failure or a request for Jamba.
- Overflow/Truncation: invalid foreign-key/revision transitions abort the
  whole transaction; no state is shortened or reconstructed from a job.

**Concurrency / Race-Scenario Analysis:**

- F-03 supplemental PATCH and F-04 POST lock this same row. Whichever commits
  first is visible to the other: F-03 can advance and clear a pointer, while a
  stale F-04 POST subsequently receives 412 rather than binding to old data.
- Terminal worker publication updates the pointer only with
  `WHERE case_id = ? AND revision = source_case_revision`; a generation for
  revision 4 cannot become current after revision 5 exists.

### Entity: CorrespondenceGeneration

Traces to: US-109 (docs/design/DESIGN_0df0ad1_f04.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `generation_id` | UUID | generation identity | Primary key; generated once at accepted POST. |
| `case_id`, `document_id`, `workflow_id` | UUID/text/UUID | authoritative identities | Required snapshots from the locked current case and F-01 intake. |
| `source_case_revision` | positive bigint | immutable case revision | Required; equals the current row revision accepted by POST. |
| `request_type_id`, `department_label`, `unit_label` | text | taxonomy snapshot | Required current F-02 values; no caller values. |
| `corpus_version` | text | corpus build identity | Required immutable selected local build, e.g. `demo-municipality-regulations-v1`. |
| `retrieval_config_version` | text | retrieval configuration identity | Required immutable version, initially `municipality-rag-v1`. |
| `model_id`, `model_revision` | nullable text / nullable 40 lowercase hex | model artifact identity | Null while queued before an LLM attempt; required and exact for every terminal result reached after LLM invocation, never caller input. |
| `prompt_schema_version` | text | prompt/output schema version | Required immutable server version. |
| `generation_status` | enum | — | Required: `queued`, `processing`, `completed`, or `failed`. |
| `source_status` | nullable enum | — | Null before retrieval; then `relevant_source_found` or `no_relevant_source`. |
| `result_status` | nullable enum | — | Null until successful terminal output; then `draft_ready` or `review_required`. |
| `correspondence_type` | nullable enum | — | Null until completion; `response_letter`, `information_letter`, `referral_letter`, `cover_letter`, or `other`. |
| `correspondence_type_detail` | nullable UTF-8 text | Unicode code points | Allowed only for `other`; non-blank when present. |
| `document_summary`, `draft_text` | nullable UTF-8 text | Unicode code points | Written together only for a completed valid result. |
| `regulation_suggestions` | JSONB array | resolved citations | Empty only for `no_relevant_source`; otherwise retrieval-owned citation objects. |
| `model_attempt_count` | small integer | attempts | Starts at 0; maximum 2 structured-generation attempts. |
| `error_code` | nullable stable uppercase token | — | Null except failed terminal generation. |
| `created_at`, `completed_at` | timestamptz / nullable timestamptz | UTC instant | Database-generated; completed_at is set once on either terminal state. |

**Invariants** (must always hold true):

- The record snapshots the F-02/F-03/corpus/model/prompt inputs selected at
  creation and is never overwritten by a newer case revision or generation.
- Lifecycle fields may advance only `queued -> processing -> completed|failed`.
  Once terminal, every result, citation, and error field is immutable.
- `completed` requires both source/result statuses, a legal correspondence
  type, summary, draft, and a JSON array of citations. A relevant-source
  completion has one or more citations; a no-source completion has exactly
  zero. `failed` requires an error code and exposes no partial output through
  GET.
- Citations are resolved from the retrieval result, not model-supplied text;
  every persisted/public item contains `source_id`, `corpus_version`, `title`,
  `source_type`, `locator`, and `chunk_id`.

**Boundary Behavior:**

- Min/Max: exactly 0..2 model attempts; model revision is exactly 40 lowercase
  hexadecimal characters; source/result statuses are absent before the relevant
  stage and never contain another enum value.
- Empty/Null/Zero: an empty retrieval set is valid only with
  `no_relevant_source`, `review_required`, and `[]`; no null/blank draft,
  summary, or type is a completed result.
- Overflow/Truncation: summary, draft, excerpt, and citation metadata obey the
  fixed PromptAndResultBudgetV1 limits; persistence rejects over-limit values
  rather than silently truncating a legal or citizen-facing document.

**Concurrency / Race-Scenario Analysis:**

- `generation_id` is the logical-result key. Concurrent/recovered workers can
  only terminalize it through a locked, expected-`processing` transition; one
  terminal result is possible.
- If F-03 changes while a worker runs, that worker may safely retain its
  revision-4 historical result but its conditional current-pointer update has
  no effect on revision 5.

### Entity: CorrespondenceGenerationJob

Traces to: US-109 (docs/design/DESIGN_0df0ad1_f04.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `job_id` | UUID | durable-job identity | Primary key; returned by accepted POST. |
| `generation_id` | UUID | logical-result identity | Required unique foreign key; exactly one job per generation. |
| `state` | enum | — | `pending`, `claimed`, or `completed`. |
| `attempt_count` | non-negative integer | lease claims | Starts at 0 and increments once per successful claim. |
| `claimed_until` | nullable timestamptz | UTC instant | A renewable finite lease; null when pending or completed. |
| `created_at`, `updated_at` | timestamptz | UTC instant | PostgreSQL-generated. |

**Invariants** (must always hold true):

- The job and its queued generation commit atomically. No committed generation
  can lack a durable job and no job can reference an uncommitted generation.
- A job is completed only in the same terminal transaction that marks its
  generation completed or failed. A dependency failure leaves it pending or
  reclaimable; PostgreSQL remains the recovery authority after restart.
- Structured output consumes at most two model attempts for one generation.
  The second invalid output terminalizes `failed/STRUCTURED_OUTPUT_INVALID`;
  it is not a third queued model attempt.

**Boundary Behavior:**

- Min/Max: claim attempts are non-negative; lease seconds are a strictly
  positive worker setting and must cover the bounded model/repair operation.
- Empty/Null/Zero: null `claimed_until` is valid only for pending/completed;
  no payload duplicates document text because the job references generation.
- Overflow/Truncation: a claim-count overflow or invalid state transition
  rolls back and leaves durable work visible rather than discarding it.

**Concurrency / Race-Scenario Analysis:**

- Claiming uses `FOR UPDATE SKIP LOCKED` over pending and expired claimed jobs,
  then atomically changes it to claimed with a lease. Competing workers cannot
  own a non-expired lease.
- The worker renews its lease before each remote LLM attempt. A crash before a
  terminal transaction makes the job reclaimable; a crash after commit finds a
  completed job and cannot create another result.

### Entity: CorrespondenceReplay

Traces to: US-109 (docs/design/DESIGN_0df0ad1_f04.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `principal_id` | opaque text | authenticated principal | Stable authorization-adapter subject; never a bearer token. |
| `case_id` | UUID | case identity | Composite replay scope component. |
| `idempotency_key` | UUID | replay identity | Composite replay scope component. |
| `source_case_revision` | positive bigint | request intent | Required immutable accepted/replayed revision. |
| `request_fingerprint` | 64 lowercase hex | SHA-256 digest | Required digest of method, case, revision, and canonical empty body. |
| `generation_id`, `job_id` | UUID | canonical result identities | Required references to the one accepted generation/job. |
| `response_status`, `response_body` | integer / JSONB | canonical HTTP response | Required 202 start response; stored without credentials or source text. |
| `created_at` | timestamptz | UTC instant | PostgreSQL-generated. |

**Invariants** (must always hold true):

- Its unique key is `(principal_id, case_id, idempotency_key)`. The same key
  cannot be shared by principals or cases.
- Exact replay returns its canonical response without another job, model call,
  revision mutation, or pointer change. A changed fingerprint/revision yields
  `IDEMPOTENCY_KEY_REUSED` before mutation.

**Boundary Behavior:**

- Min/Max: SHA-256 is exactly 64 lowercase hex; canonical response body holds
  the four required 202 properties only.
- Empty/Null/Zero: no replay is created for malformed, denied, not-ready,
  stale, or conflict requests; no raw PII/evidence resides in a replay row.
- Overflow/Truncation: a serialization/persistence failure rolls back both
  first-start state and replay, never returning an unrepeatable acceptance.

**Concurrency / Race-Scenario Analysis:**

- The replay unique index and current-case row lock are acquired in the same
  transaction. Two identical first requests converge on one row; the loser
  reads the committed canonical acceptance.

### Entity: RegulationCorpusBuild and RegulationChunk

Traces to: US-109 (docs/design/DESIGN_0df0ad1_f04.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `corpus_version` | text | build identity | Required stable value; initial build `demo-municipality-regulations-v1`. |
| `source_id` | stable text | regulation identity | Required; initial snapshot set is `REG-001` through `REG-006`. |
| `title`, `source_type`, `official_source_url`, `document_date` | text/text/nullable URI/nullable date | official-source metadata | Title/type required; URL/date optional provenance. |
| `chunk_id` | stable text | citation identity | Required, unique within a corpus build; e.g. `REG-002-chunk-014`. |
| `locator`, `excerpt`, `content` | UTF-8 text | human locator / display excerpt / indexed source text | Required; locator is article/section/heading where available. |
| `embedding` | 1024-element normalized vector | dense semantic representation | Required for active chunks; produced by pinned `BAAI/bge-m3` and L2-normalized. |
| `search_policy` | versioned JSON metadata | corpus selection/ranking policy | Optional taxonomy IDs/tags/boosts only; never Python hard-coded mappings. |

**Invariants** (must always hold true):

- Corpus content is repository-owned, versioned, offline, and derived from the
  approved public official snapshots; a build is immutable once used by a
  generation.
- `search_policy` can filter/boost a known F-02 taxonomy ID but cannot choose a
  department, unit, request type, or legal conclusion. Retrieval remains
  semantic when no matching policy entry exists.
- A retrieval citation is constructed from this metadata. The model receives
  only allowed `chunk_id` references and cannot invent one.

**Boundary Behavior:**

- Min/Max: every active chunk has all six mandatory citation fields; embeddings
  have exactly 1024 dimensions; retrieval takes top 5 and passes only chunks
  scoring at least 0.60 to Jamba.
- Empty/Null/Zero: no selected chunk is a valid retrieval outcome, not a corpus
  or model failure; `official_source_url`/`document_date` may be null.
- Overflow/Truncation: corpus ingestion rejects invalid/oversize chunks before
  build publication; no source text is silently clipped while generating
  citation locators.

**Concurrency / Race-Scenario Analysis:**

- Workers bind the selected `corpus_version` at generation creation, then read
  its immutable chunk set. A later deployment/build cannot alter citations for
  an already queued generation.

### Entity: RetrievalConfigurationV1

Traces to: US-109 (docs/design/DESIGN_0df0ad1_f04.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `retrieval_config_version` | literal text | configuration identity | Required; initial `municipality-rag-v1`. |
| `embedding_model_id` | literal text | model identity | Required; `BAAI/bge-m3`. |
| `embedding_dimension` | positive integer | vector dimensions | Required; exactly 1024. |
| `normalization`, `similarity_metric` | literal enums | vector treatment/ranking metric | Required; exactly `l2` and `cosine`. |
| `top_k`, `min_cosine_similarity` | integer/decimal | chunks/normalized cosine score | Required; exactly 5 and 0.60. |
| `benchmark_id`, `benchmark_result` | text / JSONB | calibration evidence | Required for a published configuration; records positive/negative retrieval evaluation. |

**Invariants** (must always hold true):

- Query and corpus vectors are L2-normalized before cosine comparison. Results
  sort by descending score with stable `chunk_id` ascending tie-break.
- Only top-5 chunks with score `>= 0.60` enter Jamba context. None means
  `no_relevant_source`; one or more means `relevant_source_found`.
- Any calibrated threshold/model/config change creates a new configuration
  version and benchmark record; each generation snapshots that version.

**Boundary Behavior:**

- Min/Max: cosine score is in `[-1, 1]`; 0.599999... is not relevant while
  exactly 0.60 is relevant; five is the maximum selected source count.
- Empty/Null/Zero: zero candidates is valid no-source; a null/non-finite or
  wrong-dimension vector is a configuration/dependency failure, never score 0.
- Overflow/Truncation: chunks are excluded whole by ascending relevance when a
  later prompt budget needs room; they are never cut in the middle.

**Concurrency / Race-Scenario Analysis:**

- Workers use the configuration version captured in the generation row. A
  deployment cannot apply a new threshold to work queued under v1.

### Entity: StructuredDraft and PromptProjection

Traces to: US-109 (docs/design/DESIGN_0df0ad1_f04.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `document_summary` | UTF-8 text | Unicode code points | Required model JSON field; no direct unvalidated PII. |
| `recommended_correspondence_type` | enum | — | Required approved stable ID only. |
| `correspondence_type_detail` | nullable UTF-8 text | Unicode code points | Optional and accepted only with `other`. |
| `draft_text` | UTF-8 text | Unicode code points | Required model JSON field; placeholders remain literal until backend resolution. |
| `used_source_refs` | array of chunk IDs | citation references | Required, unique; subset of the retrieval-supplied IDs. |
| `normalized_document_projection` | UTF-8 text | redacted semantic content | Bounded normalized document with placeholders, never original text. |
| `accepted_field_projection` | JSON object | field ID → canonical value/placeholder | Server-built F-03 values; sensitive values are placeholders. |
| `pii_sanitization_config_version` | text | sanitizer configuration identity | Required immutable server configuration used for this projection. |

**Invariants** (must always hold true):

- The request schema is closed: these four required model properties plus the
  explicitly optional detail are the only accepted JSON members. Markdown,
  free prose, missing required members, unknown members, bad enum values, or a
  non-retrieved source ref are structured-output failures.
- If a response contains an otherwise parseable JSON object with equivalent
  field labels, the local BGE-M3 scorer may re-label existing values at an
  inclusive cosine score of `0.60`; one original key can fill only one closed
  field. This recovery never synthesizes text, PII, source references, or
  citation metadata, and its result passes every normal validation guard.
- Jamba is not an authority for F-02 choices, F-03 field validity, citations,
  or PII. The backend substitutes only F-03 accepted canonical values into
  its own known placeholders after output and citation validation succeed.
- With no retrieved source, `used_source_refs` must be `[]`; a deterministic
  no-source guard rejects legal-basis/citation claims before publication and
  controlled repair receives the same no-source context.
- Projection order is F-03 known-value replacement, deterministic residual
  recognizers, then a configured local high-confidence PERSON/ADDRESS pass.
  An uncertain PERSON/ADDRESS sentence is omitted, not guessed or forwarded.
- Versioned F-03 field metadata, not endpoint code, marks values as `redact`,
  `exclude`, or `task_required`. `applicant_address` is redacted;
  `incident_location` can remain only when explicitly task-required.

**Boundary Behavior:**

- Min/Max: one or two total model attempts; `used_source_refs` has 0..5 unique
  entries; rendered Jamba input is at most 8192 tokens and output at most 1800.
- Empty/Null/Zero: empty/non-object model JSON is invalid; an empty source list
  is permitted only with no-source behavior. A blank summary/draft/detail is
  invalid rather than replaced with model text.
- Overflow/Truncation: the builder retains F-03 semantic fields, then
  request-relevant sentences/description, then drops lowest-score full chunks
  until budget fits. It never blindly takes the first N characters or cuts a
  chunk. An over-limit response fails validation and is never published.

**Concurrency / Race-Scenario Analysis:**

- A repair uses the same generation ID, revision snapshot, retrieval output,
  and prompt schema, plus only the first validation-error summary. It cannot
  read newer F-03 values or fresh corpus chunks between attempts.

### Entity: PromptAndResultBudgetV1

Traces to: US-109 (docs/design/DESIGN_0df0ad1_f04.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `max_jamba_input_tokens` | positive integer | rendered Jamba tokens | Exactly 8192. |
| `instructions_and_schema_tokens`, `case_context_tokens`, `retrieval_context_tokens`, `safety_margin_tokens` | integers | tokens | At most 1200, 1800, 4500; margin at least 700. |
| `max_retrieval_chunks`, `max_single_chunk_tokens` | integers | chunks/tokens | Exactly 5 and at most 1200. |
| `max_output_tokens` | positive integer | generated Jamba tokens | Exactly 1800. |
| `max_document_content_characters` | positive integer | UTF-8 characters | Exactly 6000. |
| `max_summary_characters`, `max_draft_characters`, `max_type_detail_characters` | integers | UTF-8 characters | Exactly 600, 6000, and 200. |
| `max_citations`, `max_excerpt_characters`, `max_total_excerpt_characters` | integers | citations/UTF-8 characters/UTF-8 characters | Exactly 5, 500, and 2000. |

**Invariants** (must always hold true):

- The tokenizer is the same pinned Jamba tokenizer and rendered chat template
  as the LLM service; budgeting is actual model input, not character estimate.
- Instructions/schema, case context, retrieval, and margin never exceed 8192
  tokens. Excerpts are copied from corpus chunks, never model-written.
- A successful result has a non-blank summary within 600 characters, a
  non-blank draft within 6000 characters, and at most five citations within
  individual and total excerpt limits. The prompt targets a 2–4 sentence
  summary; that is a quality target, not a rejection rule.

**Boundary Behavior:**

- Min/Max: input/output at exactly 8192/1800 tokens are allowed; one extra
  token is rejected before inference. A 600/6000/200/500 character value is
  allowed; one extra character is an output validation failure.
- Empty/Null/Zero: zero retrieval context is valid for no-source; zero text
  limits are invalid config; empty required output strings are failures.
- Overflow/Truncation: chunks are removed whole by relevance; fields/citation
  locators are never clipped. Over-limit output is rejected, not shortened.

**Concurrency / Race-Scenario Analysis:**

- Prompt schema/configuration and chunk IDs are immutable per generation, so a
  repair cannot observe a different context after a concurrent deployment.

### Entity: NoSourceLegalClaimGuardV1

Traces to: US-109 (docs/design/DESIGN_0df0ad1_f04.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `used_source_refs`, `regulation_suggestions` | arrays | citation references | Both must be exactly empty for no-source output. |
| `citation_patterns` | versioned regex set | text patterns | Rejects `\\b\\d{3,6}\\s+sayılı\\b`, `\\bmadde\\s+\\d+\\b`, and `\\b\\d+\\.\\s*madde(si|sine|sinde|ye)?\\b`. |
| `authority_terms`, `authority_connectors` | versioned Turkish token sets | guard vocabulary | Legal nouns: kanun/yönetmelik/mevzuat/tebliğ/genelge/madde; connectors: uyarınca/gereğince/göre/kapsamında/hükmü. |
| `normative_claim_terms` | versioned Turkish token set | unsafe claim vocabulary | Includes zorunludur, yasaktır, kanunen mümkündür, yasal yükümlülüktür, and kurum yükümlülüğü forms. |
| `guard_version` | text | validation policy identity | Required immutable server version persisted with generation. |

**Invariants** (must always hold true):

- No-source output has empty references/citations before text checks.
- Citation patterns are case-insensitive Turkish-aware. A legal noun plus a
  connector in the same sentence fails; `başvurunuz gereğince` alone does not.
- Normative legal-claim vocabulary is conservatively rejected for no-source;
  an administrative rewrite is required instead of an ambiguous legal claim.
- Guard failure uses the one controlled retry with explicit no-law/no-article/
  no-authority instructions. A second guard failure is
  `failed/UNVERIFIED_LEGAL_CLAIM`; no draft is published.

**Boundary Behavior:**

- Min/Max: no-source citation count is exactly zero; any forbidden match fails.
- Empty/Null/Zero: blank/no JSON draft fails structured validation before guard;
  safe administrative language without a forbidden match is valid.
- Overflow/Truncation: guard scans the complete validated draft before storage;
  no text is truncated to evade a match.

**Concurrency / Race-Scenario Analysis:**

- Guard policy/version and source status are snapshotted with the generation;
  deployment cannot make its two attempts apply different guard rules.

## Technology / design decisions

### Decision D-137: Case revision and current pointer placement

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Extend `current_validation_states` with the F-04 current-generation pointer and use its revision | Reuses the sole current F-03 case state and its existing row lock/ETag semantics. | Couples the pointer migration to the validation-owned table. | ✅ |
| Create a new independently versioned F-04 case table | Separates correspondence storage. | Creates conflicting case revisions and cross-table synchronization. | ❌ |
| Use only a latest-generation query with no pointer | Fewer current-state columns. | Cannot implement the specified current result across superseding revisions efficiently or unambiguously. | ❌ |

**Why the first option:** F-03 already owns the only approved mutable case
state/revision, and the requirement permits a case-level current pointer.

**Why not a new table:** Its revision could diverge from the required F-03
`If-Match` value.

**Why not query-only current:** An old revision's completed generation could be
mistaken for the current result after supplemental information changes.

### Decision D-138: Durable topology and terminalization

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| `workflow` API plus same-image leased worker and PostgreSQL job table | Separates HTTP latency from work, survives restart, and needs no Redis/Kafka. | Adds a worker process and lease handling. | ✅ |
| In-process FastAPI background task | Fewest services. | Process restart loses dispatch ownership and cannot safely recover work. | ❌ |
| Redis/Kafka/RabbitMQ queue | Mature queue semantics. | Adds an unapproved mandatory dependency where PostgreSQL is authoritative. | ❌ |

**Why the first option:** It implements the requested PostgreSQL-backed durable
job/outbox flow and follows the F-02 worker pattern.

**Why not an in-process task:** It cannot meet the restart guarantee.

**Why not an external queue:** The operator explicitly made Redis optional and
did not approve Kafka/RabbitMQ.

### Decision D-139: Dynamic regulation retrieval policy

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Immutable local corpus build with semantic vectors and data-only search-policy metadata | Offline, reproducible, semantic, and taxonomy policy changes need data/build updates rather than code mapping. | Requires a pinned embedding profile and corpus build tooling. | ✅ |
| Python `if request_type == ...` routing | Small initial implementation. | Explicitly forbidden hard-coded mapping; bypasses semantic retrieval. | ❌ |
| Internet search at generation time | Could access fresh material. | Violates the offline local-corpus requirement and makes citations non-reproducible. | ❌ |

**Why the first option:** It makes policy genuinely dynamic while retaining the
approved versioned public-source corpus.

**Why not Python routing:** Corpus/taxonomy metadata, not application code,
must control optional filtering/boosting.

**Why not internet search:** F-04 must not leave the local corpus.

### Decision D-140: PII and structured Jamba boundary

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Server-built redacted projection, closed JSON schema, retrieval ref allow-list, and backend placeholder resolution | Keeps F-03 authoritative and makes citations/output mechanically verifiable. | Prompt builder and repair validator are more deliberate. | ✅ |
| Send raw normalized document and accept free text | Small integration surface. | Exposes unnecessary PII and cannot prove citations/enums/required fields. | ❌ |
| Let Jamba emit PII/citation metadata then post-process heuristically | Flexible model output. | Lets the model invent/change critical values and loses source ownership. | ❌ |

**Why the first option:** It is the approved authoritative-F-03 PII rule and
the required structured-output/citation contract.

**Why not raw/free text:** It violates data minimization and cannot reject
unknown fields or fabricated refs deterministically.

**Why not post-process model authorities:** The requirements explicitly deny
Jamba authority over PII and citation metadata.

### Decision D-141: Existing service contract evolution

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Add F-04 case schemas/routes to the manifest; keep existing `/v1/retrieve` consumers compatible while adding citation metadata required by the F-04 RAG adapter; extend `/generate` with runtime model revision | Preserves current public routes while making durable F-04 provenance observable and testable. | Requires contract, mock, Docker baseline, and CI updates together. | ✅ |
| Add a client-supplied generation payload or a separate public RAG endpoint | Looks explicit to callers. | Violates backend-authoritative input and expands the public surface unnecessarily. | ❌ |
| Bypass the RAG/LLM services and write a second generator in workflow | Fewer protocol changes. | Duplicates existing logical services and weakens Jamba/runtime provenance. | ❌ |

**Why the first option:** It preserves current routes as requested while
evolving only the information F-04 must consume.

**Why not a new public payload/endpoint:** The client must not own prompt,
taxonomy, fields, or correspondence choice.

**Why not duplicate services:** F-04 is an orchestrator over retrieval and
Jamba, not a replacement for either.

### Decision D-142: Failure/retry distinction

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Retry transient dependency/lease failures durably; terminalize only validated structured-output exhaustion as specified | Preserves pending work through restarts while honoring the exact two-attempt model rule. | Requires operators to observe persistent dependencies. | ✅ |
| Mark every first dependency failure as terminal failed | Simple status handling. | Loses recoverable work after a container/network/model restart. | ❌ |
| Treat no retrieved source as failed | Few output variants. | Explicitly contradicts the review-required draft behavior. | ❌ |

**Why the first option:** It keeps durable work recoverable and reserves
`STRUCTURED_OUTPUT_INVALID` for the required two-attempt validation rule.

**Why not terminalize dependencies:** An unavailable local service is not a
logical generation result.

**Why not fail no-source:** Zero results is an expected domain outcome.

### Decision D-143: Exact Jamba budget enforcement

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Add an internal LLM tokenizer-count operation using the loaded pinned tokenizer/chat template; configure F-04 capacity as 8192 input and 1800 output tokens | Enforces the actual model-token boundary and preserves a prompt-only public generation API. | Adds one internal request before generation and expands existing LLM test/config limits. | ✅ |
| Estimate tokens from character count in workflow | No LLM interface change. | Turkish/tokenizer variation can exceed the hard model limit. | ❌ |
| Let `/generate` reject oversized prompts after assembling all context | Smallest worker. | Cannot deterministically remove lowest-score whole chunks before a model attempt. | ❌ |

**Why the first option:** F-04 has an exact 8192-token requirement; only the
loaded Jamba tokenizer plus rendered chat template can measure it correctly.
`/generate` remains client prompt-only. The internal counter receives only the
already sanitized prompt. The LLM runtime's configured input/output ceilings
evolve from 1024/512 to 8192/1800 for this approved F-04 capacity.

**Why not character estimation:** It cannot prove the token budget at the
boundary.

**Why not late rejection:** It loses the approved relevance-aware source
selection order.

### Decision D-144: Current revision with no generation

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| HTTP 200 with `generation_status: not_requested` and `result: null` | Distinguishes an available case awaiting a POST from an error or an old draft. | Adds one read-only status value. | ✅ |
| HTTP 404 | Familiar absent-resource semantics. | Incorrectly treats an accessible case/revision as absent. | ❌ |
| Return the previous revision's draft as current | Offers a visible draft. | Explicitly presents stale information as current. | ❌ |

**Why the first option:** A revision can exist without an F-04 operation; the
response makes that state explicit and never leaks G1 as revision 7's result.
`previous_generation_available: true` is optional informational metadata only.

**Why not 404:** The case exists and access has succeeded.

**Why not return G1:** It violates immutable current-revision semantics.

### Decision D-145: No-source publication guard

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Closed citation/ref check plus deterministic legal-citation, legal-authority, and normative-claim guard before publication | Prevents an unsourced hallucinated legal claim from reaching even review-required output. | Conservative vocabulary can require a plainer administrative rewrite. | ✅ |
| Prompt instruction only | Minimal implementation. | Cannot enforce the explicit safety rule when Jamba ignores an instruction. | ❌ |
| Publish unsafe draft with a review banner | Keeps more text available to a reviewer. | Explicitly rejected: review_required is not sufficient for hallucinated law/article claims. | ❌ |

**Why the first option:** It implements the supplied deterministic rules and
gives a precise terminal `UNVERIFIED_LEGAL_CLAIM` outcome after the controlled
retry.

**Why not prompt-only:** Model behavior is not a validation boundary.

**Why not banner-only publication:** It exposes the unsafe content the guard
is intended to prevent.

## Contract migration and verification

- Add `POST`/`GET /cases/{case_id}/correspondence` under the existing logical
  `workflow` service in the HTTP manifest, with distinct start, current-result,
  and F-04 nested-error schemas. Preserve existing `/v1/workflows/document`,
  `/v1/retrieve`, and `/generate` routes; no client semantic generation fields
  are added.
- The 202 response is exactly `case_id`, `job_id`, `case_revision`, and
  `generation_status: queued`. GET returns HTTP 200 with
  `generation_status: not_requested` and `result: null` when the current
  revision has no pointer; it never presents an old revision as current.
  Processing/completed/failed shapes remain approved; failed responses never
  include summary, draft, source, or citation fields.
- Extend the local `rag` adapter/result only additively for the citation data
  F-04 needs. It receives a PII-minimized query and returns chunk metadata;
  worker code maps it to the approved snake_case public citation object.
  Extend `llm /generate` success metadata with the exact model revision and add
  an internal sanitized-prompt token-count operation using the rendered Jamba
  tokenizer/template. Raise server F-04 capacity to 8192 input / 1800 output
  tokens without accepting client generation controls.
- Add a real workflow/correspondence Compose overlay with PostgreSQL, local
  corpus, deterministic structured LLM/RAG test ports for CPU CI, and a
  separately labelled GPU smoke invoking the real Jamba route. Test doubles
  remain test fixtures and are not documented as real Jamba/RAG service runs.
- Contract/mock changes run the README Docker baseline exactly. Real-service
  acceptance tests falsify: valid 202 queue, `{}`/empty body acceptance,
  semantic payload rejection, access denial, stale/precondition/key reuse,
  missing vs invalid F-03 409/no mutation, exact replay, current GET variants,
  citation allow-list, BGE-M3 top-5/cosine 0.60 boundaries, no-source guard
  regex/authority/normative rejections, first-output repair/second failure,
  worker crash/lease recovery, and revision-4 history not becoming revision-5
  current state.
- Boundary tests cover `Idempotency-Key` UUID validity, quoted revision 1 and
  bigint limits, the exact two model attempts (one/second/third disallowed),
  0 and N citation refs, `other` detail conditionality, exact 0.60 retrieval,
  8192/1800 token and character limits, residual PII placeholders, and
  `not_requested` after a revision supersedes a prior generation.

## Architecture open questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| AQ-110 | Which pinned, locally available embedding model/profile and score threshold define semantic relevance for `demo-municipality-regulations-v1`? | solution-architect | Resolved | `BAAI/bge-m3` dense 1024-dimensional L2-normalized cosine vectors; top_k 5; config version `municipality-rag-v1`; relevance is cosine `>= 0.60`. Calibration changes require a new config version and benchmark record. |
| AQ-111 | What exact deterministic PII-redaction policy applies to residual PII in normalized free text outside F-03 validated fields? | solution-architect | Resolved | First replace F-03 known values via exact/normalized span matching; then detect/replace valid TCKN, phone, e-mail, IBAN, tax number, and configured identifier patterns; then use local high-confidence PERSON/ADDRESS recognition, omitting uncertain sentences. Schema metadata distinguishes redact/exclude/task_required locations. |
| AQ-112 | What exact prompt/result limits and token-budget allocation apply? | solution-architect | Resolved | Jamba input 8192 tokens: instructions/schema <=1200, case <=1800, retrieval <=4500, margin >=700; max 5 whole chunks <=1200 each. Output <=1800 tokens; document content 6000 chars; summary/draft/type detail 600/6000/200; citations 5 with 500/2000 excerpts. |
| AQ-113 | What does GET return when current revision has no F-04 generation? | solution-architect | Resolved | HTTP 200 `{case_id, case_revision, generation_status: not_requested, result: null}`; old history is never returned as current. |
| AQ-114 | Which deterministic no-source guard prevents unsafe legal claims? | solution-architect | Resolved | Require empty refs/citations; reject supplied citation/article regexes, same-sentence legal noun+authority connector, and conservative normative legal-claim terms. Retry once; second guard failure is `UNVERIFIED_LEGAL_CLAIM` with no draft publication. |
