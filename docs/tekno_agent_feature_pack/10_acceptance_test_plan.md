# Acceptance-Test-Driven Uygulama Planı

## Amaç

Implementation başlamadan önce beklenen davranışları sabitlemek ve her feature'ı test edilebilir bir delivery unit haline getirmek.

## Test katmanları

### 1. Contract tests

Her servis request/response schema'sı için:

- valid payload kabulü
- required field eksikliği
- invalid enum/type
- stable error envelope
- backward-incompatible contract değişikliği tespiti

### 2. Service acceptance tests

`acceptance/` altındaki Gherkin senaryoları feature-level acceptance kriteridir. Test framework repo standardına göre seçilir.

### 3. Model/ML evaluation

Classification için:

- department accuracy
- unit accuracy
- request type accuracy
- exact hierarchy match

Extraction için:

- required field precision/recall veya field-level exact match
- missing-field detection precision/recall

Generation için insan değerlendirme rubric'i:

- Türkçe doğruluk/akıcılık
- resmi üslup
- kaynakla tutarlılık
- hallucination yokluğu
- bildirimde hedef kitleye uygunluk

### 4. E2E

Zorunlu akışlar:

- doğrudan text happy path
- OCR-origin happy path
- missing information -> user supplement -> resume
- low-confidence classification -> stop/review
- Jamba temporary failure -> retry notification/generation
- inactive target unit -> controlled failure
- restart/recovery

### Bu repository'de Docker quality gate sırası

1. `docker compose config --quiet`
2. `docker compose up --build -d`
3. `docker compose --profile tests run --build --rm contract-tests --mode mock`
4. GPU ortamında gerçek Jamba için `docker compose -f compose.yaml -f compose.llm.yaml up --build -d llm`
5. Gerçek Jamba'da `/health`, `/ready` ve `/v1/generate` smoke çağrıları
6. F-02 için `docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml up --build -d` ve `run_classification_intake.py`
7. F-03 için OCR + classification + validation overlay ile `run_validation_intake.py`
8. F-04/F-05/F-06 için OCR + classification + validation + llm + workflow overlay ile `run_correspondence_intake.py`
9. Aynı stack'te F-02 `needs_review` negative-path için `run_orchestration_intake.py`
10. Tüm gerçek image'lar yayınlandıktan sonra `scripts/coreaigent.ps1 e2e` ve `--mode real`

İlk üç adım mock sözleşme kontrolüdür; Jamba'nın gerçekten yüklendiğini
kanıtlamaz. Dördüncü ve beşinci adım GPU/cache gerektirir. Altıncı adımda OCR,
classification ve durable worker gerçektir; kalan servisler mock'tur. `dev llm`
testinde yalnızca `llm` gerçek, diğer servisler mock'tur. F-03 CPU acceptance
akışında OCR, classification, worker ve validation gerçektir; semantic extractor
açıkça deterministic test double'dır ve gerçek Jamba değildir. Sekizinci ve
dokuzuncu adım gerçek Jamba/BGE-M3/PostgreSQL workflow koşumlarıdır; mock
scenario response'u kullanmazlar. Tam komutlar README'nin F-04/F-05/F-06
çalıştırma bölümündedir.

## Definition of Done

Bir feature "done" değildir eğer yalnızca endpoint çalışıyorsa. DoD:

- requirement acceptance criteria karşılanmış,
- contract dokümante edilmiş,
- ilgili `.feature` senaryoları geçmiş,
- Docker ortamında smoke test geçmiş,
- hata davranışları gözlemlenebilir,
- feature scope dışı değişiklik yok,
- README/runbook gerekliyse güncellenmiş.

## Test verisi

Gerçek kamu verisi kullanılmamalıdır. Sentetik veya açık kaynak evrak örnekleri hazırlanmalı; her test örneği expected department/unit/request type ve expected required/missing field bilgisi taşımalıdır.

## Minimum demo dataseti

Demo için en az:

- 3 departman
- departman başına en az 2 birim
- toplam en az 6-10 request type
- her request type için bir complete ve bir incomplete örnek
- birkaç ambiguous/needs-review örneği

önerilir. Bunlar yarışmanın final veri seti değildir; E2E davranışını görünür kılacak minimum acceptance fixture'larıdır.
