# F-04 - Mevzuat Önerisi, Özet ve Resmi Yazı Taslağı

## Neden bu feature var?

Kullanıcı tarafından tarif edilen dört aşamalı çekirdek akışa ek olarak 1. senaryo şartnamesi açık biçimde şu yetenekleri ister:

- ilgili mevzuat, yönetmelik veya standart yazışma kurallarını önerebilme,
- evraka kısa ve öz özet oluşturma,
- üst yazı / cevap yazısı / bilgilendirme metni gibi uygun resmi yazışma taslağı oluşturma,
- resmi üsluba uygunluk.

Dolayısıyla yarışma kapsamının eksik kalmaması için bu feature backend'in zorunlu tamamlayıcı parçası olarak tanımlanmıştır.

## Önkoşul

F-03 `completion_status=complete` olmalıdır. Eksik veriyle nihai resmi yazı taslağı final kabul edilmemelidir.

## Servis sorumluluğu

İki mantıksal bileşen olabilir ancak tek container zorunlu değildir:

- `regulation-retrieval` / mevcut RAG servisi: kaynak eşleştirme
- `correspondence-generation`: Jamba kullanarak özet ve taslak üretimi

Repository'de mevcut RAG veya LLM servisleri varsa yeni duplicate servis yazmak yerine mevcut kontratlara entegre olunmalıdır.

F-04 case-level asenkron operasyonu başlatır:

```http
POST /cases/{case_id}/correspondence
Authorization: Bearer <token>
Idempotency-Key: <uuid>
If-Match: "<current_case_revision>"
```

Body semantic input kabul etmez; prompt, request type, departman, extracted
field veya correspondence type backend-authoritative case state'ten okunur.
Başarı HTTP 202 ile `case_id`, `job_id`, `case_revision` ve
`generation_status: queued` döndürür. `GET /cases/{case_id}/correspondence`
aynı authorization kuralıyla current sonucu veya processing durumunu okur.

## Mevzuat önerisi gereksinimleri

- Öneri, kaynak metne/referansa bağlanabilmelidir.
- Kaynak bulunamadığında mevzuat uydurulmamalıdır.
- `no_relevant_source` geçerli bir sonuçtur.
- Retrieval sonucu ile Jamba'nın serbest üretimi ayrıştırılmalıdır.
- Demo corpus internete çıkmaz; versioned local official-public snapshot'tır.
  `demo-municipality-regulations-v1` build'i REG-001..REG-006 kaynaklarını
  kapsar. Citation metadata retrieval'dan gelir; Jamba citation yaratamaz.
- Corpus request-type filtering/boost bilgisi versioned corpus metadata'sıdır;
  F-02 taxonomy ID'leri için application code'a hard-coded mapping eklenmez.

## Resmi yazı taslağı gereksinimleri

Completed current çıktı en az:

- `document_summary`
- `recommended_correspondence_type`
- `draft_text`
- `regulation_suggestions[]`
- `generation_metadata`

Ek durum alanları: `generation_status` (`queued|processing|completed|failed`),
`source_status` (`relevant_source_found|no_relevant_source`) ve
`result_status` (`draft_ready|review_required`). Correspondence type yalnız
`response_letter`, `information_letter`, `referral_letter`, `cover_letter` veya
`other` stable ID'lerinden biridir. `other` için açıklayıcı detail olabilir.

içermelidir.

Jamba promptu/classification sonucu/extracted alanlar structured context olarak verilmelidir. Modelden departman veya zorunlu alanları yeniden tahmin etmesi istenmemelidir.

## Güvenlik ve doğruluk sınırları

- Model olmayan mevzuat maddesi, tarih, dosya no veya kişisel bilgi uydurmamalıdır.
- Eksik veri placeholder ile açıkça işaretlenebilir; ancak F-03 tamamlanmadan final taslak statüsü verilmez.
- PII authoritative source F-03 validated state'tir. Jamba'ya minimize/redacted
  placeholder'lar verilir; backend yalnız doğrulanmış değerleri sonradan
  yerleştirir.
- Structured Jamba JSON'u schema ve retrieval citation ref'leri ile doğrulanır.
  Base instruct model geçerli JSON nesnesini markdown fence içine alabilir veya
  nesneyi kapattıktan sonra yazmaya devam edebilir; bu nedenle yanıttan ilk
  decode edilebilir JSON nesnesi okunur. Bu yalnızca ayrıştırma toleransıdır:
  şema, enum, karakter limiti, citation ve no-source guard kontrolleri
  değişmeden uygulanır. İlk geçersiz çıktıdan sonra en fazla bir repair attempt
  yapılır; ikinci hata `STRUCTURED_OUTPUT_INVALID` ile failed olur ve partial
  draft publish edilmez.
- Resmi metin çıktısı `draft` niteliğindedir; otomatik imza/onay veya gerçek kurum gönderimi bu feature'ın scope'u değildir.

## Acceptance kriterleri

- Tamamlanmış bir case için kısa Türkçe özet üretilir.
- Uygun yazışma türü seçilir ve taslak metin resmi üsluptadır.
- Bulunan mevzuat önerileri kaynak bilgisi ile döner.
- Kaynak yoksa uydurma mevzuat üretilmez.
- Eksik veya invalid bilgi bulunan case için POST HTTP 409
  `CASE_NOT_READY_FOR_CORRESPONDENCE` döner; case `waiting_for_user` kalır,
  job/Jamba/revision değişmez.
- Kaynak yoksa taslak üretilir fakat `source_status=no_relevant_source` ve
  `result_status=review_required` olur; mevzuat/madde uydurulmaz.
- Generation history immutable PostgreSQL kaydıdır; case yalnız current
  generation pointer'ı taşır. PostgreSQL durable job/outbox restart sonrası
  queued/expired-processing işi lease-safe retry ile kurtarır.

## Quality gate

`acceptance/f04_official_correspondence.feature` geçmeden uçtan uca demo tamamlanmış sayılmaz.
