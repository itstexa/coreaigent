# F-06 - Workflow Orkestrasyonu ve Case State

## Amaç

F-01..F-05 servislerini tek bir uçtan uca evrak yaşam döngüsü haline getirmek. Bu feature yeni NLP yeteneği eklemez; servislerin sırasını, durum geçişlerini, retry/stop davranışlarını ve case izlenebilirliğini tanımlar.

## Temel state modeli

Önerilen asgari durumlar:

- `received`
- `normalized`
- `classified`
- `needs_review`
- `extracting`
- `waiting_for_user`
- `ready_for_processing`
- `draft_prepared`
- `routed`
- `notification_pending`
- `completed`
- `failed`

İsimler repository standardına göre değişebilir; anlam ve geçişler korunmalıdır.

## Zorunlu geçiş kuralları

1. `received -> normalized -> classified` normal başlangıç akışıdır.
2. Classification belirsizse `needs_review`; sonraki otomatik adımlar çalışmaz.
3. Required field eksikse `waiting_for_user`.
4. Kullanıcı ek bilgi gönderdiğinde aynı case tekrar F-03 validation'a girer.
5. F-03 current revision `complete` olduğunda durable orchestrator F-04'ü otomatik başlatır; initial start ve en fazla üç cooldown retry aynı revision'a bağlanır.
6. `ready_for_processing` olmadan final routing yapılmaz. F-04'ün terminal failure'ı F-05 route yaratmaz.
7. `review_required` fallback birime route edilse bile case otomatik `completed` olmaz; yetkili reviewer ayrı idempotent operation ile tamamlayabilir.
8. Routing başarılı, notification başarısızsa route korunur ve state outstanding notification work'ü ayrı ifade eder.

## Teknik sınırlar

- Orchestrator servislerin iç ML mantığını kopyalamamalıdır.
- Her servis çağrısı correlation/case id taşımalıdır.
- Retry, özellikle non-idempotent routing gibi adımlarda duplicate side effect yaratmamalıdır.
- State persistence ve queued/leased work restart sonrası kaybolmamalıdır.
- PostgreSQL authoritative source-of-truth'tur. Start, route ve notification işleri PostgreSQL-backed durable job/outbox ve lease modeliyle yürür; Redis/message broker zorunlu değildir.
- Orchestrator F-02/F-03/F-04/F-05 kararlarını yeniden üretmez; yalnız source kayıtlarından current case projection ve durable sıralama üretir.

## Gözlemlenebilirlik

`GET /cases/{case_id}` üzerinden her demo case için en az şu bilgiler
sorgulanabilmelidir:

- current state
- tamamlanmış steps
- son hata kodu
- son güncelleme zamanı
- validation ve routing status
- applicant missing/invalid notification'ları

Demo `ADMIN` projection'ı ayrıca classification/validated fields, target
routing ve target-unit notification detail'i görebilir. Demo `USER` projection'ı
bu internal alanları almaz; bu iki fixed-token model production RBAC değildir.

## Acceptance kriterleri

- F-03 complete case client F-04 POST'u olmadan durable start job ile F-04'e geçer.
- Happy path tek case id altında F-04/F-05 notification'larına kadar tamamlanır.
- Missing-information path durur, kullanıcı tamamlayınca devam eder.
- Classification uncertainty PostgreSQL'de `needs_review` görünür kalır; validation, F-04 start veya route edilmez.
- Notification failure sonrası tekrar sadece gerekli aşamayı çalıştırır.
- Container restart sonrası pending/leased case state PostgreSQL'den deterministik şekilde recover edilir.

## Quality gate

Unit/contract testlerine ek olarak gerçek local stack'te
`run_correspondence_intake.py` ve `run_orchestration_intake.py` çalışmalıdır;
ilk koşum gerçek OCR, classification, validation, BGE-M3, Jamba, PostgreSQL ve
F-04/F-05/F-06 zincirini, ikincisi F-02 review negatif yolunu doğrular.
`acceptance/e2e_pipeline.feature` kritik path regresyonlarını tamamlar.
