/**
 * Tanıtım sayfası (/) — Stitch "Devlet Arşiv Yönetimi Sistemi" tasarımının
 * projenin düz CSS sistemine taşınmış hâli.  Tailwind CDN yerine mevcut stil
 * dosyası, Material Symbols yerine lucide-react ikonları kullanılır; böylece
 * arayüz dış bir kaynağa bağlı kalmadan kapalı ağda da açılır.
 *
 * Kartlardaki etiketler backend kapsamını olduğu gibi anlatır: mevzuat
 * kaynağı demo ortamında sözleşme taklidi olduğu için kartta yazılıdır.
 */

import {
  ArrowRight,
  BookOpen,
  Building2,
  FileSearch,
  FileText,
  Landmark,
  LockKeyhole,
  PenLine,
  ScanText,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  UserRound,
} from "lucide-react";
import { PATHS, navigate } from "./router";

const STEPS = [
  { title: "Yükleme", detail: "Evrak metni veya OCR çıktısı sisteme alınır." },
  { title: "OCR", detail: "Metin normalize edilir, dil ve güven skoru üretilir." },
  { title: "AI Analiz", detail: "Talep türü, departman ve birim sınıflandırılır." },
  { title: "Eksik Tespiti", detail: "Zorunlu alanlar doğrulanır, eksikler bildirilir." },
  { title: "Mevzuat Eşleştirme", detail: "İlgili kaynaklar taslağa referans olur." },
  { title: "Taslak", detail: "Resmî yazı taslağı insan onayına sunulur." },
];

const FEATURES = [
  {
    icon: <ScanText size={21} />,
    title: "Yüksek Hassasiyetli OCR",
    detail: "Taranmış evrak metni normalize edilir; dil tespiti ve güven skoru her dosyada kayıt altına alınır.",
    note: "Canlı serviste",
  },
  {
    icon: <FileSearch size={21} />,
    title: "Otomatik Sınıflandırma",
    detail: "Taksonomi üzerinden talep türü, departman ve birim belirlenir; düşük güven insan incelemesine düşer.",
    note: "Canlı serviste",
  },
  {
    icon: <ShieldCheck size={21} />,
    title: "Eksik Bilgi Denetimi",
    detail: "Kimlik numarası, telefon ve tarih gibi alanlar kural bazlı doğrulanır; eksikler başvurana bildirilir.",
    note: "Canlı serviste",
  },
  {
    icon: <BookOpen size={21} />,
    title: "Hukuki Öneriler",
    detail: "Taslağa kaynak gösteren mevzuat parçaları eklenir ve her öneri kaynak kimliğiyle izlenebilir.",
    note: "Demo mevzuat kaynağı",
  },
  {
    icon: <PenLine size={21} />,
    title: "Akıllı Taslak",
    detail: "Resmî yazı taslağı ve evrak özeti üretilir; nihai idari karar her zaman personeldedir.",
    note: "Canlı serviste",
  },
  {
    icon: <LockKeyhole size={21} />,
    title: "Veri Gizliliği",
    detail: "Başvurana giden bildirim süreç bilgisiyle sınırlıdır; birim bildirimi yalnızca yetkili bağlamı taşır.",
    note: "Sözleşmeyle sınırlı",
  },
];

export function Landing() {
  return (
    <div className="landing">
      <header className="landing-header">
        <div className="landing-logo">
          <div className="brand-mark"><Sparkles size={18} /></div>
          <div><strong>CoreAIgent</strong><small>Kamu Evrak Zekâsı</small></div>
        </div>
        <nav className="landing-nav">
          <a href="#surec">Nasıl Çalışır</a>
          <a href="#yetenekler">Özellikler</a>
          <a href="#giris">Giriş</a>
          <button className="primary-button" onClick={() => navigate(PATHS.panel)}>Sisteme Giriş</button>
        </nav>
      </header>

      <section className="landing-hero hero-pattern">
        <div className="landing-inner">
          <div>
            <span className="landing-badge"><Landmark size={13} /> TEKNOFEST 2026 · Kamu Teknolojileri</span>
            <h1>Yapay Zekâ ile Kamu Evrakında<em>Dijital Dönüşüm</em></h1>
            <p className="lede">
              OCR, otomatik sınıflandırma, eksik bilgi denetimi ve akıllı taslak oluşturma ile resmî
              yazışma süreçlerini saniyeler içine indirin. Güvenli, hızlı ve kurumsal yapay zekâ çözümü.
            </p>
            <div className="landing-actions">
              <button className="primary-button" onClick={() => navigate(PATHS.petition)}>
                Dilekçe Gönder <ArrowRight size={17} />
              </button>
              <button className="ghost-button" onClick={() => navigate(PATHS.panel)}>
                <Building2 size={16} /> Kurum Paneli
              </button>
            </div>
            <p className="landing-note"><ShieldCheck size={15} /> Nihai idari karar her zaman yetkili personeldedir.</p>
          </div>
          <div className="landing-visual">
            <header>
              <FileText size={17} />
              <strong>Dosya · Gürültü Şikâyeti</strong>
              <span>Örnek akış</span>
            </header>
            <div className="landing-pipeline">
              <div className="done"><UploadCloud size={16} /> Evrak alındı <span>F-01</span></div>
              <div className="done"><FileSearch size={16} /> Sınıflandırıldı <span>F-02</span></div>
              <div className="done"><ShieldCheck size={16} /> Alanlar doğrulandı <span>F-03</span></div>
              <div><PenLine size={16} /> Taslak hazırlanıyor <span>F-04</span></div>
              <div><Building2 size={16} /> Birime yönlendirme <span>F-05</span></div>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section" id="surec">
        <div className="landing-inner">
          <div className="landing-heading">
            <span>Süreç</span>
            <h2>6 Adımda Otomatik Süreç</h2>
            <p>Geleneksel evrak işleme süreçlerini yapay zekâ ile optimize ediyoruz.</p>
          </div>
          <div className="step-grid">
            {STEPS.map((step, index) => (
              <article key={step.title}>
                <b>{String(index + 1).padStart(2, "0")}</b>
                <strong>{step.title}</strong>
                <p>{step.detail}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="landing-section feature-section" id="yetenekler">
        <div className="landing-inner">
          <div className="landing-heading">
            <span>Yetenekler</span>
            <h2>Temel Yetenekler</h2>
            <p>Kurumsal hafızayı dijitalleştiren akıllı modüller.</p>
          </div>
          <div className="feature-grid">
            {FEATURES.map((feature) => (
              <article key={feature.title}>
                <span>{feature.icon}</span>
                <h3>{feature.title}</h3>
                <p>{feature.detail}</p>
                <small><ShieldCheck size={13} /> {feature.note}</small>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="landing-section" id="giris">
        <div className="landing-inner">
          <div className="landing-heading">
            <span>Giriş</span>
            <h2>İki ayrı kapı, tek iş akışı</h2>
            <p>Vatandaş dilekçesini gönderir, kurum personeli aynı dosyayı panelde takip eder.</p>
          </div>
          <div className="entry-grid">
            <article className="entry-card">
              <span className="landing-badge"><UserRound size={13} /> Vatandaş</span>
              <h3>e-Dilekçe gönder</h3>
              <p>Konunuzu seçin, kimlik ve başvuru bilgilerinizi girin; sistem resmî dilekçe metnini sizin adınıza düzenler.</p>
              <ul>
                <li><ShieldCheck size={15} /> Zorunlu alanlar anında denetlenir</li>
                <li><FileText size={15} /> Dilekçe metnini göndermeden önce görürsünüz</li>
                <li><Building2 size={15} /> Başvuru ilgili birime otomatik iletilir</li>
              </ul>
              <button className="primary-button" onClick={() => navigate(PATHS.petition)}>
                Dilekçe yazmaya başla <ArrowRight size={17} />
              </button>
            </article>
            <article className="entry-card dark">
              <span className="landing-badge"><Building2 size={13} /> Kurum</span>
              <h3>Operatör paneli</h3>
              <p>Gelen dilekçeleri tek kuyrukta görün; analiz sonucunu, eksik bilgileri ve resmî yazı taslağını dosya üzerinden yönetin.</p>
              <ul>
                <li><FileSearch size={15} /> Sunucudan gelen yetkili dosya listesi</li>
                <li><PenLine size={15} /> Taslak ve mevzuat önerileri</li>
                <li><ShieldCheck size={15} /> İnsan onaylı karar desteği</li>
              </ul>
              <button className="primary-button" onClick={() => navigate(PATHS.panel)}>
                Panele git <ArrowRight size={17} />
              </button>
            </article>
          </div>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="landing-inner">
          <div>
            <strong>CoreAIgent</strong>
            <p>Kamu evrak iş akışı için yapay zekâ destekli karar desteği · Demo Belediye Başkanlığı senaryosu</p>
          </div>
          <nav>
            <span>Veri Gizliliği</span>
            <span>Kullanım Koşulları</span>
            <span>Güvenlik Mimarisi</span>
          </nav>
        </div>
      </footer>
    </div>
  );
}
