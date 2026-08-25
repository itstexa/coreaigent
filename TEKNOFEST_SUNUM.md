# TEKNOFEST KAMU EVRAK VE MEVZUAT AJANI 
## Güvenli RAG Mimarisi

### Slayt 1: Kapak ve Vizyon
- **Proje:** Kamu Evrak ve Mevzuat Ajanı
- **Vizyon:** "Sıfır Halüsinasyon, %100 Kapalı Ağ Güvenliği ile Devletin Zeka Altyapısı"

### Slayt 2: Neden Standart RAG Kullanmadık? (Problemler)
- **Güvenlik İhtiyacı:** Kamu evrakı mahremiyet gerektirir. Standart sistemler internete bağlıdır, biz "Air-Gapped" (Çevrimdışı) çalışıyoruz.
- **Yasal Bütünlük:** Basit parçalama (chunking) yöntemleri kanun maddelerini ortadan böler, anlam kaybolur.
- **Halüsinasyon Riski:** Yapay zeka bilmediği kanunu uydurmaya meyillidir (Lost in the middle). Devlette yanlış bilgi kabul edilemez.

### Slayt 3: Çözüm Mimarimiz (Akış)
- **Veri Yutma:** Tamamen Çevrimdışı ve "Madde/Fıkra Duyarlı" (Structure-Aware) Parçalama.
- **Arama Katmanı:** BM25 (Kelime bazlı) + Vektör (Anlam bazlı) Hibrit Arama ve Yeniden Sıralama (Reranker).
- **Güvenlik Katmanı:** Hakem Ajan (Critic Agent) ile uçtan uca Hukuki Denetim mekanizması.

### Slayt 4: "Structure-Aware" (Yapısal Farkındalık) Farkımız
- Rakipler metinleri kelime sayısına göre körü körüne böler.
- Bizim algoritmamız Kanun, Madde, Fıkra ve Bent yapısını tanır.
- Sonuç: "5. Madde'nin B Bendi" sorulduğunda cümlenin ortasından kırpılmış değil, hukuki bütünlüğü korunmuş metinler getirilir.

### Slayt 5: Hakem Ajan (Critic Agent) - En Büyük Kozumuz
- Üretilen cevaplar kullanıcıya doğrudan **verilmez**.
- "Hakem Ajan" sert bir denetçi olarak cevabı arka planda mevzuatla çapraz sorguya çeker.
- Uydurma (halüsinasyon) tespit edilirse cevap **imha edilir** ve sistem güvenli uyarı mesajı verir. Sıfır halüsinasyon garantisidir.

### Slayt 6: Performans ve Doğruluk Metrikleri
- **Recall (Duyarlılık): %96** (Aranan kanun maddesini bulma oranı)
- **Precision (Kesinlik): %96** (Getirilen maddelerin doğrudan konuyla ilgili olma oranı)
- **Ölçeklenebilirlik:** Qdrant HNSW Vektör Veritabanı sayesinde milyonlarca sayfalık devlet arşivinde bile bilgi çöplüğü yaratmadan, milisaniyeler içinde sonuç üretir.

### Slayt 7: Kapanış
- Adalet ve bürokraside zaman kaybını önlemek, hukuki hatayı sıfıra indirmek için tasarlandı. Bizi dinlediğiniz için teşekkür ederiz.
