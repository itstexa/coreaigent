# F-03 - Bilgi Çıkarımı ve Eksik Bilgi Tespiti

## Amaç

F-02 sonucunda belirlenen `request_type` için gerekli alan şemasını bulmak, evrak içindeki bilgileri yapılandırılmış olarak çıkarmak ve zorunlu bilgilerden hangilerinin eksik olduğunu belirlemek.

Bu feature, şartnamedeki "içerikte geçen önemli bilgi unsurlarını çıkarma" ve "bulunması gereken ancak eksik olan bilgileri tespit etme" beklentisinin backend karşılığıdır.

## Servis sorumluluğu

Mevcut `validation` mantıksal servisi ve `POST /v1/validate` sınırı
geliştirilecektir. Yeni bir extraction servisi veya endpoint eklenmez.
Kullanıcının ek bilgisi ise validation içine sıkıştırılmaz; ayrı case-level
supplemental-information endpoint'i kullanılır.

## Request type schema registry

Her F-02 `Demo Belediyesi` request type'ı için versiyonlanabilir bir şema
bulunmalıdır. Başlangıç demo registry'si mevcut on request type'ını kapsar ve
mevcut Docker/CI user-story örnekleriyle uyumlu contact, identity, address,
date, document number, subject, description ve attachment alanlarını kullanır:

- `request_type_id`
- `schema_version`
- `required_fields[]`
- `optional_fields[]`
- her alan için type, açıklama ve mümkünse validation kuralı
- opsiyonel normalization kuralı

Örnek alan türleri: kişi/kurum adı, iletişim, tarih, olay tarihi, adres, başvuru konusu, açıklama, belge numarası vb. Gerçek liste analyst tarafından proje taksonomisine göre belirlenir.

## Çıktı

- `extracted_fields`: alan -> canonical değer + confidence
- `missing_required_fields[]`
- `invalid_fields[]`
- `schema_version`
- `completion_status`: `complete` | `missing_information` | `invalid_information`
- `user_action_required`: boolean
- kullanıcıya gösterilebilecek kısa eksik bilgi özeti

## Fonksiyonel gereksinimler

1. Required field listesi modelin keyfine göre değil request-type schema'dan gelmelidir.
2. Hibrit extraction uygulanır: TCKN, telefon ve tarih gibi kesin formatlı
   değerler deterministik kural/validator ile; diğer schema alanları Jamba ile
   çıkarılır. Jamba çıktısı da schema validation'dan geçmeden accepted olmaz.
3. `missing_information` ile `invalid_information` kesinlikle ayrılır:
   required alan için kullanılabilir değer hiç yoksa `missing_information`;
   değer varsa fakat checksum, format, parse veya enum/schema kuralı
   başarısızsa `invalid_information` üretilir.
4. Source evidence/span internal doğrulama amacıyla kullanılabilir; public
   response'a evidence, provenance veya raw PII döndürülmez.
5. Tarih, telefon, kimliksiz numara, adres gibi alanların normalize/validate davranışı alan tipine göre yapılmalıdır.
6. Zorunlu alan eksik veya geçersizse workflow F-04/F-05 nihai işlemlerine ilerlememelidir.
7. Eksik/geçersiz bilgi listesi kullanıcıya teknik field id yerine anlaşılır Türkçe label ile sunulmalıdır.
8. Kullanıcının sonradan verdiği ek bilgiler ayrı case-level endpoint ile mevcut case'e merge edilip aynı validation tekrar çalıştırılabilmelidir.
9. İkinci turda kullanıcı yalnızca eksik/geçersiz alanları tamamlamak zorunda olmalıdır; önceki geçerli alanlar kaybolmamalıdır.
10. PostgreSQL authoritative source-of-truth olmaya devam eder; yalnız current F-03 field, completion ve case/workflow state tutulur, geçmiş sonuçlar tutulmaz.
11. `POST /v1/validate`, mevcut `documentId` ile normalized metni PostgreSQL'den okur; metin validation request'ine yeniden eklenmez.
12. Public sonuçta field confidence dönebilir; source evidence/span, extractor provenance ve raw PII evidence istemciye dönmez.
13. Zorunlu attachment alanı, F-01'de PostgreSQL'e persisted edilmiş
   `sourceMetadata.attachments[]` stable referansı ile doğrulanır; public F-03
   sonucu attachment ID veya dosya adını değil yalnız canonical `present`
   değerini gösterir.

## Supplemental-information kontratı

Eksik veya geçersiz değerler için ayrı sınır şudur:

```http
PATCH /cases/{case_id}/supplemental-information
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: <uuid>
If-Match: "<current_revision>"
```

```json
{"fields":{"field_id":"value"}}
```

Başarılı istek valid değerleri aynı case'e atomik olarak merge eder, F-03'ü
yeniden çalıştırır, current validation sonucunu döner ve yeni revision'ı
`ETag` header'ında verir. Aynı idempotency key + aynı istek ilk sonucu replay
eder; farklı istekle key reuse HTTP 409'dur. Stale `If-Match` HTTP 412 ve
mutasyonsuzdur. Kimlik doğrulaması yoksa HTTP 401, case erişimi yoksa HTTP 403,
bozuk body HTTP 400 döner. Sabit demo bearer token kontrata gömülmez; case
erişimi injectable bir authorization adapter ile doğrulanır.

## Frontend sınırı

Frontend için şimdilik yalnızca geçici bir uyarı/banner/form yeterlidir. Backend `missing_required_fields` ve `user_action_required` alanlarını authoritative olarak üretmelidir. Frontend iş kurallarını yeniden hesaplamamalıdır.

## Acceptance kriterleri

- Tam evrak `complete` olur.
- Eksik zorunlu alan içeren evrak `missing_information` olur ve eksik alanlar doğru listelenir.
- Optional alan eksikliği akışı durdurmaz.
- Kullanıcı ek bilgi verdiğinde case aynı id altında yeniden değerlendirilir.
- Önceden çıkarılan geçerli alanlar ikinci turda korunur.
- Eksik bilgi varken routing/official draft finalization tetiklenmez.

## Quality gate

`acceptance/f03_missing_information.feature` geçmeden F-04/F-05 işleme alınmaz.
