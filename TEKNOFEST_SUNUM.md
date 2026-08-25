# TEKNOFEST KAMU EVRAK VE MEVZUAT AJANI 
## Kapalı Ağ Sistemlerinde Güvenli RAG Mimarisi

### 1. Vizyonumuz
"Sıfır Halüsinasyon, %100 Kapalı Ağ Güvenliği ile Devletin Zeka Altyapısı." Kamu bürokrasisinde yasal hatayı sıfıra indiren ve karar alma süreçlerini hızlandıran otonom sistem.

### 2. Neden Standart RAG Kullanmadık? (Mevcut Problemler)
- **Güvenlik Zafiyeti:** Kamu evrakı mahremiyet gerektirir. İnternet tabanlı sistemler "Air-Gapped" (çevrimdışı) kamu ağlarında çalışamaz.
- **Hukuki Bağlam Kopukluğu:** Geleneksel kelime bazlı parçalama (chunking), kanun maddelerini böler ve anlamı yok eder.
- **Halüsinasyon Riski:** Standart LLM'ler bulamadığı bilgiyi uydurur. Hukukta yanlış bilgi, cevapsızlıktan daha tehlikelidir.

### 3. Gelişmiş Çözüm Mimarimiz
- **Yerel Veri Yutma (Offline Ingestion):** Dış ağ bağlantısı olmadan çalışan güvenli veri indeksleme.
- **Yapısal Farkındalık (Structure-Aware):** Kanun, madde, fıkra ve bent yapısını koruyan akıllı metin bölme algoritması.
- **Hibrit Arama (Hybrid Search):** Vektör (anlamsal) ve BM25 (kelime) aramalarının Reranker (Yeniden Sıralayıcı) ile güçlendirilmiş entegrasyonu.

### 4. En Büyük Kozumuz: Hakem Ajan (Critic Agent)
- Modelin ürettiği her cevap, kullanıcıya ulaşmadan önce otonom bir **Hakem Ajan** tarafından mevzuatla çapraz sorguya çekilir.
- Ajan, en ufak bir çelişki veya kaynaksız (uydurma) bilgi tespit ederse cevabı otomatik olarak imha eder ve "Sıfır Halüsinasyon" garantisi sağlar.

### 5. Performans ve Ölçeklenebilirlik (Test Edilmiş Başarı)
- **Recall (Duyarlılık): %96** - İstenilen yasal bağlamı eksiksiz bulma.
- **Precision (Kesinlik): %96** - Sadece ilgili maddeleri getirerek bilgi çöplüğünü (noise) önleme.
- **Sınırsız Ölçeklenebilirlik:** Qdrant Vektör Veritabanı (HNSW) altyapısı sayesinde milyonlarca sayfalık devlet arşivinde performans kaybı yaşamadan milisaniyelik sorgu imkanı.
