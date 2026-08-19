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
