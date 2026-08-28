# Design Session — split from DESIGN.md at commit `bd84424`

> Linked from [DESIGN.md](DESIGN.md). This is a permanent requirement-analysis record for the RAG corpus-governance request.

## Analysis Context

- Source request: human operator, 2026-08-28. Do not stop the running Jamba-model download.
- Current real F-04 retrieval is an in-process `workflow` worker over versioned `services/workflow/corpus.json`; it has no real RAG HTTP service or corpus-management API.
- `feature/autonomous-core-integration` at `1e196764` contains a standalone `mevzuat-rag` package. It offers Qdrant dense/sparse indexing, local Markdown/PDF ingestion, source-hash skip, local file watch, PII redaction for PDF ingestion, retention helpers, audit records, and opt-in per-query small/medium/large resource profiles. It is not contract-compatible with current F-04, uses a separate Compose topology and dependencies, and its default generation configuration names a remote DeepSeek provider. It must not be merged wholesale into the offline contract-first runtime.
- Existing operator panel already reads the original case document through `GET /cases/{case_id}/document`. Existing BX-03A has attachment metadata APIs, but no panel upload/delete flow and no RAG-corpus management flow.
- Minimal candidate: retain `workflow` as F-04 retrieval owner; selectively reuse branch ingestion/indexing ideas only after approved lifecycle and boundary decisions. Do not create another public RAG service or merge the standalone UI.

## User Stories

### BX-12: Yönetilen RAG kaynak korpusu

As a kurum yöneticisi
I want RAG kaynak belgelerini kurum panelinden yönetmek
So that official-draft retrieval uses current, reviewable local sources.

PDF/DOCX source files are converted to normalized text through the OCR boundary. PaddleOCR is an allowed implementation candidate for raster/OCR extraction; DOCX text extraction remains part of the same OCR-boundary operation. A panel add action completes only after text conversion and corpus indexing succeed. RAG sources are hard-deleted on delete.

### BX-13: Panel belge işlemlerinin ayrıştırılması

As a kurum operatörü
I want case belgesi, case eki, and RAG kaynak belgesi işlemlerini ayrı yüzeylerde görmek
So that citizen evidence cannot be mistaken for authoritative retrieval material.

The institution panel manages both the case document/attachment surface and the RAG-source surface, but they remain visibly distinct. Existing case-document view stays an evidence view; it is not RAG authority.

### BX-14: Dinamik retrieval kapasitesi

As a platform operator
I want retrieval resource limits to adapt safely to authoritative corpus size
So that corpus growth does not silently exhaust GPU/latency budgets.

The selection favors minimum VRAM and inexpensive embedding/vector storage. `feature/autonomous-core-integration` profile logic remains reference material until an architecture selects measurable bounds.

## Gherkin Acceptance Criteria

Feature: Yönetilen RAG kaynak korpusu

  Scenario: Operator adds a PDF or DOCX source synchronously
    Given an authorized institution operator selects a PDF or DOCX RAG source
    When the operator presses add
    Then the OCR boundary converts it to normalized text
    And the source becomes searchable only after its corpus index succeeds
    And the panel returns the current source and corpus version

  Scenario: Text conversion or indexing fails
    Given an authorized institution operator selects a source that cannot be converted or indexed
    When the operator presses add
    Then the panel reports the failure
    And the source is not searchable by F-04 retrieval
    And the existing corpus remains unchanged

  Scenario: Operator edits an indexed RAG source
    Given an authorized institution operator opens an indexed RAG source
    When the operator changes the source and saves it
    Then the replacement normalized text is indexed before the change is visible
    And subsequent retrieval uses the replacement source version

  Scenario: Operator hard-deletes an indexed RAG source
    Given an authorized institution operator opens an indexed RAG source
    When the operator confirms deletion
    Then the source record, source bytes, normalized text, and indexed chunks are permanently deleted
    And subsequent retrieval cannot return that source

  Scenario: Caller without corpus-management access tries to mutate a source
    Given a caller lacks corpus-management access
    When the caller adds, changes, or deletes a RAG source
    Then the system rejects the operation
    And it changes no source or corpus index

Feature: Panel belge işlemlerinin ayrıştırılması

  Scenario: Existing case document remains distinct from RAG source material
    Given an operator opens a case in the current panel
    When the original petition is displayed
    Then it is rendered as case evidence
    And it is not presented as an authoritative RAG source

  Scenario: Operator manages case attachments
    Given an authorized institution operator opens a readable case
    When the operator adds or deletes a supported attachment
    Then the panel reflects the authoritative case attachment set
    And the attachment is not automatically added to the RAG corpus

  Scenario: Admin soft-deletes a case attachment
    Given an ADMIN operator opens a readable case attachment
    When the ADMIN operator deletes it
    Then the attachment is soft-deleted and excluded from the current attachment set
    And the attachment is not made a RAG source

  Scenario: Non-admin caller cannot delete a case attachment
    Given a caller is not an ADMIN operator
    When the caller attempts to delete a case attachment
    Then the system rejects the operation
    And the attachment remains in its current state

  Scenario: Unauthorized caller cannot access a case document
    Given a caller lacks case access
    When the caller requests the case document
    Then the system rejects the request
    And it returns no case text

Feature: Dinamik retrieval kapasitesi

  Scenario: Deployment selects a CPU retrieval configuration
    Given an approved CPU retrieval deployment profile
    When the corpus is queried
    Then retrieval uses the selected inexpensive embedding and vector-storage components
    And it uses 0 GB GPU VRAM
    And it returns its top-five retrieval result within five seconds

  Scenario: Retrieval configuration cannot meet its approved resource bounds
    Given a configured retrieval profile exceeds its approved resource limit
    When the service starts or processes a query
    Then it fails in a controlled, observable state
    And it does not silently consume the Jamba generation budget

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-212 | “Belge görüntüleme, ekleme, silme” hangi nesne içindir: citizen case document/attachment, authoritative RAG source, or both? | requirement-analysis | Resolved | Both; case documents/attachments and RAG sources need separate management surfaces. (human operator, 2026-08-28) |
| OQ-213 | RAG corpusuna yalnız kurumca onaylı yerel mevzuat mı alınır, yoksa operator-uploaded PDF/DOCX/other documents da alınır mı? Her kaynak için authority/review kuralı nedir? | requirement-analysis | Resolved | PDF and DOCX uploads are converted to text through OCR and added to the RAG corpus. (human operator, 2026-08-28) |
| OQ-214 | RAG kaynağı silinince eski immutable correspondence citation/history nasıl korunur: hard delete, inactive/soft delete, or versioned snapshot? | requirement-analysis | Resolved | Hard delete. (human operator, 2026-08-28) |
| OQ-215 | Corpus değişikliği indexe ne zaman yansır: synchronous, queued durable job, or explicit operator publish? Başarısız indexleme görünürlük durumunu nasıl etkiler? | requirement-analysis | Resolved | The add action performs the addition directly; use synchronous conversion/indexing. (human operator, 2026-08-28) |
| OQ-216 | Case attachments için panel gerçek binary upload/download/delete mi sağlamalı, yoksa mevcut metadata registration ayrı kalmalı mı? | requirement-analysis | Resolved | Both case attachments and RAG sources need management; panel actions are not metadata-only. (human operator, 2026-08-28) |
| OQ-217 | Dinamik profil için hangi deployment hardware/VRAM, corpus thresholds, latency target, concurrency, and safe fallback are approved? | requirement-analysis | Resolved | Keep RAG at minimum VRAM and use inexpensive embedding/vector storage; exact configuration is architecture work. (human operator, 2026-08-28) |
| OQ-218 | May a case document or attachment automatically become a RAG source, or must corpus admission be an explicit institution action? | requirement-analysis | Resolved | No. RAG has a separate institution-panel surface where operators add corpus documents; case attachments stay case-only. (human operator, 2026-08-28) |
| OQ-219 | Which existing demo role may add, edit, or hard-delete RAG sources, and which source-authority/review check is required before it becomes searchable? | requirement-analysis | Resolved | Reuse the existing institution-management/`ADMIN` authority; operator actions manage corpus sources directly. (human operator, 2026-08-28) |
| OQ-220 | Does hard deletion also apply to case attachments, and in which case states is it permitted? | requirement-analysis | Resolved | Case attachments must follow the same hard/soft deletion treatment as their case. The current product has no case-deletion lifecycle, so exact state behavior is tracked by OQ-222. (human operator, 2026-08-28) |
| OQ-221 | What measurable retrieval-quality, per-query latency, and RAM/VRAM limits must the low-resource profile meet? | requirement-analysis | Resolved | Use inexpensive CPU embedding/vector storage, 0 GB GPU VRAM, and return top-five retrieval within five seconds. (human operator, 2026-08-28) |
| OQ-222 | The current product has no case delete endpoint or lifecycle. Which case states permit delete, and is case deletion hard or soft? This decision also governs attachment deletion. | requirement-analysis | Resolved | There is no citizen delete button. ADMIN performs soft delete; attachment deletion follows the same rule. (human operator, 2026-08-28) |
