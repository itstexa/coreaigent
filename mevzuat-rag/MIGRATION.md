# MIGRATION — mevcut index'ten yeni pipeline'a geçiş

Bu belge, RAG upgrade'inden (Checkpoint 1-5, bkz. NOTES.md) önce kurulmuş
bir index'i olan biri için: aşağıdaki değişikliklerden hangisi **index'i
yeniden kurmayı gerektirir**, hangisi gerektirmez.

## Yeniden ingest gerektirmeyen değişiklikler

Bunlar mevcut Qdrant koleksiyonunu bozmaz, sadece sorgu zamanında davranışı
değiştirir:

- `hybrid.enabled`, `rerank.enabled`, `multi_query.enabled`, `hyde.enabled`,
  `parent_doc.enabled`, `compression.enabled`, `router.enabled`,
  `crag.enabled` — hepsi retrieval/generation zamanında uygulanır, chunk'ların
  kendisini değiştirmez.
- `retrieval.top_k`, `rerank.top_n`, `hybrid.*`, `crag.*`, `compression.*`
  parametreleri.
- `RAG_PROFILE` değiştirmek (`dev_gpu`/`edge`/`cpu_only`/`prod`).

## Yeniden ingest GEREKTİREN değişiklikler

Bunlar chunk'ların kendisini veya vektör uzayını değiştirir — eski
koleksiyonla yeni ayarlar **uyumsuz**, `QdrantStore` bunu fail-fast ile
tespit eder (`IndexMetadataMismatch`, bkz. `store.py`):

1. **`embedding.model` değişti** (ör. `BAAI/bge-m3` → başka bir model):
   Vektör uzayı tamamen farklı — eski chunk'ların vektörleriyle yeni
   sorgu vektörleri karşılaştırılamaz. `index_meta_{collection}.json`'daki
   `embedding_model` kaydı eşleşmezse `QdrantStore` başlangıçta hata verir.
   **Çözüm:** yeni bir `qdrant.collection` adı seçin (ör.
   `mevzuat_chunks_v2`) ve `ingest_pipeline.py`'yi yeniden çalıştırın —
   eskisini silmeyin, geçiş bitene kadar paralel tutun.
2. **`embedding.dim` değişti:** Qdrant'ın kendi koleksiyon config'i
   (`vectors.size`) ile karşılaştırılır, uyuşmazlıkta anında hata. Aynı
   çözüm: yeni koleksiyon adı + yeniden ingest.
3. **`chunking.max_tokens` / `chunking.overlap_tokens` değişti:**
   Chunk sınırları değişir, chunk id'leri de değişir (`chunker.py`'deki
   `uuid.uuid5` deterministik ID'ler chunk içeriğine bağlı). Eski chunk'lar
   Qdrant'ta kalır (silinmez), yeni chunk'lar eklenir — corpus çift
   birikir. **Çözüm:** `python -m mevzuat_rag.ingest_pipeline` öncesi
   koleksiyonu temizleyin (`QdrantStore.delete_by_kanun_no` her kanun için,
   veya koleksiyonu tamamen silip yeniden oluşturun).
4. **Chunker/parser mantığı değişti** (ör. `legal_structure_parser.py`'de
   bir regex düzeltmesi): Aynı sebep — chunk id'leri ve içerikleri değişir,
   yeniden ingest gerekir.

## Adım adım geçiş (embedding modeli değişikliği örneği)

```bash
# 1. Yeni ayarları config/default.yaml veya bir profile dosyasında yapın
#    (embedding.model, embedding.dim).
# 2. Yeni bir koleksiyon adı seçin:
export QDRANT_COLLECTION_MEVZUAT=mevzuat_chunks_v2
# 3. Yeniden ingest edin (eski koleksiyona dokunulmaz):
python -m mevzuat_rag.ingest_pipeline
# 4. Golden set ile doğrulayın:
python -m mevzuat_rag.eval.run_retrieval_eval
# 5. Sonuçlar tatmin ediciyse, prod'da QDRANT_COLLECTION_MEVZUAT'ı
#    kalıcı olarak günceleyin; eski koleksiyonu silin.
```

## `index_meta_{collection}.json`

Her koleksiyon için `{DATA_DIR}/index_meta_{collection}.json` dosyası
`{embedding_model, embedding_dim, collection}` tutar — ilk oluşturmada
yazılır, sonraki her açılışta karşılaştırılır. Bu dosyayı elle silmeyin;
silerseniz sistem eski index'i farklı bir modelle sessizce yanlış
yorumlayabilir (yalnızca Qdrant'ın kendi `vectors.size` kontrolü, boyut aynı
ama model farklıysa yakalayamaz).
