# mevzuat-rag — İyileştirme Fikirleri

6 paralel alt-ajanın (her biri kodu okuyup kendi alanında araştırma yaptı,
kod yazmadı) 2026-08-22 tarihinde ürettiği 29 fikrin derlemesi. Her fikir
gerçek koda/ölçüme referansla gerekçelendirildi — genel RAG tavsiyesi değil.

**Öncelik etiketleri:**
- 🟢 **Uygulandı** (bu oturumda, aşağıda listelenen 6 fikir)
- 🟡 **Key gerekmiyor, uygulanmadı** (gelecek iş, DeepSeek key beklemeden yapılabilir)
- 🔴 **DeepSeek key gerekiyor** (bu oturumda çalışan key yoktu, ertelendi)

---

## 1. Retrieval & Ranking Kalitesi

1. 🟢 **Kısaltılmış hukuki atıf formları ("TCK m.5", "5. md.")** — `citation_ref.py`
   yalnızca "5. maddede" tam yazımını yakalıyordu, kısaltmaları atlıyordu.
2. 🟡 **Adaptif rerank kesimi** — `rerank.py`'de `top_n=5` sabit; skor
   dizisinde ani düşüş (gap/elbow) tespit edilip kesim buna göre ayarlanabilir.
3. 🟡 **BM25 → gerçek ters-indeks** — `bm25_index.py`'nin kendi docstring'i
   "birkaç bin chunk'a kadar" diyor, 1M PDF hedefiyle çelişiyor. Öneri:
   Qdrant native sparse vectors (yeni servis eklemeden) > Tantivy > Meilisearch.
4. 🟡 **Hard-negative eval seti** — golden_set.jsonl'da yalnızca pozitif
   örnekler var, reranker'ın gerçek ayrım gücü ölçülmüyor.

## 2. Generation & Sadakat

1. 🔴 **Cümle/iddia bazlı doğrulama** — post_hoc_verify şu an TÜM cevabı tek
   SUPPORTED/UNSUPPORTED kararıyla değerlendiriyor; kısmi hata tüm cevabı siliyor.
2. 🔴 **Yapılandırılmış çıktı (JSON mode)** — regex tabanlı `[N]` ayıklama
   yerine DeepSeek'in `response_format=json_object` desteğiyle garanti şema.
3. 🔴 **`deepseek-reasoner` ile ikinci-geçiş** — NOTES.md'nin kendi "denenmedi"
   dediği nokta; CRAG PARTIAL/post_hoc UNSUPPORTED'ta fallback.
4. 🔴 **Çok-parçalı (multi-intent) soru ayrıştırma** — bileşik sorularda
   tek retrieval her alt-niyeti eşit yakalamıyor.
5. 🔴 **Yalnızca SUPPORTED cevapları önbellekleyen semantic cache**.

## 3. Güvenlik, Gizlilik ve Uyumluluk

1. 🟢 **Prompt injection savunması** — retrieved chunk metni hiç
   sanitizasyon olmadan LLM prompt'una enjekte ediliyordu; PDF'ler dış
   kaynaklardan geliyor (`pdf_corpus.py`), kötü niyetli içerik gömülebilir.
2. 🟢 **Audit log** — kim/ne zaman/ne sordu/hangi chunk'lar döndü kaydı
   hiç yoktu; kamu evrak sisteminde hesap verebilirlik için gerekli.
3. 🟡 **Kullanıcı bazlı yetkilendirme/erişim kontrolü** — RBAC + Qdrant
   metadata-filtreli erişim; yüksek kapsam, contract şema değişikliği gerekir.
4. 🟢 **Secrets yönetimi** — bu oturumun kendi bulgusu: 10 farklı DeepSeek
   key dosya sistemine saçılmış, hepsi geçersiz, hiçbiri secrets manager'da
   değildi.
5. 🟡 **PII redaksiyonu sonrası veri saklama/silme politikası** — Qdrant'ta
   TTL/silme mekanizması yok, KVKK'nın "amaç sona erince sil" ilkesi karşılanmıyor.

## 4. Ölçek ve Performans

1. 🟢 **BM25 invalidate() ingestion'da her dokümanda tetikleniyordu** — 1M
   PDF ingest sırasında art arda sorgu gelirse BM25 defalarca sıfırdan
   kurulma riski taşıyordu (en kritik bulgu, kendi PDF ingestion işimizle
   doğrudan çelişiyordu).
2. 🟡 **BM25 → Qdrant native sparse vectors** — (bkz. Retrieval #3, aynı fikir).
3. 🟡 **Embedding batch_size otomatik kalibrasyon** — GPU doygunluk noktası
   hiç ölçülmedi, sabit `batch_size=32`.
4. 🟡 **Semantic cache** (genel, faithfulness'a bağlı olmayan hali).
5. 🟡 **Dağıtık iş kuyruğu** — henüz gerekmiyor, checkpoint formatı zaten
   buna taşınabilir şekilde tasarlı, ertelenmeli.

## 5. Gözlemlenebilirlik, Değerlendirme ve Test

1. 🔴 **Faithfulness/halüsinasyon eval seti** — corpus-içi puanlama LLM-judge gerektirir.
2. 🟢 **CI'a retrieval eval entegrasyonu** — retrieval-only kısmı key gerektirmiyor.
3. 🟢 **Golden set büyüt + negatif örnekler** — 9 soru çok küçük, corpus-dışı
   hiç örnek yoktu.
4. 🟡 **Drift/regresyon paneli** — `eval_history.jsonl`, zamanla Recall@K trendini gösterir.
5. 🔴 **Ablation'ı generation'a genişlet** — faithfulness set'ine bağımlı.

## 6. Türk Mevzuatına Özgü Doğruluk

1. 🟢 **Yürürlük durumu takibi (mülga/değişik)** — `ChunkMetadata`'da hiç
   yürürlük alanı yoktu; mülga bir madde güncelmiş gibi sunulabiliyordu —
   hukuki karar-destek bağlamında en riskli boşluk.
2. 🟡 **Mevzuat hiyerarşisi bilgisi** (Anayasa>Kanun>KHK>Yönetmelik>Tebliğ).
3. 🟡 **Tablo/ek çıkarımı** — parser tablo-farkında değil; MVP: `contains_table` bayrağı.
4. 🟡 **Resmi Gazete takibinin kapatılması** — `list_updates()` kanun_no
   çıkarmıyor, `mevzuat_gov_tr.search()` no-op; gerçek ağ erişimi olmadan bloke.
5. 🟡 **İçtihat/emsal karar entegrasyonu** — en geniş kapsamlı, ertelenmeli.

---

## Bu oturumda uygulanan 6 fikir

| # | Fikir | Dosyalar |
|---|---|---|
| 1 | BM25 invalidate batching (ingest sırasında) | `ingest_pipeline.py`, `pipeline/bm25_index.py` |
| 2 | Yürürlük durumu takibi (mülga/değişik) | `models.py`, `legal_structure_parser.py`, `generation.py` |
| 3 | Kısaltılmış atıf formları (m.5, md.5) | `citation_ref.py` |
| 4 | Prompt injection savunması | `generation.py` |
| 5 | Audit log | yeni: `audit_log.py` |
| 6 | Golden set genişletme + negatif örnekler | `eval/golden_set.jsonl` |

Detaylar ve testler için ilgili commit mesajlarına bakın
(`git log --oneline` — 2026-08-22 sonrası).
