Feature: Hiyerarşik departman birim ve talep türü sınıflandırması

  Scenario: Geçerli hiyerarşik sınıflandırma
    Given taxonomy içinde tanımlı bir evrak örneği
    When classification çalışır
    Then bir department id seçilir
    And seçilen unit bu department'ın çocuğudur
    And seçilen request type bu unit'in izin verdiği türlerden biridir

  Scenario: Düşük güven skoru otomatik yönlendirilmez
    Given birden fazla sınıfa yakın belirsiz bir evrak
    When classification confidence 0.80 veya altında kalır
    Then status "needs_review" olur
    And geçerli en iyi zincir provisional olarak döner
    And routing tetiklenmez

  Scenario: Hiç eşleşme yoksa incelemeye alınır
    Given taxonomy içinde evrakla eşleşen geçerli bir zincir yoktur
    When classification çalışır
    Then status "needs_review" olur
    And department, unit ve request type alanları null olur

  Scenario: Eşik üstü confidence otomatik sınıflandırılır
    Given geçerli hiyerarşik adayın confidence değeri 0.81'dir
    When classification çalışır
    Then status "classified" olur
    And seçilen zincir PostgreSQL'deki current authoritative sonuçtur

  Scenario: Birden fazla eşik üstü adayda en yüksek olan tek başına seçilir
    Given üç geçerli hiyerarşik adayın confidence değerleri 0.81, 0.87 ve 0.91'dir
    When classification çalışır
    Then yalnız 0.91 confidence'lı zincir "classified" olarak döner
    And response "topCandidates" alanını içermez

  Scenario: Geçersiz parent-child zinciri authoritative sonuç olmaz
    Given başka bir department'a ait bir unit veya başka bir unit'e ait request type adayı
    When classification adayı değerlendirir
    Then geçersiz hiyerarşi "classified" olarak dönmez
    And authoritative classification kaydına yazılmaz

  Scenario: Taxonomy yüklenemezse fallback label üretilmez
    Given taxonomy kaynağı yüklenememektedir
    When classification isteği alınır
    Then servis non-ready veya kontrollü dependency hatası döner
    And department, unit veya request type uydurmaz

  Scenario: Durable job sınıflandırmayı uçtan uca tamamlar
    Given F-01 intake tarafından pending "process_document" durable outbox işi oluşturulmuştur
    And versioned "Demo Belediyesi" taxonomy yüklüdür
    When classification worker işi claim eder
    Then mevcut "POST /v1/classify" sınırı ile sınıflandırma çalışır
    And case için tek current authoritative classification PostgreSQL'e yazılır
    And job ancak persistence başarılı olduktan sonra "completed" olur
