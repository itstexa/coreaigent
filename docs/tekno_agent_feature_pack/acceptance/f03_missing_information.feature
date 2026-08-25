Feature: Bilgi çıkarımı ve eksik alan tespiti

  Scenario: Tüm zorunlu bilgiler mevcut
    Given sınıflandırılmış bir request type
    And request type schema'sındaki tüm zorunlu alanları içeren evrak
    When extraction ve validation tamamlanır
    Then completion_status "complete" olur
    And user_action_required false olur

  Scenario: Zorunlu bilgi eksik
    Given sınıflandırılmış bir request type
    And en az bir zorunlu alanı içermeyen evrak
    When extraction ve validation tamamlanır
    Then completion_status "missing_information" olur
    And eksik zorunlu alanlar kullanıcıya anlaşılır label ile listelenir
    And routing tetiklenmez

  Scenario: Mevcut fakat geçersiz bilgi eksik bilgiden ayrılır
    Given sınıflandırılmış bir request type için TCKN alanı zorunludur
    And evrakta checksum kontrolünü geçmeyen "12345678901" değeri bulunur
    When extraction ve validation tamamlanır
    Then completion_status "invalid_information" olur
    And TCKN invalid fields içinde yer alır
    And TCKN missing required fields içinde yer almaz
    And routing tetiklenmez

  Scenario: Kullanıcı eksik bilgiyi tamamlar
    Given "waiting_for_user" durumundaki bir case
    When kullanıcı eksik alanları aynı case için gönderir
    Then önceki geçerli alanlar korunur
    And validation yeniden çalışır
    And tüm zorunlu alanlar tamamlandıysa case processing'e devam edebilir

  Scenario: Supplemental PATCH stale revision ile case'i değiştiremez
    Given revision "8" olan waiting_for_user case
    When yetkili kullanıcı `If-Match: "7"` ile PATCH supplemental-information gönderir
    Then HTTP 412 döner
    And current values ve revision değişmez

  Scenario: Supplemental PATCH aynı idempotency key ile replay edilir
    Given başarılı bir supplemental PATCH isteği için Idempotency-Key kaydedilmiştir
    When yetkili kullanıcı aynı isteği aynı key ile tekrar gönderir
    Then ilk validation sonucu tekrar döner
    And ikinci merge veya validation update yapılmaz

  Scenario: Supplemental PATCH case erişimi olmadan reddedilir
    Given çağıranın case için geçerli Bearer authorization'ı yoktur
    When supplemental-information PATCH isteği gönderir
    Then HTTP 401 veya HTTP 403 döner
    And case verisi değişmez
