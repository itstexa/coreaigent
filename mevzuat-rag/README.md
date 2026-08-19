# mevzuat-rag

Türkçe mevzuat (kanun/yönetmelik) metinleri üzerinde çalışan, madde/fıkra/bent
yapısına saygılı, atıf veren (citation) bir RAG (Retrieval-Augmented
Generation) paketi. Başlangıçta [itstexa/coreaigent](https://github.com/itstexa/coreaigent)
(TEKNOFEST 2026, YAZGIT LinguAI) için geliştirildi; oradaki HTTP kontrat
bağımlılığından arındırılıp bağımsız, tekrar kullanılabilir bir paket olarak
buraya çıkarıldı — daha büyük bir mevzuat/hukuk-teknolojisi projesinin ilk
adımı.

## Pipeline

**Ingestion** (değişmeyen):

```
sample_data/legislation/*.md
        │  (ingestion/local_corpus.py — klasörü glob'lar)
        ▼
chunking/legal_structure_parser.py → Madde/Fıkra/Bent ağacı
        │
        ▼
chunking/chunker.py (StructureAwareChunker) → LegislationChunk[] (atıflı, madde/fıkra asla bölünmez)
        │
        ▼
engine.py (RAGEngine.index_chunks) → embedding.py (BAAI/bge-m3) → store.py (Qdrant)
        değişmeyen chunk'lar otomatik atlanır (source_hash karşılaştırması)
```

**Sorgu — `mevzuat_rag/pipeline/`, config'ten açılıp kapatılabilir aşamalar
zinciri** (`Stage` protokolü, `PipelineContext`, `Pipeline` runner —
`pipeline/stage.py` / `context.py` / `runner.py`):

```
[0] Router          → Self-RAG: retrieval gerekli mi?           ⏳ henüz eklenmedi (config: router.enabled)
[1] Query Transform → Multi-Query + HyDE (paralel)                ✅ (multi_query.enabled / hyde.enabled)
[2] Hybrid Retrieve → Dense (bge-m3) + Sparse (BM25) → RRF/weighted ✅ (hybrid.enabled)
[3] Rerank          → cross-encoder (bge-reranker-v2-m3)          ✅ (rerank.enabled, graceful degradation'lı)
[4] Expand          → Parent Document Retrieval                   ✅ (parent_doc.enabled)
[5] Evaluate        → CRAG: context yeterli mi?                   ⏳ henüz eklenmedi (crag.enabled)
[6] Compress        → dedup + extractive/LLM compression          ✅ (compression.enabled, llm_summarize varsayılan kapalı)
[7] Generate        → zorunlu atıflı (citation) cevap              ✅ generate.py (DeepSeek)
```

Tüm bu teknikler golden set'te doğrulandı (Recall@1/3/5=MRR=1.0, hiç kalite
kaybı yok) ve `config/default.yaml`'da artık `enabled: true` — yeni
varsayılan pipeline davranışı. Her teknik önce `enabled: false` ile eklenip
test edildikten sonra tek tek açıldı (bkz. `config/default.yaml`'daki
yorumlar). Özet:

- `hybrid.enabled`: dense (Qdrant) + sparse (BM25, `rank_bm25`, Türkçe
  tokenizasyon + Snowball stemming — `pipeline/tokenize_tr.py`) sonuçları
  RRF (varsayılan) veya ağırlıklı skorla (`hybrid.fusion: weighted`,
  `hybrid.alpha`) birleştirilir.
- `rerank.enabled`: birleşik küme `rerank.top_n`'e cross-encoder ile
  daraltılır — reranker yüklenemezse (ağ/OOM) çökmez, WARNING loglar ve
  hybrid skorlarıyla devam eder.
- `multi_query.enabled`: LLM'den orijinal sorudan `n_queries` farklı
  bakış açılı sorgu istenir (`prompts/multi_query.txt`), hepsi thread pool
  ile paralel embed+retrieve edilir, sonuçlar RRF'e girer. **Maliyet:** her
  sorguda +1 LLM çağrısı, ~2-15s ek gecikme (bkz. NOTES.md). Düşük
  kaynaklı ortamlar için `config/edge.yaml` bunu kapatıyor.
- `hyde.enabled`: yalnızca kısa/muğlak sorgularda (`hyde.trigger_max_tokens`
  altında) tetiklenir — her sorguda değil; LLM'in ürettiği hipotetik cevap
  da bir arama varyantı olarak RRF'e girer.
- Reranker/Multi-Query/HyDE LLM çağrıları da dahil her dış çağrı
  `config.generation.timeout_s` + retry (`retry_attempts`/`retry_backoff_s`)
  ile korunuyor.
- `parent_doc.enabled`: aynı maddeden gelen birden çok kazanan chunk tek
  parent'a (`store.get_chunks_by_madde` ile canlı yeniden kurulan tam madde
  metni) birleşir, en yüksek çocuk skoru korunur; toplam bağlam
  `context_window_tokens * token_budget_fraction`'ı aşarsa en düşük skorlu
  parent'lar düşer.
- `compression.enabled`: (a) embedding cosine benzerliği > `dedup_cosine_threshold`
  olan neredeyse-yinelenen adaylar birleştirilir, (b) hâlâ `token_budget`'ı
  aşıyorsa her aday sorguyla en alakalı cümlelerine indirilir (Türkçe
  tokenizasyon ile terim örtüşmesi), (c) `llm_summarize: true` yapılırsa
  (varsayılan kapalı) son çare olarak LLM özetlemesi devreye girer, atıf
  numaralarını ([1]/[2]) koruyarak.

Detaylı bulgular ve test sonuçları için [NOTES.md](NOTES.md)'ye bakın.

## Kurulum

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # DEEPSEEK_API_KEY'i doldurun
```

## Konfigürasyon (profiller)

Ayarlar üç katmanlı: **env var > `config/{profil}.yaml` > `config/default.yaml`**.
Profil `RAG_PROFILE` env var ile seçilir (varsayılan `default`):

| Profil | Ne için |
|---|---|
| `dev_gpu` | Geliştirme makinesi, CUDA, büyük batch |
| `edge` | Düşük VRAM cihaz — küçük batch/top_k, ağır aşamalar kapalı |
| `cpu_only` | CPU-only sunucu, GPU varsayımı yok |
| `prod` | Remote Qdrant zorunlu, sıkı retry/timeout |

Cihaz seçimi merkezi: `device.py:resolve_device()` — sırayla `env DEVICE` →
CUDA → MPS → CPU. Kodda hiçbir yerde `"cuda"`/`"cpu"` literali yok.

## Kullanım

```bash
# 1. Mevzuatı indeksle (sample_data/legislation/*.md içeriğini)
python -m mevzuat_rag.ingest_pipeline

# 2. Sadece retrieval (LLM/DeepSeek gerekmez)
python -c "
from mevzuat_rag.engine import RAGEngine
engine = RAGEngine()
for hit in engine.retrieve('Dilekçede hangi bilgiler zorunludur?'):
    print(hit.score, hit.chunk.citation)
"

# 3. Atıflı, DeepSeek ile üretilmiş cevap (DEEPSEEK_API_KEY gerekir)
python -m mevzuat_rag.ask "Dilekçede hangi bilgiler zorunludur?"

# 4. Retrieval değerlendirmesi (Recall@K / MRR)
python -m mevzuat_rag.eval.run_retrieval_eval

# 5. Testler (generation testi DEEPSEEK_API_KEY yoksa otomatik atlanır)
python -m pytest tests/ -v
```

## Yeni kaynak dosyası eklemek

`sample_data/legislation/` altına yeni bir `.md` dosyası bırakıp
`python -m mevzuat_rag.ingest_pipeline` çalıştırmanız yeterli — hiçbir kod
değişikliği gerekmez. Format:

```
KANUN_NO: 3071
KANUN_ADI: Dilekçe Hakkının Kullanılmasına Dair Kanun
KAYNAK_URL: https://www.mevzuat.gov.tr/...

MADDE 1- Madde metni...
MADDE 2- (1) Fıkra metni...
(2) İkinci fıkra...
a) Bent...
```

Sürekli izleme için: `python -m mevzuat_rag.ingest_pipeline --watch` —
klasörü periyodik kontrol eder, yeni/değişen dosyayı otomatik indeksler;
değişmeyen dosyalar yeniden embed edilmez.

## Mimari kararlar

- **Embedding + vektör depolama:** `sentence-transformers` ile `BAAI/bge-m3`,
  dense-only, cosine benzerlik, Qdrant — insangram projesindeki
  `src/rag/embed.py` ile aynı, kanıtlanmış desen. Sparse/hybrid/reranker yok.
- **Generation:** DeepSeek'in genel (public) API'sinde embedding endpoint'i
  yok — sadece chat completion var. Bu yüzden embedding BGE-M3'te kalıyor,
  DeepSeek yalnızca son adımda (retrieve edilen chunk'lardan atıflı cevap
  üretme) kullanılıyor.
- **Chunking:** Madde/Fıkra/Bent yapısına saygılı; bir fıkra/bent asla
  ortadan bölünmez.

## Bilinen sınırlar

- Sadece 2 gerçek, doğrulanmış mevzuat belgesi var (bkz.
  `sample_data/legislation/README.md`) — geliştirme ortamından
  `mevzuat.gov.tr`/`resmigazete.gov.tr`'ye ağ erişimi kurulamadığı için
  külliyat genişletilemedi.
- `ingestion/mevzuat_gov_tr.py` ve `ingestion/resmi_gazete.py`, gerçek
  internet erişimi olan bir ortamda doğrulanmadan production ingestion için
  kullanılmamalı.
