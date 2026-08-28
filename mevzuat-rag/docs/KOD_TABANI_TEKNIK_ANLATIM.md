# mevzuat-rag — Kod Tabanı Teknik Anlatımı

Bu belge, `mevzuat-rag` paketinin kaynak kodunun satır satır okunmasıyla üretildi. Amaç övmek ya da eleştirmek değil, sistemin **gerçekte** nasıl çalıştığını kanıtla anlatmaktır. Her teknik iddianın yanında `dosya:satır` referansı vardır. Belgelenen (docstring/config) davranışla kodun gerçekte yaptığı farklıysa, ikisi ayrı ayrı belirtilmiştir. Doğrulanamayan hiçbir iddia yoktur — böyle bir nokta varsa "bu kısım doğrulanamadı" diye ayrıca işaretlenmiştir.

---

## 0) Çağrı yüzeyi

`mevzuat-rag`, bağımsız bir HTTP servisi **değildir**. `RAGEngine` sınıfı (`mevzuat_rag/engine.py:40`) bir kütüphane facade'ıdır; `retrieve()` ve `ask()` metotlarıyla doğrudan Python'dan çağrılır (`mevzuat_rag/engine.py:188`, `:197`). `repl.py`'nin kendi docstring'i bunu açıkça söylüyor: *"This package is deliberately a library/CLI, not an HTTP server (see README)"* (`mevzuat_rag/repl.py:3-5`).

Üç somut çağrı yolu var:

1. **CLI — tek soru.** `python -m mevzuat_rag.ask "soru"` — `mevzuat_rag/ask.py:17-24`, `RAGConfig.from_env()` ile bir `RAGEngine` kurar, `engine.ask(query, actor=f"cli:{getpass.getuser()}")` çağırır.
2. **CLI — REPL.** `python -m mevzuat_rag.repl` (`make serve`) — `mevzuat_rag/repl.py:15-30`, stdin'den satır satır soru okur, aynı `engine.ask()`'i çağırır.
3. **CoreAIgent'ın kendi servisleri — subprocess köprüsü.** `services/llm/rag_connector.py` dosyasındaki `get_rag_context()` fonksiyonu (`services/llm/rag_connector.py:51-81`), mevzuat-rag'i **Python import'uyla değil, ayrı bir subprocess olarak** çalıştırıyor: `subprocess.run([PYTHON_BIN, "-c", _RETRIEVE_SCRIPT, query, str(top_k), actor], cwd=RAG_DIR, ...)` (`services/llm/rag_connector.py:56-63`). `_RETRIEVE_SCRIPT` (satır 27-48), stdin'de gömülü bir Python betiği — `RAGEngine(RAGConfig.from_env())` kurup `engine.retrieve(...)` çağırıyor, sonucu tek satır JSON olarak stdout'a basıyor. Bu, `services/workflow/pipeline.py:145` ve `services/llm/main.py:98`'de `rag_connector.get_rag_context(text[:500], actor=actor)` şeklinde çağrılıyor.

Bu üçüncü yol önemli bir mimari ayrıntı: coreaigent'ın ana süreciyle mevzuat-rag arasında **doğrudan Python import bağı yok** — süreç sınırı, ortam değişkeni dosyası (`RAG_DIR/.env`, satır 14-25) ve stdout üzerinden JSON ile kurulan bir sınır var. `get_rag_context` yalnızca `retrieve()`'i çağırıyor (satır 37) — **`ask()`'i, yani DeepSeek-üretimli cevabı hiç çağırmıyor**; coreaigent tarafı yalnızca ham retrieval sonuçlarını (`context_snippets`) alıp kendi LLM akışına context olarak veriyor (satır 80-81). Yani mevzuat-rag'in kendi üretim/CRAG/Hakem-Ajan katmanı bu entegrasyon yolunda **hiç devreye girmiyor** — coreaigent yalnızca retrieval bacağını kullanıyor.

`get_rag_context`'in `except Exception` blokları (satır 64-66, 76-78) subprocess başlatma veya çıktı ayrıştırma hatasında sessizce boş sonuç (`{"results": [], "context_snippets": []}`) döndürüyor, hatayı yalnızca `logger.error` ile loglayıp yutuyor — çağıran taraf (workflow/pipeline.py, llm/main.py) bir hatanın olup olmadığını ayırt edemiyor.

`actor` parametresi (`engine.py:207-212`'deki docstring'in vurguladığı gibi) hesap verebilirlik zincirinin tek bağlantı noktası — CLI'de OS kullanıcı adı (`ask.py:24`), subprocess köprüsünde ise çağıran servisten geçirilen serbest metin (`services/llm/main.py:98`, `rag_connector.py:34`).

---

## 1) Veri yolculuğu (ingestion)

Somut örnek: `sample_data/legislation/3071_dilekce_kanunu.md` — 3071 sayılı Dilekçe Hakkının Kullanılmasına Dair Kanun, 11 madde.

**1. Yükleme.** `ingest_pipeline.run()` (`mevzuat_rag/ingest_pipeline.py:72`) varsayılan olarak `load_fixtures()`'ı çağırır (satır 90, 34). Bu fonksiyon (`mevzuat_rag/ingestion/local_corpus.py:78-81`) `sample_data/legislation/*.md` dosyalarını glob'lar, her birini `_parse_fixture()` ile (satır 26-43) `KANUN_NO:`/`KANUN_ADI:`/`KAYNAK_URL:` başlık satırlarını ayrıştırıp bir `RawDocument`'e çevirir. 3071 için: `kanun_no="3071"`, `kanun_adi="Dilekçe Hakkının Kullanılmasına Dair Kanun"`, `url="https://www.mevzuat.gov.tr/..."`, `raw_text` = MADDE 1'den itibaren tüm gövde.

Alternatif kaynak: `--source pdf --pdf-dir <dizin>` verilirse `load_pdf_corpus()` (`mevzuat_rag/ingestion/pdf_corpus.py:275-333`) devreye girer — `multiprocessing.get_context("spawn")` ile paralel worker'lar (satır 302-304), her worker `_process_one()` içinde (satır 252-272) `extract_pdf_text()` (satır 213-249, pypdf + pdfplumber, tablo-farkında) çağırıp **hemen ardından `redact_pii(raw_text)`** uygular (satır 265). Checkpoint dosyası (`_load_checkpoint`/`_append_checkpoint`, satır 189-210) boyut+mtime parmak izine göre değişmemiş dosyaları atlar.

**Kritik ayrım — PII redaksiyonu yalnızca PDF yolunda çalışıyor.** `redact_pii` çağrısının kod tabanındaki tek yeri `pdf_corpus.py:265`'tir (doğrulama: `grep -rn "redact_pii"` tüm pakette yalnızca bu satırı ve `pii.py`'deki tanımı buluyor). `local_corpus.py`'deki `_parse_fixture()`/`load_fixtures()`/`load_offline_docs()` (satır 26-81) hiçbir yerde `redact_pii`'yi çağırmıyor. Yani `pii.py`'nin modül docstring'indeki *"kimlik/iletişim bilgilerini LLM'e/vektör deposuna ulaşmadan önce maskeler"* (`mevzuat_rag/pii.py:1-2`) ifadesi, yalnızca `--source pdf` yolu için doğru — 3071 örneğinin geçtiği `--source local` (varsayılan) yolunda PII redaksiyonu **hiç çalışmaz**. (Bu örnek belgede zaten kişisel veri yok — README bunu açıkça belirtiyor, `sample_data/legislation/README.md:3-4` — ama mimari olarak yerel/offline yoldan girecek herhangi bir belge redaksiyondan geçmeden indekslenir.)

**2. Ayrıştırma (parse).** `parse_legislation_text(raw_text, kanun_no, kanun_adi, kaynak_url)` (`mevzuat_rag/chunking/legal_structure_parser.py:90-152`) satır satır gezer: `MADDE_RE` (satır 20) her "MADDE N-" satırını yeni bir `MaddeNode` açar; `FIKRA_RE` (satır 21) "(N)" ile başlayan satırları yeni `FikraNode`; `BENT_RE` (satır 22) "a)" gibi tek harf+parantez satırlarını bent olarak ayırır. 3071 Madde 6 için: madde gövdesi tek bir fıkra (fıkra numarası yok → `current_fikra = FikraNode(fikra_no=1, ...)`, satır 137-140), üç bent (a, b, c). `_infer_mevzuat_turu("Dilekçe Hakkının Kullanılmasına Dair Kanun")` (satır 51-59) hiçbir `_MEVZUAT_TURU_PATTERNS` deseniyle eşleşmediği için varsayılan `"kanun"` döner. `DURUM_RE` (satır 30) 3071'de hiç tetiklenmez (belgede "mülga"/"değişik" işaretli madde yok) — tüm maddeler `durum="yürürlükte"` kalır. `_looks_like_table_line` (satır 82-87) da tetiklenmez — 3071'de tablo yok.

**3. Chunklama.** `StructureAwareChunker.chunk(doc)` (`mevzuat_rag/chunking/chunker.py:37-110`) her madde için fıkraları `max_tokens` (varsayılan 768, `config/default.yaml:37`) sınırına göre buffer'a toplar; buffer dolunca `flush()` (satır 45-76) bir `LegislationChunk` üretir. Madde 6 tek fıkra + üç bent olduğundan (toplam ~150 karakter, `_estimate_tokens` chars/4 sezgisiyle ~40 token, `mevzuat_rag/token_estimate.py:9-10`) 768'i asla aşmaz → tek chunk olarak flush edilir. Chunk metni `normalize_text(..., profile="embedding")` (`chunker.py:49`, `:79`) ile normalize edilir — Türkçe tırnak/whitespace/heceleme birleştirme (`mevzuat_rag/text_norm.py:97-112`). `chunk_id`, `uuid.uuid5(NAMESPACE_URL, f"{kanun_no}:{madde_no}:{buffer_first_fikra}:{len(chunks)}")` ile deterministik üretilir (satır 65) — aynı girdi her zaman aynı id'yi verir, bu da `index_chunks`'ın "değişmemiş chunk'ı atla" mantığının temelidir.

**Belgelenen ama uygulanmayan davranış: `overlap_tokens`.** `StructureAwareChunker.__init__(self, max_tokens=768, overlap_tokens=80)` (`chunker.py:33-35`) parametreyi alıp `self.overlap_tokens`'a atıyor, ama `chunk()` metodunun geri kalanında (satır 37-110) bu alan **bir daha hiç okunmuyor**. `config/default.yaml:38`'deki `overlap_tokens: 80  # ~%15` yorumu ve `RAGConfig.chunk_overlap_tokens` alanı (`config.py:226`, `:292`) ta `ingest_pipeline.py:97`'ye kadar akıyor (`StructureAwareChunker(..., overlap_tokens=engine.config.chunk_overlap_tokens)`) ve orada ölü bir parametre olarak son buluyor. Yani **sistemde hiçbir sliding-window chunk overlap yok** — chunker'ın kendi docstring'i zaten bunu bir invariant olarak açıklıyor (*"a chunk never splits a fıkra/bent in half"*, `chunker.py:3-7`) ve pratikte fıkra/bent sınırları zaten örtüşmeyi engellediği için `overlap_tokens`'ın davranışsal bir karşılığı hiç yazılmamış — config'teki değer kullanıcıya "chunk'lar arası %15 örtüşme var" izlenimi verir ama gerçek davranış budur.

**4. Embedding.** `RAGEngine.index_chunks(chunks)` (`engine.py:84-156`) önce `store.existing_source_hashes(...)` ile (satır 109) hangi chunk id'lerinin zaten aynı `source_hash` ile indekste olduğunu sorar; yalnızca değişenler `to_embed`'e girer (satır 110). Değişenler `config.embedding.batch_size` (varsayılan 32, `config.py:189`) büyüklüğünde partiler halinde `embed_texts_with_config(model, [chunk.text...], config=...)` ile embed edilir (satır 123-127, gerçek çağrı `mevzuat_rag/embedding.py:233-244` → `_embed_texts_with_config`, satır 162-230). Model: `BAAI/bge-m3`, `sentence_transformers.SentenceTransformer.encode(..., normalize_embeddings=True)` (`embedding.py:177-181`). Batch bazlı OOM'da `batch_size` yarıya iner (satır 183-190, `config.embedding.oom_retry`); geçici ağ hatalarında exponential backoff retry (satır 193-204, `max_retries=2`). Batch'in tamamı kalıcı hata verirse, `engine.py:138-151` her chunk'ı **tek tek** yeniden dener — başarısız olanlar `failed[]` listesine düşer, geri kalan ingest akışını bloklamaz.

**5. İndeksleme.** `store.upsert_chunks(batch, vectors)` (`engine.py:128` → `store.py:145-178`) her chunk için hem dense (`"dense"` adlı named vector, BGE-M3 cosine) hem sparse (`"bm25"` adlı named vector, `text_to_sparse_vector(chunk.text)`, `store.py:157`) vektörü tek bir Qdrant `PointStruct`'a yazar. Payload'a `indexed_at` (UTC ISO-8601, satır 151, 170) — bu alan §4'teki retention mekanizmasının tek çapası. `QdrantStore.__init__` (`store.py:54-73`) her açılışta `_check_index_metadata()` çağırır: koleksiyon farklı embedding modeli/boyut/metin-normalizasyon versiyonuyla kurulmuşsa `IndexMetadataMismatch` fırlatıp fail-fast yapar (satır 84-124) — sessizce yanlış-boyutlu sonuç dönmek yerine.

3071'in 11 maddesi bu döngüden geçince toplam 11 chunk (bentli Madde 6 dahil tek chunk, çünkü bentler tek fıkra buffer'ında birleşiyor) Qdrant'ın `mevzuat_chunks` koleksiyonuna yazılır; `ingest_pipeline.run()` sonunda `engine.bm25_index.invalidate()` çağrılır (satır 172) ama bu artık **no-op**'tur (bkz. §3, BM25Index).

---

## 2) Sorgu yolculuğu

Örnek soru: *"Hangi dilekçeler incelenemez?"* — `citation_expansion.py`'nin docstring'inde de somut örnek olarak geçiyor (`mevzuat_rag/pipeline/stages/citation_expansion.py:8-12`).

`RAGEngine.ask(query, actor=...)` (`engine.py:197-235`) çağrılır → `self._run(query, top_k, want_answer=True)` (satır 217, 183-186) → `_build_pipeline(want_answer=True)` (satır 158-181) bir `Pipeline` (`pipeline/runner.py:14-38`) kurar ve stage'leri sırayla çalıştırır. `default.yaml`'daki gerçek profil (`config/default.yaml:66-141`) şu stage'leri **açık** bırakıyor: router, hybrid, rerank, multi_query, hyde, parent_doc, compression, crag, post_hoc_verify — yalnızca `citation_expansion` ve `semantic_cache` **kapalı** (satır 108-109, 128-129; gerekçe: DeepSeek key'iyle uçtan uca henüz doğrulanmamış).

**[0] Router.** `RouterStage` (`pipeline/stages/router.py:73-114`) DeepSeek'e (`deepseek-chat`, `temperature=0.0`) sorunun RETRIEVE/ANSWER_DIRECTLY/CLARIFY olduğunu sorar (satır 79-93). "Hangi dilekçeler incelenemez?" mevzuata dair olduğundan RETRIEVE döner, pipeline devam eder. Router hata verirse (ağ, geçersiz JSON) güvenlik kuralı gereği **her zaman RETRIEVE**'e düşer (satır 98-100) — sistem promptu da aynı kuralı zaten talimatlandırıyor (satır 36-38).

**[1] Multi-Query + HyDE.** `MultiQueryStage` (`pipeline/stages/multi_query.py:39-73`) `prompts/multi_query.txt` şablonunu DeepSeek'e (`temperature=0.7`, `n_queries=4`) vererek 4 farklı açıdan sorgu üretir (satır 53-68); JSON parse başarısızsa sessizce `[]`'e düşer (satır 69-71), retrieval bozulmaz. `HyDEStage` (`pipeline/stages/hyde.py:37-64`) yalnızca sorgu `hyde.trigger_max_tokens=12` token'ın **altındaysa** tetiklenir (satır 39-40) — "Hangi dilekçeler incelenemez?" ~9 karakter/4≈2 token olduğundan tetiklenir; DeepSeek'ten kısa bir hipotetik cevap ister (`temperature=0.3`, satır 45-55).

**[2] Hybrid Retrieve.** `HybridRetrieveStage` (`pipeline/stages/hybrid_retrieve.py:42-139`) tüm varyantları (orijinal + 4 multi-query + 1 hyde = 6 metin) `ThreadPoolExecutor(max_workers=min(8,...))` ile paralel embed edip (satır 76-89) her biri için `engine.store.search(vector, top_k=dense_top_k=20)` çağırır (satır 91-100). Aynı anda `engine.bm25_index.search(ctx.original_query, top_k=20, store=engine.store)` (satır 114) — bu artık Qdrant'ın kendi sparse index'ine gidiyor (bkz. §3). Tüm sıralı id listeleri `reciprocal_rank_fusion` (`pipeline/fusion.py:8-14`, varsayılan `rrf_k=60`) ile birleştirilir. Rerank açık olduğu için (`config.rerank.enabled=True`) burada `ctx.top_k`'ya kesilmez (satır 136-137) — tüm füzyon sonucu Rerank'e gider.

**[3] Rerank.** `RerankStage` (`pipeline/stages/rerank.py:72-114`) `BAAI/bge-reranker-v2-m3` cross-encoder ile her (sorgu, aday metni) çiftini skorlar (satır 84-86). `min_score=0.05` altındakiler elenir (satır 98); `adaptive_cutoff=False` (varsayılan) olduğundan sabit `top_n=5`'e kesilir (satır 113). Reranker yüklenemezse crash etmez, WARNING loglar, hybrid sırasıyla `ctx.top_k`'ya keser (satır 87-90).

**[4] Parent Document Retrieval.** `ParentDocStage` (`pipeline/stages/parent_doc.py:29-97`) kazanan 5 chunk'ı `(kanun_no, madde_no)`'ya göre gruplar (satır 43-50), her grup için `store.get_chunks_by_madde(kanun_no, madde_no)` (`store.py:191-218`) ile o maddenin **tüm** kardeş chunk'larını (canlı, ayrı bir "parent metni" deposu olmadan) çekip birleştirir (satır 53-70). Madde 6 kazandıysa, bu adımda Madde 6'nın tam metni (a/b/c bentleri dahil) tek bir `parent_expanded` candidate olur. Bütçe: `context_window_tokens(8000) * token_budget_fraction(0.6) = 4800` token; sığmayan en düşük skorlu parent'lar düşer (satır 86-94).

**[9] Citation Expansion — varsayılanda KAPALI.** `CitationExpansionStage` (`citation_expansion.py:31-114`) `default.yaml:108`'de `enabled: false`. Açık olsaydı, Madde 6'nın metnindeki "4. maddede gösterilen şartlar" ifadesini `extract_same_kanun_refs` (`pipeline/citation_ref.py:39-49`, `_MADDE_REF_RE`, satır 21-24) ile yakalayıp Madde 4'ü de context'e ekleyecekti — docstring'in tam olarak anlattığı senaryo bu (satır 8-12). Bu örnekte stage kapalı olduğu için **Madde 4, yalnızca [2] Hybrid Retrieve kendi başına anlamsal olarak bulursa** context'e girer; metnin kendi atıfını takip eden bir mekanizma bu sorguda çalışmaz.

**[5] CRAG.** `CRAGStage` (`pipeline/stages/crag.py:89-207`) DeepSeek'e mevcut adayların soruyu SUFFICIENT/PARTIAL/INSUFFICIENT cevapladığını sorar (satır 95-120). Madde 6 (+ muhtemelen Madde 4) getirilmişse SUFFICIENT dönüp loop biter (satır 187-188). Evaluator LLM çağrısı hata verirse **fail-open**: `ctx.crag_evaluator_failed=True` set edilip SUFFICIENT'e düşülür (satır 116-120) — bu bayrak sessiz kalmaz, aşağıda GenerateStage'de kullanıcıya görünür bir uyarıya dönüşür.

**[6] Compression.** `CompressionStage` (`compression.py:79-110`) adayları embed edip kosinüs benzerliği `0.95`'i aşanları dedup eder (satır 93, `_dedup`, satır 41-50); toplam `token_budget=2000`'i aşıyorsa Türkçe-tokenize edilmiş sorgu terimleriyle örtüşen cümleleri seçen extractive özet uygular (satır 99-105, `_extractive_select`, satır 57-76). `llm_summarize=False` (varsayılan) olduğundan LLM özetleme bu örnekte devreye girmez.

**[7] Generate.** `GenerateStage` (`generate.py:12-52`) → `generation.generate_answer()` (`generation.py:63-104`). `_build_context()` (satır 53-60) her chunk'ı `[1] (citation)\n<KAYNAK_METNI>...</KAYNAK_METNI>` biçiminde sarar (`wrap_source`, `prompt_safety.py:35-39`) — prompt injection savunması: kaynak metindeki literal delimiter'lar önce nötrleştirilir (satır 38). `durum="mülga"` ise `[⚠️ MÜLGA — YÜRÜRLÜKTE DEĞİL]` uyarısı otomatik eklenir (`generation.py:46-49`, `:56`); 3071'in hiçbir maddesi mülga olmadığından bu örnekte tetiklenmez. DeepSeek `deepseek-chat`, `temperature=0.0`, `max_tokens=800` ile çağrılır (satır 86-96); SYSTEM_PROMPT modeli sıkı sıkıya verilen parçalara bağlı kalmaya, `[N]` referanslarıyla atıf yapmaya ve normlar hiyerarşisini (Anayasa>Kanun>KHK>Yönetmelik>Tebliğ) gözetmeye zorluyor (satır 19-44).

**[8] Hakem Ajan (Post-Hoc Verify).** `PostHocVerifyStage` (`post_hoc_verify.py:124-173`) önce **ücretsiz yapısal kontrol** yapar: `_structural_check` (satır 117-121) cevaptaki her `[N]` işaretinin `sources` listesinde karşılığı olup olmadığını regex ile denetler (`_CITATION_RE`, satır 44); yoksa LLM'e hiç gitmeden `HAKEM_BLOCKED_TEXT` ile bloklar (satır 142-151). Geçerse ve `post_hoc_verify.llm_check=True` ise (`default.yaml:130`, varsayılan açık), ikinci bir DeepSeek çağrısıyla (`verify_answer`, satır 73-114) cevabın bağlamla tamamen tutarlı olup olmadığı "sert bir hukuki denetçi" personasıyla sorulur; `is_valid=false` dönerse cevap yine bloklanır (satır 165-171). Bu da fail-open: LLM çağrısı hata verirse orijinal cevap korunur, `post_hoc_verdict="EVALUATOR_FAILED_OPEN"` (satır 159-162).

**Sonuç.** `ask.py:32-38`'in gösterdiği gibi, kullanıcıya dönen sözlükte `answer`, `sources` (madde + skor + metin), varsa `crag_status` ve `post_hoc_verdict` alanları vardır. `engine.py:229-234`'te `audit_log.log_query()` çağrılır — soru metni, dönen citation'lar, `crag=...; post_hoc=...` özet karar dizesi ve `actor` append-only olarak `logs/audit.jsonl`'a yazılır.

---

## 3) Mimari bileşenler

| Bileşen | Ne / nerede | Kanıt |
|---|---|---|
| **Embedding modeli** | `BAAI/bge-m3`, 1024 boyut, cosine, `sentence-transformers` üzerinden. Hem ingestion'da hem sorgu tarafında (embed_query) aynı model — tek model, tek vektör uzayı. | `config/default.yaml:26-27`, `embedding.py:14`, `:177-181` |
| **Vektör veritabanı** | Qdrant — remote (`QDRANT_URL`) veya embedded/on-disk (`QDRANT_LOCAL_PATH`). Named-vector şeması: `"dense"` (dense, cosine) + `"bm25"` (sparse, `Modifier.IDF`) aynı point üzerinde. | `store.py:46-47`, `:70`, `:78-82` |
| **Sparse/keyword arama** | Eskiden `rank_bm25.BM25Okapi`, tüm korpusu RAM'e çeken bir in-memory index (kendi docstring'i "a few thousand chunks at most" diyordu). **Artık Qdrant'ın native sparse index'inde** — her chunk'ın terim-sayısı vektörü upsert anında yazılıyor (`sparse_vector.py`), IDF ağırlığı Qdrant sunucu tarafında hesaplanıyor. `BM25Index` sınıfı hâlâ var ama artık yalnızca `store.search_sparse()`'a delege eden ince bir sarmalayıcı; `invalidate()` no-op. Ölçek sınırı artık yok (disk-backed, sabit bellek). | `pipeline/bm25_index.py:1-31` (docstring, eski tasarımı "artık geçerli değil" diye işaretliyor), `pipeline/sparse_vector.py:1-51`, `store.py:270-293` |
| **Reranker** | `BAAI/bge-reranker-v2-m3` cross-encoder, `sentence_transformers.CrossEncoder`. `min_score=0.05` (kalibre edilmiş eşik), `top_n=5` sabit kesim (varsayılan), opsiyonel `adaptive_cutoff` (varsayılan kapalı). | `config/default.yaml:79-86`, `pipeline/stages/rerank.py:33-38`, `:97-114` |
| **LLM (üretim + tüm yardımcı LLM çağrıları)** | **[GÜNCEL — provider-agnostic]** Artık tek bir sağlayıcıya bağlı değil: `config.py`'deki `_PROVIDER_ENV` tablosu (`deepseek` \| `jamba` \| generic `LLM_*`) `RAGConfig.generation.api_key/base_url/model`'i sağlayıcıya göre çözüyor, `llm_client.get_client(api_key, base_url)` bunu kullanıyor — her stage aynı kalıyor, hiçbiri sağlayıcıya özel kod içermiyor. Varsayılan profil hâlâ DeepSeek (`deepseek-chat`, `base_url=https://api.deepseek.com/v1`), ama `RAG_PROFILE=jamba` ile yerel bir Jamba sunucusuna (vLLM, OpenAI-uyumlu `/v1`) yönlendirilebiliyor — bu, spekülatif bir "belki bir gün" değil, 2026-08-28'de gerçek bir kiralık RTX 4090'da `ai21labs/AI21-Jamba2-3B` ile uçtan uca çalıştırılıp doğrulandı (bkz. `config/jamba_verified_limits.yaml`). Generate: `temperature=0.0`, `max_tokens=800`, `timeout=30s`, retry=2. Router/CRAG/Post-Hoc-Verify: `temperature=0.0`. Multi-Query: `temperature=0.7`. HyDE: `temperature=0.3`. Embedding için **ayrı bir sağlayıcı yok** — ne DeepSeek'in ne Jamba'nın public embedding endpoint'i var, embedding hep BGE-M3/lokal kalıyor. **Structured output:** JSON bekleyen 4 stage (router/multi_query/crag/post_hoc_verify) `llm_client.create_chat_completion(json_mode=...)` üzerinden `response_format={"type":"json_object"}` dener; backend bunu reddederse (yerel bir sunucu unsupported-param hatası verirse) YAKALANIR, `(base_url, model)` çifti için process-ömürlü olarak "desteklemiyor" işaretlenir ve düz çağrıya düşülür — çökme yok. | `llm_client.py:17-104`, `config.py:57-88` (`_PROVIDER_ENV`), `config/jamba.yaml`, `generation.py:19` (SYSTEM_PROMPT), `config/default.yaml:44-51`, `router.py:83-93`, `multi_query.py:57-64`, `hyde.py:45-55` |
| **Cache katmanları** | Yalnızca bir katman: `SemanticCacheCheckStage`/`SemanticCacheStoreStage` — sorgunun BGE-M3 embedding'inin kosinüs benzerliğine göre (tam string eşleşmesi değil) DeepSeek cevabını önbelleğe alır. Aynı embedded Qdrant client üzerinde **ayrı bir koleksiyon** (`semantic_cache`) — ikinci bir `QdrantClient` açılmıyor (on-disk lock çakışmasını önlemek için). Eşik `0.90`. **Varsayılanda kapalı** (`default.yaml:129`, "geçerli DEEPSEEK_API_KEY ile uçtan uca doğrulanana kadar açılmıyor"). | `pipeline/stages/semantic_cache.py:1-41`, `:79-118`, `config/default.yaml:122-131` |
| **Router (Self-RAG)** | `[0]` — RETRIEVE/ANSWER_DIRECTLY/CLARIFY kararı, DeepSeek `deepseek-chat`. Belirsizlikte her zaman RETRIEVE (hard-coded güvenlik kuralı). | `pipeline/stages/router.py:1-15`, `:36-38` |

Ayrıca: `RAGEngine.store` ve `.model` **lazy + thread-lock'lu tekil** (`engine.py:49-74`) — `_store_lock`/`_model_lock` (double-checked locking), çünkü Multi-Query/HyDE'nin `ThreadPoolExecutor`'ı eşzamanlı ilk-erişimde embedded Qdrant client'ının on-disk kilit dosyasında çakışabiliyordu (yorum: `engine.py:51-54`).

---

## 4) Güvenlik & veri yönetimi katmanı

**PII.** `pii.py` regex + doğrulama tabanlı (NER değil): TCKN resmi checksum algoritmasıyla doğrulanıyor (`_tckn_checksum_valid`, `pii.py:34-46` — rastgele 11 haneli madde/kanun numaralarının yanlışlıkla maskelenmesini önlemek için), ardından IBAN → e-posta → telefon → TCKN sırasıyla maskeleniyor (satır 60-87, sıra bilinçli: ayırt edici karakterli olanlar önce ayıklanırsa saf rakam dizilerinde daha az yanlış pozitif). **Ama §1'de gösterildiği gibi bu yalnızca `--source pdf` ingestion yolunda çalışıyor** — `.md`/offline-txt yolunda hiç çağrılmıyor. Kapsam dışı olarak dürüstçe belirtilmiş: serbest metindeki isim/soyisim ve açık adres (NER gerektirir) yakalanmıyor (`pii.py:9-12`).

**Erişim kontrolü / kimlik takibi.** Sistem bir HTTP servisi olmadığı için (bkz. §0) klasik JWT/OAuth/RBAC katmanı yok — bu bir eksiklik değil, çağrı yüzeyinin doğal sonucu: CLI çağrısı zaten OS kullanıcı kimliğiyle (`getpass.getuser()`) çalışıyor, subprocess köprüsünde `actor` çağıran servisten geliyor. Gerçek boşluk şurada: `actor` **hiçbir yerde zorunlu kılınmıyor** — `ask()`/`retrieve()` imzasında `actor: str | None = None` (`engine.py:188`, `:197`), `None` geçilirse audit log'a `"actor": null` yazılıyor. `engine.py:207-212`'deki docstring bunu açıkça bir sorumluluk uyarısı olarak işaretliyor: *"Never leave it at its None default in a real deployment"*. Kullanıcı-bazlı yetkilendirme (RBAC + Qdrant metadata-filtreli erişim) `docs/IMPROVEMENT_IDEAS.md`'de "🟡 uygulanmadı, yüksek kapsam" olarak listeleniyor (`docs/IMPROVEMENT_IDEAS.md`, "3. Güvenlik..." madde 3).

**Audit log.** `audit_log.log_query()` (`audit_log.py:28-47`) her `retrieve()`/`ask()` çağrısında append-only JSONL'e (`logs/audit.jsonl`) `timestamp, actor, query, citations, answer_verdict` yazıyor — thread-lock'lu (`_lock`, satır 20, 45). Ham chunk metni değil, yalnızca citation'lar (madde numaraları) loglanıyor — *"audit log'un kendisi ayrı bir PII-taşıyan yüzey olmasın diye"* (docstring, satır 9-10).

**Prompt injection savunması.** `prompt_safety.py` — dış kaynaklı (özellikle PDF) metin LLM promptuna girmeden önce `<KAYNAK_METNI>...</KAYNAK_METNI>` delimiter'larıyla sarılıyor (`wrap_source`, satır 35-39), literal delimiter taklidi önce nötrleştiriliyor. `generation.py`, `crag.py`, `post_hoc_verify.py` sistem promptlarının hepsine `INJECTION_DEFENSE_NOTE` ekleniyor (`prompt_safety.py:24-32`). Bu statik bir savunma — docstring kendi sınırını itiraf ediyor: *"ML tabanlı bir sınıflandırıcı değil, sofistike saldırılara karşı garanti vermez"* (satır 12-13).

**Retention/silme.** `retention.py` — `indexed_at` payload alanına (§1) dayanarak yaş-bazlı silme sağlıyor. İki fonksiyon: `list_retention_candidates` (dry-run, satır 85-89) ve `delete_older_than` (gerçekten siler, satır 92-106). `indexed_at` alanı eksikse (eski/legacy point) **güvenli varsayılan silinecek aday** sayılıyor — KVKK açısından en riskli durum böyle ele alınmış (satır 67-71). Bu mekanizma **hiç otomatik tetiklenmiyor** — bkz. §5.

---

## 5) Otomasyon ve insan müdahalesi

**Tam otomatik (kod içinde tetiklenen, insan müdahalesi gerektirmeyen):**
- Chunk'ın değişip değişmediğini kontrol edip yalnızca değişeni yeniden embed etme (`engine.py:109-111`).
- BM25/sparse index güncellemesi — artık upsert anında otomatik (Qdrant native sparse), ayrı bir "yeniden kur" adımı yok.
- Embedding batch OOM'da otomatik batch-size küçültme (`embedding.py:183-190`).
- Geçici hata retry (LLM çağrıları, embedding) — `retry.py:14-24`, `call_with_retry`.
- Audit log yazımı — her `ask()`/`retrieve()` çağrısında otomatik (`engine.py:194`, `:229-234`).
- CRAG düzeltme döngüsü, Post-Hoc-Verify — sorgu bazında otomatik, `max_loops` ile sınırlı.
- `--watch` modunda (`ingest_pipeline.py:253-284`) dosya sistemi 3 saniyede bir yoklanıp değişiklik varsa otomatik yeniden ingest — ama bu modun **kendisi** `python -m mevzuat_rag.ingest_pipeline --watch` komutuyla elle başlatılmalı; arka planda kalıcı bir servis/daemon olarak koşmuyor.

**Manuel tetiklemeli (bir insanın CLI komutu çalıştırması gereken):**
- **İlk ingest / yeni belge ekleme (local/PDF):** `python -m mevzuat_rag.ingest_pipeline [--source pdf --pdf-dir ...]` — `--watch` verilmedikçe tek seferlik.
- **Embedding modeli değişince yeniden-embed (reembed):** `python scripts/reembed.py --collection ... --new-model ...` — eski koleksiyona asla yazmaz, yeni koleksiyon oluşturur; prod geçişi kullanıcının `QDRANT_COLLECTION_MEVZUAT`'ı elle güncellemesiyle olur (`scripts/reembed.py:1-9`).
- **Retention/silme:** `python scripts/apply_retention_policy.py --days N [--confirm]` — varsayılan dry-run, gerçek silme için `--confirm` **zorunlu** (bilinçli güvenlik önlemi, `scripts/apply_retention_policy.py:7-10`). Otomatik bir cron/zamanlayıcı **kod tabanında yok** — script'in kendisi yalnızca elle çalıştırıldığında bir şey yapar.
- **Embedding batch-size kalibrasyonu:** `scripts/calibrate_embedding_batch.py` — GPU doygunluk noktası hiç otomatik ölçülmüyor, sabit `batch_size=32` varsayılan (`docs/IMPROVEMENT_IDEAS.md`, "4. Ölçek..." madde 3, 🟡 uygulanmadı).
- **Retrieval eval / regresyon takibi:** `scripts/eval_with_history.py`, `scripts/eval_trend_report.py` — elle çalıştırılan, `logs/eval_history.jsonl`'a kayıt bırakan araçlar; CI entegrasyonu var (`docs/IMPROVEMENT_IDEAS.md`, "5. Gözlemlenebilirlik" madde 2, 🟢 uygulandı) ama bu CI tetiklemesi de yine bir otomasyon katmanına (pipeline/workflow tanımına) bağlı, servis içinde kendiliğinden dönmüyor.
- **Konfigürasyon/üretime-hazırlık denetimi:** `scripts/rag_config_panel.py` — kod yazmaz/deploy etmez, kullanıcının kendi girdiği gerçek duruma göre KRİTİK/YÜKSEK/ORTA/DÜŞÜK uyarı listesi üretir; tamamen elle çalıştırılan bir kontrol paneli (`scripts/rag_config_panel.py:9-19`).
- **Environment doğrulama:** `scripts/verify_env.py` — yeni bir makinede ilk kurulumda elle çalıştırılması beklenen doğrulama komutu (`config/default.yaml:9`).

---

## 6) Bilinen sınırlar (kodun kendi itiraf ettikleri)

- **BM25'in eski hali** (artık terk edilmiş ama kodda iz bırakmış): `bm25_index.py`'nin docstring'i eski `rank_bm25.BM25Okapi` tasarımının kendi sınırını *"a few thousand chunks at most"* diye itiraf ediyor ve bunun 1M-dosya hedefiyle çeliştiğini not ediyor (`bm25_index.py:1-11`) — bu artık geçmişte kaldı (Qdrant native sparse'a geçildi) ama denetim izini korumak için docstring'de bırakılmış.
- **Tablo çıkarımı MVP düzeyinde.** `ChunkMetadata.contains_table` gerçek tablo yapısı çıkarmıyor, yalnızca heuristik bir "dikkat" bayrağı (`models.py:25-29`, `legal_structure_parser.py:62-64`). PDF tarafında (`pdf_corpus.py`) tablo hizalaması Markdown'a çevrilmeye çalışılıyor ama çok-sütunlu sayfalarda sıra bozulabileceği açıkça belirtiliyor (`pdf_corpus.py:132-139`).
- **Atıf tespiti yalnızca aynı-kanun içi.** `citation_ref.py` kanunlar-arası atıfları ("2577 sayılı Kanun'un 7. maddesi") hiç yakalamıyor — *"corpus'ta hiç örneği yok, o yüzden test edilemeyen/kalibre edilemeyen bir regex eklemek yanıltıcı olur"* (`citation_ref.py:6-12`).
- **Resmi Gazete/mevzuat.gov.tr canlı takibi kilitli.** `docs/IMPROVEMENT_IDEAS.md`, "6. Türk Mevzuatına Özgü Doğruluk" madde 4: `list_updates()` kanun_no çıkarmıyor, `mevzuat_gov_tr.search()` no-op — gerçek ağ erişimi olmadan bloke (🟡, uygulanmadı).
- **Citation Expansion ve Semantic Cache doğrulanmış ama varsayılanda kapalı.** İkisi de kod+test tamamlanmış durumda ama `config/default.yaml`'da bilinçli olarak `enabled: false` bırakılmış — *"yeni davranışlar doğrulanana kadar açılmıyor"* disiplini (`config/default.yaml:108-109`, `:129`; `rerank.py:98-102` yorumu aynı disiplini tekrar vurguluyor).
- **Rerank eşiği küçük corpus'ta kalibre edildi.** `min_score=0.05`, 9 corpus-içi + 4 corpus-dışı soruyla kalibre edildi; yorum kendisi *"Küçük corpus'ta ölçüldü — corpus büyüdükçe yeniden kalibre edilmeli"* diyor (`config.py:92-97`). Aynı uyarı `semantic_cache.similarity_threshold=0.90` için de var (`config.py:178-180`).
- **Chunk-level fail-open'lar sessiz değil ama LLM-çağrı hatalarına bağımlı.** CRAG/Post-Hoc-Verify/Semantic-Cache'in hepsi "fails open" politikasıyla tasarlanmış (LLM/ağ hatasında sistemi kırmak yerine mevcut sonuçla devam eder) — ama CRAG'ın fail-open'ı artık sessiz değil, `crag_status="EVALUATOR_FAILED_OPEN"` olarak kullanıcıya görünür kılınmış (`generate.py:40-47`).

---

## 7) Belgelenen ama uygulanmayan davranışlar

| Belgelenen (config/docstring) | Gerçek davranış | Kanıt |
|---|---|---|
| `chunking.overlap_tokens: 80` ("~%15 örtüşme") — `RAGConfig.chunk_overlap_tokens`, `StructureAwareChunker(overlap_tokens=...)` | Parametre alınıp `self.overlap_tokens`'a atanıyor ama `chunk()` metodunda **bir daha hiç okunmuyor** — hiçbir sliding-window overlap uygulanmıyor. | `config/default.yaml:38`, `config.py:226,292`, `ingest_pipeline.py:97`, `chunker.py:33-35` (atama) vs. `chunker.py:37-110` (kullanım yok) |
| `pii.py` modül docstring'i: *"kimlik/iletişim bilgilerini LLM'e/vektör deposuna ulaşmadan önce maskeler"* — genel bir güvenlik katmanı gibi sunuluyor | Yalnızca `--source pdf` ingestion yolunda çağrılıyor (`pdf_corpus.py:265`); `--source local` (varsayılan, `.md`/offline-txt) yolunda **hiç çağrılmıyor**. | `pii.py:1-2` vs. `grep -rn "redact_pii"` sonucu — tek çağrı noktası `pdf_corpus.py:265` |
| `RAGConfig`/`StageToggle` dataclass tanımındaki alan varsayılanları: her stage `enabled: bool = False` (`config.py:69-70` ve alt sınıflar) | Gerçek çalışma zamanı davranışı bu varsayılanlardan gelmiyor — `RAGConfig.load()` her zaman `config/default.yaml`'ı okuyup üzerine yazıyor (`config.py:298-308`), ve o dosyada router/hybrid/rerank/multi_query/hyde/parent_doc/compression/crag/post_hoc_verify hepsi `enabled: true`. Yalnızca citation_expansion ve semantic_cache gerçekten kapalı kalıyor. Dataclass'a yalnızca bakan biri (YAML'ı görmeden) "her şey varsayılan kapalı" sanabilir. | `config.py:69-251` (dataclass varsayılanları) vs. `config/default.yaml:66-141` (gerçek yüklenen değerler) — **doğrulanamadı değil, aktif bir yanlış-izlenim riski**: iki kaynağın birbiriyle tutarsız görünmesi kasıtlı olmayabilir ama kodu yalnızca `config.py`'den okuyan biri yanlış sonuca varır |
| `get_rag_context()` (coreaigent tarafı) — fonksiyon adı "RAG context" alır gibi genel bir izlenim veriyor | Yalnızca `engine.retrieve()`'i çağırıyor (`rag_connector.py:37`) — mevzuat-rag'in `ask()`'i, yani DeepSeek üretimi + CRAG + Hakem Ajan katmanı bu entegrasyon yolunda **hiç devreye girmiyor**. coreaigent tarafı yalnızca ham chunk metinlerini (`context_snippets`) alıyor, kendi ayrı LLM akışında kullanıyor. | `services/llm/rag_connector.py:27-48` (`_RETRIEVE_SCRIPT` içinde yalnızca `engine.retrieve(...)` çağrısı var, `engine.ask(...)` hiç yok) |

---

## Ek A — Config tutarsızlığının tam mekaniği

`RAGConfig` dataclass'ı (`config.py:215-254`) ve onun alt-config'leri (`RouterConfig`, `HybridConfig`, `RerankConfig`, ...) hepsi `StageToggle`'dan türer: `@dataclass class StageToggle: enabled: bool = False` (`config.py:69-70`). Yani **Python seviyesinde**, `RouterConfig()` yazsanız `enabled=False` gelir.

Ama kod tabanında `RouterConfig(...)` (veya herhangi bir stage config'i) **hiçbir yerde dataclass varsayılanlarıyla çağrılmıyor**. Tek üretim noktası `RAGConfig.load()` (`config.py:256-335`) ve o metot her stage config'ini **açıkça** yapılandırıyor:

```python
router=RouterConfig(**(y.get("router", {}) or {})),
```
(`config.py:298`, aynı desen 299-308 arası tüm stage'ler için tekrarlanıyor)

Burada `y`, `_layered_yaml(profile)`'ın döndürdüğü sözlük (`config.py:49-54`) — yani **her zaman** `config/default.yaml` okunuyor, profil "default" değilse onun üzerine `config/{profile}.yaml` deep-merge ediliyor. `y.get("router", {})` boş sözlük dönerse (`router:` anahtarı YAML'da hiç yoksa) ancak o zaman dataclass varsayılanı (`enabled=False`) devreye girer. Ama `default.yaml`'da `router:` anahtarı **var** ve `enabled: true` yazıyor (`config/default.yaml:67-68`) — dolayısıyla `y.get("router", {})` asla boş dönmüyor, dataclass varsayılanı hiçbir zaman fiilen kullanılmıyor.

**Sonuç:** Bu iki kaynak (`config.py`'deki dataclass tanımları ve `config/default.yaml`) birbirinin **belgesi değil**, birbirinden **bağımsız iki varsayılan katmanı**. `config.py` yalnızca "YAML'da o anahtar yoksa ne olur" sorusuna cevap veriyor — üretimde/gelişimde hiç karşılaşılmayan bir durum, çünkü `default.yaml` her stage'i açıkça set ediyor. Riski somutlaştırmak için doğruladığım nokta: `grep -rn "RAGConfig(" tests/ mevzuat_rag/` kod tabanında `RAGConfig`'in (ya da herhangi bir alt-config'in) dataclass constructor'ıyla doğrudan, `.load()`/`.from_env()` atlanarak çağrıldığı **tek bir yer bulamadı** — testler dahil her yol `RAGConfig.load()`/`RAGConfig.from_env()` üzerinden geçiyor (`tests/conftest.py:15`, `.env`'i yükleyip `dotenv` ile ortamı hazırlıyor, config kurulumunu yine `RAGConfig.from_env()`'e bırakıyor). Yani **bu an itibarıyla çalışma zamanında hiçbir sapma yok** — risk canlı bir bug değil, "sadece `config.py`'yi okuyan biri (yeni bir mühendis, kod incelemesi, statik analiz aracı) hangi stage'lerin fiilen açık olduğu konusunda yanlış sonuca varır" türünden bir **okunabilirlik/denetlenebilirlik riski**. Eğer ileride biri `RAGConfig(qdrant_url=..., ...)`'i `.load()` atlayarak doğrudan çağırırsa (ör. bir testte "minimal config" kurmak için), o çağrı **sessizce tüm stage'leri kapatır** — hiçbir hata/uyarı vermez, çünkü `StageToggle.enabled=False` geçerli bir dataclass durumu.

## Ek B — Donanım katmanı: BGE-M3, reranker, VRAM

**Yerel GPU/CPU hesaplaması gerektiren yalnızca 2 model var:**

| Model | Rol | Kütüphane | Kod |
|---|---|---|---|
| `BAAI/bge-m3` | Dense embedding (ingestion + sorgu tarafı embed_query/embed_texts) | `sentence_transformers.SentenceTransformer` | `embedding.py:14`, `:134` (`SentenceTransformer(model_name, device=device)`) |
| `BAAI/bge-reranker-v2-m3` | Cross-encoder reranker ([3] Rerank stage) | `sentence_transformers.CrossEncoder` | `rerank.py:33-38` |

**DeepSeek (varsayılan profil — generation, router, multi-query, HyDE, CRAG, post-hoc-verify) yerel hesaplama yapmıyor** — hepsi `https://api.deepseek.com/v1`'e giden ağ çağrıları (`llm_client.py:17-30`, `openai.OpenAI` istemcisi). Bu çağrılar hiçbir VRAM/CPU-model yükü getirmiyor, yalnızca ağ gecikmesi + API maliyeti. *(Bu, çoklu-provider mimarisi öncesindeki — ve hâlâ varsayılan profildeki — durum; aşağıdaki Jamba bölümü GÜNCEL/ek bilgidir, bunun yerine geçmez.)*

**[GÜNCEL, 2026-08-28] `RAG_PROFILE=jamba` — yerel LLM, ama AYRI bir process'te.** `config/jamba.yaml` mevzuat-rag'i yerel bir Jamba sunucusuna (`ai21labs/AI21-Jamba2-3B`, vLLM üzerinden OpenAI-uyumlu `/v1` endpoint) bağlar. **Önemli mimari ayrım:** mevzuat-rag'in kendi Python process'i bu modeli hiç yüklemiyor — yukarıdaki "yalnızca 2 model" iddiası (embedding + reranker) bu profilde de aynen doğru kalıyor. Jamba, `vllm serve` ile başlatılan **ayrı bir OS process'i** olarak GPU'yu paylaşıyor; mevzuat-rag ona da yalnızca HTTP üzerinden (DeepSeek'e gittiği gibi) istek atıyor. Gerçek bir kiralık RTX 4090'da uçtan uca doğrulanan rakamlar (bkz. `config/jamba_verified_limits.yaml`, ham log `ladder.log`):
- Jamba2-3B ağırlık ayak izi: 5.99-6.29 GiB (bfloat16, kuantizasyon yok)
- Embedding (BGE-M3): 2.292 GiB, Reranker: 2.271 GiB — üçü **aynı GPU'da eşzamanlı** yüklüyken hiç OOM alınmadı
- Context: 64.000 token'a kadar (test edilen üst sınır, gerçek tavan daha yüksek — ölçülmedi) hem Jamba yalnızken hem üç model birlikteyken hatasız
- Yükleme süresi: ilk (soğuk, model indirme dahil) 172.5s, ikinci (HF cache sıcak) 24.5s

**Qdrant (vektör veritabanı) da GPU kullanmıyor** — dense/sparse arama Qdrant'ın kendi Rust motorunda, CPU + disk/RAM üzerinde çalışıyor (`store.py`, embedded modda `QdrantClient(path=local_path)`, remote modda `QdrantClient(url=url)` — `store.py:70`). GPU'ya hiç dokunmuyor.

**Cihaz seçimi zinciri** (`device.py:11-26`, `resolve_device()`):
1. `DEVICE` env var set edilmişse onu kullan.
2. Yoksa `torch.cuda.is_available()` → `"cuda"`.
3. Yoksa `torch.backends.mps.is_available()` → `"mps"` (Apple Silicon).
4. Hiçbiri yoksa `"cpu"`.

Bu değer `RAGConfig.load()` içinde tek bir `device` olarak hesaplanıp (`config.py:261-263`) hem `embedding_device` (satır 290, legacy flat alan — `RAGEngine.model` bunu kullanıyor, `engine.py:73`), hem `EmbeddingConfig.device` (satır 323, yapısal alan — `embedding.py:_get_default_config` fallback yolunda kullanılıyor), hem de top-level `RAGConfig.device` (satır 296 — **reranker bunu kullanıyor**, `rerank.py:84`: `_get_cross_encoder(config.model, ctx.engine.config.device)`) alanlarına aynı çözümlenmiş değer olarak yazılıyor. Yani **embedding modeli ve reranker aynı cihazda** çalışır — biri GPU'da biri CPU'da kalmaz.

**Profil bazında gerçek davranış** (`config/*.yaml`):
- `default.yaml`: `device: auto` (satır 11) → host'a göre otomatik.
- `dev_gpu.yaml`: `device: cuda` sabit, `embedding.batch_size: 64` (VRAM'i daha agresif kullanır); **rerank kapalı** (`rerank.enabled: false`, "checkpoint 2'de true yapılacak" notuyla) — yani bu profilde şu an yalnızca embedding GPU'da, reranker hiç koşmuyor.
- `cpu_only.yaml`: `device: cpu` sabit, `batch_size: 16`, `oom_retry: false` ("CPU'da OOM/batch-halving anlamsız").
- `edge.yaml`: `device: auto` ama `batch_size: 8`, `top_k: 3`, rerank/multi_query/router/crag hepsi kapalı — düşük VRAM'lı cihaz için ağır aşamalar baştan devre dışı.
- `prod.yaml`: `device` anahtarını hiç override etmiyor → deep-merge sonucu yine `default.yaml`'daki `auto`'yu miras alıyor. Yani **prod'da GPU kullanılıp kullanılmayacağı, o an deploy edilen host'un donanımına ve varsa `DEVICE` env override'ına bağlı** — profilin kendisi bunu garanti etmiyor.

**Bu makinedeki (analiz ortamı) gerçek durum, doğrulandı:** `torch.cuda.is_available()` → `True`, `nvidia-smi -L` → `NVIDIA GeForce RTX 5060 Laptop GPU`. `.env` dosyasında `RAG_PROFILE=` ve `DEVICE=` **boş** (`~/coreaigent/mevzuat-rag/.env:3,5`) — yani `RAG_PROFILE` boşsa `"default"` profiline düşer (`config.py:258`) ve `default.yaml`'ın `device: auto`'su `resolve_device()`'a devrediyor; bu makinede CUDA mevcut olduğundan sonuç `"cuda"` olur. **Bu ortamda RAGEngine çalıştırılırsa hem BGE-M3 hem bge-reranker-v2-m3 GPU/VRAM üzerinde yüklenir.**

**VRAM doğrulaması koda gömülü.** `scripts/verify_env.py:39-47` — cihaz `"cuda"` ise `torch.cuda.mem_get_info()` ile boş/toplam VRAM'i sorgulayıp en az 1 GB boş VRAM olup olmadığını kontrol ediyor (eşik: `free_gb >= 1.0`, keyfi bir minimum, gerçek model boyutuna göre kalibre edildiğine dair kod içi bir kanıt yok — bu nokta doğrulanamadı). `DEPLOY.md:47-49`'da bu adım "Cihaz, VRAM (GPU'daysa), embedding modeli, Qdrant erişimi, embedding boyutu, disk alanı kontrol edilir" diye kurulum sürecinin zorunlu bir adımı olarak listeleniyor.

**Docker/deploy tarafında GPU ayrımı açık şekilde modellenmiş** (`docker-compose.yml:31-53`): `mevzuat-rag-gpu` servisi `RAG_PROFILE: dev_gpu` ile başlıyor ve `deploy.resources.reservations.devices` altında NVIDIA runtime rezervasyonu var (satır 47-53) — host'ta NVIDIA Container Toolkit gerektiği docker-compose.yml'in başındaki yorumda açıkça yazıyor (satır 2-3). `mevzuat-rag-cpu` servisi ise `RAG_PROFILE: cpu_only` ile, GPU rezervasyonu olmadan tanımlı (satır 14-29). Qdrant'ın kendisi (satır 6-12) her iki profilde de aynı — GPU'ya bağımlı değil.

**Özet tablo — hangi katman nerede çalışır:**

| Katman | Yerel mi / uzak mı | Hesaplama kaynağı |
|---|---|---|
| Router / Multi-Query / HyDE / CRAG / Post-Hoc-Verify (LLM kararları) | Uzak (DeepSeek API) | Ağ — yerel CPU/GPU yükü yok |
| Generate (nihai cevap üretimi) | Uzak (DeepSeek API) | Ağ — yerel CPU/GPU yükü yok |
| Embedding (BGE-M3) — ingestion + sorgu | Yerel | `resolve_device()`'a göre CPU **veya** GPU/VRAM |
| Reranker (bge-reranker-v2-m3) | Yerel | Embedding ile **aynı** cihaz (`ctx.engine.config.device`) |
| Sparse/BM25 skorlama (hashing + Qdrant IDF) | Yerel | Saf CPU (Qdrant motoru içinde), GPU yok |
| Dense/sparse arama (Qdrant) | Yerel ya da uzak (embedded/`QDRANT_URL`) | CPU + disk/RAM, GPU yok |
| PII redaksiyon, chunking, text-norm, audit log | Yerel | Saf CPU (regex/string işlemleri) |

---

*Bu belge, `mevzuat-rag` paketinin ve coreaigent'ın `services/llm/rag_connector.py` / `services/workflow/pipeline.py` entegrasyon noktalarının doğrudan kaynak kodu okunarak hazırlanmıştır. Referans verilen tüm satır numaraları 2026-08-28 tarihli çalışma kopyasına aittir.*
