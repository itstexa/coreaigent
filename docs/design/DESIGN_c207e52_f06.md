# Design Session — US-111 F-06 orchestration and case state

> Linked from [DESIGN.md](DESIGN.md). This file records the F-06 requirement
> analysis and remains a permanent linked record.

## User Story

### US-111: Durable case orchestration and observable case state

As a municipal case operator
I want F-01 through F-05 to advance a single case through durable, observable
workflow states
So that work stops safely when review or user input is required and resumes
without duplicate routing or lost work after a restart.

PostgreSQL remains the authoritative source of truth. The orchestrator must
not reproduce OCR, classification, validation, retrieval, Jamba, or routing
decisions; it coordinates durable case-level work and exposes an authorized
read projection. F-05's immutable route and separate notification records
remain authoritative and must not be replaced by a case-state transition.

## Unblocked Acceptance Criteria

Feature: F-06 durable orchestration and case state

  Scenario: An uncertain classification stops automatic downstream work
    Given F-02 persists a current classification with `status: needs_review`
    When orchestration evaluates the case
    Then it records a review-required case state
    And it does not start F-03, F-04, F-05, or a routing operation
    And the case remains observable after a container restart

  Scenario: A restart preserves unfinished orchestration work
    Given a case has a durable pending or leased orchestration operation
    When the orchestrator container restarts
    Then PostgreSQL retains the case state and durable operation
    And a lease-expired operation is recoverable without creating a second
    routing decision or notification record

  Scenario: Routing success is not reverted by a notification failure
    Given F-05 has persisted a `routed` operation for the current case revision
    And an applicant or target-unit notification is `failed`
    When orchestration evaluates the case
    Then it preserves the routed operation
    And it exposes notification retry as the outstanding work
    And it never sends an external e-mail

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-144 | F-03 current revision `complete` olduğunda orchestrator F-04 `POST /cases/{case_id}/correspondence` operasyonunu otomatik başlatacak mı? Başlatacaksa F-04'ün mevcut Idempotency-Key/If-Match kontratında orchestrator principal/key üretimi ve F-04 `failed` için retry/terminal policy nedir? | requirement-analysis | Open | — |
| OQ-145 | F-04 `review_required` sonucu fallback birime route edilip iki notification tamamlandığında case'in current terminal state'i `completed` mi, yoksa ayrı `needs_review`/`review_required` state'i mi olmalıdır? | requirement-analysis | Open | — |
| OQ-146 | Yetkili UI case-level state'i hangi endpoint/kontratla okur ve applicant ile hedef birim/service account için hangi role-based projection uygulanır? Özellikle `GET /cases/{case_id}/routing` target-unit payload'ını applicant'a göstermemektedir; F-06 bunun üstünde hangi case-state alanlarını döndürür? | requirement-analysis | Open | — |
| OQ-147 | `missing_information`/`invalid_information` durumunda F-06'nın "kullanıcıya eksik alan bildirimi" F-05 `NotificationRecord` modelinde ayrı audience/kind ile mi persist edilir, yoksa yalnız authorized case read modelinde mi görünür? E-mail hâlâ placeholder olarak mı kalır? | requirement-analysis | Open | — |
| OQ-148 | Case state authoritative olarak ayrı mutable PostgreSQL `current_case_states` satırında mı persist edilir, yoksa F-01..F-05 authoritative current tablolarından deterministik read projection olarak mı türetilir? State transition history/outbox audit gereksinimi var mıdır? | requirement-analysis | Open | — |
