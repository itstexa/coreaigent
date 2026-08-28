# Design Session — behavior-aware F2 assignment

> Linked from [DESIGN.md](DESIGN.md). This session extends US-120 with an
> explainable, local assignment policy for repeated or behaviorally escalated
> petitions.

## User Story

### US-122: Tekrar ve davranış sinyaline göre uzman atama

As an admin operator
I want a repeated same-topic petition or an escalated petition to be assigned
to the active staff member with the strongest historical resolution rate for
that topic
So that difficult or recurring work reaches a demonstrably effective owner
while ordinary cases remain workload-balanced.

The signal is bounded and explainable. Same-topic repetition is counted only
when the current validation has a comparison-safe applicant field and the
current classification has the same `request_type_id`. The current petition is
included in the count, so the priority threshold is the third matching
petition. Aggression is a deterministic marker score over normalized text; the
petition text and applicant identity are never copied into the explanation. A
priority case uses topic resolution rate, then topic case volume, open
workload, assignment recency, and stable staff ID as tie-breakers. With no topic
history, the existing least-open policy remains in force.

## Gherkin Acceptance Criteria

Feature: Açıklanabilir davranış-duyarlı personel ataması

  Scenario: Aynı konudaki üçüncü dilekçe uzman personele gider
    Given the current applicant has two previous validated petitions with the same request type
    And the target unit has active staff with topic history
    When the routing worker persists the current assignment
    Then the current petition has repeat_count 3 in its selection reason
    And the staff member with the highest topic resolution rate is selected

  Scenario: Agresiflik sinyali çözüm oranını önceliklendirir
    Given the petition text contains configured aggression markers
    And at least one active target-unit staff member has topic history
    When the routing worker persists the current assignment
    Then aggression_level is elevated or high
    And topic resolution rate is the primary selection policy

  Scenario: Sıradan vaka yük dengelemesini korur
    Given the petition is neither a third same-topic petition nor behaviorally escalated
    When the routing worker persists the current assignment
    Then the active target-unit member with the fewest open assignments is selected

  Scenario: Öncelikli vakada konu geçmişi yoksa dosya kaybolmaz
    Given a petition triggers the priority policy
    And no active target-unit staff member has history for its request type
    When the routing worker persists the current assignment
    Then the least-open active staff member is selected
    And the selection reason identifies the fallback workload policy

  Scenario: Açıklama PII içermez
    Given an assignment is persisted for a repeated or aggressive petition
    When an admin reads the case projection
    Then the selection reason contains only bounded counters, levels, policy, and topic metrics
    And it contains neither applicant identity nor petition text

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-183 | Çözüm oranı hangi olayla kesinleşecek ve zamanla nasıl kalibre edilecek? | requirement-analysis | Open | Bu MVP, `completed` atamaları / konu atamalarını kullanır. İnsan doğrulamalı sonuç olayı, minimum örneklem ve zaman ağırlığı sonraki kalibrasyon diliminde belirlenmelidir. |
