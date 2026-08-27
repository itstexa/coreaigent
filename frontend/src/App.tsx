import {
  Activity,
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Bell,
  BookOpen,
  Bot,
  Building2,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  ClipboardCheck,
  Clock3,
  FileCheck2,
  FilePlus2,
  FileSearch,
  FileText,
  Gauge,
  History,
  Inbox,
  Info,
  Landmark,
  LayoutDashboard,
  LoaderCircle,
  MailCheck,
  Menu,
  RefreshCw,
  Route,
  Search,
  Send,
  Server,
  ShieldCheck,
  Sparkles,
  UserRoundCheck,
  Users,
  X,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  apiErrorMessage,
  completeReview,
  getCaseBundle,
  getCaseDocument,
  getCaseSummary,
  listCases,
  runIntake,
  serviceHealth,
  startCorrespondence,
  supplementCase,
  type IntakeProgress,
} from "./api";
import { DEMO_SAMPLES, type DemoSample } from "./samples";
import {
  PAGE_SIZE,
  QUEUE_FILTERS,
  caseView,
  channelLabel,
  confidenceTone,
  initials,
  languageLabel,
  relativeAge,
  type CaseView,
  type QueueCounts,
} from "./queue";
import { loadCases, saveCase, updateStoredCase } from "./storage";
import { PATHS, casePath, navigate } from "./router";
import type {
  CaseBundle,
  CaseDocument,
  CaseListItem,
  CaseListPage,
  CaseRecord,
  CorrespondenceResult,
  ImplementationMode,
  RoutingResult,
  ServiceHealth,
  ValidationField,
} from "./types";

type View = "overview" | "new" | "case";
type DetailTab = "summary" | "analysis" | "correspondence" | "history";

const STATE_LABELS: Record<string, string> = {
  received: "Alındı",
  normalized: "Normalize edildi",
  classified: "Sınıflandırıldı",
  needs_review: "İnsan incelemesi",
  extracting: "Bilgiler çıkarılıyor",
  waiting_for_user: "Ek bilgi bekleniyor",
  ready_for_processing: "Taslak hazırlanıyor",
  draft_prepared: "Taslak hazır",
  routed: "Yönlendirildi",
  notification_pending: "Bildirim hazırlanıyor",
  completed: "Tamamlandı",
  failed: "İşlem başarısız",
};

const STEP_LABELS: Record<string, string> = {
  "F-01": "Evrak alındı",
  "F-02": "Sınıflandırma",
  "F-03": "Bilgi doğrulama",
  "F-04": "Resmî yazı taslağı",
  "F-05": "Yönlendirme ve bildirim",
};

function stateLabel(value?: string): string {
  return value ? STATE_LABELS[value] ?? value.replaceAll("_", " ") : "Durum bekleniyor";
}

function formatDate(value?: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function shortId(value: string): string {
  return value.length > 20 ? `${value.slice(0, 9)}…${value.slice(-6)}` : value;
}

function modeLabel(mode: ImplementationMode): string {
  if (mode === "mock") return "Mock sözleşme modu";
  if (mode === "real") return "Gerçek servis";
  return "Yerel servis modu";
}

function modeFromHealth(health: ServiceHealth[]): ImplementationMode {
  if (health.some((item) => item.implementation === "mock")) return "mock";
  if (health.length && health.every((item) => item.available)) return "real";
  return "unknown";
}

function StatusPill({ state, compact = false }: { state?: string; compact?: boolean }) {
  const tone = state === "completed" || state === "routed"
    ? "success"
    : state === "failed"
      ? "danger"
      : state === "needs_review" || state === "waiting_for_user"
        ? "warning"
        : "processing";
  return <span className={`status-pill ${tone} ${compact ? "compact" : ""}`}><span />{stateLabel(state)}</span>;
}

function EmptyState({ icon, title, description, action }: { icon: ReactNode; title: string; description: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

function RuntimeBadge({ mode, health }: { mode: ImplementationMode; health: ServiceHealth[] }) {
  const healthy = health.filter((item) => item.available).length;
  return (
    <div className={`runtime-badge ${mode}`} title={`${healthy}/${health.length || 4} servis hazır`}>
      <span className="runtime-dot" />
      <div>
        <strong>{modeLabel(mode)}</strong>
        <small>{healthy}/{health.length || 4} servis hazır</small>
      </div>
    </div>
  );
}

function Sidebar({
  view,
  onNavigate,
  mode,
  health,
  open,
  onClose,
}: {
  view: View;
  onNavigate: (view: View) => void;
  mode: ImplementationMode;
  health: ServiceHealth[];
  open: boolean;
  onClose: () => void;
}) {
  return (
    <>
      {open && <button className="sidebar-scrim" aria-label="Menüyü kapat" onClick={onClose} />}
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><Sparkles size={21} /></div>
          <div><strong>CoreAIgent</strong><span>Karar Destek Sistemi</span></div>
          <button className="mobile-close" onClick={onClose} aria-label="Menüyü kapat"><X size={20} /></button>
        </div>
        <nav className="main-nav" aria-label="Ana menü">
          <button className={view === "overview" ? "active" : ""} onClick={() => onNavigate("overview")}>
            <LayoutDashboard size={19} /><span>Genel Bakış</span>
          </button>
          <button className={view === "new" ? "active" : ""} onClick={() => onNavigate("new")}>
            <FilePlus2 size={19} /><span>Yeni Evrak</span>
          </button>
          <button className={view === "case" ? "active" : ""} onClick={() => onNavigate("overview")}>
            <Inbox size={19} /><span>Son Dosyalar</span>
          </button>
        </nav>
        <div className="nav-section-label">Sistem sınırları</div>
        <div className="capability-list">
          <div><Building2 size={17} /><span>Birim yönlendirme</span><Check size={15} /></div>
          <div><MailCheck size={17} /><span>Bildirim kaydı</span><Check size={15} /></div>
          <div className="muted"><Users size={17} /><span>Personel atama</span><small>API yok</small></div>
          <div className="muted"><Gauge size={17} /><span>Öncelik</span><small>API yok</small></div>
        </div>
        <div className="nav-section-label">Portal</div>
        <nav className="main-nav" aria-label="Kamuya açık sayfalar">
          <button onClick={() => navigate(PATHS.landing)}><Landmark size={19} /><span>Tanıtım sayfası</span></button>
          <button onClick={() => navigate(PATHS.petition)}><UserRoundCheck size={19} /><span>Vatandaş dilekçesi</span></button>
        </nav>
        <div className="sidebar-bottom">
          <RuntimeBadge mode={mode} health={health} />
          {mode === "mock" && <p>Deterministik demo verisi kullanılıyor; gerçek AI sonucu değildir.</p>}
        </div>
      </aside>
    </>
  );
}

function Topbar({
  title,
  subtitle,
  onMenu,
  onNew,
}: {
  title: string;
  subtitle: string;
  onMenu: () => void;
  onNew: () => void;
}) {
  return (
    <header className="topbar">
      <button className="menu-button" onClick={onMenu} aria-label="Menüyü aç"><Menu size={21} /></button>
      <div className="topbar-title"><h1>{title}</h1><p>{subtitle}</p></div>
      <div className="topbar-actions">
        <div className="decision-support"><ShieldCheck size={16} /><span>İnsan onaylı karar desteği</span></div>
        <button className="primary-button compact-button" onClick={onNew}><FilePlus2 size={17} />Yeni Evrak</button>
      </div>
    </header>
  );
}

/**
 * Operatör kuyruğu.
 *
 * Liste `GET /cases` projeksiyonundan gelir; tarayıcı belleğinden değil.
 * Vatandaş dilekçesini kendi telefonundan gönderdiğinde dosyanın panelde
 * görünmesinin tek yolu bu: yerel depolama yalnızca o tarayıcıyı bilir.
 */
function Dashboard({
  page,
  counts,
  loading,
  error,
  search,
  stateFilter,
  offset,
  onSearch,
  onStateFilter,
  onOffset,
  onRefresh,
  onNew,
  onOpen,
}: {
  page: CaseListPage | null;
  counts: QueueCounts | null;
  loading: boolean;
  error: string | null;
  search: string;
  stateFilter: string;
  offset: number;
  onSearch: (value: string) => void;
  onStateFilter: (value: string) => void;
  onOffset: (value: number) => void;
  onRefresh: () => void;
  onNew: () => void;
  onOpen: (caseId: string) => void;
}) {
  const rows = page?.cases ?? [];
  const total = page?.total ?? counts?.[""] ?? 0;
  const from = rows.length ? offset + 1 : 0;
  const to = offset + rows.length;
  const filtered = Boolean(search.trim() || stateFilter);
  // İlk yüklemede tablo yerine iskelet gösterilir; boş bir "dosya yok" ekranı
  // ile gerçekten boş bir kuyruk aynı şeye benzemesin.
  const skeleton = loading && !page;
  const done = counts?.completed ?? 0;
  const all = counts?.[""] ?? 0;
  const automation = all > 0 ? Math.round((done / all) * 100) : null;

  return (
    <div className="page-content dashboard-page">
      <section className="hero-panel">
        <div className="hero-copy">
          <span className="eyebrow"><Bot size={15} /> Kamu evrakı iş akışı</span>
          <h2>Gelen dilekçeleri tek kuyrukta yönetin.</h2>
          <p>Vatandaş portalından ve operatör konsolundan gelen her dosya aynı projeksiyonda listelenir: sınıflandırma, bilgi doğrulama, resmî yazı taslağı ve birim yönlendirmesi.</p>
          <div className="hero-actions">
            <button className="primary-button" onClick={onNew}>Yeni evrak oluştur <ArrowRight size={18} /></button>
            <span><ShieldCheck size={16} /> Nihai idari karar kullanıcıdadır.</span>
          </div>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="orbit orbit-one" /><div className="orbit orbit-two" />
          <div className="ai-core"><Sparkles size={30} /></div>
          <div className="flow-chip chip-one"><FileText size={16} /> Evrak</div>
          <div className="flow-chip chip-two"><FileSearch size={16} /> Analiz</div>
          <div className="flow-chip chip-three"><Route size={16} /> Yönlendirme</div>
        </div>
      </section>

      {/* Kartlar aynı zamanda filtredir: bir sayıyı görüp onu oluşturan
          dosyalara ulaşamamak, sayıyı süs hâline getirirdi. */}
      <section className="stat-grid" aria-label="Kuyruk özeti">
        <button type="button" className={stateFilter === "" ? "active" : ""} onClick={() => onStateFilter("")}>
          <div className="stat-icon blue"><Inbox size={20} /></div>
          <div><span>Toplam dosya</span><strong>{counts ? counts[""] ?? 0 : "—"}</strong><small>Sunucu projeksiyonu</small></div>
        </button>
        <button type="button" className={stateFilter === "needs_review" ? "active" : ""} onClick={() => onStateFilter("needs_review")}>
          <div className="stat-icon amber"><UserRoundCheck size={20} /></div>
          <div><span>İnsan incelemesi</span><strong>{counts ? counts.needs_review ?? 0 : "—"}</strong><small>Sınıflandırma güveni düşük</small></div>
        </button>
        <button type="button" className={stateFilter === "waiting_for_user" ? "active" : ""} onClick={() => onStateFilter("waiting_for_user")}>
          <div className="stat-icon violet"><Activity size={20} /></div>
          <div><span>Ek bilgi bekleniyor</span><strong>{counts ? counts.waiting_for_user ?? 0 : "—"}</strong><small>Eksik veya geçersiz alan</small></div>
        </button>
        <button type="button" className={stateFilter === "completed" ? "active" : ""} onClick={() => onStateFilter("completed")}>
          <div className="stat-icon green"><CheckCircle2 size={20} /></div>
          <div><span>Tamamlanan</span><strong>{counts ? done : "—"}</strong><small>{automation === null ? "İş akışı tamamlandı" : `Kuyruğun %${automation}'i tamamlandı`}</small></div>
        </button>
      </section>

      <section className="panel recent-panel">
        <div className="panel-heading">
          <div><span className="section-kicker">Çalışma alanı</span><h2>Dosya kuyruğu</h2></div>
          <div className="queue-tools">
            <label className="queue-search">
              <Search size={16} />
              <input value={search} placeholder="Evrak no, başvuran, konu…" onChange={(event) => onSearch(event.target.value)} />
              {search && <button type="button" className="queue-clear" onClick={() => onSearch("")} aria-label="Aramayı temizle"><X size={14} /></button>}
            </label>
            <button className="ghost-button compact-button" onClick={onRefresh} disabled={loading}>
              {loading ? <LoaderCircle size={16} className="spin" /> : <RefreshCw size={16} />} Yenile
            </button>
          </div>
        </div>

        <div className="queue-chips" role="group" aria-label="Duruma göre filtrele">
          {QUEUE_FILTERS.map((item) => (
            <button
              key={item.value}
              type="button"
              className={stateFilter === item.value ? "queue-chip active" : "queue-chip"}
              onClick={() => onStateFilter(item.value)}
            >
              {item.short}
              <em>{counts ? counts[item.value] ?? 0 : "·"}</em>
            </button>
          ))}
        </div>

        {error && <div className="error-banner"><AlertCircle size={18} /><p>{error}</p><button onClick={onRefresh}>Yeniden dene</button></div>}

        {skeleton ? (
          <div className="queue-skeleton" aria-hidden="true">
            {[0, 1, 2, 3, 4].map((row) => <div key={row}><i /><i /><i /><i /></div>)}
          </div>
        ) : rows.length === 0 && !error ? (
          <EmptyState
            icon={<Inbox size={27} />}
            title={filtered ? "Bu filtreye uyan dosya yok" : "Henüz dosya yok"}
            description={filtered
              ? "Arama veya durum filtresini temizleyerek kuyruğun tamamını görebilirsiniz."
              : "Vatandaş portalından gelen ilk dilekçe ya da konsoldan oluşturacağınız ilk evrak burada listelenir."}
            action={filtered
              ? <button className="secondary-button" onClick={() => { onSearch(""); onStateFilter(""); }}>Filtreleri temizle</button>
              : <button className="secondary-button" onClick={onNew}>Evrak oluştur</button>}
          />
        ) : (
          <div className="case-table-wrap">
            <table className="case-table">
              <thead><tr><th>Evrak</th><th>Talep türü</th><th>Başvuran</th><th>Birim</th><th>AI güveni</th><th>Yaş</th><th>Durum</th><th /></tr></thead>
              <tbody>{rows.map((item) => {
                const tone = confidenceTone(item.classification_confidence);
                return (
                  <tr key={item.case_id} onClick={() => onOpen(item.case_id)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") onOpen(item.case_id); }}>
                    <td>
                      <div className="case-name">
                        <span className="document-icon"><FileText size={18} /></span>
                        <div>
                          <strong>{item.document_id ?? shortId(item.case_id)}</strong>
                          <small>{channelLabel(item.channel) ?? shortId(item.case_id)} · {languageLabel(item.language)}</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="source-label">{item.request_type_label ?? item.title ?? "Sınıflandırılmadı"}</span>
                      {item.classification_reason && <small className="reason-line" title={item.classification_reason}>{item.classification_reason}</small>}
                    </td>
                    <td>
                      <div className="applicant-cell">
                        <span aria-hidden="true">{initials(item.applicant_name)}</span>
                        <span>{item.applicant_name ?? "Bilinmiyor"}</span>
                      </div>
                    </td>
                    <td>{item.unit_label ?? "—"}<small className="reason-line">{item.department_label ?? ""}</small></td>
                    <td>
                      {typeof item.classification_confidence === "number" ? (
                        <div className={`score-cell ${tone}`}>
                          <strong>%{Math.round(item.classification_confidence * 100)}</strong>
                          <i><b style={{ width: `${Math.round(item.classification_confidence * 100)}%` }} /></i>
                        </div>
                      ) : <span className="score-cell none">Puan yok</span>}
                    </td>
                    <td><span className="age-cell" title={formatDate(item.created_at ?? item.updated_at)}><Clock3 size={13} /> {relativeAge(item.created_at ?? item.updated_at)}</span></td>
                    <td><StatusPill state={item.state} compact /></td>
                    <td><ChevronRight size={18} /></td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        )}

        {page && rows.length > 0 && (
          <div className="queue-pager">
            <p className="queue-footnote">
              <Info size={14} /> {total} dosyanın {from}–{to} arası · liste 5 saniyede bir yenilenir
            </p>
            <div className="pager-buttons">
              <button className="ghost-button compact-button" disabled={offset === 0} onClick={() => onOffset(Math.max(0, offset - PAGE_SIZE))}>
                <ArrowLeft size={15} /> Önceki
              </button>
              <button className="ghost-button compact-button" disabled={to >= total} onClick={() => onOffset(offset + PAGE_SIZE)}>
                Sonraki <ArrowRight size={15} />
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function IntakePage({ mode, onCreated, onCancel }: { mode: ImplementationMode; onCreated: (record: CaseRecord) => void; onCancel: () => void }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [sourceType, setSourceType] = useState<"text" | "ocr">("text");
  const [sample, setSample] = useState<DemoSample | null>(null);
  const [progress, setProgress] = useState<IntakeProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const chooseSample = (item: DemoSample) => {
    setSample(item);
    setTitle(item.title);
    setText(item.text);
    setSourceType(item.sourceType);
    setError(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (text.trim().length < 40) {
      setError("Backend contract’ı en az 40 normalize karakter gerektiriyor.");
      return;
    }
    setBusy(true);
    try {
      const record = await runIntake({
        title: title.trim() || "Başlıksız evrak",
        text,
        sourceType,
        documentId: mode === "mock" && sample ? `doc-${sample.id}` : undefined,
        sourceMetadata: sourceType === "ocr" ? { origin: "pre-extracted-ocr-text" } : {},
      }, setProgress);
      onCreated(record);
    } catch (caught) {
      setError(apiErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-content intake-page">
      <button className="back-link" onClick={onCancel}><ArrowLeft size={17} />Genel bakışa dön</button>
      <div className="intake-header">
        <div><span className="eyebrow"><FilePlus2 size={15} /> Yeni case</span><h2>Yeni evrakı sisteme alın</h2><p>Mevcut contract metin veya daha önce çıkarılmış OCR metni kabul eder. PDF/görsel binary yükleme bu backend’de bulunmuyor.</p></div>
        <div className="step-indicator"><span className="active">1</span><i /><span>2</span><i /><span>3</span></div>
      </div>
      <div className="intake-layout">
        <form className="panel intake-form" onSubmit={submit}>
          <div className="form-section-heading"><div><span>01</span><div><h3>Belge kaynağı</h3><p>Backend `sourceType` değerini seçin.</p></div></div></div>
          <div className="source-toggle">
            <button type="button" className={sourceType === "text" ? "active" : ""} onClick={() => setSourceType("text")}><FileText size={20} /><span><strong>Doğrudan metin</strong><small>Metin içeriği hazır</small></span></button>
            <button type="button" className={sourceType === "ocr" ? "active" : ""} onClick={() => setSourceType("ocr")}><FileSearch size={20} /><span><strong>OCR çıktısı</strong><small>Önceden çıkarılmış metin</small></span></button>
          </div>
          <div className="form-section-heading"><div><span>02</span><div><h3>Evrak içeriği</h3><p>AI pipeline’ına aktarılacak normalize metin.</p></div></div></div>
          <label className="field-label">Dosya başlığı<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Örn. Gürültü şikâyeti" disabled={busy} /></label>
          <label className="field-label">Belge metni<textarea value={text} onChange={(event) => { const next = event.target.value; setText(next); setSample(DEMO_SAMPLES.find((item) => item.text === next) ?? null); }} placeholder="Evrak metnini buraya yapıştırın…" rows={11} disabled={busy} /><small>{text.trim().length} karakter · minimum 40</small></label>
          {error && <div className="error-banner"><AlertCircle size={18} /><span>{error}</span></div>}
          {busy && <div className="processing-banner"><LoaderCircle className="spin" size={19} /><div><strong>{progress?.message ?? "İşlem başlatılıyor"}</strong><span>Sayfayı kapatmadan backend yanıtı bekleniyor.</span></div></div>}
          <div className="form-actions"><button type="button" className="ghost-button" onClick={onCancel} disabled={busy}>Vazgeç</button><button className="primary-button" disabled={busy}>{busy ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}Analizi başlat</button></div>
        </form>
        <aside className="intake-aside">
          <section className="panel samples-panel">
            <div className="panel-heading"><div><span className="section-kicker">Hızlı demo</span><h2>Örnek evraklar</h2></div></div>
            {DEMO_SAMPLES.map((item) => <button type="button" key={item.id} className={sample?.id === item.id ? "sample-card active" : "sample-card"} onClick={() => chooseSample(item)} disabled={busy}><span><FileText size={18} /></span><div><strong>{item.title}</strong><small>{item.eyebrow}</small></div><ChevronRight size={17} /></button>)}
            {mode === "mock" && <div className="mock-callout"><Bot size={18} /><p>Mock modunda kontrollü uçtan uca akış için örnek evraklardan birini seçin. Serbest metin golden scenario olmadığı için mock tarafından reddedilebilir.</p></div>}
          </section>
          <section className="trust-card"><ShieldCheck size={22} /><div><strong>Karar desteği sınırı</strong><p>Sınıflandırma, eksik bilgi, rota ve taslaklar öneridir. Sistem nihai idari karar veya otomatik resmî gönderim yapmaz.</p></div></section>
        </aside>
      </div>
    </div>
  );
}

function MetricCard({ label, value, detail, tone = "default" }: { label: string; value: string; detail: string; tone?: string }) {
  return <article className={`metric-card ${tone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function SummaryTab({ record, view, bundle }: { record?: CaseRecord; view: CaseView; bundle: CaseBundle }) {
  const { status, routing, correspondence } = bundle;
  return (
    <div className="detail-grid">
      <div className="detail-main">
        <section className="panel case-overview-card">
          <div className="panel-heading"><div><span className="section-kicker">Dosya durumu</span><h2>İş akışı özeti</h2></div><StatusPill state={status.state} /></div>
          <div className="metrics-row">
            <MetricCard label="Validation" value={status.validation_status ? stateLabel(status.validation_status) : "Bekleniyor"} detail={`Case revision ${status.case_revision}`} tone={status.validation_status === "complete" ? "success" : "warning"} />
            <MetricCard label="Yönlendirme" value={status.routing_status === "routed" ? "Tamamlandı" : "Bekleniyor"} detail={routing.routing_status === "routed" ? routing.target_unit.label : "Backend sonucu yok"} tone={status.routing_status === "routed" ? "success" : "default"} />
            <MetricCard label="Öncelik" value="Mevcut değil" detail="Backend contract alanı yok" />
            <MetricCard label="Personel" value="Atanmamış" detail="Assignment API bulunmuyor" />
          </div>
        </section>
        <section className="panel narrative-card">
          <div className="panel-heading"><div><span className="section-kicker">Karar desteği</span><h2>AI analiz görünümü</h2></div><span className="recommendation-label"><Sparkles size={14} /> Öneri niteliğinde</span></div>
          <div className="narrative-grid">
            <div><span className="narrative-icon"><FileSearch size={19} /></span><div><small>Sınıflandırma</small><strong>{view.requestTypeLabel ?? status.operational_context?.request_type_id ?? "Henüz görünür değil"}</strong><p>{view.reason ?? "Sınıflandırma gerekçesi henüz yayımlanmadı."}</p></div></div>
            <div><span className="narrative-icon"><Building2 size={19} /></span><div><small>Önerilen hedef</small><strong>{routing.routing_status === "routed" ? routing.target_department.label : view.departmentLabel ?? "Yönlendirme bekleniyor"}</strong><p>{routing.routing_status === "routed" ? `${routing.target_unit.label} · ${routing.route_kind === "fallback" ? "İnsan incelemesi fallback rotası" : "Sınıflandırma temelli rota"}` : "Nihai rota frontend tarafından hesaplanmaz."}</p></div></div>
            <div><span className="narrative-icon"><ClipboardCheck size={19} /></span><div><small>Bilgi yeterliliği</small><strong>{status.validation_status ? stateLabel(status.validation_status) : "Doğrulama bekleniyor"}</strong><p>{record?.validation ? `${record.validation.extractedFields.length} alan çıkarıldı; ${record.validation.missingRequiredFields.length} eksik, ${record.validation.invalidFields.length} geçersiz.` : "Güncel validation özeti backend state’inden izleniyor."}</p></div></div>
            <div><span className="narrative-icon"><BookOpen size={19} /></span><div><small>Yazışma</small><strong>{correspondence.generation_status === "completed" ? "İncelenebilir taslak hazır" : stateLabel(correspondence.generation_status)}</strong><p>{correspondence.generation_status === "completed" ? correspondence.document_summary : "Taslak tamamlanana kadar eski içerik gösterilmez."}</p></div></div>
          </div>
        </section>
        {view.text && <section className="panel source-document"><div className="panel-heading"><div><span className="section-kicker">{view.textOrigin === "server" ? "Özgün dilekçe" : "Yerel kayıt"}</span><h2>Vatandaşın yazdığı metin</h2></div><span className="quiet-label"><Info size={14} /> {view.textOrigin === "server" ? "Kurum kaydından okundu" : "Yalnızca bu tarayıcıda saklandı"}</span></div><pre>{view.text}</pre></section>}
      </div>
      <aside className="detail-aside">
        <section className="panel next-action-card">
          <span className="section-kicker">Sonraki adım</span>
          {status.state === "waiting_for_user" ? <><div className="action-icon warning"><AlertCircle size={23} /></div><h3>Eksik bilgileri tamamlayın</h3><p>Backend, süreç devam etmeden önce kullanıcı girdisi bekliyor.</p></> : status.state === "needs_review" ? <><div className="action-icon warning"><UserRoundCheck size={23} /></div><h3>İnsan incelemesi gerekli</h3><p>Bu sonuç otomatik nihai karar olarak kabul edilmemelidir.</p></> : status.state === "completed" ? <><div className="action-icon success"><BadgeCheck size={23} /></div><h3>İş akışı tamamlandı</h3><p>Case’in güncel revision’ındaki tüm otomatik adımlar tamamlandı.</p></> : <><div className="action-icon processing"><LoaderCircle className="spin" size={23} /></div><h3>Backend çalışıyor</h3><p>Sayfa, authoritative case state’ini otomatik olarak yeniliyor.</p></>}
        </section>
        <section className="panel identifiers-card"><span className="section-kicker">İzlenebilirlik</span><dl><div><dt>Case ID</dt><dd title={status.case_id}>{shortId(status.case_id)}</dd></div><div><dt>Evrak no</dt><dd title={view.documentId ?? undefined}>{view.documentId ? shortId(view.documentId) : "Henüz atanmadı"}</dd></div><div><dt>Başvuran</dt><dd>{view.applicantName ?? "Bilinmiyor"}</dd></div><div><dt>Kanal</dt><dd>{channelLabel(view.channel) ?? "Belirtilmedi"}</dd></div><div><dt>Dil</dt><dd>{languageLabel(view.language)}</dd></div><div><dt>Revision</dt><dd>{status.case_revision}</dd></div><div><dt>Son güncelleme</dt><dd>{formatDate(status.updated_at)}</dd></div></dl></section>
      </aside>
    </div>
  );
}

function fieldsFromNotice(bundle: CaseBundle, record?: CaseRecord): ValidationField[] {
  const local = [...(record?.validation?.missingRequiredFields ?? []), ...(record?.validation?.invalidFields ?? [])];
  if (local.length) return local;
  for (const notice of bundle.status.applicant_notifications) {
    const payload = notice.payload as { fields?: ValidationField[] };
    if (Array.isArray(payload?.fields)) return payload.fields;
  }
  return [];
}

function AnalysisTab({ record, view, bundle, onSupplement }: { record?: CaseRecord; view: CaseView; bundle: CaseBundle; onSupplement: (fields: Record<string, string>) => Promise<void> }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fields = fieldsFromNotice(bundle, record);
  const validated = record?.validation?.extractedFields ?? [];
  const operational = bundle.status.operational_context?.validated_fields ?? {};
  const classified = Boolean(view.requestTypeLabel || view.unitLabel);

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(null);
    try { await onSupplement(values); setValues({}); } catch (caught) { setError(apiErrorMessage(caught)); } finally { setBusy(false); }
  };

  return (
    <div className="analysis-layout">
      <section className="panel analysis-card">
        <div className="panel-heading"><div><span className="section-kicker">F-02</span><h2>Sınıflandırma sonucu</h2></div>{view.confidence !== null && <span className={`confidence-ring ${confidenceTone(view.confidence)}`}>%{Math.round(view.confidence * 100)}<small>güven</small></span>}</div>
        {classified ? <div className="classification-chain"><div><small>Departman</small><strong>{view.departmentLabel ?? "Eşleşme yok"}</strong></div><ChevronRight size={18} /><div><small>Birim</small><strong>{view.unitLabel ?? "Eşleşme yok"}</strong></div><ChevronRight size={18} /><div><small>Talep türü</small><strong>{view.requestTypeLabel ?? "Eşleşme yok"}</strong></div></div> : <p className="muted-copy">Sınıflandırma etiketleri henüz projeksiyonda yok; public API yalnız stable ID’leri sunuyor: {bundle.status.operational_context?.department_id ?? "—"} / {bundle.status.operational_context?.unit_id ?? "—"}.</p>}
        {view.reason && <div className="explanation-box"><Bot size={18} /><div><strong>Kullanıcıya sunulan açıklama</strong><p>{view.reason}</p>{view.classifierVersion && <small>{view.classifierVersion}{view.taxonomyVersion ? ` · ${view.taxonomyVersion}` : ""}</small>}</div></div>}
        {view.confidence !== null && view.confidence <= 0.8 && <div className="boundary-note"><AlertCircle size={18} /><p>Güven puanı F-02’nin 0,80 eşiğinin altında: dosya otomatik olarak insan incelemesine ayrılır, sınıflandırma nihai kabul edilmez.</p></div>}
      </section>

      <section className="panel analysis-card">
        <div className="panel-heading"><div><span className="section-kicker">F-03</span><h2>Çıkarılan ve doğrulanan bilgiler</h2></div><StatusPill state={bundle.status.validation_status ?? "extracting"} compact /></div>
        {validated.length > 0 ? <div className="field-grid">{validated.map((field) => <div key={field.id}><small>{field.label}</small><strong>{field.value}</strong><span>%{Math.round(field.confidence * 100)} güven</span></div>)}</div> : Object.keys(operational).length > 0 ? <div className="field-grid">{Object.entries(operational).map(([id, raw]) => { const value = typeof raw === "string" ? raw : raw.value; const confidence = typeof raw === "object" ? raw.confidence : undefined; return <div key={id}><small>{id}</small><strong>{value ?? "—"}</strong>{confidence !== undefined && <span>%{Math.round(confidence * 100)} güven</span>}</div>; })}</div> : <EmptyState icon={<ClipboardCheck size={25} />} title="Alan sonucu henüz yok" description="Validation tamamlandığında backend tarafından sunulan alanlar burada görünür." />}
      </section>

      {bundle.status.state === "waiting_for_user" && <form className="panel supplement-card" onSubmit={submit}>
        <div className="panel-heading"><div><span className="section-kicker">Kullanıcı aksiyonu</span><h2>Eksik veya geçersiz bilgileri tamamla</h2></div><AlertCircle size={22} /></div>
        <p>Gönderim, güncel revision için idempotent `PATCH supplemental-information` işlemini kullanır.</p>
        {fields.length ? fields.map((field) => <label className="field-label" key={field.id}>{field.label}<input required value={values[field.id] ?? ""} onChange={(event) => setValues((current) => ({ ...current, [field.id]: event.target.value }))} placeholder={`${field.label} girin`} disabled={busy} /><small>{field.id}</small></label>) : <label className="field-label">Alan kimliği<input required value={values["field-id"] ?? ""} onChange={(event) => setValues({ "field-id": event.target.value })} placeholder="Backend bildirimi alan listesi içermedi" /></label>}
        {error && <div className="error-banner"><AlertCircle size={18} />{error}</div>}
        <button className="primary-button" disabled={busy || !Object.values(values).some((value) => value.trim())}>{busy ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}Bilgileri gönder</button>
      </form>}
    </div>
  );
}

function CorrespondenceTab({ result, routing, onStart, busy }: { result: CorrespondenceResult; routing: RoutingResult; onStart: () => void; busy: boolean }) {
  if (result.generation_status === "not_requested") return <EmptyState icon={<BookOpen size={28} />} title="Yazışma henüz başlatılmadı" description="F-06 uygun case’lerde taslağı otomatik başlatır. Gerekirse contract’taki idempotent manuel başlatma işlemini kullanabilirsiniz." action={<button className="primary-button" onClick={onStart} disabled={busy}>{busy ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}Taslağı başlat</button>} />;
  if (result.generation_status === "queued" || result.generation_status === "processing") return <EmptyState icon={<LoaderCircle className="spin" size={29} />} title="Taslak hazırlanıyor" description="Backend retrieval ve yapılandırılmış üretim adımlarını tamamlıyor. Bu görünüm otomatik yenilenir." />;
  if (result.generation_status === "failed") return <EmptyState icon={<AlertCircle size={29} />} title="Taslak üretilemedi" description={`Backend hata kodu: ${result.error_code}. Partial veya eski taslak gösterilmiyor.`} />;
  if (result.generation_status !== "completed") return null;
  return (
    <div className="correspondence-layout">
      <section className="panel draft-card">
        <div className="draft-toolbar"><div><span className="section-kicker">AI tarafından üretilen taslak</span><h2>{result.recommended_correspondence_type.replaceAll("_", " ")}</h2></div><span className={`verification-pill ${result.result_status}`}><ShieldCheck size={15} />{result.result_status === "draft_ready" ? "İncelemeye hazır" : "Kaynak incelemesi gerekli"}</span></div>
        <div className="draft-disclaimer"><Info size={17} /><span>Bu içerik resmî belge değil, kullanıcı incelemesi ve düzenlemesi gereken bir taslaktır.</span></div>
        <div className="draft-summary"><small>Belge özeti</small><p>{result.document_summary}</p></div>
        <article className="official-draft"><div className="draft-seal">CoreAIgent <span>taslak</span></div><pre>{result.draft_text}</pre></article>
      </section>
      <aside className="correspondence-aside">
        <section className="panel references-card"><span className="section-kicker">Mevzuat / referans</span><h3>{result.source_status === "relevant_source_found" ? `${result.regulation_suggestions.length} kaynak eşleşti` : "İlgili kaynak bulunamadı"}</h3>{result.regulation_suggestions.map((source) => <div className="reference-item" key={source.chunk_id}><span><BookOpen size={17} /></span><div><strong>{source.title}</strong><p>{source.locator}</p><small>{source.source_id} · {source.corpus_version}</small></div></div>)}{!result.regulation_suggestions.length && <div className="boundary-note"><AlertCircle size={18} /><p>Mevzuat iddiası üretilmedi. Taslak insan incelemesi gerektirir.</p></div>}</section>
        <section className="panel route-card"><span className="section-kicker">F-05 yönlendirme</span>{routing.routing_status === "routed" ? <><div className="route-path"><span><Building2 size={18} /></span><div><small>Departman</small><strong>{routing.target_department.label}</strong></div></div><div className="route-line" /><div className="route-path"><span><Route size={18} /></span><div><small>Hedef birim</small><strong>{routing.target_unit.label}</strong></div></div></> : <p className="muted-copy">Routing sonucu bekleniyor.</p>}</section>
      </aside>
    </div>
  );
}

function HistoryTab({ bundle }: { bundle: CaseBundle }) {
  const allSteps = ["F-01", "F-02", "F-03", "F-04", "F-05"];
  return (
    <section className="panel history-card">
      <div className="panel-heading"><div><span className="section-kicker">Lifecycle projection</span><h2>İşlem geçmişi</h2></div><span className="quiet-label"><Info size={14} /> Public audit event listesi değildir</span></div>
      <div className="history-notice"><History size={18} /><p>Backend yalnız güncel state, tamamlanan feature adımları, notice kayıtları ve son güncelleme zamanını yayımlar. Aşağıdaki zaman çizelgesi bu authoritative projection’dan oluşturulur; ayrı actor/timestamp event’leri uydurulmaz.</p></div>
      <div className="timeline">{allSteps.map((step) => { const complete = bundle.status.completed_steps.includes(step); const current = !complete && ((step === "F-03" && ["extracting", "waiting_for_user"].includes(bundle.status.state)) || (step === "F-04" && ["ready_for_processing", "draft_prepared"].includes(bundle.status.state)) || (step === "F-05" && ["routed", "notification_pending"].includes(bundle.status.state))); return <div className={`timeline-item ${complete ? "complete" : current ? "current" : "pending"}`} key={step}><span>{complete ? <Check size={16} /> : current ? <LoaderCircle className="spin" size={16} /> : <CircleDashed size={16} />}</span><div><small>{step}</small><strong>{STEP_LABELS[step]}</strong><p>{complete ? "Backend completed_steps içinde" : current ? `Güncel state: ${stateLabel(bundle.status.state)}` : "Henüz tamamlanmadı"}</p></div></div>; })}</div>
      {bundle.status.applicant_notifications.length > 0 && <div className="notice-list"><h3>Başvuru sahibi kayıtları</h3>{bundle.status.applicant_notifications.map((notice, index) => <div key={`${notice.created_at}-${index}`}><Bell size={17} /><div><strong>{stateLabel(notice.kind)}</strong><p>{JSON.stringify(notice.payload)}</p><small>{formatDate(notice.created_at)}</small></div></div>)}</div>}
    </section>
  );
}

function CaseDetail({
  caseId,
  record,
  onBack,
  onRecordUpdate,
}: {
  caseId: string;
  record?: CaseRecord;
  onBack: () => void;
  onRecordUpdate: (updates: Partial<CaseRecord>) => void;
}) {
  const [bundle, setBundle] = useState<CaseBundle | null>(null);
  const [row, setRow] = useState<CaseListItem | null>(null);
  const [original, setOriginal] = useState<CaseDocument | null>(null);
  const [tab, setTab] = useState<DetailTab>("summary");
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    try {
      const next = await getCaseBundle(caseId);
      setBundle(next); setError(null);
      onRecordUpdate({ state: next.status.state, updatedAt: next.status.updated_at });
    } catch (caught) {
      if (!quiet || !bundle) setError(apiErrorMessage(caught));
    } finally { if (!quiet) setRefreshing(false); }
  }, [caseId, onRecordUpdate, bundle]);

  // Kuyruk satırı ve özgün dilekçe metni ayrı uçlardan gelir; ikisi de dosyanın
  // hangi tarayıcıdan gönderildiğinden bağımsızdır.  Biri gelmezse sayfa
  // durmaz: bundle tek başına iş akışı görünümünü taşır.
  const reload = useCallback(async () => {
    const [summary, doc] = await Promise.allSettled([getCaseSummary(caseId), getCaseDocument(caseId)]);
    if (summary.status === "fulfilled") setRow(summary.value);
    if (doc.status === "fulfilled") setOriginal(doc.value);
  }, [caseId]);

  useEffect(() => { void refresh(); void reload(); }, [caseId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (bundle && ["completed", "failed"].includes(bundle.status.state)) return;
    const timer = window.setInterval(() => { void refresh(true); void reload(); }, 2500);
    return () => window.clearInterval(timer);
  }, [bundle?.status.state, refresh, reload]);

  const view = useMemo(() => caseView(record, row, original), [record, row, original]);

  const supplement = async (fields: Record<string, string>) => {
    if (!bundle) return;
    const { validation } = await supplementCase(caseId, bundle.status.case_revision, fields);
    onRecordUpdate({ validation });
    await new Promise((resolve) => window.setTimeout(resolve, 700));
    await refresh();
  };
  const start = async () => { if (!bundle) return; setActionBusy(true); try { await startCorrespondence(caseId, bundle.status.case_revision); await refresh(); } catch (caught) { setError(apiErrorMessage(caught)); } finally { setActionBusy(false); } };
  const review = async () => { if (!bundle) return; setActionBusy(true); try { await completeReview(caseId, bundle.status.case_revision); await refresh(); } catch (caught) { setError(apiErrorMessage(caught)); } finally { setActionBusy(false); } };

  return (
    <div className="page-content case-detail-page">
      <div className="case-detail-header">
        <button className="back-link" onClick={onBack}><ArrowLeft size={17} />Dosyalara dön</button>
        <div className="case-title-row"><div className="large-doc-icon"><FileText size={25} /></div><div><span className="eyebrow">Case · {shortId(caseId)}</span><h2>{view.title}</h2><p>{view.sourceType === "ocr" ? "OCR-origin metin" : "Doğrudan metin"} · {view.createdAt ? formatDate(view.createdAt) : "Oluşturma zamanı yayımlanmadı"}{channelLabel(view.channel) ? ` · ${channelLabel(view.channel)}` : ""}</p></div><div className="case-header-actions">{bundle?.status.state === "needs_review" && <button className="secondary-button" onClick={review} disabled={actionBusy}><UserRoundCheck size={17} />İncelemeyi tamamla</button>}<button className="icon-button" onClick={() => { void refresh(); void reload(); }} disabled={refreshing} title="Yenile"><RefreshCw className={refreshing ? "spin" : ""} size={19} /></button></div></div>
        <div className="detail-tabs"><button className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}>Genel Bakış</button><button className={tab === "analysis" ? "active" : ""} onClick={() => setTab("analysis")}>AI Analizi</button><button className={tab === "correspondence" ? "active" : ""} onClick={() => setTab("correspondence")}>Yazışma</button><button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>İşlem Geçmişi</button></div>
      </div>
      {error && <div className="error-banner page-error"><AlertCircle size={18} /><span>{error}</span><button onClick={() => void refresh()}>Yeniden dene</button></div>}
      {!bundle ? <div className="panel loading-panel"><LoaderCircle className="spin" size={28} /><h3>Case durumu yükleniyor</h3><p>Workflow projection henüz oluşmadıysa birkaç saniye içinde yeniden deneyin.</p></div> : <>{tab === "summary" && <SummaryTab record={record} view={view} bundle={bundle} />}{tab === "analysis" && <AnalysisTab record={record} view={view} bundle={bundle} onSupplement={supplement} />}{tab === "correspondence" && <CorrespondenceTab result={bundle.correspondence} routing={bundle.routing} onStart={start} busy={actionBusy} />}{tab === "history" && <HistoryTab bundle={bundle} />}</>}
    </div>
  );
}

export function App({ view, caseId }: { view: View; caseId: string | null }) {
  const [cases, setCases] = useState<CaseRecord[]>(() => loadCases());
  const [page, setPage] = useState<CaseListPage | null>(null);
  const [counts, setCounts] = useState<QueueCounts | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [queueLoading, setQueueLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [health, setHealth] = useState<ServiceHealth[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const mode = modeFromHealth(health);

  useEffect(() => { void serviceHealth().then(setHealth); }, []);

  // Sayaçlar ayrı sorgularla alınır: liste sayfalandığı için gösterilen 25
  // satırdan çıkarılan bir toplam, kuyruğun tamamını yanlış anlatırdı.  Her
  // sekme kendi `state` sayısını sorar, `""` filtresiz toplamdır.
  const loadQueue = useCallback(async () => {
    setQueueLoading(true);
    try {
      const [list, ...totals] = await Promise.all([
        listCases({ limit: PAGE_SIZE, offset, state: stateFilter, q: search.trim() }),
        ...QUEUE_FILTERS.map((filter) => listCases({ limit: 1, state: filter.value })),
      ]);
      setPage(list);
      setCounts(Object.fromEntries(QUEUE_FILTERS.map((filter, index) => [filter.value, totals[index].total])));
      setQueueError(null);
    } catch (error) {
      setQueueError(apiErrorMessage(error));
    } finally {
      setQueueLoading(false);
    }
  }, [search, stateFilter, offset]);

  // Filtre ya da arama değiştiğinde sayfa başa döner: ikinci sayfada durup
  // filtreyi değiştirmek, sonucu olmayan bir sayfada boş tablo gösterirdi.
  useEffect(() => { setOffset(0); }, [search, stateFilter]);

  // Yazarken her tuşta sorgu atılmasın diye ilk çağrı kısa bir gecikmeyle
  // yapılır; sonrasında kuyruk beş saniyede bir kendini yeniler.
  useEffect(() => {
    if (view !== "overview") return;
    let cancelled = false;
    const run = () => { if (!cancelled) void loadQueue(); };
    const first = window.setTimeout(run, 300);
    const timer = window.setInterval(run, 5_000);
    return () => { cancelled = true; window.clearTimeout(first); window.clearInterval(timer); };
  }, [view, loadQueue]);

  const goTo = (next: View) => {
    setSidebarOpen(false);
    navigate(next === "new" ? PATHS.panelIntake : PATHS.panel);
  };
  const openCase = (id: string) => { setSidebarOpen(false); navigate(casePath(id)); };
  const created = (record: CaseRecord) => { setCases(saveCase(record)); navigate(casePath(record.caseId)); };
  const updateRecord = useCallback((updates: Partial<CaseRecord>) => {
    if (!caseId) return;
    setCases(updateStoredCase(caseId, updates));
  }, [caseId]);
  const selectedRecord = cases.find((item) => item.caseId === caseId);
  const headings = view === "overview"
    ? ["Genel Bakış", "Sistem durumu ve bekleyen işlemler"]
    : view === "new"
      ? ["Yeni Evrak", "Gerçek API contract’ı üzerinden yeni case oluşturun"]
      : ["Dosya Detayı", "Backend kaynaklı analiz ve süreç görünümü"];

  return (
    <div className="app-shell">
      <Sidebar view={view} onNavigate={goTo} mode={mode} health={health} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="main-shell">
        <Topbar title={headings[0]} subtitle={headings[1]} onMenu={() => setSidebarOpen(true)} onNew={() => goTo("new")} />
        {view === "overview" && (
          <Dashboard
            page={page}
            counts={counts}
            loading={queueLoading}
            error={queueError}
            search={search}
            stateFilter={stateFilter}
            offset={offset}
            onSearch={setSearch}
            onStateFilter={setStateFilter}
            onOffset={setOffset}
            onRefresh={() => void loadQueue()}
            onNew={() => goTo("new")}
            onOpen={openCase}
          />
        )}
        {view === "new" && <IntakePage mode={mode} onCreated={created} onCancel={() => goTo("overview")} />}
        {view === "case" && caseId && (
          <CaseDetail caseId={caseId} record={selectedRecord} onBack={() => goTo("overview")} onRecordUpdate={updateRecord} />
        )}
      </main>
    </div>
  );
}

