# Mimari

## Genel akış

```
Evrak (metin/PDF/görsel)
        │
        ▼
   ┌─────────┐   document-input
   │   OCR   │──────────────────────┐
   └─────────┘                      │ ocr-result
        │                           ▼
        │                   ┌───────────────┐
        │                   │ Classification │  documentType, extractedFields
        │                   └───────────────┘        (source_text dahil)
        │                           │ classification-result
        │                           ▼
        │                   ┌───────────────┐
        │                   │   Validation   │  missingFields, conflicts
        │                   └───────────────┘
        │                           │ validation-result
        │                           ▼
        │                   ┌───────────────┐        ┌────────────────┐
        │                   │      RAG       │───────▶│ mevzuat-rag/   │
        │                   │  (connector)   │  query │ (kara kutu)    │
        │                   └───────────────┘◀────────┤ RAGEngine      │
        │                           │ rag-result       └────────────────┘
        │                           ▼
        │                   ┌───────────────┐
        │                   │      LLM       │  department, draft
        │                   │ (route/draft/  │
        │                   │  summarize)    │
        │                   └───────────────┘
        │                           │ llm-response
        ▼                           ▼
   ┌─────────────────────────────────────┐
   │              Workflow                │  workflow-result
   │  (orkestratör + UI, tek FastAPI app) │
   └─────────────────────────────────────┘
```

`contracts/schemas/*.json` her okun giriş/çıkış şemasını, `contracts/http/manifest.json`
ise mantıksal servis-endpoint haritasını tanımlar. Her servisin `main.py`'si
bu şemalara birebir uyar (`additionalProperties:false` ile doğrulanabilir).

## Servisler

| Servis | Sorumluluk | Runtime bağımlılık |
| --- | --- | --- |
| `services/ocr` | PDF metin çıkarma (pypdf) + taranmış belge OCR (Tesseract, `tur`) | Yok (CPU) |
| `services/classification` | Few-shot ile evrak türü tespiti (yerel Jamba2) | Jamba2-3B-Turkish |
| `services/validation` | Zorunlu alan eksikliği (regex + Jamba2 few-shot) + çelişki tespiti | Jamba2-3B-Turkish |
| `services/llm` | Birim yönlendirme, taslak/özet üretimi, RAG bağlayıcısı | Jamba2-3B-Turkish |
| `services/workflow` | Orkestratör (pipeline) + kullanıcı API'leri + statik UI | Jamba2-3B-Turkish (paylaşılan) |
| `mevzuat-rag/` | Mevzuat retrieval (kara kutu, dokunulmadı) | Kendi embedding modeli + DeepSeek |

Her servisin kendi `Dockerfile` + `requirements.txt`'i vardır ve
`contracts/http/manifest.json`'daki bağımsız HTTP servisi olarak
paketlenebilir. **Geliştirme/demo ortamında** ise `services/workflow`, diğer
üç Jamba2-bağımlı servisin (`classification`, `validation`, `llm`) Python
modüllerini doğrudan import edip **tek bir paylaşılan model örneğiyle**
çalıştırır — sebep, sonraki bölümde.

## Neden air-gapped ve neden tek-süreç paylaşımlı model?

TEKNOFEST şartnamesi (`docs/teknofest_requirements.md`) "%100 Kapalı Ağ"ı ana
farklılaştırıcı olarak konumlandırıyor. Bu yüzden:

1. **Runtime'da hiçbir servis DeepSeek'e (veya başka bir cloud API'ye) çağrı
   atmaz.** Sınıflandırma, doğrulama, yönlendirme, taslak üretimi tamamen
   yerel `Jamba2-3B-Turkish` ile yapılır (`model_loader.py`, her serviste
   aynı desen: `HF_HUB_OFFLINE=1`, `local_files_only=True`, pinlenmiş
   revizyon). DeepSeek sadece bu kod tabanını üretirken (geliştirme aracı
   olarak) kullanıldı.
2. **8GB VRAM sınırı.** Faz 5'te üç servisin (classification, validation,
   llm) kendi Jamba2 kopyasını aynı anda ayrı container'larda GPU'ya
   yüklemeye çalışmasının gerçekçi olmadığı görüldü (3 × ~5.8GB > 8GB).
   `services/workflow/pipeline.py` bu üçünün iş mantığını (contract'lara
   uyan aynı fonksiyonları) tek süreçte, tek model örneğiyle çağırır — HTTP
   üzerinden değil, doğrudan Python import ile. Bu bir mock değil: aynı
   gerçek model, aynı gerçek çıkarım, sadece süreç/ağ sınırı yok.
3. **RAG istisnası.** `mevzuat-rag/` "kutsal kutu" olarak korundu — hiçbir iç
   dosyası değiştirilmedi. Kendi embedding modeli (`BAAI/bge-m3`) de GPU
   istediğinden, `services/llm/rag_connector.py` onu ayrı bir `subprocess`
   içinde çağırır (kendi CUDA context'i) — Jamba2 ile aynı GPU'da
   çakışmasını (CUDA OOM) önlemek için. RAG'ın kendi pipeline'ı
   (HyDE/Multi-Query) DeepSeek'e ağ çağrısı yapar; bu tek bilinen
   air-gap istisnasıdır ve RAG'ın iç mimarisine ait olduğu için kapsamımızın
   dışındadır (bkz. TECH_DEBT.md).

## Hata toleransı

`pipeline.py`, adımları iki sınıfa ayırır:

- **Kritik:** OCR hiç metin üretemezse (`corrupt_pdf`, boş belge vb.) pipeline
  orada durur, `status: "rejected"` döner, kalan adımlar `"skipped"` olarak
  işaretlenir — yanlış/uydurma bir sonuç üretilmez.
- **Kritik değil:** RAG kaynak bulamazsa veya validation/llm bir adımda
  istisna fırlatırsa, o adım `"failed"`/`"skipped"` olarak loglanır ama
  pipeline boş/varsayılan değerlerle devam eder; nihai `status` buna göre
  `manual_review`'a düşebilir ama sistem çökmez.

Her adım `workflowId`'yi correlation ID olarak taşıyan structured JSON log
üretir (`{timestamp, service, correlationId/workflowId, ...}`).

## Bilinen model sınırlamaları

`Jamba2-3B-Turkish`, kapalı-uçlu görevlerde (sınıflandırma, evet/hayır alan
kontrolü, birim eşleştirme — few-shot ile) güvenilir sonuç veriyor. Açık uçlu
üretimde (çelişki açıklaması, uzun taslak metni) bazen tutarsız/konudan sapan
içerik üretebiliyor; bu durumlar kod içinde yorumlarla işaretlendi ve
kullanıcıya "insan gözden geçirmesi gereken taslak" olarak sunuluyor —
otomatik gönderim için değil. Ayrıntılar için `services/llm/draft.py` ve
`services/validation/llm_checks.py` içindeki notlara ve TECH_DEBT.md'ye
bakın.
