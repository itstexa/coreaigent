# CoreAIgent — 4+1 dakikalık ürün anlatımı ve jüri teknik soru-cevap rehberi

Bu metin, sahnede okunacak kelimesi kelimesine bir senaryo değil; doğal
konuşma ritmini koruyan, demoda hangi ekranı ne zaman göstereceğini anlatan
bir akıştır. Süreler yaklaşık değerlerdir.

## 4 dakikalık hikâye

### 0:00–0:40 · Problem: vatandaşın cümlesi kurumda kaybolmasın

“Bir vatandaş belediyeye başvurduğunda elinde çoğu zaman yalnızca kendi
cümleleri vardır: ‘Gece yarısı yine uyuyamadık, artık bir çözüm istiyoruz.’
Kurumun elinde ise bu cümleyi doğru birime, doğru kişiye, doğru öncelikle ve
doğru resmî yazıyla ulaştırma sorumluluğu vardır. Bugün bu aradaki iş; farklı
ekranlar, elle kopyalama ve kişiden kişiye değişen yorumlarla ilerleyebiliyor.

CoreAIgent’in çıkış noktası şu: Vatandaştan karmaşık bir form istemeyelim.
Vatandaş dilekçesini kendi cümleleriyle yazsın; sistem o cümleyi kurumsal,
izlenebilir ve insan onaylı bir iş akışına dönüştürsün.”

### 0:40–1:20 · Neden yalnızca sınıflandırma yetmez?

“Sınıflandırma artık tek başına farklılaştırıcı değil. Asıl soru, bu dosyanın
kurum içinde nasıl güvenli biçimde sonuçlanacağıdır. CoreAIgent metni alıyor,
dilini ve alanlarını çıkarıyor, eksik veya geçersiz bilgiyi ayırıyor, benzer
geçmiş başvuruları gösteriyor, mevzuat bağlamını arıyor, incelenebilir bir
taslak hazırlıyor ve dosyayı açıklanabilir bir gerekçeyle birime yönlendiriyor.

Bir alan bulunamadığında vatandaşa bütün formu tekrar doldurtmuyoruz; yalnızca
eksik alanı soruyoruz. Güven eşiği yetmiyorsa da sistemi zorla karar verdirmiyor,
dosyayı insan incelemesine bırakıyoruz.”

### 1:20–2:20 · Ürün: tek giriş, görünür süreç

“Şimdi bir gürültü şikâyeti yazıyorum. Konu seçmedim, doğru birim seçmedim;
yalnızca olayı, yeri, zamanı ve talebimi anlattım.

İlk aşamada evrak kayda giriyor ve normalize ediliyor. İkinci aşamada sürüm
kontrollü taksonomi, metindeki bağımsız konu sinyallerini değerlendiriyor.
Üçüncü aşamada başvuru sahibi, olay adresi, tarih, açıklama gibi alanlar
çıkarılıyor ve kayıt defterindeki kurallarla doğrulanıyor. Eksik bir şey varsa
vatandaşa tek bir tamamlayıcı adım gösteriliyor.

Dosya tamamlandığında workflow yerel mevzuat corpus’unda arama yapıyor, kaynak
bağlamını Jamba’ya veriyor ve çıkan metni PII, kaynak ve uzunluk kontrollerinden
geçiriyor. Sonuç imzalı bir karar değil; yetkili personelin inceleyebileceği
resmî yazı taslağıdır. Ardından dosya ilgili birimin kuyruğuna düşüyor ve tüm
durum değişiklikleri kalıcı bir işlem iziyle takip ediliyor.”

### 2:20–3:10 · Farkımız: insana ve sonuca göre karar desteği

“CoreAIgent’in yarışmadaki farkı, metindeki iletişim gerilimini ve tekrar eden
konuyu operasyonel bir sinyale dönüştürmesi. Bu bir psikolojik teşhis değil,
vatandaşı etiketlemek hiç değil. Türkçe ve İngilizce sınırlı işaretler ile aynı
konuda kaçıncı başvuru olduğunu ölçüyoruz.

Örneğin aynı konuda üçüncü başvuru geldiyse veya iletişim gerilimi yükseldiyse,
sistemin kuralı dosyayı yalnızca en boş masaya değil, o konuda çözüm oranı en
yüksek aktif personele önermeye geçiyor. Kararın yanında skor, seviye, konu
geçmişi ve seçimin gerekçesi görünüyor. Böylece ‘AI böyle dedi’ demiyoruz;
‘Bu politika, şu ölçümlerle bu öneriyi yaptı’ diyebiliyoruz.

Aynı ekranda benzer geçmiş vakaların tarihini ve çözülüp çözülmediğini görüyor,
vatandaşın metnini gereksiz yere tekrar açmadan kurum hafızasını kullanıyoruz.”

### 3:10–4:00 · Güven: insan döngüsü, yerel model, ölçülebilir gelişim

“Bu sistemin güvenlik çizgisi net. Jamba yerel çalışıyor; model ve sürümü
pinli, çalışma çevrimdışı ve üretim tek bir seri hatta sınırlandırılmış durumda.
Türkçe metin ile İngilizce ağırlıklı model arasında, yine yerel ve önbellekli
Marian çeviri köprüsü var. Kimlik gibi yapılandırılmış alanlar bu köprüye
gönderilmiyor.

Mevzuat önerisi yoksa model kaynak uyduramıyor; taslak her zaman incelenebilir,
imzasız bir öneri. Vatandaş verisi de öğrenmeye otomatik gitmiyor. Yetkili
personel tamamlanmış dosyayı ‘doğrulanmış örnek’ olarak işaretlerse, eğitim
sınırında çalışan deterministik DLP/PII filtresi devreye giriyor: ad, T.C.
kimlik ve telefon alanları placeholder ile maskeleniyor; açıkça dışlanması
gereken kimlikler adaydan çıkarılıyor; metin içindeki T.C., telefon, e-posta ve
IBAN desenleri de tekrar taranıyor. Ham dilekçe yalnızca yetkili vaka kaydında
kalıyor, aday kaydına ham kimlik alanı yazılmıyor. Bu, otomatik fine-tuning değil;
denetlenebilir bir veri toplama sınırı. Sonraki adımda yalnızca toplu onay,
değerlendirme ve geri alma kontrolünden geçen sürüm yayınlanabilir.

Bizim vaadimiz daha çok otomasyon değil: doğru kişiye, doğru bağlamla, nedenini
göstererek ulaşan ve insan kararını güçlendiren bir kurum hafızası.”

## +1 dakikalık canlı demo koreografisi

1. **Dilekçe ekranı:** “Dilekçenizi kendi cümlelerinizle yazın” alanına adres,
   tarih, olay ve talep içeren kısa bir gürültü şikâyeti yaz. “Konu veya birim
   seçmedim; sistem serbest metinden çıkarıyor” de.
2. **Analiz sonucu:** Güven yüzdesini, eşleşen sinyalleri ve eksik/geçersiz
   alan ayrımını göster. Düşük güven varsa özellikle “burada insan incelemesi
   güvenlik mekanizmasıdır” de.
3. **Operasyon paneli:** Dosya kuyruğunda renkli kategori, öncelik ve yönlendirme
   gerekçesini göster. Bir dosya açıp “Kullanıcı iletişim analizi” kartında
   skor, tekrar sayısı, seviye ve önerilen personeli göster.
4. **AI Analizi:** Yerel mevzuat bağlamı, taslak ve kaynaklı öneriyi göster;
   “Bu imzalı cevap değil, insan onayına sunulan taslak” cümlesini kur.
5. **Kontrollü öğrenme:** Tamamlanmış dosyada “Doğrulanmış örnek olarak kaydet”
   düğmesine bas. “Bu kayıt PII azaltılmış adaydır; model kendini canlıda
   eğitmiyor” de.
6. **Kapanış:** “Vatandaş yalnızca dilekçe yazdı; kurum ise açıklanabilir,
   ölçülebilir ve geri beslemeli bir iş akışı kazandı” cümlesiyle bitir.

## Jürinin teknik sorularına kısa ve savunulabilir cevaplar

### Model ve Türkçe

**Jamba gerçekten kullanılıyor mu?** Evet. Gerçek GGUF hattında
`ai21labs/AI21-Jamba2-3B` modeli, sabit revision ile host llama.cpp/Vulkan
sunucusunda çalışıyor; Docker’daki LLM servisi bu sunucuya sözleşmeli bir
adaptör. CUDA overlay’i de referans çalışma yolumuz.

**Jamba İngilizce ağırlıklıysa Türkçe nasıl anlıyor?** Workflow içinde iki yerel,
önbellekli Marian modeli var: Türkçe→İngilizce ve İngilizce→Türkçe. İnsan
okunur prompt bağlamı çevriliyor, dönüş tekrar Türkçeleştiriliyor. Kimlik,
ID ve citation gibi yapısal alanlar çeviri sınırına sokulmuyor. Modeller sabit
revision’lı ve normal çalışmada ağdan indirme kapalı.

**Sınıflandırmayı da Jamba mı yapıyor?** Hayır; mevcut ürün bunu bilerek
sürüm kontrollü `semantic-v3` taksonomi ve bağımsız sinyal gruplarıyla
deterministik yapıyor. Bu; aynı metne aynı sonucu, açıklanabilir eşleşmeleri ve
düşük güven durumunda güvenli insan incelemesini garanti ediyor. Jamba,
mevzuat bağlamlı taslak üretiminde kullanılıyor.

### Akış ve veri

**Bir dilekçeden taslağa akış nedir?** OCR/intake → sınıflandırma → alan
çıkarımı ve doğrulama → eksik bilgi tamamlama → workflow içindeki yerel RAG →
Jamba taslağı → deterministik guard’lar → birim ve personel önerisi.

**RAG ayrı bir servis mi?** Kamu sözleşmesi için bir RAG sınırı var; gerçek
overlay’de retrieval workflow worker içinde BGE-M3 yoğun arama ile Türkçe
lexical/BM25 sıralamasını RRF ile birleştiriyor. Bu yüzden “yedinci canlı servis”
iddiasında bulunmuyoruz.

**Model halüsinasyonunu nasıl sınırlıyorsunuz?** Prompt yalnızca saklanan
alanlar ve getirilen kaynak parçalarıyla kuruluyor. Çıktı; PII politikası,
kaynak/citation alt kümesi, uzunluk, alan biçimi ve mevzuat dayanağı guard’ları
ile reddedilebiliyor. Guard reddi dosyayı `needs_review` yapıyor; imzalı cevap
üretmiyor.

**Eksik bilgi nasıl işliyor?** Validation her alanı `missing` veya `invalid`
olarak ayırıyor. Vatandaş yalnızca eksik alanı tamamlıyor; `If-Match` revision
ve idempotency anahtarı ile aynı düzeltmenin iki kez yazılması veya eski verinin
üstüne yazılması engelleniyor.

### Duygu, atama ve adalet

**Agresiflik ölçümü bir duygu modeli mi?** Hayır. Kısıtlı Türkçe/İngilizce işaret
kelimeleriyle 0–1 arası davranış sinyali üretiyoruz. Bu tıbbi, psikolojik veya
hukuki bir hüküm değildir; yalnızca destek ve atama kararına yardımcı bir
operasyon sinyalidir. Ham dilekçe metni atama gerekçesine yazılmaz.

**Personel ataması nasıl seçiliyor?** Olağan dosyada aynı birimdeki etkin
personel arasında açık iş yükü en az olan seçiliyor. Üçüncü aynı konu başvurusu
veya yükselmiş sinyal varsa önce o konuda tamamlanmış/başarılı iş oranı,
ardından konu hacmi, açık yük, yakınlık ve kararlı ID ile bağ kırılıyor. Uygun
personel yoksa dosya kaybolmuyor; `unassigned` olarak kuyrukta kalıyor.

**Bu adil mi; agresif vatandaşı cezalandırmıyor musunuz?** Amaç ceza değil,
gerilimi yüksek veya tekrarlanan başvuruyu deneyimli bir personele önererek
çözüm süresini kısaltmak. Sinyal görünür, politika sabit, nihai karar insanda;
metin ve kimlik gerekçeye sızmıyor. Üretimde bu sinyal için düzenli bias ve
yanlış-pozitif ölçümü gerekir.

### Güvenlik, dayanıklılık ve ölçüm

**PII ve DLP nasıl?** Ham metin PostgreSQL’de yetkili vaka erişimiyle tutulur;
model prompt’u ve öğrenme adayı öncesinde yerel `municipality-pii-v1`
politikası uygulanır. Ad, T.C. kimlik, telefon gibi `redact` alanları typed
placeholder’a çevrilir; `exclude` alanları yapılandırılmış adaydan atılır;
metin ayrıca T.C., telefon, e-posta ve IBAN desenleri için taranır. Böylece
yeniden eğitim hattına ham kimlik taşıyan aday gönderilmez. Bu bir kurumsal DLP
ürününün tüm ağ trafiğini denetlediği iddiası değildir; bizim garanti ettiğimiz
şey, Jamba/prompt ve kontrollü öğrenme sınırındaki deterministik veri kaybı
önleme filtresidir. Case action log yalnızca sistem aktörü, durum, revision ve
hata kodu tutar; dilekçe metnini veya taslağı loglamaz.

**Sistem yeniden başlarsa işler kaybolur mu?** Servisler PostgreSQL’de kalıcı
outbox/job kayıtları ve lease/retry mekanizması kullanıyor. Worker kapanırsa
lease süresi dolan iş tekrar `pending` olur; işlem izi de aynı transaction’da
oluşur.

**Yetkilendirme gerçek mi?** Demo’da token’lar nginx arkasında sabitlenmiş
gösterim kimlikleridir; üretim RBAC/SSO değildir. Bunu gerçek kimlik yönetimi
diye sunmuyoruz; sonraki ürünleştirme adımı budur.

**Ne ölçüyorsunuz?** Sınıflandırma güveni ve insan incelemesi oranı, eksik bilgi
oranı, taslak guard-red oranı, doğru yönlendirme geri bildirimi, çözüm süresi,
aynı konu tekrarları ve personel konu çözüm oranı. Başarı yalnız model skoru
değil, doğru kişiye ulaşma ve sonuçlanma metriğidir.

**Fine-tuning yaptınız mı; DLP orada da çalışıyor mu?** Hayır, şu an canlı
fine-tuning yok. Yeniden eğitim için toplanan aday, daha veri setine girmeden
önce DLP/PII filtresinden geçiyor; ham kimlik alanları maskeleniyor veya
çıkarılıyor ve aday durumu `candidate` olarak kalıyor. Fine-tuning ancak toplu
onay, ikinci bir anonimleştirme incelemesi, offline değerlendirme, sürümleme ve
geri alma adımlarından sonra yapılmalı. Bu yüzden bugün “model kendini eğitiyor”
demiyoruz; “güvenli eğitim adayı topluyoruz” diyoruz.

**Daha fazla vaktiniz olsaydı ne eklerdiniz?** Personel CRUD ve gerçek RBAC,
operatör düzeltme nedenleri, çözüm etiketi/ölçümü, anonim veri dışa aktarma ve
otomatik değerlendirme hattını tamamlar; ardından duygu sinyalini yalnızca
destek kalitesi için kalibre ederdik.

## Sahnede asla söyleme

- “Model kendini gerçek zamanlı eğitiyor.” (Şu an yalnızca kontrollü aday kaydı var.)
- “AI hukuki/idari kararı veriyor.” (Taslak ve yönlendirme önerisi var; son karar insanda.)
- “Agresif kullanıcıyı tespit edip cezalandırıyoruz.” (Sınırlı davranış sinyali, destek amacıyla.)
- “RAG yedinci canlı servis ve her şeyi biliyor.” (Retrieval workflow içinde, corpus ile sınırlı.)
- “Görüntü/PDF OCR’ını burada yapıyoruz.” (Intake, hazır metin veya OCR’dan gelen metni kabul ediyor.)
- “E-posta gönderiyoruz veya yazıyı imzalıyoruz.” (Bildirim kalıcı kayıt; dış dispatch yok.)
- “Demo token’ları üretim kimlik doğrulaması.” (Yalnızca yerel gösterim katmanı.)

## Tek cümlelik konumlandırma

**CoreAIgent, vatandaşın serbest metin dilekçesini; Türkçe bağlamı koruyan,
duygusal gerilimi cezaya çevirmeden doğru desteği öneren, kaynaklı taslak ve
ölçülebilir insan-onaylı kurum hafızasına dönüştüren yerel karar destek
sistemidir.**
