# Design Session — US-109 F-04 legislation and official correspondence

> Linked from [DESIGN.md](DESIGN.md). This file holds the F-04
> requirement-analysis session and remains a permanent linked record.

## User Stories

### US-109: Mevzuat önerisi, özet ve resmî yazı taslağı

As a document-processing operator
I want a complete municipal-document case to receive source-grounded
legislation recommendations, a concise Turkish summary, and an appropriate
official-correspondence draft
So that an authorized human can review a usable, non-fabricated response before
any later routing or sending step.

F-04 consumes F-02's current classified taxonomy chain and F-03's current
validation state. It must not independently reclassify the document or infer
required fields. A case is eligible only when F-03's authoritative
`completionStatus` is `complete`; `missing_information` and
`invalid_information` cannot receive a final correspondence draft. Retrieval
and Jamba generation remain distinct responsibilities: retrieval supplies
source-grounded context, while Jamba may produce only a draft. It cannot
invent legislation, article numbers, dates, file numbers, or personal data.
Automatic signature, approval, notification, or transmission is out of scope.

The feature-pack establishes the intended outcome but does not define the
terminal-result shape and did not reconcile its English request-type boosting
examples with the existing F-02 taxonomy IDs. The operator resolved both on
2026-08-25: retrieval policy is data-driven rather than hard-coded, and the
existing feature-pack correspondence-result fields are retained and minimally
extended below for the defined status/citation model.

### Final retrieval, safety, and current-read decisions

F-04 uses the local `BAAI/bge-m3` dense embedding model (1024 dimensions,
L2-normalized cosine similarity) with `top_k: 5`. The versioned
`municipality-rag-v1` configuration sets `min_cosine_similarity: 0.60`:
only chunks at or above it enter Jamba context; no such chunk produces
`no_relevant_source`. Threshold calibration changes require a new retrieval
configuration version and recorded positive/negative benchmark result.

Before retrieval/Jamba, normalized text receives F-03 known-value placeholder
replacement, deterministic residual TCKN/phone/e-mail/IBAN/tax/identifier
sanitization, and high-confidence local PERSON/ADDRESS handling. Uncertain
PERSON/ADDRESS sentences are omitted. Versioned field metadata distinguishes
redacted applicant addresses from task-required incident locations.

The Jamba input is at most 8192 tokens: instructions/schema 1200, case 1800,
retrieval 4500, safety margin at least 700. At most five whole 1200-token
chunks are used. Output is at most 1800 tokens; summary/draft/type detail are
600/6000/200 characters; citations are at most five with 500-character each
and 2000-character total excerpts. Current revision without a generation
returns HTTP 200 with `generation_status: not_requested` and `result: null`.

For `no_relevant_source`, citation refs/suggestions must be empty and a
deterministic legal-claim guard rejects specified law/article patterns,
legal-noun plus authority-connector claims, and conservative normative legal
claims. One repair is permitted; a second guard failure is
`UNVERIFIED_LEGAL_CLAIM` and publishes no draft.

### Public result contract

`GET /cases/{case_id}/correspondence` has no result-history list: it reads the
case's current generation pointer for its current case revision. It returns:

- while queued/processing: `case_id`, `case_revision`, and
  `generation_status`;
- on completed generation: those fields plus `generation_id`,
  `source_status`, `result_status`, `corpus_version`,
  `document_summary`, `recommended_correspondence_type`, optional
  `correspondence_type_detail`, `draft_text`, and
  `regulation_suggestions`;
- on failed generation: `case_id`, `case_revision`, `generation_id`,
  `generation_status: failed`, and `error_code`, without a partial draft.

`recommended_correspondence_type` is one stable ID from the approved enum.
Each public regulation suggestion contains the retrieval-owned mandatory
citation metadata: `source_id`, `corpus_version`, `title`, `source_type`,
`locator`, and `chunk_id`; its optional `official_source_url`,
`document_date`, `excerpt`, and `retrieval_score` may be present. Internal
model revision, prompt/schema versions, attempts, and immutable historical
records remain in PostgreSQL rather than this current-result response.

## Gherkin Acceptance Criteria

Feature: F-04 source-grounded official correspondence generation

  Scenario: An authorized caller queues generation for a complete immutable case revision
    Given an authorized principal can access a case at current revision `4`
    And F-03's authoritative completion status is `complete`
    When it sends `POST /cases/{case_id}/correspondence` with Bearer authorization,
      an Idempotency-Key UUID, and `If-Match: "4"`
    Then the service creates one immutable generation record and one durable PostgreSQL job atomically
    And it returns HTTP 202 with `case_id`, `job_id`, `case_revision: 4`, and `generation_status: queued`
    And the client-supplied request has no prompt, taxonomy, field, or correspondence-type input

  Scenario: An identical generation start is idempotently replayed
    Given an authenticated principal has queued a correspondence generation for case revision `4`
    When the same principal repeats the same case, revision, and Idempotency-Key
    Then it receives the original job or terminal result
    And no second generation record or durable job is created

  Scenario: A reused key or stale case revision cannot start another generation
    Given an authenticated principal has used an Idempotency-Key for a correspondence generation
    When it reuses that key for another revision or request intent
    Then it receives HTTP 409 with code `IDEMPOTENCY_KEY_REUSED`
    And no second generation is created
    When it sends an otherwise valid request with a stale If-Match revision
    Then it receives HTTP 412 with code `CASE_REVISION_CONFLICT`
    And no generation job is created

  Scenario: An incomplete or invalid case cannot queue F-04
    Given F-03's authoritative completion status is `missing_information` or `invalid_information`
    When an authorized caller starts correspondence generation with a current If-Match revision
    Then it receives HTTP 409 with code `CASE_NOT_READY_FOR_CORRESPONDENCE`
    And the response identifies `waiting_for_user` and the current completion status
    And no job is created, Jamba is not called, and the case revision does not change

  Scenario: An unauthorized caller cannot read or start a known case's generation
    Given a caller knows a case ID but has no access to that case
    When it calls either F-04 case-level endpoint
    Then the service rejects the caller without disclosing a generation result
    And it creates no generation job

  Scenario: Retrieval-backed generation produces only retrieval-grounded citations
    Given a queued generation is processing a complete case revision
    And local corpus `demo-municipality-regulations-v1` returns relevant chunks
    When the worker retrieves, redacts/minimizes model context, and invokes Jamba
    Then the model receives only the F-02/F-03 authoritative context, allowed correspondence types,
      retrieval chunks, citation reference IDs, and the structured output schema
    And each returned citation is resolved from retrieval metadata with source_id, corpus_version,
      title, source_type, locator, and chunk_id
    And the completed result has `source_status: relevant_source_found` and `result_status: draft_ready`

  Scenario: Current-result reading distinguishes processing, completed, and failed generation
    Given an authorized caller reads the current correspondence generation for a case revision
    When its generation is queued or processing
    Then it receives case_id, case_revision, and the current generation_status only
    When its generation is completed
    Then it additionally receives generation_id, source/result status, corpus version, summary,
      stable correspondence type, draft, and retrieval-owned citations
    When its generation has failed
    Then it receives generation_id and error_code without a partial draft

  Scenario: No relevant source produces a review-required draft without fabricated law references
    Given local retrieval returns no relevant corpus chunk for a complete case revision
    When the worker generates an official-format draft
    Then it persists `generation_status: completed`, `source_status: no_relevant_source`,
      `result_status: review_required`, and an empty regulation-suggestions list
    And the draft contains no asserted legislation, article number, or legal-basis claim
    And absence of a source is not treated as a model failure

  Scenario: Structured-output validation semantically recovers only existing model values
    Given Jamba returns a JSON object surrounded by Markdown/noise or with semantically equivalent field labels
    When strict closed-schema validation rejects the object
    Then the backend may extract that object and use local BGE-M3 cosine search with inclusive score `>= 0.60`
      to re-label existing values to the closed fields and stable correspondence-type enum
    And each input key may satisfy at most one closed field
    And the recovery never creates text, source references, citation metadata, or PII values
    And the recovered object still passes the complete schema, citation, and no-source legal-claim guards

  Scenario: Structured-output validation allows one generation repair and never publishes partial output
    Given Jamba's first output has an unknown field, an invalid correspondence type,
      a missing required field, or an unreturned citation reference
    When backend schema and citation validation rejects that output
    Then it makes at most one controlled repair attempt with the same generation ID and source context
    And if the second output is invalid, it persists `generation_status: failed` with
      `error_code: STRUCTURED_OUTPUT_INVALID`
    And no partial draft becomes the current result or advances to F-05

  Scenario: Generation survives a worker or container restart
    Given a durable F-04 job is queued or has an expired processing lease
    When its worker or container restarts
    Then PostgreSQL recovers the immutable generation and durable job
    And a lease-safe retry produces at most one logical terminal result for that generation ID

  Scenario: A newer case revision supersedes rather than overwrites an earlier generation
    Given generation `G1` is complete for case revision `4`
    When authoritative supplemental information advances the case to revision `5`
    Then `G1` remains immutable history but is not current for revision `5`
    And a new accepted F-04 request can create generation `G2` for revision `5`

  Scenario: Corpus policy adapts to taxonomy and corpus metadata without code routing
    Given a corpus build declares searchable metadata or boosts for a taxonomy request type
    When retrieval builds a query for that classified request type
    Then it uses that versioned corpus policy only as search-space filtering or ranking input
    And changing corpus/taxonomy metadata does not require a hard-coded F-02 request-type mapping

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-130 | F-04 hangi public boundary ile başlatılır ve sonucu nasıl okunur: mevcut `workflow` service altında yeni case-level endpoint, mevcut `rag`/`llm` endpoint’lerinin yalnız internal orchestration’ı, yoksa başka bir onaylı route mu? Method, path, authorization ve idempotency davranışı nedir? | requirement-analysis | Resolved | Case-level async boundary: `POST /cases/{case_id}/correspondence` requires Bearer authorization, UUID Idempotency-Key, and quoted If-Match; no client semantic inputs. It returns 202 queued. `GET /cases/{case_id}/correspondence` requires authorization and reads processing/current result. Replay scope is authenticated principal + case + key; stale revision is 412. |
| OQ-131 | Demo için authoritative mevzuat/standart yazışma corpus’u nereden gelir: repository-owned sentetik/curated belediye kaynakları mı, belirli resmi açık kaynaklar mı, yoksa operator tarafından sağlanan bir corpus mu? Her öneride zorunlu citation alanları nelerdir? | requirement-analysis | Resolved | Offline, versioned local corpus `demo-municipality-regulations-v1` uses official public-text snapshots for REG-001 through REG-006. Retrieval-owned citations require source_id, corpus_version, title, source_type, locator, and chunk_id; Jamba never creates citation metadata. |
| OQ-132 | Retrieval hiç kaynak bulamazsa F-04 tam olarak hangi sonucu üretir: yalnız `no_relevant_source` ve taslak yok mu, kaynak-iddiası içermeyen bir bilgi talebi/cevap taslağı mı, yoksa insan incelemesine mi gider? | requirement-analysis | Resolved | Generate a case-content/official-format draft without legal claims. Persist source_status `no_relevant_source`, result_status `review_required`, and no suggestions. This is not generation failure. |
| OQ-133 | F-04 sonucunun kesin public schema’sı, allowed `recommendedCorrespondenceType` değerleri, status’ları ve Türkçe resmî üslup/kalite kabul rubriği nedir? | requirement-analysis | Resolved | Lifecycle: queued/processing/completed/failed; source: relevant_source_found/no_relevant_source; result: draft_ready/review_required. Types are response_letter, information_letter, referral_letter, cover_letter, or other plus optional detail. The current terminal GET shape is resolved in OQ-138. |
| OQ-134 | Özet, draft, retrieval referansları ve generation metadata PostgreSQL’de current-only olarak mı persist edilir; yeniden denemeler/idempotency ve container restart sırasında pending generation nasıl dayanıklı kalır? | requirement-analysis | Resolved | Persist immutable generation history plus case current-generation pointer. PostgreSQL durable outbox/job creates generation atomically; lease-safe workers retry stale work and must not create a second logical result for a generation ID. |
| OQ-135 | Jamba’ya hangi canonical context verilir (normalized text, F-02 IDs/labels, F-03 accepted fields, retrieval excerpts) ve prompt/response PII redaction, maximum size, timeout ve structured-output failure davranışı nedir? | requirement-analysis | Resolved | Redact/minimize PII with F-03 validated values as the sole authority; model preserves placeholders and backend resolves them. Model gets bounded canonical semantic context, allowed type enum, retrieval chunks/refs, and JSON schema. Unknown fields, invalid enum/missing required values, or unknown citations are schema failures; allow one repair, then fail `STRUCTURED_OUTPUT_INVALID`. |
| OQ-136 | F-03 `missing_information` veya `invalid_information` durumunda F-04 çağrısı HTTP reddi mi döner, current workflow state’i `waiting_for_user` olarak mı kalır, yoksa ikisi farklı çağıranlar için farklı mı uygulanır? | requirement-analysis | Resolved | Return HTTP 409 `CASE_NOT_READY_FOR_CORRESPONDENCE`, retain `waiting_for_user`, create no job, call no Jamba, and do not change revision. |
| OQ-137 | Kararda geçen `address_change_request`, `business_license_application`, `road_sidewalk_issue`, ve `environmental_cleaning_complaint` corpus-boost mapping’leri mevcut F-02 taxonomy ID’leri (`adres-bildirimi`, `ruhsat-basvurusu`, vb.) ile nasıl eşleşir; F-02’de bulunmayan iki request type eklenmeli mi? | requirement-analysis | Resolved | Hard-coded mapping or F-02 taxonomy additions are not allowed. A versioned corpus/search-policy metadata layer dynamically supplies optional request-type filtering/boosting; retrieval remains semantic and works without a matching boost entry. |
| OQ-138 | `GET /cases/{case_id}/correspondence` terminal response’unun başarı, `review_required`, ve `failed` durumlarında exact public JSON schema’sı nedir; immutable history metadata’sından hangileri dışarı açılır? | requirement-analysis | Resolved | No F-04 automated test existed. Preserve the feature-pack's existing result fields and minimally extend them: processing exposes case/revision/status; completed exposes current summary, stable type, draft, source/result status, corpus version, and retrieval citations; failed exposes ID/status/error only. Internal prompt/model/attempt/history metadata remains persisted but non-public. |
