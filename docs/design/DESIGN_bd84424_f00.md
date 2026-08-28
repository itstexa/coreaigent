# Design Session — split from DESIGN.md at commit `bd84424`

> Linked from [DESIGN.md](DESIGN.md). This is the permanent F0 requirement
> record for the competition build.

## User Stories

### US-116: Case ticket and action trace

As an operator
I want every case to have a stable ticket reference and an immutable record of
its system state transitions
So that I can explain where a petition is in the workflow without inventing a
history from its current projection.

The competition build has fixed demo tokens rather than user identities. F0
therefore records `system` as the actor. It deliberately does not claim staff
assignment, a human audit identity, or an external ticketing integration; those
belong to future F2/authentication scope.

## Gherkin Acceptance Criteria

Feature: F0 case ticket and action trace

  Scenario: First projected state creates one traceable ticket
    Given a case enters the workflow state projection
    When its first state is persisted
    Then exactly one stable local ticket reference exists for that case
    And the first immutable action identifies the system and resulting state

  Scenario: A meaningful case state change is retained
    Given a case already has a ticket and an action history
    When the workflow persists a different state or revision
    Then one new immutable system action is appended
    And earlier actions remain unchanged

  Scenario: An unchanged projection does not inflate the log
    Given a case projection is already persisted
    When an orchestrator pass persists no state or revision change
    Then it does not append an action-log entry

  Scenario: An applicant cannot read operational trace data
    Given a caller has only the USER demo token
    When it reads the case status
    Then the response does not contain the ticket or action trace

  Scenario: An administrator reads a bounded non-PII trace
    Given a caller has the ADMIN demo token
    When it reads a case status
    Then it receives the local ticket reference and actions in chronological order
    And an action contains no original petition text, accepted field values, draft, or notification payload

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-176 | Should F0 introduce staff identities or an external ticketing vendor? | requirement-analysis | Resolved | No. The current system has only fixed USER/ADMIN demo tokens. F0 is a local, system-actor trace; F2/authentication can extend actor and assignment later. |
