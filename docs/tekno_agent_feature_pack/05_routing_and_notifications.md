# F-05 - Nihai Birim Yönlendirme ve Bildirim Üretimi

## Amaç

Tamamlanmış ve sınıflandırılmış evrakı doğru hedef birime sevk etmek; kullanıcı ve evraka bakacak birim için birbirinden farklı, bağlama uygun bildirim içerikleri üretmek.

## Önkoşullar

- F-02 classification sonucu geçerli olmalı.
- F-03 `completion_status=complete` olmalı.
- Hedef birim taxonomy'de aktif olmalı.

## Servis sorumluluğu

Önerilen mantıksal servis: `routing-notification-service`.

Bildirim metinleri Jamba tabanlı yerel `llm` servisini kullanır. Routing kararı ise LLM serbest metnine bırakılmamalı; F-02 stable ids ve routing registry üzerinden verilmelidir.

## Routing çıktısı

- `case_id`
- `target_department_id`
- `target_unit_id`
- `request_type_id`
- `routing_status`: `routed` | `pending_review` | `failed`
- `routed_at`
- routing reason/audit metadata

## Kullanıcı bildirimi

Kullanıcıya yönelik içerik örnek anlamı:

- başvurunun alındığı,
- hangi genel süreçte olduğu,
- hedef birim adı,
- varsa sonraki beklenen adım.

İç yazışma detayları veya gereksiz teknik metadata kullanıcıya sızdırılmamalıdır.

## Birim bildirimi

Hedef birime yönelik içerik kullanıcı mesajından ayrı template/prompt kullanmalıdır ve en az:

- talep türü,
- kısa özet,
- önemli çıkarılmış alanlar,
- varsa mevzuat/standart yazışma önerisi,
- case/document id

içerebilmelidir.

## Fonksiyonel gereksinimler

1. Aynı case'in tekrarlı çağrıda iki kez sevk edilmesi engellenmeli veya idempotent olmalıdır.
2. Bildirim üretilemedi diye başarılı routing geri alınmamalıdır; routing ve notification durumları ayrı izlenmelidir.
3. Jamba servis hatası retry edilebilir bir notification failure olarak tutulmalıdır.
4. Kullanıcı ve birim mesajları aynı prompt çıktısının küçük varyasyonu olmak zorunda değildir; hedef kitleye özgü üretim yapılmalıdır.
5. Notification payload yapısal olarak saklanmalı; yalnızca raw text log'a güvenilmemelidir.
6. Geçersiz/inactive unit'e sevk yapılamamalıdır.

## Acceptance kriterleri

- Complete case doğru unit id'ye bir kez route edilir.
- User notification ve unit notification ayrı üretilir.
- Jamba geçici hata verdiğinde routing kaydı korunur ve notification retry edilebilir.
- Eksik bilgili case route edilmez.
- Inactive hedef birim kontrollü hata verir.

## Quality gate

`acceptance/f05_routing_notifications.feature` geçmeden F-06 E2E orchestration tamamlanmış sayılmaz.
