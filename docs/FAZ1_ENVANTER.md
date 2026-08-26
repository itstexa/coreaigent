# Faz 1 — Envanter, Durum Tespiti ve Kapsam

## Mevcut kaynak kod envanteri (Görev 65)

| Servis | Durum | Konum |
|---|---|---|
| `rag` | Olgun, çalışır durumda (offline ingestion, hibrit arama, Hakem Ajan/Critic Agent, post-hoc verification, retention policy, 20+ test) | `mevzuat-rag/` |
| `ocr` | Yok — bu görevde inşa ediliyor | `services/ocr/` |
| `classification` | Yok — bu görevde inşa ediliyor | `services/classification/` |
| `validation` | Yok | `services/validation/` |
| `llm` | Yok (agent orkestrasyonu Faz 5) | `services/llm/` |
| `workflow` | Yok (Faz 6) | `services/workflow/` |

Branch durumu: `main` uzak/yerel; geliştirme `feature/rag-advanced-pipeline`
(RAG işi, dokunulmuyor) ve bu görev için açılan
`feature/autonomous-core-integration` üzerinde ilerliyor.

Contract-first altyapı zaten hazır: `contracts/schemas/*.json` (6 servis için
giriş/çıkış şemaları) ve `contracts/http/manifest.json` (endpoint haritası).
Faz 3-6, bu şemalara birebir uyacak şekilde kodlanıyor.

## Kullanılan modellerin envanteri (Görev 64)

| Model | Durum | Kullanım alanı |
|---|---|---|
| `serda-dev/Jamba2-3B-Turkish` | Yerelde HF cache'de indirilmiş (`~/.cache/huggingface/hub`), henüz inference smoke-test yapılmadı | Faz 4-5 agent runtime (air-gap kararı gereği) |
| RAG embedding modeli | `mevzuat-rag/.env` → `RAG_EMBEDDING_MODEL` üzerinden yapılandırılmış, üretimde | Mevzuat retrieval |
| DeepSeek (`deepseek-v4-flash`) | API key doğrulandı (200 OK) | Yalnızca geliştirme aracı (kod üretimi) — runtime agent'larda kullanılmayacak |

## Jamba2-3B-Turkish durumu (Görev 44)

- Model dosyaları yerel HF cache'de mevcut, indirilmiş.
- `transformers==5.9.0`, `torch==2.12.0` kurulu.
- **Açık:** gerçek bir inference smoke-test henüz koşulmadı (Faz 5'te agent
  geliştirmesiyle birlikte yapılacak — o an gerçek kısıtlar/VRAM ihtiyacı
  netleşir).

## Desteklenecek evrak türleri (Görev 15)

Bkz. [EVRAK_TURLERI.md](EVRAK_TURLERI.md).

## Uçtan uca veri akışı (Görev 60)

`document-input` (OCR girişi: PDF/görsel/metin) → `ocr` (`ocr-result`) →
`classification` (`classification-result`) → `validation`
(`validation-result`, eksik bilgi) → `rag` (`rag-result`, mevzuat kaynakları)
→ `llm` (`llm-response`, taslak+yönlendirme) → `workflow`
(`workflow-result`, birleşik sonuç). Şema sözleşmeleri
`contracts/schemas/` içinde zaten tanımlı; her adımın girdi/çıktısı
`contracts/http/manifest.json` ile sabitlenmiş.

## Çalışan / çalışmayan bileşenler (Görev 61)

- **Çalışıyor:** RAG (`mevzuat-rag`) — indeksleme, hibrit arama, Hakem Ajan,
  DeepSeek üzerinden cevap üretimi (bkz. [TECH_DEBT.md](../TECH_DEBT.md)).
- **Çalışmıyor / henüz yok:** OCR, classification, validation, llm-agent,
  workflow servisleri; UI; uçtan uca entegrasyon. Faz 3-7'nin konusu.
- **Mock altyapı hazır:** `docker compose up --build -d` + kontratlara göre
  deterministik mock servisler zaten çalışır durumda (`mocks/`,
  `docs/service-implementation.md`).
