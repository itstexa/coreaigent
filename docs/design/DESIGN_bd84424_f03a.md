# Design Session — same-applicant history (user F3)

## User Stories

### US-118: Explainable same-applicant similar history

As an operator
I want to see a bounded list of a validated applicant's earlier, textually
similar petitions
So that I can recognise a recurring issue without treating a model suggestion
as a decision.

## Gherkin Acceptance Criteria

Feature: Same-applicant similar petition history

  Scenario: A related prior petition is shown to an operator
    Given two cases have the same validated applicant identity
    And their petition texts share the configured minimum token overlap
    When an ADMIN reads the newer case's related-case projection
    Then the projection lists the older case with its submission time, current
    state, resolved flag, and deterministic similarity score

  Scenario: An unvalidated or unrelated case is not exposed as history
    Given the current case has no validated applicant identity, or another case
    belongs to a different applicant or is below the similarity threshold
    When an ADMIN reads the related-case projection
    Then no unrelated case is returned

  Scenario: A USER cannot read cross-case history
    Given a USER credential
    When it requests related cases
    Then the service returns `403 FORBIDDEN`

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-178 | What should “past moderators” mean before an employee/authentication model exists? | requirement-analysis | Open | Not implemented or fabricated. The initial projection exposes only factual case state and resolved status. |
