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
5. `ready_for_processing` olmadan final routing yapılmaz.
6. Draft ve mevzuat feature'ı başarısız olsa dahi hata açıkça tutulur; sistem tamamlanmış görünmez.
7. Routing başarılı, notification başarısızsa state bunu ayrı ifade eder ve retry mümkün olur.

## Teknik sınırlar

- Orchestrator servislerin iç ML mantığını kopyalamamalıdır.
- Her servis çağrısı correlation/case id taşımalıdır.
- Retry, özellikle non-idempotent routing gibi adımlarda duplicate side effect yaratmamalıdır.
- State persistence restart sonrası kaybolmamalıdır.
- Basit demo için message broker zorunlu değildir; HTTP tabanlı orchestration yeterli olabilir. Broker yalnızca repo/mimari gerçekten gerektiriyorsa eklenmelidir.

## Gözlemlenebilirlik

Her case için en az şu bilgiler sorgulanabilmelidir:

- current state
- tamamlanmış steps
- son hata kodu
- son güncelleme zamanı
- classification ids
- missing fields
- routing sonucu
- notification statuses

## Acceptance kriterleri

- Happy path tek case id altında baştan sona tamamlanır.
- Missing-information path durur, kullanıcı tamamlayınca devam eder.
- Classification uncertainty route edilmez.
- Notification failure sonrası tekrar sadece gerekli aşamayı çalıştırır.
- Container restart sonrası in-flight case state korunur veya deterministik şekilde recover edilir.

## Quality gate

`acceptance/e2e_pipeline.feature` tüm kritik path'lerde geçmelidir.
