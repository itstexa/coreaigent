# Proposals Register — Ürünleştirme ve yarışma vitrini

Bu kayıt, çalışan ürünün gerçek kullanıcı akışı gözlemlendikten sonra
çıkarılmış önerileri içerir. Hiçbiri onaylanmış kapsam değildir; bir öneri,
insan operatör `DESIGN.md` içine taşıyana kadar yalnızca adaydır.

## Index

| ID | Başlık | Sınıf | Lens | Maliyet | Güven | Durum | Sonuç |
|---|---|---|---|---|---|---|---|
| PP-1 | Personel havuzu ve manuel yeniden atama | PP | affordance | multi-pass | high | Proposed | — |
| PP-2 | Vatandaş için bekleme ve geri dönüş güvencesi | PP | waiting | a pass | high | Proposed | — |
| PP-3 | İnsan incelemesi için düzeltme yolu | PP | recovery | multi-pass | high | Proposed | — |
| PP-4 | Model/servis durumunu doğru adlandırma | PP | coherence | a pass | high | Proposed | — |
| PP-5 | Sonuç etiketi ve kalite ölçümü | PP | completeness | multi-pass | medium | Proposed | — |
| PD-1 | Duygu sinyalinden güvenli destek yönlendirmesine | PD | delight | needs architecture | high | Proposed | — |
| PD-2 | Anonim, denetlenebilir öğrenme defteri | PD | the ambitious version | needs architecture | high | Proposed | — |
| PD-3 | Dilekçeden sonuçlanmaya kurum hafızası | PD | the whole product | multi-pass | medium | Proposed | — |

## Refinements (PP)

### PP-1 | Personel havuzu ve manuel yeniden atama
**Lens:** affordance
**Evidence:** Panelde dosya personel önerisini ve açık dosya yükünü gösteriyor; fakat personel ekleme, pasife alma veya operatörün öneriyi güvenli biçimde değiştireceği bir kontrol yok.
**Proposal:** ADMIN-only personel havuzu yönetimi, atanabilirlik durumu ve manuel yeniden atama eklenmeli. Her değişiklik gerekçesiyle aksiyon günlüğüne yazılmalı.
**Value:** Demo verisinden gerçek operasyon masasına geçilir; yanlış atama veritabanına müdahale etmeden düzeltilebilir.
**Cost:** multi-pass
**Confidence:** high
**Against:** Kimlik sistemi ve rol modeli yarışma süresini büyütür; kısa demoda mevcut otomatik öneri yeterli görülebilir.

### PP-2 | Vatandaş için bekleme ve geri dönüş güvencesi
**Lens:** waiting
**Evidence:** Dilekçe gönderiminden sonra sonuç ekranı hızlıca geliyor; ancak uzun Jamba üretiminde yaklaşık süre, sekme kapanırsa ne olacağı veya referansla geri dönme yolu açıkça gösterilmiyor.
**Proposal:** Aşama başına canlı durum, tahmini bekleme aralığı, “sekme kapanırsa kaydınız korunur” açıklaması ve referansla devam etme bağlantısı eklenmeli.
**Value:** Kullanıcı aynı dilekçeyi tekrar göndermez; yavaş yerel modelin güvenilirliği görünür hâle gelir.
**Cost:** a pass
**Confidence:** high
**Against:** Tahminler donanım ve kuyruk yüküne göre değişir; yanlış ETA güveni azaltabilir.

### PP-3 | İnsan incelemesi için düzeltme yolu
**Lens:** recovery
**Evidence:** Gerçek serbest metin denemesinde %67 güvenle `needs_review` sonucu ve “Başvurumu tamamla” eylemi görüldü; operatör sınıflandırma önerisini düzeltecek veya nedenini işaretleyecek görünür bir yol yok.
**Proposal:** İnsan incelemesi ekranında kategori/birim düzeltmesi, düzeltme nedeni ve yeniden çalıştırma eylemi sağlanmalı; bu karar öğrenme adayıyla ilişkilendirilmeli.
**Value:** Düşük güvenli dosya çıkmaz sokak olmaktan çıkar ve en değerli etiketler kontrollü biçimde toplanır.
**Cost:** multi-pass
**Confidence:** high
**Against:** Yanlış operatör etiketi veri kalitesini bozabilir; rol ve onay sınırı olmadan açılmamalı.

### PP-4 | Model/servis durumunu doğru adlandırma
**Lens:** coherence
**Evidence:** Önceki panel gözleminde rozet 4/4 servis diyordu; ürünün gerçek kapanışında RAG uyumluluk sınırı ve Jamba katmanı görünmüyordu. Bu turda rozet altı servisi raporlayacak şekilde düzeltildi.
**Proposal:** Rozet, altı servisin hazır olmasını ve RAG’ın workflow içindeki uyumluluk sınırı olduğunu ayrı adlandırmaya devam etmeli; “Jamba sınıflandırma” gibi üretici olmayan bileşenleri model diye etiketlememeli.
**Value:** Jüri ve operatör mock, gerçek model ve gerçek retrieval sınırlarını tek bakışta doğru anlar.
**Cost:** a pass
**Confidence:** high
**Against:** Daha fazla teknik ayrıntı ilk bakışı ağırlaştırabilir; ayrıntı tooltip veya durum panelinde tutulmalı.

### PP-5 | Sonuç etiketi ve kalite ölçümü
**Lens:** completeness
**Evidence:** Case detayında taslak, yönlendirme ve benzer geçmiş görünür; fakat “çözüldü/çözülmedi”, gerçek işlem süresi ve operatör düzeltme sonucu için standart kapanış etiketi yok.
**Proposal:** Kapanışta sonuç etiketi, çözüm süresi, yönlendirme doğru/yanlış geri bildirimi ve isteğe bağlı kısa neden alınmalı; dashboard bu etiketleri oran ve trend olarak göstermeli.
**Value:** Güven skoru ve personel ataması varsayım değil, ölçülen sonuçla iyileşir.
**Cost:** multi-pass
**Confidence:** medium
**Against:** İnsanların kapanış etiketi girmesi ek iş yaratır; ilk sürümde üç seçenekli kısa form kullanılmalı.

## Directions (PD)

### PD-1 | Duygu sinyalinden güvenli destek yönlendirmesine
**Lens:** delight
**Evidence:** Ürün agresiflik skorunu ve tekrar konu sinyalini dosya detayında görünür kılıyor; bu, salt sınıflandırma yapan bir rakibin göstermediği operasyonel bağlamdır.
**Proposal:** Skoru “vatandaş agresif” diye damgalamak yerine iletişim gerilimi, tekrar başvuru ve öncelikli insan desteği sinyali olarak adlandırın. Yüksek sinyalde daha deneyimli personele öneri ve empatik yanıt şablonu üretin.
**Value:** Duygu özelliği cezalandırma değil çözüm hızlandırma hikâyesine dönüşür; jüriye etik ve ölçülebilir bir farklılaşma sunar.
**Cost:** needs architecture
**Confidence:** high
**Against:** Duygu çıkarımı hatalı olabilir; tıbbi/psikolojik iddia yapılmamalı ve personel kararı yerine geçmemeli.

### PD-2 | Anonim, denetlenebilir öğrenme defteri
**Lens:** the ambitious version
**Evidence:** Kontrollü öğrenme adayı artık PII azaltımıyla kaydedilebiliyor; ancak adayın kim tarafından onaylandığı, hangi revizyondan geldiği ve dışa aktarım/eval sonucu ürün yüzeyinde henüz tek bir hikâye değil.
**Proposal:** Her düzeltme ve kapanış kararı anonim örnek, kaynak revizyonu, onaylayan rolü ve değerlendirme sonucu ile deftere alınmalı. Fine-tuning yalnız toplu onaydan sonra, sürümlü ve geri alınabilir bir yayın adımı olmalı.
**Value:** “Model kendini eğitiyor” iddiası yerine güvenilir insan-döngülü veri ürünü ortaya çıkar; kurum hafızası denetlenebilir kalır.
**Cost:** needs architecture
**Confidence:** high
**Against:** Veri yönetişimi, saklama süresi ve değerlendirme hattı ciddi kapsamdır; yarışma demosunda yalnız aday kuyruğu gösterilebilir.

### PD-3 | Dilekçeden sonuçlanmaya kurum hafızası
**Lens:** the whole product
**Evidence:** Case detayında benzer geçmiş başvurular, çözülme durumu ve yönlendirme görünür; fakat bu bilgi yeni başvurunun riskini veya beklenen çözüm yolunu özetleyen tek bir “sonraki en iyi adım”a dönüşmüyor.
**Proposal:** Benzer vakaları yalnız listelemek yerine zaman, birim, çözüm oranı ve kullanılan mevzuatla özetleyen açıklanabilir vaka hafızası oluşturun; operatöre önerilen sonraki adımı ve dayanağını gösterin.
**Value:** CoreAIgent “gelen metni sınıflandıran araç”tan “kurumun çözüm hafızası”na yükselir.
**Cost:** multi-pass
**Confidence:** medium
**Against:** Geçmiş kararlar hatalı veya mevzuatı eskimiş olabilir; her öneri kaynak ve tarih ile sınırlanmalı, otomatik karar verilmemeli.
