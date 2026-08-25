# F-08 - Docker Compose, Servis İzolasyonu ve Yerel Çalıştırma

## Amaç

Mock sözleşme stack'i, tek gerçek servis geliştirme stack'i ve tüm gerçek
servis E2E stack'i birbirine karıştırmadan çalıştırılabilir hale getirmek.

## Repository'deki servis haritası

| Compose servisi | Logical rol | Bu repodaki durum |
| --- | --- | --- |
| `ocr` | intake/OCR | `compose.ocr.yaml` ile PostgreSQL-backed gerçek intake veya base mock |
| `classification` | hiyerarşik sınıflandırma | `compose.classification.yaml` ile PostgreSQL-backed gerçek API + durable worker veya base mock |
| `validation` | eksik bilgi/validasyon | `compose.validation.yaml` ile PostgreSQL-backed gerçek servis veya base mock |
| `rag` | mevzuat retrieval | contract mock; gerçek implementasyon bekliyor |
| `llm` | Jamba structured generation | `compose.llm.yaml` ile gerçek GPU image'ı veya base mock |
| `workflow` | orchestration, draft, routing | contract mock; gerçek implementasyon bekliyor |

Bu nedenle feature pack'teki logical rollerin yedi ayrı container olması
zorunlu değildir; ancak `contracts/http/manifest.json` sınırları ve sabit
container DNS adları korunur.

## Üç çalıştırma modu

| Mod | Komut | Ne kanıtlar |
| --- | --- | --- |
| Mock baseline | `docker compose up --build -d` | 6 deterministic mock ve 58 golden scenario |
| Bir gerçek OCR servis | `scripts/coreaigent.ps1 dev ocr` | PostgreSQL-backed gerçek intake + diğer servis mock'ları |
| Bir gerçek LLM servis | `scripts/coreaigent.ps1 dev llm` | Gerçek Jamba + diğer servis mock'ları |
| F-03 CPU acceptance | OCR + classification + validation overlay | Gerçek PostgreSQL servisleri, açıkça injected deterministic extractor |
| Tam gerçek E2E | `scripts/coreaigent.ps1 e2e` | `.env` içindeki tüm SHA-pinned image'lar |

`dev` ve `integration` seçilen servis için Dockerfile yoksa durur; mock'u
gerçek servis gibi göstermez. Tam E2E akışında `compose.integration.yaml`
yalnızca immutable image tag'lerini kullanır; local `compose.llm.yaml` bu
akışa eklenmez.

## Mock baseline doğrulaması

Bu repository için zorunlu Docker kontrolü aşağıdaki akıştır:

```bash
docker compose config --quiet
docker compose up --build -d
docker compose --profile tests run --build --rm contract-tests --mode mock
docker compose ps
docker compose down --volumes --remove-orphans
```

Bu komut gerçek Jamba başlatmaz. Jamba ağırlığı, GPU veya gerçek servis image'ı
gerektirmeden kontratları ve 58 mock senaryoyu doğrular.

## Gerçek OCR intake geliştirme akışı

`compose.ocr.yaml`, base `ocr` mock'unu gerçek `services/ocr/Dockerfile` ile
değiştirir ve yalnız bu development topolojisine PostgreSQL 16 ekler. Redis
gerekmez; intake kaydı ve durable outbox aynı PostgreSQL transaction'ında
oluşturulur.

```bash
docker compose -f compose.yaml -f compose.ocr.yaml config --quiet
docker compose -f compose.yaml -f compose.ocr.yaml up --build -d
docker compose -f compose.yaml -f compose.ocr.yaml --profile tests run --build --rm --entrypoint python contract-tests /app/run_ocr_intake.py --phase all
docker compose -f compose.yaml -f compose.ocr.yaml --profile tests run --rm --entrypoint python contract-tests /app/run_ocr_intake.py --phase restart-create
docker compose -f compose.yaml -f compose.ocr.yaml restart ocr
docker compose -f compose.yaml -f compose.ocr.yaml --profile tests run --rm --entrypoint python contract-tests /app/run_ocr_intake.py --phase restart-verify
docker compose -f compose.yaml -f compose.ocr.yaml down --volumes --remove-orphans
```

## Gerçek Jamba geliştirme akışı

`compose.llm.yaml` base `llm` mock'unun image/build tanımını gerçek
`services/llm/Dockerfile` ile değiştirir, GPU ister, HF cache mount eder ve
healthcheck'i `/ready` endpoint'ine bağlar:

```bash
cp .env.example .env
export HF_CACHE_DIR=/media/serda/home_extra/hf-cache
docker compose -f compose.yaml -f compose.llm.yaml config --quiet
docker compose -f compose.yaml -f compose.llm.yaml up --build -d llm

curl http://localhost:8085/health
curl http://localhost:8085/ready
docker compose -f compose.yaml -f compose.llm.yaml logs --tail 100 llm
```

## Gerçek validation geliştirme akışı

F-03, normalized metni PostgreSQL'den okur; `POST /v1/validate` body’sine
metin eklemez. Aşağıdaki CPU akışı `EXTRACTOR_MODE=deterministic` ile gerçek
validation servisinin persistence, missing/invalid ayrımı ve supplemental
idempotency davranışını doğrular. Bu Jamba testi değildir.

```bash
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.validation.yaml config --quiet
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.validation.yaml up --build -d
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.validation.yaml --profile tests run --build --rm --entrypoint python contract-tests /app/run_validation_intake.py
docker compose -f compose.yaml -f compose.ocr.yaml -f compose.classification.yaml -f compose.validation.yaml down --volumes --remove-orphans
```

Validation current state için restart predicate'i ayrıca `--phase
restart-create`, `docker compose ... restart validation` ve `--phase
restart-verify` sırasıyla doğrulanır.

Gerçek Jamba extraction için bu overlay'e ayrıca `compose.llm.yaml` eklenir ve
validation `EXTRACTOR_MODE=jamba` ile `http://llm:8080/generate` adresine
bağlanır. Jamba hazır değilse validation `/ready` veya extraction isteği
başarılı gibi davranmaz.

Model cache hazır değilse `/ready` başarılı olmaz. Cache'i image layer'ına
almayın; `HF_CACHE_DIR` ile host cache bind edin veya Compose'un
`llm-hf-cache` named volume'unu önceden doldurun. GPU host'ta NVIDIA Container
Toolkit bulunmalıdır.

## Network, readiness ve state

- Container-to-container çağrı adresleri `http://ocr:8080`, `http://llm:8080`
  gibi service DNS adlarıdır; `localhost` yalnız host smoke için kullanılabilir.
- `/health` liveness, `/ready` dependency/model readiness'tir.
- Jamba model yüklenmeden `/ready` `200` dönmez.
- Mock stack ephemeral'dir ve state persistence iddia etmez. OCR development
  overlay'i `ocr-postgres-data` named volume'u ile F-01 state/outbox
  dayanıklılığını doğrular.
- `.env` secret olmayan demo/runtime ayarlarını taşır; gerçek secret commit
  edilmez.

## Acceptance kriterleri

- Yeni geliştirici mock baseline'ı README'deki tek akışla çalıştırabilir.
- Gerçek Jamba yalnız GPU + pinned model/cache koşulları sağlanınca ready olur.
- Service discovery sabit Compose DNS adlarıyla yapılır.
- Mock, development, integration ve E2E modlarının neyi kanıtladığı açıkça
  ayrıdır.
- Offline demo, önceden doldurulmuş cache ile dış model API'sine ihtiyaç
  duymaz.
