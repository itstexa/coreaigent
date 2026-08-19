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
[1] Query Transform → Multi-Query + HyDE (paralel)                ⏳ henüz eklenmedi (multi_query / hyde)
[2] Hybrid Retrieve → Dense (bge-m3) + Sparse (BM25) → RRF        ✅ dense var, BM25/RRF ⏳ (hybrid.enabled)
[3] Rerank          → cross-encoder, top_k → top_n                ⏳ henüz eklenmedi (rerank.enabled)
[4] Expand          → Parent Document Retrieval                   ⏳ henüz eklenmedi (parent_doc.enabled)
[5] Evaluate        → CRAG: context yeterli mi?                   ⏳ henüz eklenmedi (crag.enabled)
[6] Compress        → dedup + extractive/LLM compression          ⏳ henüz eklenmedi (compression.enabled)
[7] Generate        → zorunlu atıflı (citation) cevap              ✅ generate.py (DeepSeek)
```

Şu an `RAGEngine.retrieve()`/`.ask()`, `[2] Hybrid Retrieve` (dense-only) ve
`[7] Generate`'i çalıştıran iki aşamalı bir `Pipeline` kurup çağırıyor —
davranış, bu mimari genişlemeden önceki dense-only akışla birebir aynı. Her
teknik önce `config/default.yaml`'da `enabled: false` ile eklenip test
edildikten sonra tek tek açılacak (bkz. `config/default.yaml`'daki yorumlar).

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
