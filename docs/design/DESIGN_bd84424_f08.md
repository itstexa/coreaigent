# Design Session — split from DESIGN.md at commit `bd84424`

## User Stories

### US-117: Explainable petition priority

As an operator
I want the case queue to place urgent safety-related petitions before routine
ones and show why
So that limited human review capacity reaches the most time-sensitive work
first.

F8 is deterministic and local: it does not use Jamba, does not infer a legal
severity, and does not change the route or an administrative decision.

## Gherkin Acceptance Criteria

Feature: F8 explainable petition priority

  Scenario: A critical safety signal rises to the top of the queue
    Given a petition contains a configured critical-risk phrase
    When the workflow projects the case
    Then it stores the `critical` priority with its matching rule label
    And the ADMIN queue orders it before lower-scored cases

  Scenario: A service-impact signal is elevated without becoming critical
    Given a petition contains a configured service-impact phrase but no critical-risk phrase
    When the workflow projects the case
    Then it stores the `high` priority with its matching rule label

  Scenario: An ordinary petition remains routine
    Given a petition contains none of the configured priority phrases
    When the workflow projects the case
    Then it stores `normal` priority and the routine reason

  Scenario: Priority never changes routing or invents urgency
    Given a petition is already classified and routed
    When F8 calculates its priority
    Then its target department and unit remain unchanged
    And only configured deterministic phrases can create `critical` or `high` priority

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-177 | Should priority use a model, a legal SLA, or only safe observable signals in the competition build? | requirement-analysis | Resolved | Use only repository-owned deterministic safety/service-impact phrases. A future owner-approved SLA or classifier can replace the rule table without changing the case API shape. |
