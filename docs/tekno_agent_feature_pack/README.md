# TEKNOFEST 2026 - 1. Senaryo Backend Feature Pack

Bu paket bir master prompt değildir. Requirement Analyst -> Architect -> Senior Developer -> Version Control -> Quality/Test zincirinin ayrı ayrı tüketebileceği, spec-driven ve acceptance-test-driven feature tanımlarıdır.

## Kaynak ve kapsam

Temel kaynak: TEKNOFEST 2026 Türkçe Yapay Zeka Dil Ajanları Yarışması, 1. Senaryo teknik şartnamesi; özellikle 6.4.1 Evrak Sınıflandırma ve İçerik Analizi, 6.4.2 Resmi Yazı Taslaklama ve Birim Yönlendirme ve puanlama kriterleri.

Bu pakette kullanıcı tarafından tarif edilen akış ana omurgadır:

1. Metin veya OCR çıktısı alınır.
2. Evrak hiyerarşik olarak departman -> birim -> talep/dilekçe türü seviyelerinde sınıflandırılır.
3. Talep türünün gerektirdiği bilgiler çıkarılır ve eksikler tespit edilir.
4. Eksik bilgi varsa süreç beklemeye alınır ve kullanıcıya neyin eksik olduğu bildirilir.
5. Bilgiler tam ise mevzuat/standart yazışma önerileri ve gerekli resmi yazı taslağı hazırlanabilir.
6. Evrak doğru hedef birime yönlendirilir.
7. Jamba tabanlı yerel LLM servisiyle kullanıcı ve hedef birim için ayrı bildirim içerikleri üretilir.
8. Tüm akış Docker servisleri üzerinde uçtan uca çalışır.

## Önemli tasarım sınırları

- Backend tüm iş mantığının sahibi olmalıdır. Frontend ilk aşamada yalnızca backend durumlarını, eksik bilgi uyarısını ve sonuçları gösterecek geçici/minimal bir arayüz olabilir.
- OCR motorunun kendisi bu paketin zorunlu implementasyon kapsamına dahil değildir; sistem doğrudan metin veya OCR servisinden üretilmiş metni aynı kontrata normalize etmelidir.
- Jamba referansları doğrulandı: istenen `mamba`/`jamba` klasörleri yok; mevcut referanslar `mamba-cpt-tr`, `jamba-sft` ve `santosvbasvuru` içindeki model server'dır. Bu repo'da canonical servis adı `llm`, Docker içi adres `llm:8080`, gerçek Jamba overlay'i `compose.llm.yaml` ve ortak generation endpoint'i `/v1/generate`'dir. Ayrıntı için [F-07](07_jamba_inference_integration.md) ve [F-08](08_docker_and_runtime.md) okunmalıdır.
- Departman, birim, dilekçe türü ve zorunlu alan listeleri hard-code edilmiş switch/case yığını olarak tasarlanmamalıdır. Versiyonlanabilir taxonomy/schema verisi olmalıdır.
- Dış kapalı API bağımlılığı eklenmemelidir. Yarışma demosu yerel/on-premise çalışabilir olmalıdır.
- Her feature tamamlanmadan sıradaki feature'a geçilmemelidir; feature tamamlanması acceptance kriterleri ve ilgili `.feature` senaryolarının geçmesi ile tanımlanır.

## Önerilen implementasyon sırası

1. `01_document_intake.md`
2. `02_hierarchical_classification.md`
3. `03_information_extraction_missing_info.md`
4. `04_legislation_and_official_correspondence.md`
5. `05_routing_and_notifications.md`
6. `06_orchestration_and_case_state.md`
7. `07_jamba_inference_integration.md`
8. `08_docker_and_runtime.md`
9. `09_api_contracts.md` ortak kontratları sabit `contracts/http/manifest.json` ve JSON Schema'larla eşleştirir.
10. `10_acceptance_test_plan.md` ve `acceptance/*.feature` her aşamada quality gate olarak kullanılmalıdır.

## Çalıştırma gerçeği

`docker compose up --build -d` yalnız deterministic mock stack'i başlatır.
Gerçek Jamba için GPU/cache gerektiren `compose.llm.yaml` overlay'i gerekir;
tam gerçek E2E ise `.env` içindeki SHA-pinned servis image'larıyla çalışır.
Mock sonuçları gerçek model veya gerçek business-service sonucu olarak
sunulamaz.

## Skill zinciri için genel çalışma kuralı

Her dosya işlendiğinde:

- Requirement Analyst: belirsizlikleri, acceptance criteria'yı, edge-case'leri ve repo gerçekleriyle çelişkileri netleştirir.
- Architect: servis sınırını, veri modelini, bağımlılıkları, container iletişimini ve hata akışını belirler.
- Senior Developer: yalnızca onaylanmış spec/contract üzerinden implementation yapar.
- Version Control: feature kapsamı dışındaki değişiklikleri ayırır; atomik commit/PR üretir.
- Quality/Test: acceptance senaryolarını, contract testlerini ve gerekli E2E akışını çalıştırır.

Bir aşamada yeni bir belirsizlik bulunursa sessiz varsayım yapılmaz; open question olarak kaydedilir ve mümkünse repo/reference dosyalarından çözülür.
