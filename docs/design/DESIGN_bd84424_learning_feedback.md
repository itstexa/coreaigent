# Design Session — operator-approved learning feedback

> This session narrows the request for learning from real petitions to a safe
> MVP: an admin explicitly promotes a completed, validated case to an
> anonymized training candidate. It does not run model fine-tuning in the web
> request or silently add every incoming petition to a dataset.

## User Story

### US-123: Doğrulanmış vakayı eğitim adayı olarak kaydetme

As an admin operator
I want to promote a reviewed case, including corrected missing fields, to a
PII-minimized learning candidate
So that future dataset export and model evaluation can use real, human-checked
examples without treating unreviewed data as ground truth.

## Gherkin Acceptance Criteria

Feature: Operator-approved learning candidates

  Scenario: A reviewed case is saved as a learning candidate
    Given the current case has a complete validation state and an admin is viewing it
    When the admin selects “Eğitim örneğine ekle”
    Then the system stores one current-revision candidate with sanitized text and validated fields
    And the case detail shows that the candidate is awaiting dataset export

  Scenario: A case with missing information cannot become a candidate
    Given the current case still has missing or invalid required fields
    When an admin attempts to promote it
    Then the system rejects the request with a review-state error
    And it stores no learning candidate

  Scenario: Repeating the same promotion is idempotent
    Given a learning candidate already exists for the current case revision
    When the admin submits the promotion again
    Then the system returns the existing candidate
    And it does not create a duplicate candidate

  Scenario: Candidate data does not expose direct identifiers
    Given a candidate is created from a case containing applicant identity fields
    When the candidate is persisted
    Then identity fields are redacted in the candidate text
    And the candidate record contains no applicant name, TCKN, or phone value

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-184 | Eğitim adayı birikiminden model fine-tuning ne zaman ve hangi insan onayıyla çalıştırılacak? | requirement-analysis | Open | Bu MVP yalnızca admin-onaylı, PII-minimized adayları toplar; otomatik fine-tuning ve yayınlama sonraki aşamadır. |