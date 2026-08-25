# F-01 - Evrak Girdisi ve Normalizasyon

## Amaç

Sisteme doğrudan metin veya OCR sonucundan gelen evrak içeriğini tek bir güvenilir backend kontratına dönüştürmek ve sonraki servislerin girdi kaynağının ne olduğundan bağımsız çalışmasını sağlamak.

## Servis sorumluluğu

Mevcut mantıksal/Compose servisi: `ocr`; intake davranışı mevcut
`POST /v1/ocr` kontratı değiştirilerek burada uygulanacaktır. Ayrı bir intake
endpoint veya servis eklenmez.

Bu servis OCR yapmayı zorunlu olarak üstlenmez. OCR ayrı bir servis ise onun çıktısını kabul eder. Doğrudan metin de aynı endpoint/kontrat üzerinden kabul edilebilir.

## Girdi

Asgari alanlar:

- `schemaVersion`: tam olarak `2.0`
- `requestId`: trace için zorunlu id
- `documentId`: zorunlu, stable idempotency anahtarı
- `sourceType`: `text` | `ocr`
- `text`
- opsiyonel `sourceMetadata`: dosya adı, sayfa sayısı, OCR confidence özeti ve
  F-03 attachment presence için `attachments[]` stable referansları vb.
- opsiyonel `correlationId`

## Çıktı

Normalize edilmiş evrak nesnesi:

- `documentId`
- `caseId`
- `workflowId`
- `text` (normalize edilmiş metin)
- `language`
- `confidence`
- `ingestStatus: queued`
- `warnings[]`

## Fonksiyonel gereksinimler

1. Boş, whitespace-only veya 40 karakterden kısa metin downstream'e gönderilmemelidir.
2. Türkçe karakterler korunmalıdır; anlamsal içeriği bozacak aggressive normalization yapılmamalıdır.
3. Satır sonları, gereksiz kontrol karakterleri ve OCR kaynaklı görünmez karakterler güvenli biçimde normalize edilmelidir.
4. Orijinal metin izlenebilirlik amacıyla PostgreSQL'de saklanır; downstream için normalize edilmiş metin ayrı tutulur ve response'ta yalnız normalize edilmiş metin bulunur.
5. Aynı stable document identity tekrar gönderildiğinde idempotent replay yapılmalı; mevcut document/case/workflow identity dönmeli ve ikinci kayıt veya durable job oluşturulmamalıdır.
6. OCR confidence gibi metadata mevcutsa korunmalı fakat classification sonucu için tek başına karar verici olmamalıdır.
7. Original ve normalized metinler ile case/workflow state PostgreSQL'de persist edilmelidir. PostgreSQL authoritative source-of-truth'tur; ilk dispatch mekanizması PostgreSQL-backed durable job/outbox'tır.
8. Container restart sonrasında hiçbir case veya pending iş kaybolmamalıdır. Redis ilk implementasyonda zorunlu değildir.
9. Bu feature hiçbir departman/birim/talep türü kararı vermemelidir.
10. Aynı `documentId` değişmiş metin, source type, metadata veya correlation ID ile tekrar gelirse HTTP 409 non-retryable hata döner; mevcut state değişmez.

## Hata davranışı

- Metin yoksa, normalize edildikten sonra 40 karakterden kısaysa veya source type desteklenmiyorsa: HTTP 400 + makine tarafından işlenebilir validation hatası.
- Aynı `documentId` için değişmiş immutable input: HTTP 409 + non-retryable validation hatası.
- Internal persistence/queue problemi: 5xx; belge kaybolmuş gibi başarılı cevap verilmez.
- Downstream henüz hazır değilse intake kaydı başarılı kabul edilebilir ancak processing state açıkça `queued`/`pending` olmalıdır.

## Acceptance kriterleri

- Doğrudan metin girdisi normalize edilip tekil document id ile kabul edilir.
- OCR servisi çıktısı aynı normalize edilmiş belge kontratına çevrilir.
- Boş metin reddedilir.
- Türkçe karakterler bozulmaz.
- Aynı immutable belge için idempotent replay yapılır; farklı immutable input aynı `documentId` ile reddedilir.
- 39 karakterlik metin reddedilir; 40 karakterlik metin kabul edilir.
- Restart sonrası pending case/workflow state ve durable job PostgreSQL'den recover edilebilir.
- Downstream servisler `source_type` üzerinden branching yapmak zorunda kalmaz.

## Out of scope

- OCR modelinin eğitimi/servislenmesi.
- Departman sınıflandırması.
- Eksik bilgi tespiti.
- Jamba ile metin üretimi.

## Quality gate

`acceptance/f01_intake.feature` senaryoları geçmeden F-02'ye geçilmez.
