# Mevzuat Metni Normalizasyon Standardı

Sürüm: 1.0.0 (`mevzuat_rag.text_norm.TEXT_NORM_VERSION`)

## 1. Kapsam ve amaç

Bu standart, mevzuat metinlerinin chunking çıkışında embedding'e girmeden önce ve
lexical (BM25) sorgu/doküman metinlerinde uygulanan normalizasyon kurallarını tanımlar.

Amaç; aynı yasal ifadenin farklı kaynaklardan, boşluk/özel karakter farklarıyla gelse
bile aynı metin temsiline indirgenmesini sağlamak, BM25 ve embedding davranışını
tutarlı kılmak ve normalizasyon kuralı değiştiğinde index'in sessizce bozulmasını
önlemektir.

## 2. Profiller

- `embedding`: Vektör üretimi için kullanılır. Case korunur. NFC, görünmez karakter
  temizliği, tırnak normalleştirme, satır sonu heceleme birleştirme ve whitespace
  kuralları uygulanır.
- `lexical`: BM25/lexical arama için kullanılır. `embedding` çıktısına ek olarak
  Türkçe-farkında lowercase uygulanır ve Türkçe karakterler ASCII-fold edilir.
- `display`: Kullanıcıya gösterim içindir. NFC, görünmez karakter ve whitespace kuralları
  uygulanır; tire birleştirme ve tırnak düzleştirme uygulanmaz.

## 3. Kurallar

### 3.1 Unicode normalizasyon

Tüm profillerde `unicodedata.normalize("NFC", text)` uygulanır. Aynı harfin compose/decompose
formlarının farklı sayılmasını engeller.

### 3.2 Türkçe karakter bütünlüğü

Python `str.lower()` / `str.upper()` doğrudan kullanılmaz. Python'da `"İ".lower()` bozuk
sonuç üretebilir (`i` + combining dot). Bu yüzden Türkçe-farkında yardımcılar kullanılır:

- `_turkish_lower`: `I` → `ı`, `İ` → `i`, ardından `.lower()`.
- `_turkish_upper`: `i` → `İ`, `ı` → `I`, ardından `.upper()`.

Embedding metni case korunarak saklanır. Lowercase sadece `lexical` profilinde üretilir.

### 3.3 Whitespace

- Tab karakteri boşluğa çevrilir.
- CRLF ve CR, `\n` olarak normalize edilir.
- Ardışık boşluklar tek boşluğa indirilir.
- İkiden fazla ardışık `\n`, iki `\n` olarak sınırlanır.
- Metnin başındaki ve sonundaki whitespace temizlenir.

### 3.4 Tire ve satır sonu hecelemesi

Satır sonu heceleme tiresi birleştirilir: `kanun-\nun` → `kanunun`.

Birleştirme yalnızca tire öncesi ve sonrası harf ise yapılır. Böylece madde
numaralarındaki tire korunur: `MADDE 5-` dokunulmaz.

### 3.5 Görünmez karakterler

- Zero-width space (U+200B) kaldırılır.
- Soft hyphen (U+00AD) kaldırılır.
- Non-breaking space (U+00A0) normal boşluğa çevrilir.

### 3.6 Tırnak/apostrof

Eğik/akıllı tırnaklar düz forma normalize edilir:

- `'` / `'` → `'`
- `"` / `"` → `"`

Bu, "5018 sayılı Kanun'un" gibi ifadelerde tutarlılık için kritiktir.

### 3.7 Korunan biçimler

Aşağıdakiler normalizasyon tarafından bozulmaz:

- Madde/fıkra/bent numaralandırması
- Evrak sayı formatı
- Tarih formatları
- Sayısal değerler
- Romen rakamları
- Parantez içi atıflar

### 3.8 Uygulanmayan işlemler

- Stopword temizliği yapılmaz: mevzuat metninde her kelime anlam taşır.
- Embedding tarafında stemming yapılmaz; yalnızca BM25 kanalı ilgili tokenizer'ı kullanır.
- Embedding tarafında lowercase yapılmaz.
- Noktalama temizliği yapılmaz.

## 4. Sürümleme ve index etkisi

`TEXT_NORM_VERSION` semver string'dir. Normalizasyon kurallarında chunk metnini veya
token üretimini etkileyen her değişiklik bu sürümü artırmalıdır.

Qdrant index metadata'sına yazılan `text_norm_version` ile karşılaştırma yapılır.
Versiyon değiştiyse eski vektörlerle yeni metinler uyumsuz olacağı için
`IndexMetadataMismatch` ile fail-fast davranılır. Bu durumda ilgili koleksiyon yeniden
ingest edilmelidir.

## 5. Uygulama noktası ve geriye dönük uyumluluk

`normalize_text()` tek yerde çağrılır: chunker'ın çıkışında (`chunker.py`'nin
`flush()` ve tek-fıkra dallarında), embedding'e girmeden önce — `LegislationChunk.text`'e
yazılan metin zaten `profile="embedding"` ile normalize edilmiş metindir. `source_hash`
bu normalize edilmiş metin üzerinden hesaplanır, böylece normalizasyon kuralı
değiştiğinde hash de değişir ve ilgili chunk otomatik olarak yeniden embed edilir.

`embed_texts()`/`embed_query()` girdiyi TEKRAR normalize etmez — girdinin zaten
normalize edilmiş olduğunu varsayar. Sorgu tarafında (`pipeline/stages/hybrid_retrieve.py`,
`pipeline/stages/crag.py`) her `embed_query`/`embed_texts` çağrısından önce sorgu/HyDE
metni `normalize_text(text, profile="embedding")` ile normalize edilir.

`QdrantStore(text_norm_version=...)` parametresi varsayılan olarak `None`'dır — bu
sürümlemeden ÖNCE oluşturulmuş bir index (`index_meta_{collection}.json` dosyasında
`text_norm_version` alanı yok) `text_norm_version=None` ile hâlâ sorunsuz açılır (kontrol
atlanır). Ancak bu projede zaten mevcut olan `data/qdrant_local` altındaki test/dev
koleksiyonları, bu değişiklikten SONRA `text_norm_version="1.0.0"` ile açılırsa
`IndexMetadataMismatch` fırlatır çünkü o koleksiyonun chunk'ları normalizasyondan
ÖNCE indekslenmiştir ve gerçekten uyumsuzdur — bu durumda `python -m
mevzuat_rag.ingest_pipeline` ile yeniden ingest edilmesi gerekir (bkz. MIGRATION.md).
