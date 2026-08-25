# F-02 - Hiyerarşik Evrak Sınıflandırma

## Amaç

Normalize edilmiş evrak metnini üç seviyeli bir kamu iş akışı taksonomisine yerleştirmek:

1. Departman
2. Departman içindeki birim
3. Talep/dilekçe/işlem türü

Sonuç, sonraki bilgi çıkarımı ve yönlendirme aşamalarının deterministik şekilde hangi şemayı kullanacağını belirlemelidir.

## Servis sorumluluğu

Mevcut `classification` mantıksal servisi ve `POST /v1/classify` sınırı
geliştirilecektir; ikinci bir classification endpoint'i eklenmez.

Embedding, klasik classifier, reranker, Jamba tabanlı classification veya hibrit yöntem kullanılabilir. Mimari, repository ve ölçüm sonuçlarına göre seçilmelidir. Feature belirli bir ML tekniğini zorunlu kılmaz.

## Taksonomi gereksinimi

Taksonomi koddan bağımsız ve versiyonlanabilir olmalıdır. Her kayıt en az:

- `department_id`, `department_name`
- `unit_id`, `unit_name`, `parent_department_id`
- `request_type_id`, `request_type_name`, `parent_unit_id`
- opsiyonel açıklama/örnekler/anahtar kavramlar
- `taxonomy_version`

içermelidir.

İlk veri kaynağı, repository içinde sürümlenen `Demo Belediyesi` taxonomy
fixture'ıdır. Bu fixture demo/evaluation içindir; harici gerçek belediye verisi
olarak sunulmaz.

## Çıktı

- `department`
- `unit`
- `request_type`
- her seviye için `confidence`
- `taxonomy_version`
- kısa `classification_reason` veya açıklanabilirlik alanı
- `status`: `classified` | `needs_review`

`topCandidates` alanı döndürülmez. Birden fazla geçerli zincir `0.80` eşiğini
geçerse yalnız confidence değeri en yüksek olan tek zincir döndürülür. Tam skor
eşitliği stable taxonomy ID ile deterministik olarak çözülür.

`needs_review` sonucunda geçerli bir en iyi tahmin varsa department/unit/request
type zinciri provisional olarak gösterilir; hiç eşleşme yoksa üç alan da
`null` olur. Her iki durumda da otomatik yönlendirme yapılmaz.

## Fonksiyonel gereksinimler

1. Birim seçimi yalnızca seçilen departmanın altındaki birimler arasında yapılmalıdır.
2. Talep türü yalnızca seçilen birimin izin verdiği türler arasından seçilmelidir.
3. Confidence skoru mevcut repository sözleşmesindeki `0..1` aralığındadır: yalnızca `0.80` değerinden kesinlikle büyük skor `classified` olur; `0.80` ve altı `needs_review` olur. Bu durumda otomatik yönlendirme yapılmaz.
4. `topCandidates` sözleşmeye eklenmez. Birden fazla geçerli aday eşik üstündeyse yalnız en yüksek confidence'lı aday seçilir; tam eşitlik stable taxonomy ID ile deterministik çözülür.
5. Sınıflandırma sonucu sonraki feature'lar tarafından tekrar tahmin edilmemeli; PostgreSQL'de case başına tek current authoritative classification kaydı tutulmalı, geçmiş sonuçlar saklanmamalıdır.
6. Model/embedding index versiyonu ve taxonomy versiyonu observability için izlenebilir olmalıdır.
7. Kullanıcıya açıklanan label ile backend'de kullanılan stable id ayrılmalıdır.
8. F-01'in PostgreSQL durable outbox içindeki `process_document` işi, çalışan tarafından tüketilmeli; sınıflandırma ve current result persistence başarılı olmadan job `completed` olmamalıdır.

## Ölçüm

Asgari olarak ayrı ölçülmelidir:

- department accuracy
- unit accuracy
- request type accuracy
- end-to-end exact hierarchical match
- abstain/needs-review oranı

Yanlış bir departmanın altında doğru isimli ama semantik olarak başka bir birim seçmek başarılı sayılmamalıdır.

## Hata davranışı

- Taxonomy bulunamaz/yüklenemez: servis unhealthy/failed; fallback ile uydurma label üretilmez.
- Hiçbir sınıf eşleşmiyorsa: `needs_review`; department, unit ve request type `null` olur.
- Model geçici olarak kullanılamıyorsa kontrollü retry veya 5xx; statik ilk label'a düşme gibi sessiz fallback yapılmaz.

## Acceptance kriterleri

- Test taxonomy'sinde doğru departman -> birim -> request type zinciri üretilir.
- Geçersiz parent-child kombinasyonu üretilemez.
- `0.80` confidence örneği `needs_review`, `0.81` örneği `classified` olur.
- Düşük confidence'ta geçerli en iyi zincir provisional olarak görünür; hiç eşleşmede zincir alanları `null` olur.
- Birden fazla eşik-üstü adayda yalnız en yüksek confidence'lı tek zincir döner; `topCandidates` yoktur.
- Sonuç stable id ve görünen label içerir.
- Taxonomy versiyonu response içinde izlenebilir.
- F-01 intake → durable outbox → classification → PostgreSQL current result → completed-job akışı gerçek servislerle çalışır.

## Out of scope

- Zorunlu alan çıkarımı.
- Harici bir belediye sistemine bildirim veya entegrasyon.
- Kullanıcı/birim bildirim metni üretimi.

## Quality gate

`acceptance/f02_classification.feature` geçmeden F-03'e geçilmez.
