# Jamba2-3B Turkish SFT — Failure Analysis

**Analysis ID:** ANALYSIS-001  
**Model:** `linguai/Jamba2-3B-Turkish-SFT-v1`  
**Snapshot:** `5202214fe552041fc6dfe1e6486b61f75eb5fce0`  
**Scope:** Analysis/diagnostic only. No code, training, dataset download, model change, or reference-model comparison.

## 1. Executive diagnostic

Gerçek GPU üzerinde yapılan test sonuçları:

- Golden contract/schema: **58/58 PASS**
- Non-empty generation: **58/58**
- Exact golden draft match: **0/58**
- BGE-M3 mean similarity: **0.644**
- BGE-M3 `<0.60`: **19/58**
- BGE-M3 `<0.70`: **38/58**
- F-03 gerçek Jamba structured extraction: **PASS**
- F-04 structured correspondence JSON: **PASS**
- JSON parse/validation/PII kontrolleri: **PASS**
- JSON repair: **gerekmedi**
- F-04 generation attempt count: **1**

Ana teşhis: `/v1/generate` prompt'u modelden beklenen idari aksiyonu açıkça istemiyor. `task` alanı doğrulanıyor fakat model prompt'una aktarılmıyor; model yalnızca genel bir Türkçe yardımcı sistem mesajı ve source text görüyor. Bu nedenle sorun hem prompt/adapter hem de gerçek SFT capability gap'lerinin birleşimidir.

Conservative manuel task değerlendirmesi:

- `PASS`: 3/58
- `PARTIAL`: 19/58
- `FAIL`: 36/58

Raw artifactler:

- `/tmp/coreaigent-golden-jamba.jsonl`
- `/tmp/coreaigent-golden-jamba-scored-20260827.jsonl`

## 2. Failure distribution

Contract/schema durumu tüm case'lerde `PASS`tır. Aşağıdaki dağılım semantic task correctness içindir.

| Primary failure | Case count |
|---|---:|
| `unnecessary_clarification` | 15 |
| `input_repetition` | 11 |
| `wrong_action` | 13 |
| `unnecessary_refusal` | 7 |
| `under_generation` | 5 |
| `unsupported_claim` | 1 |
| `semantic_drift` | 1 |
| `wrong_official_format` | 1 |
| `missing_required_fact` | 1 |
| Semantic PASS | 3 |

İkincil pattern'ler:

- `context_misread`: s07, s14
- `wrong_decision`: s14, s18, s23, s29, s33, s35, s37, s39, s51
- `hallucination/unsupported_claim`: s18, s22, s38, s51, s52, s58
- `over_generation`: s15, s22, s33, s52, s58
- `truncation`: s58
- `instruction_following_failure`: geniş biçimde tüm veri setine yayılmıştır.

### Case-level analysis

Contract sütunundaki tüm case'ler JSON Schema/contract açısından `PASS`tır. Actual action alanı raw generation'ın okunmasıyla çıkarılmış semantic özettir.

| Case | BGE | Task | Expected action → actual action | Failure | Severity |
|---|---:|---|---|---|---|
| s01 | .735 | PARTIAL | İK'ya ilet → tarih/neden soruyor | clarification | Medium |
| s02 | .689 | FAIL | Raporlu izni değerlendir → source'u tekrar ediyor | repetition, under-generation | High |
| s03 | .612 | FAIL | İletişim bilgisini tamamlat → genel “lütfen yazın” | clarification | High |
| s04 | .539 | FAIL | Bilgi talebini kaydet → izin/help istiyor | clarification | High |
| s05 | .550 | FAIL | Destek birimine yönlendir → şikâyeti tekrar edip soru soruyor | wrong action, clarification | High |
| s06 | .637 | FAIL | Hukuk incelemesine ilet → source'u paraphrase ediyor | repetition | High |
| s07 | .603 | FAIL | Resmi yazıyı kaydet → bilgi talebi olarak okuyor | context misread | High |
| s08 | .764 | FAIL | Mali Hizmetler'e ilet → “fatura ektedir” diyor | repetition | High |
| s09 | .829 | PASS | Desteklenmiyor de → uygun refusal | — | — |
| s10 | .592 | FAIL | Manuel okunabilirlik incelemesi → düzenleme teklif ediyor | wrong action | High |
| s11 | .706 | PARTIAL | Adres değişikliğini işle → adres/belge istiyor | clarification | Medium |
| s12 | .588 | FAIL | Nakli İK'ya gönder → bilgi istiyor | clarification | High |
| s13 | .661 | FAIL | KVKK kapsamında incele → talimat veriyor | wrong action | High |
| s14 | .556 | FAIL | Bilgi İşlem'e yönlendir → kullanıcı adı/şifre istiyor | wrong action, misread | Critical |
| s15 | .670 | PARTIAL | İmzalı dilekçe iste → genel hukuk açıklaması | over-generation | Medium |
| s16 | .638 | FAIL | Satın alma talebini ilet → “Bağlam”ı tekrar ediyor | repetition | High |
| s17 | .803 | FAIL | Resmi yazıyı kaydet → source'u tekrar ediyor | repetition | High |
| s18 | .530 | FAIL | Gizli şekilde Hukuk'a ilet → yasa dışı/etik dışı diye reddediyor | refusal, unsupported claim | Critical |
| s19 | .705 | FAIL | Erişilebilirlik başvurusunu değerlendir → source'u tekrar ediyor | repetition | High |
| s20 | .671 | FAIL | Ruhsat sorgusunu ilet → anlamsız soru üretiyor | wrong action | High |
| s21 | .715 | FAIL | Mali incelemeye al → talebi tekrar ediyor | repetition | High |
| s22 | .663 | FAIL | Fazla mesai başvurusunu incele → uydurma 40 saat formülü | unsupported claim | Critical |
| s23 | .497 | FAIL | Etik şikâyeti gizli incele → reddediyor | refusal | Critical |
| s24 | .758 | FAIL | Arşiv talebini kaydet → yalnız başlığı tekrar ediyor | repetition | High |
| s25 | .616 | PARTIAL | Tutanağı ilgili birime ilet → belge toplamayı soruyor | clarification | Medium |
| s26 | .600 | FAIL | Bozuk formatı reddet → dosya açma izni soruyor | wrong action | High |
| s27 | .676 | PARTIAL | Belgeyi kaydet → doğruluk kontrolü iddia ediyor | wrong action | Medium |
| s28 | .725 | FAIL | Tebligatı acil Hukuk'a ilet → source'u tekrar ediyor | repetition | High |
| s29 | .714 | FAIL | Silme talebini incele → reddediyor | refusal | Critical |
| s30 | .701 | PARTIAL | Sosyal yardım başvurusunu değerlendir → belge toplamayı teklif ediyor | clarification | Medium |
| s31 | .569 | FAIL | İhale bilgi talebini kaydet → genel ihale açıklaması | wrong action | High |
| s32 | .599 | PARTIAL | Savunmayı gizli dosyaya ilet → genel yardım teklifi | clarification | High |
| s33 | .407 | FAIL | Enerji önerisini ilgili birime ilet → ev içi enerji tavsiyesi | semantic drift | Critical |
| s34 | .635 | PARTIAL | Mali mevzuat incelemesi → yardım teklif ediyor | clarification | Medium |
| s35 | .440 | FAIL | Kayıp evrakı kaydet/araştır → reddediyor | refusal | Critical |
| s36 | .840 | PASS | Eksik kimlik bilgisini tamamlat → açıkça tamamlanmasını istiyor | — | — |
| s37 | .597 | FAIL | Hukuki değerlendirmeye ilet → reddediyor | refusal | Critical |
| s38 | .627 | FAIL | Lisans talebini Bilgi İşlem'de değerlendir → legality advice | wrong action | High |
| s39 | .723 | FAIL | E-imza sorununu teknik incele → reddediyor | refusal | Critical |
| s40 | .663 | FAIL | Sözleşme yazısını ilet → “Bağlam”ı tekrar ediyor | repetition | High |
| s41 | .669 | FAIL | Ödeme emrini mali kontrole al → belgeyi tanımlıyor | wrong action | High |
| s42 | .703 | PARTIAL | Araç talebini planlamaya ilet → yapabileceğini söylüyor | under-generation | Medium |
| s43 | .533 | FAIL | Yetkili manuel inceleme → belgeyi tanımlıyor | wrong action | High |
| s44 | .855 | PARTIAL | Ziyaretçi kaydını işle → yapılabilir olduğunu söylüyor | under-generation | Low |
| s45 | .585 | PARTIAL | Staj başvurusunu İK'ya gönder → bilgi istiyor | clarification | Medium |
| s46 | .728 | PASS | Geri bildirim için teşekkür et → uygun teşekkür | — | — |
| s47 | .737 | PARTIAL | İhaleyi Hukuk'a yönlendir → yalnız itiraz edilebileceğini söylüyor | under-generation | Medium |
| s48 | .716 | PARTIAL | Toplantı talebini takvime ilet → yazmaya yardım teklif ediyor | clarification | Medium |
| s49 | .619 | PARTIAL | Hasar başvurusunu mali incele → belge/talimat teklif ediyor | clarification | Medium |
| s50 | .730 | PARTIAL | Öncelikli işleme al → bildirimi yapabileceğini söylüyor | under-generation | Medium |
| s51 | .500 | FAIL | Diploma kayıtlardan doğrula → yasa dışı diye reddediyor | refusal, wrong decision | Critical |
| s52 | .439 | FAIL | Sahtecilik şüphesini gizli incele → ilgisiz etik/çoğalma anlatısı | hallucination, drift | Critical |
| s53 | .696 | PARTIAL | Eğitim talebini planla → konu soruyor | clarification | Medium |
| s54 | .612 | PARTIAL | Veri düzeltme başvurusunu işle → yeni veri istiyor | missing fact; clarification justified | Medium |
| s55 | .727 | PARTIAL | Kayıp kimliği kaydet → belge/adım listesi teklif ediyor | under-generation | Medium |
| s56 | .519 | FAIL | Toplu başvuruyu manuel incele → kavramı açıklıyor | wrong action | High |
| s57 | .581 | PARTIAL | Zorunlu eki yüklet → belge/yönerge teklif ediyor | clarification | Medium |
| s58 | .557 | FAIL | Acil yazıyı Hukuk'a yönlendir → tekrarlanan `[Adresiniz]` şablonu, kesilme | wrong format, over-generation, truncation | Critical |

## 3. BGE-M3 limits and low-score analysis

BGE-M3 yalnız yardımcı triage metriği olarak kullanılmalıdır. Negation, approval/rejection, missing information, state change ve opposite decision durumlarında lexical similarity yanıltıcıdır.

19 case `<0.60`:

| Case | Score | Interpretation |
|---|---:|---|
| s04 | .539 | Kayıt aksiyonu yerine izin/yardım talebi |
| s05 | .550 | Şikâyeti tekrar ediyor, yönlendirme yok |
| s10 | .592 | Manuel inceleme yerine düzenleme önerisi |
| s12 | .588 | İK yönlendirmesi yerine clarification |
| s14 | .556 | Bilgi İşlem görevi credential isteğine dönüşüyor |
| s18 | .530 | Meşru ihbarı yanlış refusal ile karşılıyor |
| s23 | .497 | Etik şikâyetinde hatalı refusal |
| s31 | .569 | Kayıt aksiyonu yerine genel ihale açıklaması |
| s32 | .599 | Gizli personel süreci yerine genel yardım |
| s33 | .407 | Konu tamamen ev içi enerji tavsiyesine kayıyor |
| s35 | .440 | Kayıp evrak için hatalı refusal |
| s37 | .597 | Hukuki değerlendirme yerine refusal |
| s43 | .533 | Manuel inceleme yerine kavram tanımı |
| s45 | .585 | İK değerlendirmesi yerine clarification |
| s51 | .500 | Diploma doğrulaması illegal ilan ediliyor |
| s52 | .439 | Sahtecilik şüphesi anlamsız etik anlatıya dönüşüyor |
| s56 | .519 | Manuel inceleme yerine tanım veriliyor |
| s57 | .581 | Eksik ek için net işlem mesajı üretilemiyor |
| s58 | .557 | Resmi format şablonuna sapma ve truncation |

BGE'nin yanlış güven verdiği örnekler s08 (`.764`), s17 (`.803`), s24 (`.758`) ve s39 (`.723`) case'leridir. Bu çıktılar lexical olarak beklenene yakın olsa da beklenen idari aksiyonu gerçekleştirmemektedir.

## 4. s33 / s35 / s51 / s52 / s58 deep dive

### s33

- **Expected behaviour:** Öneriyi ilgili birime değerlendirme için iletmek.
- **Actual behaviour:** Evde enerji tasarrufu tavsiyeleri veriyor.
- **Primary failure:** `semantic_drift`, `wrong_action`
- **Secondary failure:** `context_misread`, `over_generation`
- **Likely capability gap:** Source text ile istenen idari transformation arasındaki ayrımı kuramama.
- **SFT data needed:** Vatandaş önerisi → kurumsal kayıt/değerlendirme/yönlendirme dönüşümü.
- **Suggested synthetic variations:** Enerji, su, atık, erişilebilirlik, ulaşım ve çevre önerileri; farklı kurum/birimler; olumlu, olumsuz ve eksik bağlamlı örnekler. 20–100 varyant.

### s35

- **Expected behaviour:** Kayıp evrak bildirimini kaydetmek ve araştırma sürecine almak.
- **Actual behaviour:** “Üzgünüm, bu durumda yardımcı olamam.”
- **Primary failure:** `unnecessary_refusal`
- **Secondary failure:** `wrong_decision`
- **Likely capability gap:** Benign idari bildirimleri güvenli görev olarak tanıyamama.
- **SFT data needed:** Kayıp/yanlış yönlendirilmiş/ulaşmayan evrak için kayıt, araştırma ve takip cevabı.
- **Suggested synthetic variations:** Kayıp dilekçe, teslim edilmeyen ek, yanlış birime giden belge, kayıp başvuru numarası. 20–100 varyant.

### s51

- **Expected behaviour:** Diploma doğrulama talebini ilgili kayıtlar üzerinden incelemeye almak.
- **Actual behaviour:** Diploma doğrulamasını “yasa dışı ve etik dışı” ilan ediyor.
- **Primary failure:** `unnecessary_refusal`, `wrong_decision`
- **Secondary failure:** `unsupported_claim`
- **Likely capability gap:** Doğrulama/inceleme gibi meşru idari görevleri güvenlik ihlali sanma.
- **SFT data needed:** Belge ve kayıt doğrulama taleplerinde inceleme başlatma, yetkili birime gönderme ve eksik bilgi isteme ayrımı.
- **Suggested synthetic variations:** Diploma, sertifika, hizmet belgesi, ruhsat, kayıt numarası ve kurum teyidi. 20–100 varyant.

### s52

- **Expected behaviour:** Sahtecilik şüphesini gizli manuel incelemeye almak.
- **Actual behaviour:** Sahteciliğin yayılmasına ve etik sorunlara yol açtığına dair ilgisiz açıklama.
- **Primary failure:** `hallucination`, `semantic_drift`
- **Secondary failure:** `wrong_action`, `unsupported_claim`, `wrong_tone`
- **Likely capability gap:** Hassas iddia içeren metinlerde nötr işlem aksiyonu üretememe.
- **SFT data needed:** İddia doğrulaması yapmadan “bildirim alındı, yetkili incelemeye gönderildi” davranışı.
- **Suggested synthetic variations:** Sahte imza, sahte fatura, sahte kimlik, değiştirilmiş tarih ve şüpheli mühür. 20–100 varyant.

### s58

- **Expected behaviour:** Acil resmi yazıyı Hukuk birimine öncelikli iletmek.
- **Actual behaviour:** “Resmi Yazı” şablonu, tekrarlanan `[Adresiniz]` placeholder'ları ve kesilmiş çıktı.
- **Primary failure:** `wrong_official_format`
- **Secondary failure:** `over_generation`, `instruction_following_failure`, `truncation`
- **Likely capability gap:** Kısa kurumsal action response yerine genel dilekçe şablonuna geçme.
- **SFT data needed:** Resmi yazı source text → tek/iki cümlelik kurumsal acknowledgement/routing cevabı.
- **Suggested synthetic variations:** Acil mahkeme yazısı, süreli tebligat, kurumlar arası yazı ve hukuki görüş talebi; placeholder'sız ve uzunluk kontrollü örnekler. 20–100 varyant.

## 5. Capabilities to preserve

### CAP-001 — Structured JSON

F-03 extraction ve F-04 correspondence structured JSON akışları geçti. JSON parse, schema validation, PII redaction ve source guard davranışları korunmalı.

### CAP-002 — Açık eksik-bilgi tespiti

s36 güçlü bir örnektir: kimlik bilgisinin tamamlanması gerektiğini açıkça söylüyor.

### CAP-003 — Meşru unsupported refusal

s09 doğru şekilde desteklenmeyen belgeyi reddediyor.

### CAP-004 — Nezaket ve geri bildirim tonu

s46 uygun teşekkür üretiyor.

### CAP-005 — Türkçe üretim ve konu tanıma

s44, s46 ve s50'de konu tamamen kaybolmuyor; ancak konu tanıma tek başına task correctness değildir.

### CAP-006 — PII/source güvenliği

F-04 testinde PII dışarı sızmadı, kaynaksız hukuki iddia guard'ı çalıştı.

## 6. SFT capability gaps

| Capability | Severity | Evidence | Recommended weight |
|---|---|---|---:|
| Official correspondence action/state transformation | Critical | 30+ case'te route/record/review aksiyonu yok | 28% |
| Exact instruction following; source'u tekrar etmeme | High | 11 doğrudan repetition ve geniş echo pattern'i | 20% |
| Clarification vs completion kararı | High | 15 gereksiz clarification | 17% |
| Refusal/decision polarity | Critical | 7 hatalı refusal; s18/s23/s51 kritik | 12% |
| Context grounding/fact preservation | High | s07, s14, s18, s22, s52 | 10% |
| Extraction → response synthesis | High | Alanı doğru okuyup aksiyona çevirememe | 8% |
| Structured JSON | Low/preserve | F-03/F-04 PASS | 5% |

## 7. Recommended SFT mixture

`DATAREC-001`

- **28%** official correspondence action/state
- **20%** instruction following ve transformation
- **17%** clarification/missing-information handling
- **12%** refusal ve decision polarity
- **10%** context grounding/fact preservation
- **8%** extraction → response synthesis
- **5%** structured JSON

Cross-cutting criteria:

- Source text'i aynen/paraphrase ederek bırakmama
- İstenen aksiyonu açıkça yazma
- Gereksiz soru sormama
- Meşru görevi reddetmeme
- Kaynakta olmayan hukuk/olgusal iddia eklememe
- Placeholder/repeated-template üretmeme
- Kısa, resmi ve tamamlanmış cevap üretme

Golden case'leri veya yakın paraphrase'lerini training'e koyma. Yeni örnekler task yapısını koruyup kişi, kurum, belge türü, karar, eksik bilgi ve wording eksenlerinde ayrışmalı.

## 8. Evaluator adjustments

### EVALREC-001 — Exact match

Exact match yalnız regression metriği olmalı; ana kalite metriği olmamalı.

### EVALREC-002 — Explicit semantic action

Her case için `route`, `record`, `review`, `request_missing_information`, `reject_unsupported`, `manual_review` veya `thank_acknowledge` etiketi tutulmalı.

### EVALREC-003 — Ayrı boyutlar

Sonuçlar ayrı raporlanmalı:

- `task_correctness`
- `contract_compliance`
- `grounding`
- `hallucination`
- `tone_format`

### EVALREC-004 — BGE kullanımı

BGE-M3 yalnız triage için kullanılmalı. Negation ve karar polarity için ayrıca binary assertions gerekli:

- Beklenen action var mı?
- Beklenen department/unit var mı?
- Beklenen karar polaritesi korunmuş mu?
- Gereksiz refusal var mı?
- Clarification gerçekten gerekli mi?

### EVALREC-005 — Structured JSON ayrımı

Prose `/v1/generate` ve structured workflow generation ayrı evaluator setleri olmalı. `/v1/generate` içindeki `draft` alanının JSON olmaması contract hatası değildir; F-03/F-04 raw structured generation testleri JSON parse ve schema guard ile devam etmelidir.

### EVALREC-006 — Biçim kontrolleri

Minimal ek kontroller:

- Tekrarlanan placeholder
- Kesilmiş son cümle
- Genel dilekçe şablonuna sapma
- Gereksiz uzunluk
- Source-only echo

Yeni ağır evaluation platformuna gerek yok; mevcut runner'a semantic action assertions ve küçük bir insan inceleme tablosu yeterlidir.

## 9. Prompt-level issues

### PROMPTREC-001 — `likely_prompt_issue`

`/v1/generate` içinde `task` alanı doğrulanıyor fakat model prompt'una task talimatı olarak eklenmiyor. Model “draft reply üret ve source'tan idari aksiyon çıkar” bilgisini almıyor.

### PROMPTREC-002 — `mixed`

Model prompt'u genel Türkçe assistant prompt'u seviyesinde kalıyor. Beklenen route/record/review aksiyonu, hedef birim ve cevap stili açıkça belirtilmiyor.

### PROMPTREC-003 — `likely_prompt_issue`

F-04 structured prompt açık JSON şeması, allowed values, source policy ve stop talimatı içeriyor ve başarılı oluyor. Aynı modelin F-04'te başarılı olup prose golden'da zayıf olması prompt formatının güçlü etkisini gösteriyor.

### PROMPTREC-004 — `mixed`

s18, s23, s35, s39 ve s51'deki sistematik refusal yalnız prompt sorunu değildir; SFT refusal/allowability davranış boşluğu da vardır.

### PROMPTREC-005 — `likely_prompt_issue`

s58 generation için kısa cevap sınırı, resmi cevap formatı ve placeholder yasağı yeterince zorlayıcı değildir. Output 512 token sınırına ulaşarak kesilmiştir.

## 10. Training readiness decision

**Primary: `NEEDS_PROMPT_FIX_FIRST`**

Önce golden evaluation prompt'unda task/action/state talimatı açık hale getirilmeli. Mevcut ölçüm prompt ile SFT kabiliyetini tam ayıramıyor.

**Secondary: `READY_FOR_NEW_SFT`**

Prompt düzeltmesinden sonra yeni SFT gerekliliği hâlâ güçlü görünmektedir. Özellikle hatalı refusal, input repetition, resmi aksiyona dönüştürememe ve semantic drift sistematik capability gap'leridir.

`NEEDS_EVALUATOR_FIX_FIRST` kararı uygun değildir; evaluator iyileştirilmeli fakat mevcut failure'lar raw output'larda açıkça görülmektedir.

## 11. Remaining genuine open questions

### OQ-001

Golden expected draft'lar route/record/review aksiyonları içeriyor. Bu aksiyonlar model tarafından source text'ten çıkarılmalı mı, yoksa orchestration katmanından prompt'a explicit verilmesi mi bekleniyor?

### OQ-002

`draft_reply` görevi nihai resmi cevap mı, yoksa idari işlem acknowledgement/routing cevabı mı? Golden cevaplar ikinci davranışı test ediyor.

### OQ-003

Eksik tarih, adres veya başvuru detayı olduğunda beklenen davranış clarification mı, yoksa yine de genel idari taslak üretmek mi? s01, s11, s45 ve s54 için bu karar semantic label'ı etkiliyor.

### OQ-004

Prose `/v1/generate` ve structured workflow generation aynı model davranış standardını mı paylaşmalı, yoksa ayrı evaluator/task sözleşmeleri mi olmalı?

Reference/eski model karşılaştırması yapılmamıştır.
