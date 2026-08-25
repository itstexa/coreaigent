Feature: Uçtan uca kamu evrak işleme akışı

  Scenario: Happy path
    Given geçerli ve tüm zorunlu bilgileri içeren Türkçe bir dilekçe
    When evrak sisteme gönderilir
    Then evrak normalize edilir
    And department unit ve request type sınıflandırılır
    And önemli alanlar çıkarılır
    And eksik zorunlu alan bulunmaz
    And özet ve gerekli resmi yazı taslağı hazırlanır
    And evrak doğru hedef birime route edilir
    And kullanıcı bildirimi hazırlanır
    And hedef birim bildirimi hazırlanır
    And case "completed" olur

  Scenario: Eksik bilgi nedeniyle dur ve devam et
    Given zorunlu bir alanı eksik Türkçe dilekçe
    When evrak sisteme gönderilir
    Then case "waiting_for_user" durumuna gelir
    And kullanıcıya eksik alan bildirilir
    When kullanıcı eksik alanı aynı case için tamamlar
    Then case yeniden validate edilir
    And başarılıysa kalan pipeline adımları devam eder
    And case "completed" olur

  Scenario: Belirsiz sınıflandırma güvenli biçimde durur
    Given taxonomy açısından belirsiz bir evrak
    When classification yeterli confidence üretemez
    Then case otomatik olarak yanlış birime route edilmez
    And case review gerektiren bir durumda kalır
