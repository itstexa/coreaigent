Feature: Mevzuat önerisi özet ve resmi yazı taslağı

  Scenario: Tam case için taslak hazırlanır
    Given completion_status "complete" olan bir case
    When correspondence generation çalışır
    Then kısa Türkçe evrak özeti üretilir
    And uygun resmi yazışma türü önerilir
    And resmi üsluba uygun bir draft_text üretilir

  Scenario: Asenkron generation current revision ile sıraya alınır
    Given yetkili bir çağıranın revision 4 olan complete case'e erişimi vardır
    When POST /cases/{case_id}/correspondence isteğini If-Match "4" ve Idempotency-Key ile gönderir
    Then HTTP 202 ve generation_status "queued" döner
    And bir durable generation işi oluşturulur

  Scenario: Kaynak bulunmayan mevzuat uydurulmaz
    Given ilgili mevzuat kaynağı retrieval tarafından bulunamamıştır
    When generation çalışır
    Then sistem olmayan mevzuat maddesi üretmez
    And source_status "no_relevant_source" ile result_status "review_required" döner
    And draft_text yalnız case içeriğine ve resmî yazışma biçimine dayanır

  Scenario: Eksik veya invalid bilgili case final taslak alamaz
    Given completion_status "missing_information" veya "invalid_information" olan bir case
    When final correspondence generation istenir
    Then HTTP 409 CASE_NOT_READY_FOR_CORRESPONDENCE döner
    And final draft ve durable job oluşturulmaz

  Scenario: Geçersiz structured model çıktısı partial draft yayınlamaz
    Given modelin ilk structured çıktısı unknown citation veya enum dışı correspondence type içerir
    When backend output'u doğrular
    Then en fazla bir repair attempt yapar
    And ikinci hata generation_status "failed" ve error_code "STRUCTURED_OUTPUT_INVALID" olur
