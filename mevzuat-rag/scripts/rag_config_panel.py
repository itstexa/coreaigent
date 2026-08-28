#!/usr/bin/env python3
"""
CoreAIgent mevzuat-rag — Konfigürasyon Kontrol Paneli
=======================================================

KULLANIM
--------
1) Aşağıdaki "AYARLAR" bölümündeki değerleri kendi sisteminizin GERÇEK
   durumuna göre True/False veya sayı olarak düzenleyin.
   (Bir bayrağı ne yaptığından emin değilseniz koddaki açıklamayı okuyun —
   her biri, doğrulanmış denetim bulgularından türetildi.)
2) Dosyayı çalıştırın:  python rag_config_panel.py
3) Çıktı size: KRİTİK / YÜKSEK / ORTA / DÜŞÜK önceliklerle uyarılar,
   genel bir "Üretime Hazırlık Skoru" ve önceliklendirilmiş bir aksiyon
   listesi verir.

Bu araç kod yazmaz, deploy etmez — sadece SİZİN girdiğiniz gerçek durumu
denetlenmiş kurallara göre değerlendirir. "Doğru cevap" kodun kendisinde,
bu panel yalnızca o cevabı okunabilir bir karara çevirir.
"""

from dataclasses import dataclass, field
from enum import Enum


# =====================================================================
# AYARLAR — Kendi sisteminizin GERÇEK durumuna göre düzenleyin
# =====================================================================

@dataclass
class RAGConfig:
    # --- Çağrı yüzeyi (deployment surface) ---
    # Bunu doldurmadan "auth ekle" / "load test yap" önerileri anlamsızdır.
    # "cli_only"      : yalnızca repl.py gibi interaktif, tek operatörlü CLI
    # "internal_call" : CoreAIgent'ın başka bir bileşeni tarafından
    #                    in-process/kütüphane olarak çağrılıyor
    # "http_service"  : bağımsız, ağ üzerinden erişilen bir web servisi VAR
    # "unknown"       : henüz doğrulanmadı — ÖNCE BUNU NETLEŞTİRİN
    #
    # DOĞRULANDI (2026-08-28): "http_service". Kanıt:
    #   - services/workflow/main.py: gerçek FastAPI uygulaması
    #     (`app = FastAPI(title="Workflow Orchestrator")`), citizen-facing
    #     /upload, /v1/workflows/document, /status/{id}, /result/{id} ve
    #     statik frontend (`/`) sunuyor.
    #   - services/workflow/pipeline.py:run_pipeline() -> rag_connector.py
    #     -> subprocess -> mevzuat_rag.engine.retrieve() zinciriyle
    #     mevzuat-rag'a in-process/subprocess olarak ulaşıyor (mevzuat-rag
    #     paketinin KENDİSİ "internal_call", ama uçtan uca sistem ağdan
    #     erişilen bir HTTP servisi).
    #   - services/llm/main.py de ayrı bir FastAPI uygulaması (/v1/generate),
    #     aynı rag_connector'ı kullanıyor.
    #   - grep ile services/ genelinde jwt/authorization/api-key deseni
    #     SIFIR sonuç verdi (auth eklenmeden önce) — bkz. madde 1.
    deployment_surface: str = "http_service"

    # --- Ölçek ---
    corpus_size_chunks: int = 2                # Şu an kaç chunk var (gerçek sayı)
    corpus_size_target: int = 1_000_000         # Hedeflenen nihai ölçek

    # --- Retrieval mimarisi ---
    hybrid_bm25_enabled: bool = True            # BM25 (sparse) hibrit arama açık mı
    bm25_backend: str = "in_memory"             # "in_memory" | "qdrant_native_sparse" | "disk_backed"
    reranker_enabled: bool = True                # Cross-encoder rerank açık mı
    rerank_top_n: int = 5                        # Rerank sonrası context'e giren chunk sayısı
    query_filter_enabled: bool = False           # search() sorgu anında metadata filtresi alıyor mu
                                                  # (ör. "sadece yürürlükteki madde")
    hnsw_tuned: bool = False                     # HNSW m / ef_construct elle ayarlandı mı

    # --- Pipeline aşamaları (opsiyonel geliştirmeler) ---
    multi_query_enabled: bool = True
    hyde_enabled: bool = True
    crag_enabled: bool = True
    # DOĞRULANDI (2026-08-28): "onay" yazılı bir risk kaydıyla değil, riski
    # ortadan kaldıran bir KOD değişikliğiyle sağlandı (bilinçli tercih —
    # panel bunu kabul ediyor çünkü sonuç aynı: sessiz risk kalmadı).
    # crag.py._evaluate() artık istisna yakaladığında ctx.crag_evaluator_failed
    # = True set ediyor; GenerateStage bunu görürse (generate.py) hem
    # answer["crag_status"] = "EVALUATOR_FAILED_OPEN" set ediyor HEM DE
    # answer["answer"] metninin başına "[⚠️ SONUÇ DOĞRULANAMADI...]" uyarısını
    # ekliyor — ask.py CLI'da da ayrıca satır olarak basılıyor. Artık "sessiz"
    # SUFFICIENT fallback yok; kullanıcı ve audit_log (answer_verdict alanına
    # "crag=EVALUATOR_FAILED_OPEN" olarak yazılıyor) bunu görebiliyor.
    # Doğrulama: tests/test_crag_fail_open.py (4/4 test yeşil).
    crag_fail_open_approved: bool = True
    semantic_cache_enabled: bool = False
    post_hoc_verify_enabled: bool = True

    # --- Chunking ---
    chunk_overlap_configured: int = 80           # Config'te yazan overlap değeri
    chunk_overlap_functional: bool = False       # chunk() metodu bu değeri GERÇEKTEN kullanıyor mu
                                                  # (kod okunarak doğrulanmalı — varsayılan False)

    # --- Embedding / model yönetimi ---
    auto_reembed_trigger_wired: bool = False     # IndexMetadataMismatch → reembed script'ini
                                                  # otomatik tetikleyen bağlantı kuruldu mu

    # --- OCR / ingestion ---
    ocr_service_exists: bool = True
    ocr_auto_bridge_wired: bool = False          # status:"failed" kayıtlarını otomatik OCR'a
                                                  # yönlendiren köprü kuruldu mu

    # --- Otomasyon ---
    scheduler_exists: bool = False               # Herhangi bir cron/celery-beat/systemd-timer var mı
    reindexing_automated: bool = False
    retention_deletion_automated: bool = False   # KVKK silme otomatik mi tetikleniyor

    # --- Güvenlik & uyum ---
    # DOĞRULANDI (2026-08-28): services/workflow/auth.py ve services/llm/auth.py
    # eklendi, /upload, /v1/workflows/document, /status/{id}, /result/{id} ve
    # /v1/generate uçlarına Depends(verify_api_key) ile bağlandı (X-API-Key
    # header, WORKFLOW_API_KEYS/LLM_API_KEYS env değişkeniyle yönetiliyor).
    # BİLİNÇLİ SINIRLAMA: env değişkeni boşsa auth sessizce devre dışı kalıp
    # actor="anonymous" döner (mevcut mock/test akışını kırmamak için) — bkz.
    # auth.py docstring'i. Production checklist'ine bu değişkenin varlığını
    # doğrulayan bir adım eklenmeli.
    access_control_enabled: bool = True
    # DOĞRULANDI: actor artık main.py (auth) -> pipeline.run_pipeline(actor=)
    # -> rag_connector.get_rag_context(actor=) -> subprocess argv ->
    # engine.retrieve(actor=)/ask(actor=) -> audit_log.log_query(actor=)
    # zinciriyle uçtan uca taşınıyor. tests/test_audit_log.py'ye eklenen
    # test_engine_retrieve_writes_audit_entry içindeki ikinci assert bunu
    # doğruluyor (actor="test:operator_1" verilince audit satırına gerçekten
    # yazılıyor). CLI yolları (ask.py/repl.py) actor="cli:<os_user>" kullanıyor;
    # eval/demo scriptleri "eval:<script_adı>"/"demo:<script_adı>" kullanıyor.
    audit_actor_tracked: bool = True
    pii_regex_coverage: bool = True              # TCKN/telefon/e-posta/IBAN regex kapsamı
    pii_ner_coverage: bool = False                # İsim/adres için NER tabanlı katman var mı

    # --- Hukuki doğruluk (bu domain'e özel) ---
    norm_hierarchy_programmatic_check: bool = False  # Anayasa>Kanun>KHK>Yönetmelik çakışması
                                                       # kod ile mi tespit ediliyor, yoksa
                                                       # sadece system prompt talimatı mı

    # --- Generation ---
    llm_provider_count: int = 1                  # Kaç farklı LLM sağlayıcı/yedek var
    llm_cost_pressure: bool = False               # False = kendi barındırılan model (Jamba vb.),
                                                   # maliyet artık kısıt değil, KAPASİTE kısıt
    streaming_enabled: bool = False
    native_json_mode: bool = False

    # --- Değerlendirme ---
    eval_set_discriminative: bool = False         # Golden set farklı configleri gerçekten
                                                   # ayırt edebiliyor mu (Recall/MRR hep 1.0
                                                   # çıkıyorsa buraya False yazın)
    load_test_done: bool = False                  # Eşzamanlı kullanıcı yükü altında test var mı
    p95_p99_measured: bool = False


class Severity(Enum):
    KRITIK = (4, "🔴 KRİTİK")
    YUKSEK = (3, "🟠 YÜKSEK")
    ORTA = (2, "🟡 ORTA")
    DUSUK = (1, "⚪ DÜŞÜK")

    def __lt__(self, other):
        return self.value[0] < other.value[0]


@dataclass
class Finding:
    severity: Severity
    baslik: str
    aciklama: str
    aksiyon: str


# =====================================================================
# KURAL MOTORU — denetimde doğrulanmış bulgulara dayanır, değiştirmeyin
# =====================================================================

def evaluate(cfg: RAGConfig) -> list[Finding]:
    f: list[Finding] = []

    # --- Çağrı yüzeyi netliği (auth/load-test önerilerinin önkoşulu) ---
    if cfg.deployment_surface == "unknown":
        f.append(Finding(
            Severity.KRITIK, "Çağrı yüzeyi belirsiz",
            "Bu sistemin gerçekte nasıl çağrıldığı (CLI mi, CoreAIgent'ın "
            "iç bir bileşeni mi, bağımsız HTTP servisi mi) doğrulanmadı. "
            "Aşağıdaki erişim kontrolü ve kapasite bulguları bu bilgi "
            "olmadan YANLIŞ çözüme yönlendirebilir (ör. HTTP servisi "
            "yokken JWT önermek gibi).",
            "Önce gerçek çağrı yüzeyini tespit edin (repo'da web "
            "framework/servis giriş noktesi ara, agent_reach_connector.py'yi "
            "tam okuyun). Bu netleşmeden diğer erişim kontrolü maddelerini "
            "uygulamaya başlamayın."
        ))

    # --- Erişim kontrolü & hesap verebilirlik ---
    if not cfg.access_control_enabled and cfg.deployment_surface == "http_service":
        f.append(Finding(
            Severity.KRITIK, "Erişim kontrolü yok (HTTP servisi)",
            "Bağımsız bir HTTP servisi olduğu doğrulandı ama auth/middleware "
            "katmanı yok. Herhangi bir çağıran tüm mevzuat verisine "
            "erişebiliyor.",
            "JWT/API-key/session tabanlı auth ekleyin."
        ))
    elif not cfg.access_control_enabled and cfg.deployment_surface == "internal_call":
        f.append(Finding(
            Severity.YUKSEK, "Kimlik üst katmandan geçirilmiyor (iç çağrı)",
            "Bu paket CoreAIgent'ın bir bileşeni tarafından in-process "
            "çağrılıyor — kendi JWT/auth'unu implemente etmesi doğru "
            "katman değil. Ama çağıran bileşen zaten kimlik doğrulaması "
            "yapıyorsa bile, o kimlik bu pakete hiç aktarılmıyor.",
            "Kendi auth'unuzu yazmayın — çağıran katmandaki kimliği "
            "engine.ask(query, actor=...) imzasına parametre olarak "
            "geçirin. Auth sorumluluğu üst katmanda kalmalı."
        ))
    elif not cfg.access_control_enabled and cfg.deployment_surface == "cli_only":
        f.append(Finding(
            Severity.ORTA, "Erişim kontrolü yok (yalnızca CLI)",
            "Doğrulanan tek giriş noktesi repl.py — tek operatörlü, "
            "interaktif bir CLI. JWT/API-key bu senaryoda gereksiz "
            "karmaşıklık; asıl kontrol OS/dosya izinleri seviyesinde "
            "olmalı. Ama bu paket ileride bir servise dönüşürse (ör. "
            "agent_reach_connector.py üzerinden) bu madde yeniden KRİTİK "
            "olur.",
            "Şimdilik: script'e erişimi olan kullanıcıları/dosya izinlerini "
            "netleştirin. Bir servis katmanı eklendiği AN bu maddeyi "
            "yeniden değerlendirin."
        ))

    if not cfg.audit_actor_tracked:
        f.append(Finding(
            Severity.KRITIK, "audit_log.actor boş",
            "Sorgu logları kim tarafından yapıldığını kaydetmiyor. Bir "
            "itiraz/denetim durumunda geriye dönük hiçbir şey ispatlanamaz. "
            "Bu bulgu çağrı yüzeyinden BAĞIMSIZ olarak geçerlidir — CLI "
            "olsa bile hangi operatörün hangi sorguyu attığı kayıt "
            "altına alınmalı.",
            "engine.ask() ve audit_log çağrılarına actor parametresini "
            "geçirin. Kaynağı: HTTP servisiyse auth token'dan, iç çağrıysa "
            "üst katmandan, CLI ise işletim sistemi kullanıcı adından "
            "(os.getlogin() vb.) alınabilir."
        ))

    # --- BM25 / ölçek ---
    if cfg.hybrid_bm25_enabled and cfg.bm25_backend == "in_memory":
        if cfg.corpus_size_target > 5_000:
            f.append(Finding(
                Severity.KRITIK, "BM25 ölçek duvarı",
                f"In-memory BM25, belgelenmiş sınırı (~birkaç bin chunk) ile "
                f"hedef ölçeğiniz ({cfg.corpus_size_target:,} chunk) arasında "
                f"uçurum var. Gerçek toplu ingest'te OOM veya devre dışı kalma "
                f"riski kesin.",
                "Qdrant native sparse vectors'a veya disk-backed bir BM25 "
                "implementasyonuna geçin — 1M ölçeğine çıkmadan ÖNCE."
            ))
        elif cfg.corpus_size_chunks > 3_000:
            f.append(Finding(
                Severity.YUKSEK, "BM25 sınırına yaklaşılıyor",
                f"Mevcut korpus ({cfg.corpus_size_chunks:,} chunk) belgelenmiş "
                f"in-memory sınırına yaklaşıyor.",
                "Sparse backend geçişini planlamaya şimdi başlayın."
            ))

    # --- CRAG fail-open ---
    if cfg.crag_enabled and not cfg.crag_fail_open_approved:
        f.append(Finding(
            Severity.KRITIK, "CRAG fail-open onaysız",
            "CRAG bir alt bileşen hata verdiğinde sessizce SUFFICIENT'e "
            "düşüyor (sadece WARNING logluyor). Kod bunu 'bilinçli tasarım' "
            "olarak belgeliyor, ama bu riskin bir yetkili tarafından "
            "onaylandığına dair kayıt yok.",
            "Ya bu davranışı yazılı olarak (risk kaydı ile) onaylatın, ya da "
            "hata durumunda kullanıcıya 'sonuç doğrulanamadı' uyarısı "
            "gösterecek şekilde değiştirin."
        ))

    # --- Norm hiyerarşisi (hukuki doğruluk) ---
    if not cfg.norm_hierarchy_programmatic_check:
        f.append(Finding(
            Severity.YUKSEK, "Norm hiyerarşisi sadece prompt'ta",
            "Anayasa>Kanun>KHK>Yönetmelik çakışma kontrolü yalnızca LLM'e "
            "verilen bir talimat; kod tarafında doğrulama yok. Çelişen iki "
            "chunk context'e girdiğinde yanlış hiyerarşiyle cevap üretme "
            "riski var.",
            "mevzuat_turu alanına göre programatik bir sıralama/çelişki "
            "tespiti katmanı ekleyin (LLM'e bırakmayın)."
        ))

    # --- Retention / KVKK ---
    if not cfg.retention_deletion_automated:
        f.append(Finding(
            Severity.YUKSEK, "Silme otomasyonu yok",
            "Retention silme fonksiyonu var ama yalnızca manuel CLI ile "
            "çalıştırılabiliyor. KVKK'nın gerektirdiği düzenli silme "
            "otomatik tetiklenmiyor.",
            "Silme fonksiyonunu bir scheduler'a (cron/celery-beat) bağlayın."
        ))

    # --- PII kapsamı ---
    if cfg.pii_regex_coverage and not cfg.pii_ner_coverage:
        f.append(Finding(
            Severity.ORTA, "PII kapsamı eksik",
            "PII redaksiyonu yalnızca TCKN/telefon/e-posta/IBAN gibi "
            "örüntüsü belirgin alanları kapsıyor; serbest metindeki isim ve "
            "adres tespit edilmiyor.",
            "İsim/adres için NER tabanlı bir katman ekleyin; bu arada "
            "raporlarda 'PII korumalı' ifadesini kapsam belirterek kullanın."
        ))

    # --- OCR köprüsü ---
    if cfg.ocr_service_exists and not cfg.ocr_auto_bridge_wired:
        f.append(Finding(
            Severity.ORTA, "OCR otomatik yönlendirilmiyor",
            "Taranmış PDF'ler status:'failed' ile açıkça loglanıyor (sessiz "
            "değil) ama OCR servisine otomatik yönlendirilmiyor — bir "
            "insanın bu kayıtları görüp elle yönlendirmesi gerekiyor.",
            "İngestion'da status:'failed' + 'taranmış görüntü olabilir' "
            "kaydını yakalayıp OCR servisini otomatik tetikleyen bir köprü "
            "ekleyin. (Ucuz düzeltme — script'ler zaten var, sadece bağlayın.)"
        ))

    # --- Re-embed otomasyonu ---
    if not cfg.auto_reembed_trigger_wired:
        f.append(Finding(
            Severity.ORTA, "Re-embed tetiklemesi manuel",
            "reembed.py iyi tasarlanmış (dry-run, chunk-count doğrulama) "
            "ama IndexMetadataMismatch fırlatıldığında otomatik "
            "tetiklenmiyor — sistem durup insan beklemek zorunda kalıyor.",
            "Mismatch exception'ını yakalayıp reembed.py'yi (ya da en "
            "azından bir alert'i) otomatik tetikleyen bir except bloğu "
            "ekleyin. (Ucuz düzeltme.)"
        ))

    # --- Chunking overlap ölü kod ---
    if cfg.chunk_overlap_configured > 0 and not cfg.chunk_overlap_functional:
        f.append(Finding(
            Severity.ORTA, "chunk_overlap ölü kod",
            f"Config {cfg.chunk_overlap_configured} token overlap iddia "
            f"ediyor ama chunk() metodu bu değeri hiç okumuyor. "
            f"Dokümantasyon davranış vaat ediyor, kod uygulamıyor.",
            "Ya overlap mantığını gerçekten uygulayın, ya da config'ten "
            "kaldırıp yanıltıcı görünümü ortadan kaldırın."
        ))

    # --- Query-time filtre ---
    if not cfg.query_filter_enabled:
        f.append(Finding(
            Severity.ORTA, "Sorgu anında metadata filtresi yok",
            "search() bir filter/query_filter parametresi almıyor — "
            "'sadece yürürlükteki madde' gibi bir pre-filter sorgu anında "
            "uygulanamıyor.",
            "Qdrant query_filter desteğini search() imzasına ve çağıran "
            "kodlara ekleyin."
        ))

    # --- HNSW ---
    if not cfg.hnsw_tuned and cfg.corpus_size_target > 100_000:
        f.append(Finding(
            Severity.ORTA, "HNSW parametreleri varsayılan",
            "Collection oluşturulurken hnsw_config geçilmiyor (m, "
            "ef_construct varsayılan). Büyük ölçekte bu, arama kalitesi "
            "veya bellek kullanımı açısından ayarlanmamış bırakılmış "
            "olabilir.",
            "Hedef ölçeğe göre m/ef_construct değerlerini ölçüp elle "
            "ayarlayın."
        ))

    # --- Otomasyon / scheduler ---
    if not cfg.scheduler_exists:
        f.append(Finding(
            Severity.ORTA, "Scheduler/cron yok",
            "Re-indexing, retention silme, health-check gibi periyodik "
            "işleri tetikleyecek hiçbir otomasyon katmanı yok — hepsi "
            "manuel script bağımlı.",
            "Basit bir cron/celery-beat/systemd-timer katmanı kurun; "
            "yukarıdaki birkaç 'manuel tetikleme' bulgusunu tek seferde "
            "çözer."
        ))

    # --- LLM sağlayıcı yedekliliği ---
    if cfg.llm_provider_count <= 1:
        sev = Severity.ORTA if not cfg.llm_cost_pressure else Severity.YUKSEK
        f.append(Finding(
            sev, "Tek LLM sağlayıcısı, yedeksiz",
            "Generation aşaması tek bir sağlayıcıya bağımlı. Bu sağlayıcı "
            "(kendi barındırdığınız model dahil) kesintiye uğrarsa "
            "retrieve-only dışında sistem durur.",
            "En azından bir fallback (ikinci model/sağlayıcı veya "
            "'şu an yanıt üretilemiyor, kaynaklar burada' modu) tanımlayın."
        ))

    # --- Kapasite (maliyet değil, throughput) ---
    if cfg.llm_provider_count >= 1 and not cfg.llm_cost_pressure:
        stage_calls = sum([
            cfg.multi_query_enabled, cfg.hyde_enabled, cfg.crag_enabled,
            cfg.post_hoc_verify_enabled
        ]) + 1  # +1 ana generation çağrısı
        if stage_calls >= 4 and not cfg.load_test_done:
            if cfg.deployment_surface == "cli_only":
                f.append(Finding(
                    Severity.DUSUK, "Eşzamanlı yük testi (şimdilik anlamsız)",
                    f"Tek operatörlü CLI'da sorgular zaten seri geliyor — "
                    f"'eşzamanlı kullanıcı yükü' senaryosu şu an mevcut "
                    f"değil. Sorgu başına ~{stage_calls} ardışık LLM çağrısı "
                    f"olması yine de tek sorgunun gecikmesini etkiler ama "
                    f"bu bir kapasite riski değil, kullanıcı deneyimi "
                    f"konusu.",
                    "Öncelik değil. Bu paket bir servise dönüştüğü AN "
                    "(deployment_surface değiştiğinde) bu maddeyi YÜKSEK'e "
                    "yeniden sınıflandırın."
                ))
            elif cfg.deployment_surface in ("internal_call", "http_service"):
                yuzey_aciklama = (
                    "CoreAIgent'ın çağıran bileşeni üzerinden eşzamanlı "
                    "istek gönderilebiliyor"
                    if cfg.deployment_surface == "internal_call" else
                    "bağımsız HTTP servisi eşzamanlı istek alabiliyor"
                )
                f.append(Finding(
                    Severity.YUKSEK, "Kapasite testi yok (maliyet değil, throughput riski)",
                    f"Maliyet kısıtı kalktı (kendi barındırılan model) ama "
                    f"sorgu başına ~{stage_calls} ardışık LLM çağrısı var ve "
                    f"{yuzey_aciklama}. Kendi GPU'nuzda bu, eşzamanlı yük "
                    f"arttıkça gecikmeyi katlanarak büyütebilir — hiç "
                    f"ölçülmemiş.",
                    "HTTP değil, gerçek çağrı yolunuz üzerinden (ör. "
                    "engine.ask()'e N thread/process ile paralel çağrı) "
                    "eşzamanlı yük testi yapın; darboğaza göre top_n/CRAG "
                    "loop sayısını ayarlayın."
                ))
            else:  # unknown
                f.append(Finding(
                    Severity.ORTA, "Kapasite riski değerlendirilemiyor",
                    "Çağrı yüzeyi belirsiz olduğu için 'eşzamanlı yük' "
                    "senaryosunun gerçekte var olup olmadığı bilinmiyor.",
                    "Önce çağrı yüzeyini netleştirin (bkz. 'Çağrı yüzeyi "
                    "belirsiz' bulgusu), sonra bu maddeyi yeniden "
                    "değerlendirin."
                ))

    # --- Eval güvenilirliği ---
    if not cfg.eval_set_discriminative:
        f.append(Finding(
            Severity.YUKSEK, "Eval seti ayrım gücünden yoksun",
            "Golden set tüm konfigürasyon kombinasyonlarında aynı "
            "(Recall/MRR=1.0) skoru veriyor — bu, sistemin mükemmel "
            "olduğunun değil, eval'in hiçbir farkı ayırt edemediğinin "
            "kanıtı. Şu an hiçbir config değişikliğinin gerçekten iyi mi "
            "kötü mü olduğu bilinmiyor.",
            "Zor, hard-negative içeren gerçekçi bir golden set kurun. Bu, "
            "diğer tüm iyileştirmelerin doğruluğunu ölçebilmeniz için "
            "önkoşuldur."
        ))

    # --- Yük/performans ölçümü ---
    if not cfg.p95_p99_measured:
        f.append(Finding(
            Severity.DUSUK, "p95/p99 sürekli ölçülmüyor",
            "Gecikme yalnızca debug modda, tek kullanıcı senaryosunda "
            "ölçülüyor. Production'da sürekli izleme yok.",
            "Sürekli metrik toplama + alerting (ör. p95 > eşik) ekleyin."
        ))

    # --- Streaming / JSON mode ---
    if not cfg.streaming_enabled:
        f.append(Finding(
            Severity.DUSUK, "Streaming yok",
            "Yanıtlar tek seferde dönüyor, kullanıcı deneyimi için "
            "streaming yok.",
            "Öncelik değil ama kullanıcı deneyimi iyileştirmesi olarak "
            "not edin."
        ))
    if not cfg.native_json_mode:
        f.append(Finding(
            Severity.DUSUK, "Native JSON mode kullanılmıyor",
            "Yapılandırılmış çıktılar manuel ```-temizleme + json.loads ile "
            "parse ediliyor — kırılgan bir desen, birden fazla dosyada "
            "tekrarlanıyor.",
            "Sağlayıcının native JSON/structured-output modunu kullanın; "
            "tekrarlanan parse kodunu tek bir yardımcı fonksiyona toplayın."
        ))

    return sorted(f, key=lambda x: x.severity, reverse=True)


def readiness_score(findings: list[Finding]) -> tuple[int, str]:
    weights = {Severity.KRITIK: 10, Severity.YUKSEK: 5, Severity.ORTA: 2, Severity.DUSUK: 1}
    penalty = sum(weights[fx.severity] for fx in findings)
    score = max(0, 100 - penalty)
    if score >= 90:
        etiket = "PRODUCTION'A HAZIR"
    elif score >= 70:
        etiket = "SIKI ÇEMBERLE PRODUCTION'A YAKIN"
    elif score >= 40:
        etiket = "PİLOT/İÇ KULLANIM İÇİN UYGUN, PRODUCTION DEĞİL"
    else:
        etiket = "ÜRETİME HAZIR DEĞİL"
    return score, etiket


def print_report(cfg: RAGConfig) -> None:
    findings = evaluate(cfg)
    score, etiket = readiness_score(findings)

    print("=" * 72)
    print(" CoreAIgent mevzuat-rag — Üretime Hazırlık Raporu")
    print("=" * 72)
    print(f"\nÜretime Hazırlık Skoru: {score}/100  →  {etiket}\n")

    if not findings:
        print("Tanımlı kurallara göre açık bir bulgu yok. Yine de bu panel "
              "yalnızca sizin girdiğiniz bayraklara güvenir — bayrakları "
              "kod okuyarak doğruladığınızdan emin olun.\n")
        return

    counts = {}
    for fx in findings:
        counts[fx.severity] = counts.get(fx.severity, 0) + 1
    print("Özet:", "  ".join(f"{sev.value[1]}: {n}" for sev, n in counts.items()))
    print("-" * 72)

    current_sev = None
    for fx in findings:
        if fx.severity != current_sev:
            current_sev = fx.severity
            print(f"\n### {fx.severity.value[1]} ###")
        print(f"\n▸ {fx.baslik}")
        print(f"   Durum : {fx.aciklama}")
        print(f"   Aksiyon: {fx.aksiyon}")

    print("\n" + "=" * 72)
    print(" Önerilen sıralama: önce tüm KRİTİK, sonra YÜKSEK maddeler.")
    print(" ORTA maddelerin çoğu (OCR köprüsü, re-embed tetikleme, overlap)")
    print(" ucuz düzeltmelerdir — bunları KRİTİK'lerle paralel yapabilirsiniz.")
    print("=" * 72)


if __name__ == "__main__":
    config = RAGConfig()
    print_report(config)
