# Design Session — US-112 F-08 Compose developer-mode dependency closure

> Linked from [DESIGN.md](DESIGN.md). This record analyses the next feature-pack
> step after F-06.

## User Story

### US-112: Truthful local Compose development modes

As a demo operator
I want each documented local development/test command to start the dependencies
its selected service actually needs
So that a command never presents a mock-only path as the PostgreSQL/Jamba-backed
municipal workflow.

## Unblocked Acceptance Criteria

Feature: F-08 truthful Compose modes

  Scenario: The documented mock baseline remains isolated
    Given an operator runs the base Compose test commands
    When the mock scenario suite executes
    Then it starts only deterministic contract mocks
    And it does not claim PostgreSQL, BGE-M3, or Jamba inference verification

  Scenario: A requested local dependency closure is unavailable
    Given a selected development mode requires an unavailable local Dockerfile,
    PostgreSQL dependency, GPU, or pinned model cache
    When the operator invokes that mode
    Then the command fails before presenting a mock as the requested real service
    And its error identifies the missing prerequisite

  Scenario: A full local workflow dependency closure is available
    Given every dependency of the selected service has a local implementation
    And local Jamba GPU/cache prerequisites are available when workflow generation is exercised
    When the operator invokes the selected development or development-test command
    Then Compose starts the complete local dependency closure
    And the acceptance command calls the real local services rather than scenario mock responses

  Scenario: Only an unavailable dependency falls back to a mock
    Given a selected local service requires a dependency without a local implementation
    When the operator invokes the development command
    Then only that unavailable dependency may remain a contract mock
    And the command and test output identify the mixed topology
    And the result is not described as a full real end-to-end verification

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-150 | `scripts/coreaigent.ps1 dev/test development <service>` currently adds dependency overlays only for `ocr` and `llm`; classification, validation, and workflow therefore cannot form their required local state chain. Should F-08 change each selected mode to bring up its full real local dependency closure (`classification` → OCR/PostgreSQL; `validation` → OCR/classification/PostgreSQL; `workflow` → OCR/classification/validation/workflow and real Jamba), or preserve a selected-service-only mock-upstream mode and expose the full chain only as a separate explicit command? This determines GPU/cache prerequisites, test semantics, and documentation. | requirement-analysis | Resolved | Local implementationı bulunan tüm servisler dependency closure içinde gerçek başlatılır ve gerçek test edilir. Local implementationı olmayan dependency (ör. OCR) contract mock kalabilir; komut mixed topology'yi açıkça belirtir ve sonuç full real E2E diye sunulmaz. |
