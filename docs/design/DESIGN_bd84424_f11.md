# Design Session — US-114 F-11 local translation bridge and US-115 competition UI

> Linked from [DESIGN.md](DESIGN.md). This record is scoped to the operator's
> 2026-08-28 request: keep petition data local, use Jamba's stronger English
> generation path for Turkish petitions, and present CoreAIgent as a truthful,
> polished petition-analysis product rather than an e-government clone.

## User Stories

### US-114: Yerel Türkçe/İngilizce üretim köprüsü

As a citizen submitting a Turkish petition
I want the system to analyse it and return readable Turkish output
So that the English-strong Jamba runtime does not lower the quality of my case.

### US-115: CoreAIgent petition and operator experience

As a competition demonstrator
I want a Turkish CoreAIgent experience built around entering a petition and
seeing its real analysis
So that the product demonstrates the implemented pipeline without claiming
unimplemented public-service capabilities.

## Gherkin Acceptance Criteria

Feature: Local Turkish generation bridge

  Scenario: A Turkish petition reaches the English Jamba generation path
    Given the two pinned local translation models are ready
    And a case's detected language is `tr`
    When workflow builds a sanitized Jamba generation request
    Then human-readable request values are translated locally to English before Jamba is called
    And Jamba receives the English instruction shape
    And generated summary and draft wording are translated locally back to Turkish before persistence
    And structured keys, citation identifiers, case state and routing rules remain unchanged.

  Scenario: Translation is unavailable
    Given a Turkish case is eligible for generation
    And the local translation service is not ready
    When workflow attempts to process the case
    Then it does not send a Turkish prompt to Jamba as a fallback
    And the durable job remains retryable rather than publishing a degraded draft.

  Scenario: An English petition avoids a needless translation pass
    Given a case's detected language is `en`
    When workflow generates a draft or applicant notification
    Then it uses the existing English Jamba prompt directly
    And no translation model is called.

Feature: Truthful CoreAIgent competition UI

  Scenario: A visitor starts from the CoreAIgent landing page
    Given the public application is open
    When the visitor selects the petition action
    Then the interface uses CoreAIgent branding and Turkish copy
    And the intake journey accepts a petition text as its primary input
    And it does not describe itself as e-Devlet or claim binary OCR upload, official dispatch, sign-in, or staff assignment.

  Scenario: An operator opens a case
    Given the operator panel has a real case projection
    When the operator views its analysis
    Then the UI renders only API-backed classification, missing information, draft, citations, and routing data
    And unavailable capabilities are not presented as working controls.

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-174 | Which translation model pair should supply the local Turkish/English bridge? | requirement-analysis | Resolved | The operator approved a local Docker-integrated solution. Use `Helsinki-NLP/opus-mt-tc-big-tr-en` at `2261c8fc7b1af59caee87f8ff0ecf3fbccfe8391` and `Helsinki-NLP/opus-mt-tc-big-en-tr` at `e539fc16a8a1a0ea5950eb339b595bfcce990e90`; preserve their CC-BY-4.0 attribution in documentation. |
| OQ-175 | What public brand and portal framing should the UI use? | requirement-analysis | Resolved | Use the existing CoreAIgent brand, Turkish copy, and a petition-analysis framing. Do not use e-Devlet or imply an official government portal. |
