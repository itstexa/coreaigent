# Design Session — local hybrid retrieval

## User Stories

### US-119: Local hybrid legislation retrieval

As a case worker
I want the official-draft flow to combine semantic and exact Turkish legal-term
retrieval
So that an explicit statute/article reference is not lost when wording differs.

## Gherkin Acceptance Criteria

Feature: Local hybrid legislation retrieval

  Scenario: An exact legal term can improve a semantically relevant rank
    Given the local BGE-M3 retrieval results and the same local corpus
    When a query contains a Turkish legal term found in a corpus chunk
    Then the system fuses dense and lexical ranks deterministically
    And citations still come only from the repository corpus

  Scenario: A lexical hit cannot bypass source safety
    Given a chunk has no semantic or lexical evidence for the query
    When retrieval builds the generation context
    Then it is not surfaced as a citation
    And no external API, Qdrant server, or unpinned model is used

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-179 | Should the complete standalone `mevzuat-rag` package (Qdrant, cross-encoder, LLM stages) replace the current workflow now? | requirement-analysis | Resolved | No. Integrate its offline hybrid-retrieval core in the existing worker now. Keep the full standalone package as a later migration after its sources, Qdrant lifecycle, and local Jamba API compatibility are reviewed. |
