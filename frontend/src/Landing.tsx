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
  { title: "Dilekçe", detail: "Kişi talebini kendi cümleleriyle doğrudan metin alanına yazar." },
  { title: "Metin analizi", detail: "Metin normalize edilir, dili ve işleme güveni belirlenir." },
  { title: "AI Analiz", detail: "Talep türü, departman ve birim sınıflandırılır." },
  { title: "Eksik Tespiti", detail: "Zorunlu alanlar doğrulanır, eksikler bildirilir." },
  { title: "Mevzuat Eşleştirme", detail: "İlgili kaynaklar taslağa referans olur." },
  { title: "Taslak", detail: "Resmî yazı taslağı insan onayına sunulur." },
];

const FEATURES = [
  {
    icon: <ScanText size={21} />,
    title: "Metin Analizi",
    detail: "Yazdığınız dilekçe normalize edilir; dil tespiti ve güven skoru dosyaya kaydedilir.",
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
          <div><strong>CoreAIgent</strong><small>Dilekçe Analiz Sistemi</small></div>
        </div>
        <nav className="landing-nav">
          <a href="#surec">Nasıl Çalışır</a>
          <a href="#yetenekler">Özellikler</a>
          <a href="#giris">Giriş</a>
          <button className="primary-button" onClick={() => navigate(PATHS.panel)}>Operasyon Paneli</button>
        </nav>
      </header>

      <section className="landing-hero hero-pattern">
        <div className="landing-inner">
          <div>
            <span className="landing-badge"><Landmark size={13} /> TEKNOFEST 2026 · Kamu Teknolojileri</span>
            <h1>Dilekçenizi yazın.<em>Analizi CoreAIgent’e bırakın.</em></h1>
            <p className="lede">
              Serbest metin dilekçenizden konu, ilgili birim ve eksik bilgiler çıkarılır; kaynaklı
              resmî taslak hazırlanır. Son karar daima yetkili incelemesindedir.
            </p>
            <div className="landing-actions">
              <button className="primary-button" onClick={() => navigate(PATHS.petition)}>
                Dilekçe analizi başlat <ArrowRight size={17} />
              </button>
              <button className="ghost-button" onClick={() => navigate(PATHS.panel)}>
                <Building2 size={16} /> Operasyon paneli
              </button>
            </div>
            <p className="landing-note"><ShieldCheck size={15} /> Nihai idari karar her zaman yetkili personeldedir.</p>
          </div>
          <div className="landing-visual">
            <header>
              <FileText size={17} />
              <strong>Dilekçe · Gürültü Şikâyeti</strong>
              <span>Örnek akış</span>
            </header>
            <div className="landing-pipeline">
              <div className="done"><UploadCloud size={16} /> Metin alındı <span>F-01</span></div>
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
            <h2>6 Adımda Dilekçe Analizi</h2>
            <p>Tek ihtiyacınız dilekçenizi kendi cümlelerinizle yazmak.</p>
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
            <h2>Tek giriş, görünür süreç</h2>
            <p>Dilekçe sahibi metni yazar; yetkili ekip aynı dosyayı panelden takip eder.</p>
          </div>
          <div className="entry-grid">
            <article className="entry-card">
              <span className="landing-badge"><UserRound size={13} /> Dilekçe sahibi</span>
              <h3>Dilekçeni yaz</h3>
              <p>Konuyu, olayı ve talebinizi anlatın. CoreAIgent metinden gerekli bilgileri ve doğru işlem yolunu çıkarır.</p>
              <ul>
                <li><ShieldCheck size={15} /> Zorunlu alanlar anında denetlenir</li>
                <li><FileText size={15} /> Metin olduğu gibi sizin kontrolünüzde kalır</li>
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
            <p>Dilekçe analizi için yerel yapay zekâ destekli karar desteği</p>
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
