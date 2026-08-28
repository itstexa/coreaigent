# Design Session — split from DESIGN.md at commit `bd84424`

> Linked from [DESIGN.md](DESIGN.md). This session defines the operator-facing
> F2 assignment slice requested after F0/F8/F3 delivery.

## User Stories

### US-120: Birim içi otomatik personel ataması

As an admin operator
I want a completed, routed case to be assigned to an active staff member in
its target unit
So that the work queue has an accountable first owner without manual sorting.

The first slice uses a PostgreSQL-backed local staff registry. A staff member
has a stable ID, display name, role, unit, and active flag. The registry is
seeded with non-sensitive demo operators for each taxonomy unit; this is a
runtime fixture, not an authentication system. Assignment is created for the
current routed case revision only. Manual reassignment and staff CRUD remain
outside this slice.

## Gherkin Acceptance Criteria

Feature: Birim içi otomatik personel ataması

  Scenario: En az açık dosyası olan aktif personele atama yapılır
    Given a case has a completed validation state and a routed target unit
    And at least two active staff members belong to that target unit
    When the routing worker persists the current route
    Then it persists exactly one assignment for that case revision
    And the assigned staff member is the active member with the fewest open assignments

  Scenario: Eşit yükte atama deterministik ve adildir
    Given two active staff members in a unit have the same open assignment count
    When two new cases are routed to that unit
    Then the older last-assigned member is selected first
    And a stable staff ID breaks any remaining tie

  Scenario: Aynı vaka revizyonu tekrar işlense de ikinci atama oluşmaz
    Given a case revision already has an assignment
    When the routing job is replayed for that same case revision
    Then the existing assignment remains unchanged
    And no second assignment row is created

  Scenario: Aktif personel yoksa dosya kaybolmaz
    Given a routed unit has no active staff member
    When the routing worker persists the current route
    Then the route remains persisted
    And the assignment is explicitly `unassigned`
    And the case is visible to an admin for manual follow-up

  Scenario: Personel ataması vatandaşa açılmaz
    Given a case has an assignment
    When a USER token reads the case status or routing result
    Then the response contains no staff identity or assignment data
    And an ADMIN token may read the assignment projection

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-180 | Personel kimlikleri hangi dış kimlik sağlayıcısından gelecek? | requirement-analysis | Resolved | Bu yarışma diliminde dış kimlik sağlayıcı yok; PostgreSQL içindeki sınırlı demo personel kaydı kullanılır ve bu kimlik doğrulama iddiası değildir. |
| OQ-181 | İlk dilimde manuel yeniden atama ve personel CRUD gerekli mi? | requirement-analysis | Resolved | Hayır. F2 otomatik ilk atamayı ve admin görünürlüğünü kapsar; yeniden atama/CRUD sonraki dilimdir. |
