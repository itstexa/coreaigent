Feature: Evrak girdisi ve normalizasyon

  Scenario: Doğrudan Türkçe metin kabul edilir
    Given en az 40 karakterlik geçerli bir Türkçe evrak metni
    When evrak source_type "text" ile gönderilir
    Then sistem benzersiz bir document ve case kimliği döndürür
    And Türkçe karakterleri korunmuş normalize edilmiş metin oluşturulur

  Scenario: OCR çıktısı aynı downstream kontratına dönüştürülür
    Given OCR servisinden üretilmiş geçerli bir metin
    When evrak source_type "ocr" ile gönderilir
    Then downstream için doğrudan metin girdisiyle aynı normalize edilmiş belge yapısı üretilir

  Scenario: Boş metin reddedilir
    Given yalnızca whitespace içeren bir evrak
    When intake çağrısı yapılır
    Then başarılı processing başlatılmaz
    And makine tarafından ayırt edilebilir bir validation hatası döner

  Scenario: 39, 40 ve 41 karakter sınırları
    Given sırasıyla 39, 40 ve 41 karakterlik metinler
    When intake çağrısı yapılır
    Then 39 karakterlik metin kalıcı kayıt veya job oluşturmadan reddedilir
    And 40 ve 41 karakterlik metinler kabul edilir

  Scenario: Aynı belge idempotent olarak tekrar oynatılır
    Given kabul edilmiş değişmez bir belge girdisi
    When aynı documentId ve aynı değişmez alanlarla tekrar gönderilir
    Then aynı case ve workflow kimlikleri döner
    And ikinci bir outbox job oluşturulmaz

  Scenario: Aynı kimlikle değişmiş içerik reddedilir
    Given kabul edilmiş bir documentId
    When farklı metin, kaynak türü, metadata veya correlationId ile tekrar gönderilir
    Then HTTP 409 non-retryable validation hatası döner
    And mevcut document, case, workflow ve outbox job değişmez

  Scenario: Bekleyen intake işi yeniden başlatmadan sonra kalır
    Given PostgreSQL'de pending outbox job içeren kabul edilmiş bir belge
    When OCR container yeniden başlatılır
    Then document, case, workflow ve pending job tekrar bulunabilir
