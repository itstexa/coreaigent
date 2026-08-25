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

## Acceptance Criteria

Feature: F-06 durable orchestration and case state

  Scenario: A complete current revision automatically starts F-04
    Given F-03 persists a current case revision with `completion_status: complete`
    And F-02 remains `classified`
    When the orchestrator evaluates the durable case state
    Then it starts one F-04 generation for that exact revision without a client request
    And it retries an F-04 failure at most three times after the initial attempt
    And each retry is scheduled with the configured cooldown
    And after the final failed attempt it records `failed` and the terminal error code
    And it does not create F-05 routing for the failed generation

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

  Scenario: Missing or invalid information creates a persisted applicant notification
    Given F-03 persists `missing_information` or `invalid_information`
    When orchestration evaluates the case
    Then it persists one applicant notification with the current required or invalid field summary
    And it exposes that notification through the authorized case projection
    And it does not send external e-mail or start F-04/F-05

  Scenario: Review-required work cannot auto-complete
    Given a case is `needs_review` or an F-04 result is `review_required`
    When all automatic work for the current revision has reached its terminal state
    Then the case remains `needs_review`
    And no automatic transition changes it to `completed`
    And only an authorized reviewer completion operation may make that transition

  Scenario: Current case state layers over existing authoritative tables
    Given F-01 through F-05 have persisted a case's current records
    When the orchestrator changes the case workflow state
    Then it upserts one PostgreSQL current-case-state row with current state, completed steps, last error and update time
    And it does not overwrite F-02 classification, F-03 validation, F-04 generation history, F-05 route, or notification records

  Scenario: The demo user reads only its case projection
    Given the single configured demo `USER` token
    When it reads `GET /cases/{case_id}` for a demo case
    Then it receives current state, public validation status, applicant notifications and process-facing routing status
    And it does not receive target-unit notification payloads or internal draft context

  Scenario: The demo administrator reads assigned-unit detail and completes review
    Given the single configured demo `ADMIN` token
    When it reads `GET /cases/{case_id}` for a routed case
    Then it receives the routing target and target-unit operational notification payload
    When it posts `POST /cases/{case_id}/review-completion` with `Idempotency-Key` and `If-Match`
    Then it changes only a current `needs_review` case to `completed`
    And an ordinary `USER` token receives 403 for the reviewer operation

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-144 | F-03 current revision `complete` olduğunda orchestrator F-04 `POST /cases/{case_id}/correspondence` operasyonunu otomatik başlatacak mı? Başlatacaksa F-04'ün mevcut Idempotency-Key/If-Match kontratında orchestrator principal/key üretimi ve F-04 `failed` için retry/terminal policy nedir? | requirement-analysis | Resolved | Otomatik başlar. İlk çağrıdan sonra en fazla üç cooldown'lu retry yapılır; önerilen repo default'u `F04_RETRY_COOLDOWN_SECONDS=30` configurable'dir. Son retry de başarısızsa terminal hata kaydedilir, o case F-05'e geçmez ve worker sonraki case'lere devam eder. |
| OQ-145 | F-04 `review_required` sonucu fallback birime route edilip iki notification tamamlandığında case'in current terminal state'i `completed` mi, yoksa ayrı `needs_review`/`review_required` state'i mi olmalıdır? | requirement-analysis | Resolved | Otomasyon case'i `completed` yapmaz; case `needs_review` kalır. Yetkili reviewer ayrı bir yetkili işlemle `completed` durumuna çekebilir. |
| OQ-146 | Yetkili UI case-level state'i hangi endpoint/kontratla okur ve applicant ile hedef birim/service account için hangi role-based projection uygulanır? Özellikle `GET /cases/{case_id}/routing` target-unit payload'ını applicant'a göstermemektedir; F-06 bunun üstünde hangi case-state alanlarını döndürür? | requirement-analysis | Superseded | Ayrı kimlik sahibinin F-01 intake anında nasıl belirleneceği aşağıdaki OQ-149'a taşındı. Endpoint shape, owner/grant kaynağı netleşince tamamlanacaktır. |
| OQ-147 | `missing_information`/`invalid_information` durumunda F-06'nın "kullanıcıya eksik alan bildirimi" F-05 `NotificationRecord` modelinde ayrı audience/kind ile mi persist edilir, yoksa yalnız authorized case read modelinde mi görünür? E-mail hâlâ placeholder olarak mı kalır? | requirement-analysis | Resolved | PostgreSQL'ye applicant notification insert edilir ve authorized case projection'da gösterilir. E-mail external dispatch değildir; placeholder kalır. |
| OQ-148 | Case state authoritative olarak ayrı mutable PostgreSQL `current_case_states` satırında mı persist edilir, yoksa F-01..F-05 authoritative current tablolarından deterministik read projection olarak mı türetilir? State transition history/outbox audit gereksinimi var mıdır? | requirement-analysis | Resolved | Önceki authoritative current tablolara ek olarak bir mutable PostgreSQL `current_case_states` satırı tutulur. F-02/F-03/F-04/F-05 kaynak kayıtları overwrite edilmez; ayrı immutable state-history zorunlu değildir. |
| OQ-149 | F-01'in mevcut public intake kontratı authentication/principal taşımıyor. Applicant ownership ve unit-ataması yetkisini güvenli uygulamak için case owner hangi doğrulanmış principal kaynağından persist edilir; unit/service-account principal'ları ve reviewer rolü hangi repository RBAC registry'sinden çözülür? | requirement-analysis | Resolved | Demo yalnız iki sabit Bearer permission kullanır: tek `USER` token tüm demo case'leri kendi case'i gibi okur; tek `ADMIN` token atanmış birim ayrıntıları ve reviewer completion işlemini görür/yapar. Birim-per-user assignment, login/auth provider ve production security scope dışıdır. |

## Demo Case Contract

`GET /cases/{case_id}` Bearer authorization gerektirir. `USER` yalnız
process-facing projection alır; `ADMIN` target-unit payload dahil demo
operational projection alır. `POST /cases/{case_id}/review-completion` yalnız
`ADMIN` içindir; boş body kabul eder, `Idempotency-Key: <uuid>` ve
`If-Match: "<current_revision>"` zorunludur. Geçerli yalnız `needs_review`
case'i `completed` yapar; diğer current state'ler `409 CASE_NOT_REVIEWABLE`
döndürür. Bu sabit-token model demo kolaylığıdır, production authorization
değildir.
