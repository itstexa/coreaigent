# CoreAIgent — Kamu Evrak ve Yazışma Süreçleri İçin Akıllı Agent Destek Sistemi

TEKNOFEST Yapay Zeka Dil Ajanları Yarışması, Senaryo 1 kapsamında geliştirilen,
kamu kurumlarına gelen evrakları okuyan, sınıflandıran, eksik bilgi/çelişki
tespit eden, ilgili mevzuatı tarayan, uygun birime yönlendiren ve düzenlenebilir
resmî yazı taslağı üreten uçtan uca bir sistem.

Mimari doküman için [ARCHITECTURE.md](ARCHITECTURE.md), bilinen sınırlamalar
için [TECH_DEBT.md](TECH_DEBT.md), yarışma gereksinimleri için
[docs/teknofest_requirements.md](docs/teknofest_requirements.md)'e bakın.

## Mimari özet

Contract-first, 6 mantıksal servis (`contracts/schemas/`, `contracts/http/manifest.json`):
`ocr → classification → validation → rag → llm → workflow`.

**Runtime çıkarım air-gapped'dir:** sınıflandırma, doğrulama, yönlendirme ve
taslak üretimi yerel `Jamba2-3B-Turkish` modeliyle yapılır, çalışma zamanında
hiçbir internet/bulut API çağrısı yapmaz. DeepSeek Cloud API sadece
**geliştirme sırasında kod üretimi için** kullanıldı, üretim sisteminin parçası
değildir. Tek bilinen istisna `mevzuat-rag/` (RAG) alt sisteminin kendi iç
mimarisidir — bkz. TECH_DEBT.md.

## Kurulum

### 1. Sistem bağımlılıkları

```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-tur python3-venv
```

### 2. Python ortamı

Tüm servisler (`ocr`, `classification`, `validation`, `llm`, `workflow`) tek bir
paylaşılan sanal ortamı kullanır (repo kökünde `.venv/`):

```bash
cd coreaigent
python3 -m venv .venv
.venv/bin/pip install fastapi uvicorn pydantic torch transformers accelerate \
    pypdf pytesseract pillow qdrant-client sentence-transformers rank-bm25
```

(Son üç paket — `qdrant-client`, `sentence-transformers`, `rank-bm25` —
`services/llm/rag_connector.py`'nin ayrı bir alt-süreçte çağırdığı
`mevzuat-rag/` için gereklidir; bkz. Mimari.)

### 3. Jamba2-3B-Turkish modelini indirin

```bash
.venv/bin/python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('serda-dev/Jamba2-3B-Turkish')
"
```

Bu ~5.7GB indirir ve `~/.cache/huggingface/hub` altına yerleşir. Servisler
modeli belirli bir revizyona pinlenmiş (`model_loader.py` içindeki
`MODEL_REVISION`) ve tamamen `local_files_only=True` + `HF_HUB_OFFLINE=1` ile
yükler — indirme bittikten sonra internet gerekmez.

**Donanım notu:** Model bf16'da ~5.8GB VRAM kullanır; 8GB'lık bir GPU'da
rahatça çalışır. Daha küçük VRAM'de `model_loader.py`'deki `device_map`
`"cpu"`'ya (otomatik fallback zaten var, `torch.cuda.is_available()` kontrolü)
düşer ama çıkarım belirgin şekilde yavaşlar.

### 4. RAG (mevzuat-rag) ortamı

`mevzuat-rag/` ayrı, dokunulmamış bir alt sistemdir ve kendi `.env`'ine
ihtiyaç duyar:

```bash
cp mevzuat-rag/.env.example mevzuat-rag/.env
# mevzuat-rag/.env içine DEEPSEEK_API_KEY doldurun (platform.deepseek.com'dan
# doğrudan kopyalayın — bkz. mevzuat-rag/docs/SECRETS.md, başka bir .env'den
# veya global shell export'undan KOPYALAMAYIN).
```

RAG'ın kendi retrieval pipeline'ı (HyDE/Multi-Query aşamaları) DeepSeek'e ağ
çağrısı yapar — bu, sistemin geri kalanının aksine air-gapped değildir; bkz.
TECH_DEBT.md.

## Çalıştırma

Tüm sistemi (OCR, sınıflandırma, doğrulama, RAG bağlayıcısı, yönlendirme,
taslak üretimi ve UI) tek bir servis çalıştırır — model tek sefer belleğe
yüklenir ve diğer adımlar aynı süreç içinde onu paylaşır:

```bash
cd services/workflow
../../.venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8080
```

İlk açılışta model yüklenir (birkaç saniye). Ardından tarayıcıda
`http://localhost:8080` adresini açın — evrak yükleme, işlem adımları ve
sonuç (sınıflandırma, eksik bilgiler, yönlendirme, düzenlenebilir taslak)
ekranları buradadır.

Doğrudan API ile de kullanılabilir:

```bash
curl -X POST http://localhost:8080/upload \
  -H "Content-Type: application/json" \
  -d '{
    "schemaVersion":"1.0","requestId":"r1","documentId":"d1",
    "scenarioId":"demo","contentType":"text/plain",
    "content":"Sayın Müdürlüğünüze, ... rica ederim.","source":"citizen_portal"
  }'
# -> {"workflowId": "...", "status": "completed"}

curl http://localhost:8080/result/<workflowId>
```

Contract-uyumlu tek çağrılık uç nokta: `POST /v1/workflows/document`
(`contracts/schemas/document-input.schema.json` → `workflow-result.schema.json`).

### Neden ayrı ayrı Docker container'ları değil de tek süreç?

`services/{ocr,classification,validation,llm,workflow}/Dockerfile` her biri
`contracts/http/manifest.json`'daki bağımsız servisi ayrı ayrı çalıştırabilecek
şekilde yazıldı ve doğru. Ancak bu geliştirme makinesindeki **tek 8GB GPU**,
`classification` + `validation` + `llm`'in üçünün de kendi Jamba2 kopyasını
aynı anda GPU'ya yüklemesine yetmez (3 × ~5.8GB). Bu yüzden
`services/workflow/pipeline.py`, o üç servisin iş mantığını (HTTP üzerinden
değil) doğrudan Python fonksiyonu olarak çağırıp **tek bir paylaşılan model
örneği** kullanır — gerçek modelle, gerçek çıkarımla, sadece süreç sınırı
farklı. Daha büyük/çoklu GPU'lu bir ortamda her servis kendi container'ında,
`compose.yaml`'a eklenecek gerçek image'larla bağımsız da çalıştırılabilir;
bu, mevcut mimarinin bir uzantısıdır, yeniden yazımı değil.

## Test

Her servisin kendi doğrulaması gerçek modelle/gerçek girdilerle interaktif
olarak yapıldı (mock kullanılmadı); ayrıntılar için git log'daki her Faz
commit'inin açıklamasına bakılabilir. Otomatik bir pytest paketi bu görev
kapsamında eklenmedi — Faz 8'in kapsamı doğrulanan davranışı belgelemekti.

## Bilinen sınırlamalar

Bkz. [TECH_DEBT.md](TECH_DEBT.md): RAG'ın kendi DeepSeek bağımlılığı, RAG +
yerel LLM'in aynı GPU'da eşzamanlı VRAM çakışması, ve küçük modelin serbest
metin (taslak/çelişki tespiti) üretimindeki güvenilirlik sınırları.

## Kaynak kod teslimi

Bu depo Apache-2.0 lisansı altındadır ([LICENSE](LICENSE)) —
[docs/teknofest_requirements.md](docs/teknofest_requirements.md)'teki "açık
kaynak paylaşım" gereksinimi. **Doğrulanmadı:** mevcut `origin`
(`github.com:itstexa/coreaigent`) şartnamedeki "Türkiye Açık Kaynak
Platformu" hesabıyla aynı mı — teslimden önce teyit edilmeli.

---

## Contract-first altyapı (orijinal tasarım notları)

Bu depo contract-first bir yerel ortamla başladı — mantıksal servis adları ve
adresleri kalıcıdır:

| Service | Address | Responsibility |
| --- | --- | --- |
| `ocr` | `http://ocr:8080` | document text extraction |
| `classification` | `http://classification:8080` | document type and classification |
| `validation` | `http://validation:8080` | missing information detection |
| `rag` | `http://rag:8080` | regulation/knowledge retrieval |
| `llm` | `http://llm:8080` | structured generation |
| `workflow` | `http://workflow:8080` | draft, routing and final workflow result |

Deterministik mock servisler (`mocks/`) ve kontrat testleri
(`docker compose --profile tests up`) hâlâ mevcut ve şema uyumluluğunu
denetlemek için kullanılabilir; ayrıntılar için
[docs/service-implementation.md](docs/service-implementation.md) ve
[contracts/README.md](contracts/README.md).
