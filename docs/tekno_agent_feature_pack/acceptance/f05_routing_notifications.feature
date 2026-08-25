Feature: Nihai routing ve iki hedefli bildirim

  Scenario: Complete case doğru birime yönlendirilir
    Given complete ve geçerli hierarchical classification'a sahip bir case
    When routing çalışır
    Then target_unit_id classification ile tutarlı olur
    And routing_status "routed" olur

  Scenario: Kullanıcı ve birim için farklı bildirimler hazırlanır
    Given başarılı şekilde route edilmiş bir case
    When notification generation çalışır
    Then kullanıcı için süreç odaklı bir bildirim üretilir
    And hedef birim için evrak özeti ve işlem bağlamı içeren ayrı bir bildirim üretilir

  Scenario: Jamba bildirimi başarısız olsa da routing kaybolmaz
    Given routing başarıyla tamamlanmış bir case
    And Jamba servisi geçici olarak kullanılamaz
    When notification generation başarısız olur
    Then routing kaydı "routed" kalır
    And notification status "failed" veya retryable olur
