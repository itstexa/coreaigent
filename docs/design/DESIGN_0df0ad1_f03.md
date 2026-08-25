# Design Session — split from DESIGN.md at commit `0df0ad1`

> Linked from [DESIGN.md](DESIGN.md). This file holds the F-03
> requirement-analysis session and remains a permanent linked record.

## User Stories

### US-108: F-03 bilgi çıkarımı ve eksik bilgi tespiti

As a document-processing operator
I want the system to extract fields defined by the classified request type's
schema and identify missing required fields
So that a case can safely wait for only the information it still needs before
later processing.

The existing `validation` logical service and `POST /v1/validate` boundary are
evolved rather than replaced. Its result contract gains the F-03 extraction and
completion information while retaining its identity and role in the Docker/CI
contract graph. The required-field list is authoritative from a repository
owned, versioned `Demo Belediyesi` request-type registry, not generated ad hoc
by a model. The registry covers the ten request types already in F-02's demo
taxonomy and uses the existing feature-pack examples (contact, identity,
address, date, document number, request subject, description, and attachment
information) as the demo field vocabulary.

Extraction is hybrid: deterministic rules extract and validate well-defined
values such as TCKN, telephone numbers, and dates; Jamba extracts the remaining
schema-defined semantic fields. Every extracted value is accepted only after
its schema validation rule succeeds. The public validation response may expose
per-field confidence but never source spans, extractor provenance, or raw PII
evidence. PostgreSQL remains the authoritative source of truth and retains only
current field, completion, and case/workflow state; F-03 result history is not
retained. `POST /v1/validate` loads normalized text from PostgreSQL by its
existing `documentId`. Supplemental information uses a separate case-level
endpoint, not `POST /v1/validate`.

A complete record is `complete`; missing required fields produce
`missing_information` with human-readable Turkish labels and require user
action. Optional-field absence alone does not stop the case. Supplemental
values must merge into the same case, retain prior valid values, and trigger a
new validation pass. A case with missing required fields must not advance to
F-04/F-05 final processing. `invalid_information` is distinct: a value is
present but violates its schema validation rule, for example a checksum-invalid
TCKN, malformed telephone number, unparsable date, or disallowed value.

The supplemental endpoint is `PATCH /cases/{case_id}/supplemental-information`.
It requires `Authorization: Bearer <token>`, JSON content,
`Idempotency-Key: <uuid>`, and `If-Match: "<current_revision>"`. Its body is
`{"fields":{"<field_id>":"<value>"}}`; on success it atomically merges valid
values, reruns F-03, returns the current validation result, and emits the next
quoted revision in `ETag`. A repeated key with the same request replays its
original response; key reuse with different request data returns a conflict.
A stale revision returns HTTP 412 without mutation, and a malformed request,
missing authentication, or denied case access returns a controlled HTTP 400,
401, or 403 response respectively. Authorization is enforced by an injectable
case-access adapter; no fixed bearer token is embedded in the contract.

## Gherkin Acceptance Criteria

Feature: F-03 information extraction and missing information

  Scenario: A complete classified document can proceed
    Given a classified case whose request-type schema is available
    And the document and accepted supplemental values contain every required field
    When F-03 extraction and validation run
    Then the completion status is `complete`
    And user action is not required
    And the case is eligible for subsequent processing

  Scenario: Missing required fields stop subsequent processing
    Given a classified case whose request-type schema is available
    And one or more required fields have no accepted value
    When F-03 extraction and validation run
    Then the completion status is `missing_information`
    And the missing fields are returned with human-readable Turkish labels
    And user action is required
    And F-04/F-05 final processing is not started

  Scenario: A present but invalid required value is distinguished from absence
    Given a classified case whose request-type schema requires a TCKN
    And the document or supplemental data contains `12345678901`
    When F-03 deterministic validation runs
    Then the completion status is `invalid_information`
    And the TCKN appears as an invalid field rather than a missing field
    And F-04/F-05 final processing is not started

  Scenario: Missing optional fields do not block a complete record
    Given a classified case whose request-type schema has an optional field without a value
    And every required field has an accepted value
    When F-03 extraction and validation run
    Then the completion status is `complete`
    And the optional-field absence does not require user action

  Scenario: Supplemental information preserves valid prior values
    Given a case is waiting for user information with accepted extracted values
    And the case has a known set of missing required fields
    When the user supplies values for those fields for the same case
    Then the accepted prior values remain available
    And F-03 validation runs again for that case
    And the result is `complete` only if every required field has an accepted value

  Scenario: A supplemental value cannot overwrite a valid current value with an invalid one
    Given a case has a current valid telephone number
    When a supplemental-information request supplies a telephone number that fails the schema rule
    Then the system reports `invalid_information`
    And the prior valid telephone number remains the current accepted value

  Scenario: Supplemental information revalidates one current case atomically
    Given an authorized caller has a case at revision `7` waiting for user information
    And the caller supplies `If-Match: "7"` and a new idempotency key
    When it sends `PATCH /cases/{case_id}/supplemental-information` with valid JSON fields
    Then the service merges valid values and reruns F-03 in one authoritative update
    And it returns the current validation result with `ETag: "8"`

  Scenario: A stale supplemental revision cannot mutate the case
    Given a case is currently at revision `8`
    When an authorized caller sends supplemental information with `If-Match: "7"`
    Then the service returns HTTP 412
    And the current fields, completion state, and revision remain unchanged

  Scenario: A repeated supplemental request is idempotent
    Given a supplemental request was successfully accepted with an idempotency key
    When the same caller repeats the same request with that key
    Then it receives the original response without another merge or validation update

  Scenario: Supplemental access is required
    Given a caller has no valid bearer authorization for a case
    When it sends a supplemental-information request
    Then the service returns HTTP 401 or HTTP 403
    And it does not disclose or mutate the case's current data

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-121 | F-03 mevcut sabit `validation`/`POST /v1/validate` sınırını ve `validation-result` kontratını mı geliştirecek, yoksa yeni bir extraction/validation service veya endpoint mi kullanılacak? | requirement-analysis | Resolved | Mevcut `validation` logical service ve `POST /v1/validate` boundary geliştirilecek; Docker/CI contract graph korunmaya çalışılacak. |
| OQ-122 | İlk çalışan demo için `Demo Belediyesi` taxonomy'deki hangi request type'lar desteklenecek ve her biri için required/optional alanlar, Türkçe label’lar, field type’ları, normalize/validation kuralları tam olarak nedir? | requirement-analysis | Resolved | F-02'nin mevcut on request type'ını kapsayan versioned Demo Belediyesi registry kullanılacak; mevcut Docker/CI user-story ve feature-pack örnekleriyle uyumlu field vocabulary uygulanacak. Kesin kayıt tablosu mimaride tanımlanacak. |
| OQ-123 | Çıkarım yöntemi nedir: deterministik kural/regex, Jamba structured extraction, başka bir model, ya da hibrit mi? Çıkarım confidence’ı ve source evidence/span hangi kesin shape ve güvenlik kuralıyla dönecek? | requirement-analysis | Resolved | Hibrit: TCKN gibi kural-tabanlı metinler kodla çekilir; diğer schema alanlarını Jamba çeker. Evidence/spans için kesin contract shape'i OQ-127'de ayrıştırıldı. |
| OQ-124 | F-03 authoritative state PostgreSQL'de hangi current-only kayıtlar olarak tutulacak; extracted değer, source evidence, missing/invalid sonucu ve case/workflow state'in update kuralı nedir? Historical result tutulacak mı? | requirement-analysis | Resolved | PostgreSQL authoritative source of truth olmaya devam eder; sistem current state tutar, geçmiş F-03 sonuçları tutulmaz. Kesin tablo ve update predicates mimaride tanımlanacak. |
| OQ-125 | Kullanıcının tamamlayıcı bilgi gönderdiği mevcut endpoint/contract hangisidir; field değerleri nasıl kimliklendirilir, aynı case’e yetkilendirme/idempotency/çakışma davranışı nedir? | requirement-analysis | Resolved | Supplemental information validation endpoint içine sıkıştırılmayacak; ayrı case-level supplemental-information endpoint bulunacak. Kesin HTTP contract OQ-129'da ayrıştırıldı. |
| OQ-126 | `invalid_information` hangi koşullarda üretilir ve eksik, çıkarılamayan, geçersiz, çelişkili değerlerin kullanıcıya gösterimi ile tekrar-deneme davranışı nedir? | requirement-analysis | Resolved | `missing_information`: required alan için hiçbir kullanılabilir değer yoktur. `invalid_information`: değer vardır fakat schema kuralını karşılamaz; checksum-invalid TCKN, geçersiz telefon, parse edilemeyen tarih ve disallowed değer örnekleridir. |
| OQ-127 | Jamba veya deterministic extractor tarafından bulunan değerlerin evidence/source span, confidence, extractor provenance ve PII redaction alanları validation-result kontratında hangi kesin formatta dönmelidir? | requirement-analysis | Resolved | Public response per-field confidence dönebilir; source evidence/span, extractor provenance ve raw PII evidence istemciye dönmez. |
| OQ-128 | `POST /v1/validate` mevcut v3 classification-result request'inden extraction için gereken normalized metne nasıl erişir: payload'a eklenen alanla mı, PostgreSQL'den document/case lookup ile mi, yoksa başka bir contract-preserving mekanizmayla mı? | requirement-analysis | Resolved | Validation normalized metni mevcut `documentId` ile PostgreSQL authoritative source-of-truth'tan okur. |
| OQ-129 | Ayrı case-level supplemental-information endpoint'in HTTP method/path, request/response alanları, idempotency anahtarı, kimlik/erişim kuralı ve eşzamanlı güncelleme çakışması davranışı nedir? | requirement-analysis | Resolved | `PATCH /cases/{case_id}/supplemental-information`; Bearer auth, JSON, `Idempotency-Key`, `If-Match` kullanır. Eksik response/error/concurrency detayları repository contract style'ına uygun olarak tanımlandı ve acceptance kriterlerine eklendi. |
