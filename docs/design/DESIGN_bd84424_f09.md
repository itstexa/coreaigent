# Design Session — F9 routing confidence

> Linked from [DESIGN.md](../DESIGN.md). This session records the first,
> explainable UI slice of routing confidence without inventing a calibrated
> probability or changing the routing authority.

## User Stories

### US-121: Yönlendirme güvenini görünür kılma

As an operator
I want to see how confidently the selected unit was reached
So that I can distinguish a classification-backed route from a fallback route
and decide when human review deserves attention.

## Gherkin Acceptance Criteria

Feature: F9 yönlendirme güveni

  Scenario: Classified route exposes its source confidence
    Given a case has a routed `classified` route and an authoritative F-02 confidence
    When an operator opens the case overview or correspondence routing card
    Then the UI shows the confidence as a percentage
    And it labels the value as derived from the F-02 classification score
    And it names the selected target unit

  Scenario: Fallback route is explicitly low confidence
    Given a case has a routed `fallback` route
    When an operator opens the case
    Then the UI shows `%0`
    And it explains that the route is fallback and needs human review

  Scenario: Missing routing result does not imply confidence
    Given the current case has no routed result or no published F-02 score
    When an operator opens the case
    Then the UI shows `Bekliyor` or `—`
    And it does not display a fabricated percentage

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-182 | Should a future routing-confidence model be calibrated from reviewer outcomes, and if so which labeled event is authoritative? | requirement-analysis | Open | — |
