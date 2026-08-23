# Paralel Ajanlarla İyileştirme Turu — 2026-08-22/23

`docs/IMPROVEMENT_IDEAS.md`'deki 29 fikirden key gerektirmeyen 6 tanesini
6 izole git worktree ajanına paralel olarak uygulattık. Bu rapor süreci,
karşılaşılan gerçek sorunları ve sonuçları belgeliyor — gelecekte benzer bir
paralel-ajan turu yapılacaksa buradaki dersler tekrarlanmasın diye.

## Uygulanan 6 fikir

| # | Fikir | Commit |
|---|---|---|
| 1 | Adaptif rerank kesimi (`adaptive_cutoff`) | `6042470`, `1e12624` |
| 2 | Embedding batch_size GPU kalibrasyon scripti | `cce3a20` |
| 3 | Hard-negative eval seti (6 gerçek çift) | `83caf2b` |
| 4 | Eval history / drift paneli | `83caf2b` |
| 5 | Mevzuat hiyerarşisi + tablo/ek uyarı bayrağı | `77b22d8` |
| 6 | PII saklama/silme (retention) politikası | `77b22d8` |

Tümü varsayılan davranışı bozmadan, testlerle doğrulanarak eklendi. Tam
suite: ~159 test, 1 önceden var olan ilgisiz hata dışında yeşil.

## Karşılaşılan gerçek sorunlar

### 1. Worktree'lerin çoğu eski bir commit'ten başlamıştı

6 ajan da aynı anda, art arda `Agent` çağrılarıyla başlatıldı — ama her
worktree, o an ana branch'in HEAD'i neredeyse (yarış koşulu). Sonuç: yalnızca
2 ajan (adaptif rerank, batch kalibrasyon) güncel taban üzerindeydi ve
doğrudan `git merge` ile birleştirilebildi. Diğer 4 ajan (retention,
eval-history, hard-negative, mevzuat-hiyerarşisi) çok daha eski bir commit'te
başladı — `durum` alanı, `prompt_safety.py`, `citation_expansion.py` gibi o
sıradaki işler onların worktree'sinde hiç yoktu.

**Çözüm:** Kör `git merge` yerine her worktree'nin diff'i elle incelendi;
yeni/bağımsız dosyalar (retention.py, eval_history.py, hard_negatives.jsonl
gibi) doğrudan kopyalandı, paylaşılan dosyalara (models.py,
legal_structure_parser.py, chunker.py, store.py, generation.py) dokunan
değişiklikler mevcut koda göre elle yeniden uygulandı.

**Ders:** Paralel worktree ajanları başlatırken, özellikle art arda birden
fazla ajan aynı dosyaları değiştirecekse, ya (a) hepsini tam olarak aynı
commit'ten başlatmak için önce tek bir senkron commit/push yapıp öyle
başlatmak, ya da (b) her ajanın işini kabul etmeden önce worktree'nin taban
commit'ini kontrol etmek gerekiyor (`git rev-list --count HEAD..<ana-branch>`).

### 2. `durum` alanı Qdrant'a hiç yazılmıyordu (kritik bug, önceki turda bulundu)

Bu bug bu turdan önce (yürürlük durumu takibi eklenirken) bulunup düzeltildi,
ama **aynı hatanın tekrarlanmaması** bu turun tasarım kriteri oldu: mevzuat
hiyerarşisi ajanına açıkça uyarıldı, o da kendi eklediği `mevzuat_turu` ve
`contains_table` alanlarını store.py'nin 4 noktasında (yazma + 3 okuma)
senkron tutup gerçek bir Qdrant round-trip testiyle kanıtladı.

### 3. Kendi taşıma sürecimde 2 hata yaptım

- `legal_structure_parser.py`'ye `_looks_like_table_line` fonksiyonunu
  tanımladım ama parse döngüsüne **bağlamayı unuttum** — fonksiyon var,
  hiç çağrılmıyordu. Testler bunu yakaladı (`contains_table` hep `False`
  çıktı), düzeltildi.
- Round-trip testinde "tablo" kelimesini hem sorgu hem madde 2'nin metninde
  ("tablo değil") kullanmak, embedding/BM25'in yanlış maddeyi çekmesine yol
  açan flaky bir test tasarımıydı. `engine.retrieve()` yerine
  `store.scroll_all_chunks()` ile deterministik hale getirildi.

### 4. 6 paralel ajan + kendi doğrulamam aynı GPU'yu (8GB) paylaştı

Art arda/eşzamanlı çalışan pytest süreçleri (her biri embedding + reranker
modeli yüklüyor) GPU'yu doyurdu (%90+ dolu), bu da **gerçek olmayan** test
hatalarına yol açtı: "Embedding model yüklenemedi", "CUDA out of memory".
En az 3 ayrı seferde aynı testler (`test_citation_expansion.py`,
`test_bm25_invalidate_batching.py`, `test_audit_log.py`, `test_min_score.py`)
GPU doluyken FAILED, boşken PASSED verdi.

**Çözüm:** Ajanların kendi arka plan test süreçleri, ajan tamamlanma raporu
gönderdikten SONRA da bazen arka planda takılı kalmaya devam etti (yetim
process). `ps aux` + `nvidia-smi` ile tespit edilip, işi zaten tamamlanmış
ajanların yetim süreçleri `kill` edildi, GPU boşaltılıp kritik testler temiz
ortamda yeniden doğrulandı.

**Ders:** Paralel ajanlar GPU-yoğun test paketleri çalıştırıyorsa, "FAILED"
sonucu körü körüne gerçek bir regresyon sanılmamalı — önce `nvidia-smi` ile
GPU/süreç yükü kontrol edilmeli, şüpheli hata varsa GPU boşken izole olarak
yeniden koşulmalı.

### 5. Gerçek bir regresyon da bulundu (GPU'yla ilgisiz)

`test_min_score.py`, `engine.config.rerank`'i bare `MagicMock()` ile
mock'luyordu. Adaptif rerank kesiminin `getattr(config, "adaptive_cutoff",
False)` kontrolü, Mock'un auto-vivify edilen attribute'unun varsayılan
olarak "truthy" olması yüzünden yanlışlıkla `True` sayıldı — `TypeError`.
`config.adaptive_cutoff is True` kontrolüne geçilerek düzeltildi (hem
kaynak kodda hem testin kendi mock kurulumunda, defans katmanı olarak).

## Canlı doğrulama (LLM'siz, gerçek çalıştırma)

Testlerin ötesinde, tüm parçaların birlikte gerçekten çalıştığını canlı bir
çalıştırmayla doğruladık (`RAGConfig.citation_expansion.enabled=True`,
gerçek corpus, gerçek Qdrant, LLM yok):

| Soru | Sonuç |
|---|---|
| "Hangi dilekçeler incelenemez?" | Madde 6 (0.9969) + **Madde 4 "(atıf üzerinden genişletildi)"** (0.8972) — `[9]` canlıda çalışıyor |
| "Resmi yazışmalarda kağıt boyutu nedir?" | 2646 Madde 5, `mevzuat_turu=yönetmelik` doğru çıkarıldı (başlıkta "Kanun" hiç geçmiyor) |
| "Türkiye'nin başkenti neresidir?" | **0 sonuç** — `min_score` corpus-dışı soruyu doğru eledi |

Router/Multi-Query/HyDE/CRAG her sorguda 401 alıp güvenli şekilde (retrieve'e
düşerek / SUFFICIENT varsayarak) devam etti — sistemi kilitlemedi, bu da
kendi başına doğru bir davranış.

## Kapsam dışı kalanlar

`docs/IMPROVEMENT_IDEAS.md`'deki 4 fikir hâlâ 🔴 (DeepSeek key gerektiriyor):
cümle bazlı post-hoc doğrulama, yapılandırılmış (JSON mode) çıktı,
`deepseek-reasoner` fallback, çok-parçalı soru ayrıştırma, faithfulness eval
seti, ablation'ın generation'a genişletilmesi. Kullanıcı bazlı yetkilendirme
(Güvenlik #3) ve Resmi Gazete takibinin kapatılması de kapsam dışı bırakıldı
(sırasıyla çok geniş kapsam / gerçek ağ erişimi gerekiyor).
