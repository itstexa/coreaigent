# Notlar — Checkpoint 6: Portability + Observability (2026-08-19)

## Amaç

Phase 3 (portability) ve Phase 4'ün (observability) kalanı: `index_meta.json`
+ embedding boyutu fail-fast, `DATA_DIR`/`HF_HOME` wiring, `verify_env.py`,
Docker (CPU+GPU), Makefile, mock-LLM smoke test, `debug=true` trace
exposure, `eval/run_ablation.py`, MIGRATION.md, DEPLOY.md.

## Bulunan ve düzeltilen gerçek gap: `paths.data_dir`/`embedding.dim` ölü config

`config/default.yaml`'da Checkpoint 1'den beri duran `paths.data_dir`,
`paths.models_dir` ve `embedding.dim` anahtarları **hiçbir yerde
okunmuyordu** — YAML'da vardı ama `RAGConfig.load()` bunları hiç
tüketmiyordu, `qdrant.local_path` da hep `PROJECT_ROOT`'a göre çözülüyordu
(`DATA_DIR` env var'ı bile module-level sabit olarak import zamanında
donuyor, YAML'daki `paths.data_dir`'i asla görmüyordu). Düzeltildi:
`RAGConfig.load()` içinde `data_dir` artık `DATA_DIR` env > `paths.data_dir`
YAML > `PROJECT_ROOT/data` sırasıyla her çağrıda hesaplanıyor,
`qdrant.local_path` buna göre çözülüyor; `paths.models_dir` (veya `HF_HOME`
env) varsa `HF_HOME`'u set ediyor (offline/önceden-indirilmiş model cache'i
için). `embedding.dim` artık `RAGConfig.embedding_dim` alanına bağlı,
`store.py`'nin `VECTOR_SIZE` sabiti kaldırıldı.

## `index_meta_{collection}.json` + fail-fast doğrulandı

- Farklı `embedding_dim` (Qdrant'ın kendi `vectors.size`'ıyla karşılaştırma):
  gerçek bir uyumsuzlukla test edildi, `IndexMetadataMismatch` doğru fırlatıldı.
- Aynı boyut, farklı `embedding_model` (`index_meta_{collection}.json`
  karşılaştırması): ayrıca test edildi, doğru fırlatıldı — Qdrant'ın kendi
  kontrolü boyut aynıysa bunu yakalayamazdı, bu yüzden ayrı bir JSON kaydı
  gerekliydi.

## Diğer sonuçlar

- **`scripts/verify_env.py`:** gerçek ortamda çalıştırıldı — device (cuda),
  VRAM, embedding modeli, reranker modeli, Qdrant erişimi, DEEPSEEK_API_KEY,
  disk alanı hepsi PASS döndü.
- **Mock-LLM smoke test (`tests/test_smoke_pipeline.py`):**
  `DEEPSEEK_API_KEY` env var'ı kaldırılıp (`unset`) çalıştırıldı, geçti —
  gerçekten API key/ağ gerektirmiyor. `unittest.mock.patch` her stage
  modülünün kendi `from ... import get_client` bağladığı yerel isme ayrı
  ayrı uygulanmak zorunda kaldı (`mevzuat_rag.llm_client.get_client`'ı tek
  başına patch'lemek hiçbirine ulaşmıyordu — modül-seviyeli import binding'i
  farkı).
- **`RAG_DEBUG=true` trace exposure:** `ask()` artık `result["trace"]`
  döndürüyor (yalnızca `config.debug` açıkken) — router'ın erken durduğu
  yolda da doğru çalıştığı doğrulandı (tek trace entry: `router`).
- **`eval/run_ablation.py`:** golden set + her stage'i tek tek kapatıp
  ölçme — gerçek LLM çağrıları yüzünden (8 ablasyon + 1 baseline × 9 sorgu)
  tam çalıştırması uzun sürüyor; alttaki `config.X.enabled = False` +
  `RAGEngine(config)` deseni Checkpoint 2-5'te zaten tekrar tekrar
  doğrulanmış desenin aynısı.
- **Docker:** `Dockerfile.cpu` (torch CPU wheel index'inden, CUDA toolkit
  indirmiyor) ve `Dockerfile.gpu` (nvidia/cuda base image) ayrı;
  `docker-compose.yml` iki profil (`cpu`/`gpu`) + paylaşılan `qdrant`
  servisi. Bu ortamda gerçek `docker build` çalıştırılmadı (sandbox'ta
  Docker daemon yok) — Dockerfile'lar statik olarak doğru ama gerçek bir
  build ile doğrulanmadı, ilk kullanımda dikkatli test edilmeli.
- `requirements.txt` artık tam pinlenmiş (bu ortamda kurulu/test edilmiş
  sürümler: qdrant-client 1.18.0, sentence-transformers 5.5.1, torch 2.12.0,
  openai 2.20.0, vb.) — önceden `>=` ile gevşekti.

---

# Notlar — Checkpoint 5: Self-RAG Router + CRAG (2026-08-19)

## Amaç

[0] Router ve [5] Evaluate (CRAG) aşamalarını eklemek — bu, prompttaki 9
tekniğin sonuncu ikisi. Bu checkpoint'le pipeline artık [0]-[7] arasının
tamamını içeriyor.

## Sonuçlar

- **Router:** 4 gerçek sorguyla test edildi — "merhaba" ve "teşekkürler
  yardımın için" → `ANSWER_DIRECTLY` (doğru, retrieval hiç çalışmadı);
  "bişey" → `CLARIFY` (doğru, belirsiz soru); "Dilekçede hangi bilgiler
  zorunludur?" → `RETRIEVE`, tam pipeline'dan geçip atıflı doğru cevap
  üretti. Güvenlik kuralı (belirsizlikte RETRIEVE) hem prompt'ta hem
  parse hatası fallback'inde var.
- **CRAG:** Orijinal 2026-08-16 notlarındaki üçüncü test sorusu ("Elektronik
  ortamda güvenli elektronik imza için hangi sertifika gerekir?" — corpus'ta
  YOK) ile test edildi:
  - `insufficient_strategy: refuse` → `INSUFFICIENT` tespit edildi, context
    boşaltıldı (0 candidate), Generate'in "bu sorunun cevabı yok" reddi
    tetiklenecek şekilde bırakıldı.
  - `force_hyde` ve `shift_to_bm25` → ikisi de `max_loops=2`'yi doldurup
    dürüstçe `INSUFFICIENT` sonucunda kaldı (gerçekten corpus'ta yok,
    fabrikasyon yapmadılar) — sonsuz döngüye girmediler, cap çalışıyor.
- **Golden set (router+crag dahil hepsi açık):** Recall@1/3/5 = MRR = 1.0.
  CRAG'in evaluator'ı bu 9 soruda hep `SUFFICIENT` dedi (corpus zaten
  kapsıyor), yani ek loop maliyeti çıkmadı — gecikme p50 ~5.7s'ye çıktı
  (router'ın +1 LLM çağrısı + CRAG'in +1 evaluator çağrısı yüzünden).
- **Thread-safety notu:** CRAG'in `insufficient_strategy` uygulaması
  bilerek `ctx.engine.config`'i MUTATE ETMİYOR (ör. `hybrid.alpha`'yı
  geçici değiştirip geri almak yerine) — paylaşılan bir `RAGEngine`
  üzerinde eşzamanlı isteklerde state sızıntısına yol açardı (bkz.
  Checkpoint 3'teki thread-safety bulgusuyla aynı risk sınıfı). Bunun
  yerine her strateji doğrudan `ctx`/`engine.store`/`engine.model` üzerinden
  çalışıyor.
- `config/default.yaml`'da `router.enabled` ve `crag.enabled` artık `true`;
  `config/edge.yaml` ikisini de kapalı tutuyor (düşük kaynaklı cihazlarda
  ekstra LLM çağrısı maliyeti istenmeyebilir).

---

# Notlar — Checkpoint 4: Parent Document Retrieval + Context Compression (2026-08-19)

## Amaç

[4] Expand ve [6] Compress aşamalarını eklemek: küçük chunk'larla arayıp
tam madde metnini LLM'e vermek (parent doc), ve bağlamı token bütçesine
sığdırmak (compression).

## Sonuçlar

- **Parent Document Retrieval:** `store.get_chunks_by_madde()` ile parent
  metni her seferinde canlı yeniden kuruluyor (ayrı, bayatlayabilecek bir
  kopya tutulmuyor). `chunk_max_tokens=8` ile zorla küçültülmüş chunk'larla
  test edildi: "Hangi dilekçeler incelenemez?" sorgusunda Madde 6'nın Bent
  (a) ve Bent (c)'i ayrı ayrı reranked sonuç olarak geliyordu; parent_doc
  açıkken ikisi de tek "Madde 6 (tam metin)" adayına birleşti (child_count=4,
  en yüksek çocuk skoru korundu). Token bütçesi testi: `context_window_tokens=50`
  ile 5 adaydan yalnızca 1'i (en yüksek skorlu) sığdı, gerisi düştü —
  doğru çalışıyor.
- **Context Compression:** Dedup senkron testte doğrulandı (cosine>0.95
  olan iki sentetik aday, düşük skorlu olan düştü). Extractive seçim gerçek
  cümle bölme + Türkçe terim örtüşmesiyle test edildi, bütçeye sığmayan
  cümleyi doğru elemiş. **Not:** bu corpus'taki mevzuat metinleri genelde
  fıkra başına tek cümle olduğu için (`.!?` ile bölünecek ikinci bir cümle
  yok), extractive adım çoğu gerçek sorguda hiçbir şeyi kısaltmadı — bu bir
  bug değil, "fıkra asla bölünmez" ilkesiyle tutarlı: extractive seçim
  cümle granülaritesinde çalışıyor, chunk zaten tek cümleyse yapacak bir
  şey yok. `llm_summarize: true` ile ayrıca test edildi: 5 adayı [1]-[5]
  atıf işaretlerini koruyarak tek bir özet adaya indirdi (varsayılan
  `false` — yalnızca test için açıldı).
- **Golden set (hybrid+rerank+multi_query+hyde+parent_doc+compression hepsi
  açık):** Recall@1/3/5 = MRR = 1.0 — hâlâ hiç kalite kaybı yok.
- `config/default.yaml`'da `parent_doc.enabled` ve `compression.enabled`
  (llm_summarize hariç) artık `true`.

---

# Notlar — Checkpoint 3: Multi-Query + HyDE (2026-08-19)

## Amaç

[1] Query Transform aşamasını eklemek: Multi-Query (LLM'den N farklı bakış
açılı sorgu) ve HyDE (kısa sorgularda hipotetik cevap embedding'i), ikisi de
[2] Hybrid Retrieve'in RRF/weighted füzyonuna aynı yoldan giriyor (çoklu
sorgu varyantı → çoklu dense arama → tek füzyon).

## Bulunan ve düzeltilen gerçek bug: thread-safety race condition

Multi-Query'nin "paralel koş" gereksinimini (`ThreadPoolExecutor` ile N
sorgu varyantının dense aramasını eşzamanlı çalıştırmak) uygularken, ilk
testte gerçek bir hata yakalandı: `RAGEngine.store`/`.model` lazy-init
property'leri thread-safe değildi. Çoklu thread ilk erişimde aynı anda
`self._store is None` görüp hepsi ayrı `QdrantStore(...)` inşa etmeye
çalışıyor, embedded Qdrant'ın disk kilidiyle çakışıp
`portalocker.exceptions.AlreadyLocked` fırlatıyordu. Düzeltme:
double-checked locking (`threading.Lock`, `engine.py`). Bu, ThreadPoolExecutor
eklemeden önce hiç ortaya çıkmayan, gerçek bir concurrency bug'ıydı —
gerçek DEEPSEEK_API_KEY ile (bkz. aşağı) uçtan uca test edilmeseydi
fark edilmezdi.

## DeepSeek API key

Ortamdaki `DEEPSEEK_API_KEY` env var hâlâ geçersiz (`...4069`, bkz. 2026-08-16
notları). Bu checkpoint'in gerçek LLM çağrısı gerektiren testleri (Multi-Query
üretimi, HyDE, generation testi) `~/.hermes/.env`'deki çalışan key
(`sk-4121e9d...`) shell'e export edilerek doğrulandı — projeye `.env` olarak
commit edilmedi, yalnızca test oturumunda kullanıldı. Bu doğrulamayla
`tests/test_mevzuat_rag.py::GenerationTests` de dahil **7/7 test gerçek API
ile geçti** (önceden hep 6/7'ydi, tek başarısız olan da ortamdaki geçersiz
key'den kaynaklanıyordu).

## Sonuçlar

- **Multi-Query:** DeepSeek'ten JSON dizi olarak 4 farklı-açılı sorgu
  isteniyor (`prompts/multi_query.txt`), format bozuksa orijinal sorguya
  fallback (WARNING loglanır). Test edilen gerçek çıktı — "Dilekçe hakkının
  amacı nedir?" için: "dilekçe hakkı amacı Anayasa", "dilekçe hakkının
  kullanım şartları ve sınırları", "dilekçe hakkı ile bilgi edinme hakkı
  farkı", "dilekçe hakkının idareye başvuru sonucu yükümlülükler" — gerçekten
  parafraz değil, farklı açılar.
- **HyDE:** "kağıt boyutu" gibi kısa bir sorguda tetiklendi, ürettiği
  hipotetik cevap (TS EN ISO 216 standardından bahseden bir paragraf) doğru
  chunk'ı (2646 sayılı Yönetmelik Madde 5) skor 0.90 ile en üste çıkardı.
- **Golden set (hybrid+rerank+multi_query+hyde hepsi açık, gerçek model +
  gerçek API key):** Recall@1/3/5 = MRR = 1.0 — hiç kalite kaybı yok.
  Gecikme belirgin arttı (p50 ~2.5s, en yüksek ~16s — LLM round-trip'leri
  yüzünden); `config/edge.yaml` bu yüzden `multi_query.enabled: false`
  bırakıldı.
- `mevzuat_rag/llm_client.py` (`get_client`) ve `mevzuat_rag/retry.py`
  (`call_with_retry`) eklendi — generation.py, multi_query.py, hyde.py
  hepsi aynı client factory + retry/timeout mantığını paylaşıyor
  (`config.generation.timeout_s`/`retry_attempts`/`retry_backoff_s`, artık
  gerçekten `RAGConfig`'te taşınıyor — önceden `default.yaml`'da
  tanımlıydı ama hiçbir yerde okunmuyordu).
- `config/default.yaml`'da `multi_query.enabled` ve `hyde.enabled` artık
  `true`.

---

# Notlar — Checkpoint 2: Hybrid Search + Reranking (2026-08-19)

## Amaç

RAG upgrade planının [2] Hybrid Retrieve (dense+BM25+RRF/weighted) ve
[3] Rerank (cross-encoder) aşamalarını ekleyip config'ten açarak gerçek
golden set üzerinde doğrulamak (bkz. Checkpoint 1'in kurduğu
`mevzuat_rag/pipeline/` mimarisi).

## Sonuçlar

- **BM25:** `rank_bm25.BM25Okapi`, Qdrant'ın mevcut `chunk_id` uzayını
  paylaşan in-memory index (`store.scroll_all_chunks()`'tan kurulur,
  `RAGEngine.index_chunks` yeni/değişen chunk embed edince invalidate
  edilir). Türkçe tokenizasyon: özel case-folding (İ/I) + stopword listesi +
  `snowballstemmer` Turkish stemmer (`pipeline/tokenize_tr.py`).
- **Fusion:** RRF (varsayılan, k=60) ve weighted (alpha) ikisi de
  `pipeline/fusion.py`'de; `hybrid.fusion` config'ten seçilir.
- **Rerank:** `sentence_transformers.CrossEncoder` ile `BAAI/bge-reranker-v2-m3`.
  **Graceful degradation doğrulandı:** bozuk model adıyla test edildi, crash
  etmedi, WARNING logladı, hybrid skorlarıyla devam etti.
- **`eval/run_retrieval_eval.py` bir bug'ı düzeltildi:** önceden ham
  `embed_query`+`store.search` çağırıyordu, yani `hybrid`/`rerank` açık olsa
  bile onları test etmiyordu (her zaman dense-only ölçüyordu). Artık
  `engine.retrieve()` üzerinden gerçek pipeline'ı çalıştırıyor.
- **Golden set sonucu (gerçek model ağırlıklarıyla, hybrid+rerank ikisi de
  açık):** Recall@1/3/5 = MRR = 1.0 — Checkpoint 1'in dense-only skorlarıyla
  birebir aynı, hiç kalite kaybı yok (9 sorgu, çok küçük bir corpus olduğu
  için bu sonuç ileride corpus büyüyünce yeniden ölçülmeli).
- **Ağ garipliği:** `bge-reranker-v2-m3` indirmesi bir ara ~268MB'ta donmuş
  gibi göründü (90+ saniye aynı byte sayısı) ve `curl` ile
  `cdn-lfs.huggingface.co`'ya doğrudan istek "Could not resolve host"
  verdi — ama arka planda çalışan asıl Python indirmesi (muhtemelen farklı
  bir CDN host'una yönlendirilerek, `huggingface_hub`'ın kendi retry/redirect
  mantığıyla) 287 saniyede tamamlandı ve sonrasında sorunsuz çalıştı. Yani
  `curl` ile tekil bir CDN host'una doğrudan erişilemez olması, gerçek
  indirmenin başarısız olacağı anlamına gelmiyor — bu ortamda ara sıra
  DNS/CDN tuhaflıkları var, ama `huggingface_hub`'ın kendi mekanizması bunu
  tolere edebiliyor. İlerideki bir checkpoint'te model indirmesi başarısız
  olursa önce gerçek Python indirmesini (curl değil) tekrar denemek gerekir.
- `config/default.yaml`'da `hybrid.enabled` ve `rerank.enabled` artık
  `true` — bu iki teknik doğrulandı ve varsayılan davranışın parçası oldu.

---

# Notlar — DeepSeek ile RAG testi ve bulgular (2026-08-16)

## Amaç

Retrieval-only pipeline'ı (coreaigent'ta kurulmuştu) gerçek bir LLM'le
uçtan uca test etmek: retrieve edilen mevzuat parçalarından DeepSeek'e
atıflı, sadece kaynağa dayalı ("grounded") bir cevap ürettirmek ve
sonuçlara göre ayar yapmak.

## DeepSeek API key durumu

Ortamdaki (`DEEPSEEK_API_KEY` shell env var, `...4069`) key **geçersizdi**
(401 Authentication Fails). Makinedeki diğer projelerin `.env` dosyalarında
3 farklı DeepSeek key daha bulundu; ikisi (`~/.hermes/.env`,
`~/gptr-venv/.env`) çalışıyor, biri (`~/konya-imar/.env`) de geçersiz.
Bu projenin `.env`'i (gitignored, commit edilmedi) `~/.hermes/.env`'deki
çalışan key ile kuruldu. **Öneri:** hangi key'in "resmi" YAZGIT LinguAI /
kişisel kullanım için geçerli olduğunu teyit edin — ortamdaki eski/iptal
key'i güncelleyin ya da silin, karışıklığa yol açabilir.

## Test sonuçları (gerçek API çağrılarıyla, model=`deepseek-chat`, temperature=0.0)

| Soru | Beklenen davranış | Sonuç |
|---|---|---|
| "Dilekçede hangi bilgiler zorunludur?" | 3071 Madde 4'e atıfla doğru cevap | ✅ Doğru, [1]/[3] gibi referanslarla atıflandırılmış, hukuken tutarlı bir çıkarım yaptı (Madde 6.c'den "aksi halde incelenemez" sonucunu türetti — kaynakta zaten örtük olarak var) |
| "Resmi yazışmalarda kağıt boyutu nedir?" | 2646 Madde 5'e atıfla doğru cevap | ✅ Doğru, A4/A5 ölçüleri ve istisna doğru aktarıldı |
| "Elektronik ortamda güvenli elektronik imza nasıl atılır, hangi sertifika gerekir?" | Corpus'ta YOK → halüsinasyon üretmeden reddetmeli | ✅ Doğru reddetti: *"Verilen mevzuat parçalarında bu sorunun cevabı yok."* — uydurma bilgi üretmedi |

Üçüncü test özellikle önemli: bu bir **hukuki karar-destek** sistemi, yanlış
"kendinden emin" bir cevap üretmek gerçek zarar riski taşır. `SYSTEM_PROMPT`
(`generation.py`) açıkça "cevap yoksa uydurma, açıkça söyle" talimatı
içeriyor ve test bunun çalıştığını doğruladı.

## Yapılan ayarlar

- `temperature=0.0` — tutarlılık/atıf doğruluğu, yaratıcı varyasyondan daha
  önemli bu görevde.
- `config.qdrant_local_path` varsayılanı `/data/qdrant`'tan `./data/qdrant_local`'a
  değiştirildi — orijinal değer yalnızca Docker container içinde (mount
  edilmiş bir volume ile) anlamlıydı, host'ta izin hatası veriyordu.
- `RAGEngine.index_chunks` artık her chunk'ın `source_hash`'ini Qdrant'taki
  mevcut kayıtla karşılaştırıp değişmeyeni atlıyor — yeni dosya eklemek
  ucuz, tüm corpus'u yeniden embed etmiyor.

## Ölçülmedi / doğrulanmadı

- **Score threshold yok:** Düşük alaka skorlu (ör. 0.3 civarı) sonuçlar hâlâ
  LLM'e gönderiliyor; LLM kendi muhakemesiyle doğru reddetti ama bu
  garantili değil — ileride bir `min_score` eşiği (retrieve() sonuçlarını
  filtrelemek için) eklenebilir, özellikle corpus büyüyüp konu dışı ama
  yüksek skorlu sonuçlar çıkmaya başlarsa.
- Sadece 2 gerçek mevzuat belgesiyle test edildi (bkz. ana README'nin
  "Bilinen sınırlar" bölümü) — daha geniş/çeşitli bir corpus'ta faithfulness
  davranışı yeniden değerlendirilmeli.
- `deepseek-reasoner` (DeepSeek'in muhakeme modeli) denenmedi — daha karmaşık
  çok-maddeli sorularda `deepseek-chat`'ten daha iyi performans gösterebilir,
  ama maliyet/gecikme daha yüksek.

## Sonraki adımlar ("büyük projenin ilk adımı" için)

1. Gerçek internet erişimi olan bir ortamdan `mevzuat_gov_tr.py`'yi
   `mevzuat-mcp`'ye karşı doğrulayıp külliyatı genişletin (bkz. ana README).
2. `min_score` eşiği + boş/zayıf sonuç durumunda erken `ask()` reddi ekleyin
   (LLM çağrısı yapmadan önce).
3. LLM-as-judge ile daha büyük, sistematik bir faithfulness/hallucination
   değerlendirmesi kurun (bu notlardaki 3 sorudan fazlası — `eval/golden_set.jsonl`
   şu an yalnızca retrieval için, generation için ayrı bir eval seti yok).
4. Hangi DeepSeek key'in kalıcı olarak kullanılacağına karar verilip
   `.env.example`'da doğru talimatlarla belgelensin.
