/**
 * Vatandaş e-Dilekçe portalı (/dilekce).
 *
 * Vatandaş dilekçesini kendi cümleleriyle yazar; portal metne dokunmaz.  Konu
 * seçimi, alan formu ve şablon yoktur, çünkü ürünün gösterdiği şey tam olarak
 * bunun tersi: serbest bir dilekçeden talep türünü, ilgili birimi ve dosyanın
 * alanlarını yapay zekânın kendisinin çıkarması.
 *
 * Gönderimden sonra hattın her adımı vatandaşa görünür kalır: F-01 dili ve
 * evrak kaydını, F-02 talep türünü güven puanı ve Türkçe gerekçesiyle, F-03 ise
 * metinden çıkardığı alanları güven değerleriyle bildirir.  Yapay zekâ bir alanı
 * bulamadıysa yalnız o alan vatandaşa sorulur ve `supplemental-information`
 * ile dosyaya eklenir; portal hiçbir kararı kendi başına vermez.
 */

import {
  AlertTriangle, ArrowLeft, Building2, CheckCircle2, CircleDashed, FileSearch, FileText,
  Languages, LoaderCircle, ScanText, Send, ShieldCheck, Sparkles, Tags, Timer, Wand2,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { apiErrorMessage, revisionFrom, runIntake, supplementCase, type IntakeProgress } from "./api";
import {
  MIN_TEXT_LENGTH,
  PETITION_CHANNEL,
  SAMPLES,
  fieldDef,
  normalizedLength,
  petitionReference,
  petitionTextIssues,
  petitionTitle,
  supplementIssue,
  supplementValue,
  type PetitionFieldDef,
  type PetitionSample,
} from "./petition";
import { saveReceipt, type PetitionReceipt } from "./petition-receipt";
import { PATHS, navigate, thanksPath } from "./router";
import type { CaseRecord, ValidationResult } from "./types";

type Phase = "write" | "analyzing" | "result";

interface Stage {
  feature: string;
  icon: ReactNode;
  title: string;
  detail: string;
}

/**
 * Hattın vatandaşa gösterilen adımları.
 *
 * Sıra `runIntake`'in bildirdiği adım sırasıyla birebir aynıdır; RAG ve taslak
 * üretimi vatandaş tarafında tek bir "dosya açılışı" adımı olarak görünür,
 * çünkü ikisi de gönderimden sonra kurum içinde sürer.
 */
const STAGES: Stage[] = [
  {
    feature: "F-01",
    icon: <ScanText size={15} />,
    title: "Evrak alımı ve dil tespiti",
    detail: "Metin normalleştirilir, dili işaret kelimelerinden belirlenir ve kurum evrak kaydına alınır.",
  },
  {
    feature: "F-02",
    icon: <Tags size={15} />,
    title: "Talep sınıflandırma",
    detail: "Taksonomideki konu sinyalleri sayılır; talep türü, ilgili birim ve güven puanı belirlenir.",
  },
  {
    feature: "F-03",
    icon: <FileSearch size={15} />,
    title: "Alan çıkarımı ve doğrulama",
    detail: "Kimlik, tarih ve konu alanları serbest metinden çıkarılır, kayıt defterindeki kurallarla denetlenir.",
  },
  {
    feature: "F-05",
    icon: <Building2 size={15} />,
    title: "Dosya açılışı ve yönlendirme",
    detail: "Case yaşam döngüsü başlatılır ve dosya yetkili birimin kuyruğuna düşer.",
  },
];

const STAGE_OF: Record<IntakeProgress["step"], number> = {
  intake: 0,
  classification: 1,
  validation: 2,
  rag: 3,
  generation: 3,
  queued: 3,
};

const LANGUAGE_LABELS: Record<string, string> = { tr: "Türkçe", en: "İngilizce", unknown: "Belirlenemedi" };

const COMPLETION_LABELS: Record<ValidationResult["completionStatus"], string> = {
  complete: "Dosya eksiksiz",
  missing_information: "Eksik bilgi var",
  invalid_information: "Geçersiz bilgi var",
};

/**
 * Boş alanın kendisi bir yönlendirme.
 *
 * Vatandaşa "ne yazacağımı bilmiyorum" dedirtmemek için hitap satırı ve
 * anlatılması beklenen üç şey örnek olarak durur; metnin tamamı silinebilir,
 * portal bu ipuçlarının hiçbirini dilekçeye eklemez.
 */
const PLACEHOLDER = `İlgili Birime,

Talebinizi kendi cümlelerinizle anlatın: neyin, nerede ve ne zaman olduğunu, kurumdan ne istediğinizi yazın. Adınızı, T.C. kimlik numaranızı ve ulaşılabilir telefonunuzu da eklerseniz dosyanız daha hızlı ilerler.

Ad Soyad
T.C. Kimlik No:
Telefon:`;

/**
 * Alanın değerini kimin bulduğu.
 *
 * Doğrulama servisi kimlik numarasını, telefonu ve tarihi desenle bulup
 * sağlamasından geçirir; kalan alanları dil modeli çıkarır.  Vatandaşa hangi
 * değerin nasıl bulunduğunu söylemek, güven puanının tek başına anlatmadığı
 * şeydir.
 */
const RULE_KINDS = new Set<PetitionFieldDef["kind"]>(["tckn", "phone", "date"]);

function fieldSource(fieldId: string): { label: string; title: string } {
  return RULE_KINDS.has(fieldDef(fieldId).kind)
    ? { label: "Kural", title: "Desenle bulundu ve sağlama algoritmasından geçirildi." }
    : { label: "Dil modeli", title: "Dil modeli metinden çıkardı; kayıt defteri kuralıyla doğrulandı." };
}

function percent(value: number): string {
  return `%${Math.round(value * 100)}`;
}

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} sn`;
}

function SupplementField({ field, value, onChange }: { field: PetitionFieldDef; value: string; onChange: (next: string) => void }) {
  const id = `eksik-${field.id}`;
  return (
    <div className={`portal-field ${field.kind === "textarea" ? "wide" : ""}`}>
      <label htmlFor={id}>{field.label}<span> *</span></label>
      {field.kind === "textarea" ? (
        <textarea id={id} value={value} placeholder={field.placeholder} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <input
          id={id}
          type={field.kind === "date" ? "date" : "text"}
          inputMode={field.kind === "tckn" || field.kind === "phone" ? "numeric" : undefined}
          maxLength={field.kind === "tckn" ? 11 : undefined}
          value={value}
          placeholder={field.placeholder}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {field.hint && <small>{field.hint}</small>}
    </div>
  );
}

export function PetitionForm() {
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>("write");
  const [issues, setIssues] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [marks, setMarks] = useState<Array<{ stage: number; at: number }>>([]);
  const [now, setNow] = useState(() => Date.now());
  const [record, setRecord] = useState<CaseRecord | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [revision, setRevision] = useState<number | undefined>(undefined);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [answerIssues, setAnswerIssues] = useState<string[]>([]);
  const [answersBusy, setAnswersBusy] = useState(false);
  const [answered, setAnswered] = useState(false);
  const [usedSample, setUsedSample] = useState<string | null>(null);

  const length = normalizedLength(text);
  const classification = record?.classification;
  const reference = record ? petitionReference(record.caseId) : "";

  // Canlı geçen süre: hattın hangi adımında ne kadar beklendiği vatandaşın
  // gördüğü tek performans bilgisi, bu yüzden tahmini değil ölçülen süre.
  useEffect(() => {
    if (phase !== "analyzing") return;
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [phase]);

  const stageState = (index: number): "done" | "running" | "waiting" => {
    const reached = marks.some((mark) => mark.stage >= index);
    if (!reached) return "waiting";
    if (phase === "result") return "done";
    return marks.some((mark) => mark.stage > index) ? "done" : "running";
  };

  const stageElapsed = (index: number): number | null => {
    const start = marks.find((mark) => mark.stage === index);
    if (!start) return null;
    const next = marks.find((mark) => mark.stage > index);
    return (next?.at ?? (phase === "analyzing" ? now : marks.at(-1)?.at ?? now)) - start.at;
  };

  const totalElapsed = marks.length ? (phase === "analyzing" ? now : marks.at(-1)?.at ?? now) - marks[0].at : 0;

  /**
   * Yapay zekânın vatandaşa sorduğu alanlar.
   *
   * Liste doğrulama servisinden gelir; portal kendi zorunlu alan fikrini
   * eklemez.  Ek dosya isteyen bir alan sorulamaz, çünkü portalda yükleme yok:
   * o alan ayrı bir not olarak gösterilir.
   */
  const asked = useMemo<PetitionFieldDef[]>(() => {
    if (!validation) return [];
    const seen = new Map<string, PetitionFieldDef>();
    for (const field of [...validation.missingRequiredFields, ...validation.invalidFields]) {
      const definition = fieldDef(field.id, field.label);
      if (definition.kind !== "attachment" && !seen.has(field.id)) seen.set(field.id, definition);
    }
    return [...seen.values()].slice(0, 8);
  }, [validation]);

  const attachmentAsked = useMemo(() => {
    if (!validation) return [] as PetitionFieldDef[];
    return validation.missingRequiredFields
      .map((field) => fieldDef(field.id, field.label))
      .filter((field) => field.kind === "attachment");
  }, [validation]);

  const receiptOf = (created: CaseRecord, state: ValidationResult | null): PetitionReceipt => ({
    reference: petitionReference(created.caseId),
    caseId: created.caseId,
    documentId: created.documentId,
    subjectLabel: created.classification?.requestType?.label ?? "Talep türü belirlenemedi",
    unitHint: created.classification?.unit?.label ?? "Manuel inceleme",
    submittedAt: created.createdAt,
    state: created.state,
    confidence: created.classification?.confidence,
    reason: created.classification?.classificationReason,
    completionStatus: state?.completionStatus,
    fieldCount: state?.extractedFields.length,
    language: created.language,
  });

  const onProgress = (progress: IntakeProgress) => {
    const stage = STAGE_OF[progress.step] ?? 0;
    setMessage(progress.message);
    setMarks((current) => (current.at(-1)?.stage === stage ? current : [...current, { stage, at: Date.now() }]));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (phase === "analyzing") return;
    const found = petitionTextIssues(text);
    setIssues(found);
    if (found.length) {
      setError(null);
      return;
    }
    const title = petitionTitle(text);
    setError(null);
    setMarks([]);
    setNow(Date.now());
    setAnswered(false);
    setAnswerIssues([]);
    setPhase("analyzing");
    try {
      const created = await runIntake(
        {
          title,
          text,
          sourceType: "text",
          sourceMetadata: { title, channel: PETITION_CHANNEL, ...(usedSample ? { sample: usedSample } : {}) },
        },
        onProgress,
      );
      setRecord(created);
      setValidation(created.validation ?? null);
      setRevision(created.validationRevision);
      setAnswers({});
      saveReceipt(receiptOf(created, created.validation ?? null));
      setPhase("result");
    } catch (issue) {
      setError(apiErrorMessage(issue));
      setPhase("write");
    }
  };

  const sendAnswers = async () => {
    if (!record || !revision || answersBusy) return;
    const problems = asked
      .map((field) => supplementIssue(field, answers[field.id] ?? ""))
      .filter((problem): problem is string => Boolean(problem));
    setAnswerIssues(problems);
    if (problems.length) return;
    setAnswersBusy(true);
    try {
      const fields = Object.fromEntries(asked.map((field) => [field.id, supplementValue(field, answers[field.id] ?? "")]));
      const { validation: next, etag } = await supplementCase(record.caseId, revision, fields);
      setValidation(next);
      setRevision(revisionFrom(etag));
      setAnswers({});
      setAnswered(true);
      saveReceipt(receiptOf(record, next));
    } catch (issue) {
      setAnswerIssues([apiErrorMessage(issue)]);
    } finally {
      setAnswersBusy(false);
    }
  };

  const useSample = (sample: PetitionSample) => {
    setText(sample.sampleText);
    setUsedSample(sample.requestTypeId);
    setIssues([]);
    setError(null);
  };

  /**
   * Yeni bir dilekçeye dönüş.
   *
   * Makbuz `sessionStorage`'da kalır, çünkü açılan dosya gerçekten var; sıfırlanan
   * yalnız bu sayfanın çözümleme durumudur.
   */
  const restart = () => {
    setPhase("write");
    setText("");
    setRecord(null);
    setValidation(null);
    setRevision(undefined);
    setMarks([]);
    setIssues([]);
    setError(null);
    setMessage("");
    setAnswers({});
    setAnswerIssues([]);
    setAnswered(false);
    setUsedSample(null);
    window.scrollTo({ top: 0 });
  };

  return (
    <div className="portal">
      <header className="portal-header">
        <div className="brand-mark"><Sparkles size={17} /></div>
        <div><strong>CoreAIgent</strong><small>Dilekçe Analiz Akışı</small></div>
        <button className="portal-back" onClick={() => navigate(PATHS.landing)}>
          <ArrowLeft size={15} /> Ana sayfa
        </button>
      </header>

      <main className="portal-main">
        <div className="portal-inner">
          <div className="portal-head">
            <span><FileText size={13} /> Dilekçe yaz</span>
            <h1>{phase === "result" ? "Dilekçeniz çözümlendi" : "Dilekçenizi kendi cümlelerinizle yazın"}</h1>
            <p>
              {phase === "result"
                ? "Aşağıda yapay zekânın dilekçenizden çıkardığı sonuçları görüyorsunuz. Eksik bir alan varsa yalnız o alan sorulur; nihai karar her zaman yetkili personeldedir."
                : "Konu seçmenize, form doldurmanıza gerek yok. Talebinizi anlatın; talep türünü, ilgili birimi ve dilekçenizdeki bilgileri yapay zekâ metninizden çıkarır."}
            </p>
          </div>

          <div className="portal-grid">
            {phase === "result" && record ? (
              <div className="portal-form">
                <section className="decision-card">
                  <header>
                    <div className="decision-mark"><CheckCircle2 size={20} /></div>
                    <div>
                      <h2>{classification?.requestType?.label ?? "Talep türü belirlenemedi"}</h2>
                      <p>
                        {classification?.status === "classified"
                          ? `${classification.department?.label ?? "-"} · ${classification.unit?.label ?? "-"} birimine yönlendirilecek`
                          : "Sınıflandırıcı yeterli güvene ulaşamadı; dosyanız insan incelemesine düştü."}
                      </p>
                    </div>
                    <div className="decision-reference"><span>Başvuru referansı</span><strong>{reference}</strong></div>
                  </header>

                  <div className="confidence">
                    <div className="confidence-head">
                      <span>Sınıflandırma güveni</span>
                      <strong>{percent(classification?.confidence ?? 0)}</strong>
                    </div>
                    <div className="confidence-bar"><i style={{ width: `${Math.round((classification?.confidence ?? 0) * 100)}%` }} /></div>
                    <p>{classification?.classificationReason ?? "Sınıflandırma gerekçesi bildirilmedi."}</p>
                  </div>

                  <div className="decision-facts">
                    <div><span><Languages size={13} /> Dil</span><strong>{LANGUAGE_LABELS[record.language ?? "unknown"]}</strong></div>
                    <div><span><FileText size={13} /> Evrak</span><strong>{record.documentId}</strong></div>
                    <div><span><Timer size={13} /> Süre</span><strong>{seconds(totalElapsed)}</strong></div>
                    <div><span><Tags size={13} /> Model</span><strong>{classification?.classifierVersion ?? "-"}</strong></div>
                  </div>
                </section>

                <section className="portal-step">
                  <header>
                    <b>F-03</b>
                    <div>
                      <h2>Metinden çıkarılan bilgiler</h2>
                      <p>
                        {validation
                          ? `${COMPLETION_LABELS[validation.completionStatus]} · ${validation.extractedFields.length} alan bulundu`
                          : "Talep türü belirlenemediği için alan çıkarımı çalıştırılmadı."}
                      </p>
                    </div>
                  </header>
                  {validation && validation.extractedFields.length > 0 ? (
                    <table className="field-table">
                      <thead>
                        <tr><th>Alan</th><th>Değer</th><th>Kaynak</th><th>Güven</th></tr>
                      </thead>
                      <tbody>
                        {validation.extractedFields.map((field) => {
                          const source = fieldSource(field.id);
                          return (
                            <tr key={field.id}>
                              <td>{field.label}</td>
                              <td className="value">{field.value}</td>
                              <td><span className={`badge ${source.label === "Kural" ? "rule" : "model"}`} title={source.title}>{source.label}</span></td>
                              <td className="confidence-cell">{percent(field.confidence)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  ) : (
                    <p className="empty-note">Dilekçenizden doğrulanabilir bir alan çıkarılamadı.</p>
                  )}
                </section>

                {asked.length > 0 && (
                  <section className="portal-step">
                    <header>
                      <b><Wand2 size={14} /></b>
                      <div>
                        <h2>Yapay zekânın bulamadığı bilgiler</h2>
                        <p>Dilekçenizde yer almadığı için bu alanlar sorulur; yalnız bunları doldurmanız yeterli.</p>
                      </div>
                    </header>
                    <div className="portal-fields">
                      {asked.map((field) => (
                        <SupplementField
                          key={field.id}
                          field={field}
                          value={answers[field.id] ?? ""}
                          onChange={(next) => setAnswers((current) => ({ ...current, [field.id]: next }))}
                        />
                      ))}
                    </div>
                    {answerIssues.length > 0 && (
                      <div className="portal-issues supplement-issues">
                        <strong><AlertTriangle size={16} /> Bilgiler gönderilemedi</strong>
                        <ul>{answerIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
                      </div>
                    )}
                    <div className="supplement-actions">
                      <button className="primary-button" type="button" onClick={sendAnswers} disabled={!revision || answersBusy}>
                        {answersBusy ? <LoaderCircle size={16} className="spin" /> : <Send size={16} />}
                        {answersBusy ? "Gönderiliyor…" : "Eksik bilgileri gönder"}
                      </button>
                      <p>
                        {revision
                          ? "Bilgiler dosyanıza eklenir ve doğrulama yeniden çalışır."
                          : "Bu dosyada tamamlama isteği açık değil; eksik bilgi için kurum sizinle iletişime geçecek."}
                      </p>
                    </div>
                  </section>
                )}

                {attachmentAsked.length > 0 && (
                  <div className="portal-issues">
                    <strong><AlertTriangle size={16} /> Kuruma iletilmesi gereken ek</strong>
                    <ul>
                      {attachmentAsked.map((field) => (
                        <li key={field.id}>{field.label} portaldan yüklenemez; kuruma elden veya e-posta ile iletmeniz gerekir.</li>
                      ))}
                    </ul>
                  </div>
                )}

                {answered && asked.length === 0 && (
                  <div className="portal-note success">
                    <CheckCircle2 size={16} /> Gönderdiğiniz bilgiler dosyanıza eklendi ve doğrulama yeniden çalıştı.
                  </div>
                )}

                <div className="portal-actions">
                  <button className="primary-button" type="button" onClick={() => navigate(thanksPath(reference))}>
                    <CheckCircle2 size={17} /> Başvurumu tamamla
                  </button>
                  <button className="ghost-button" type="button" onClick={restart}>Yeni dilekçe yaz</button>
                  <p>Dosyanız kurum kaydında açık kaldı; referans numaranızla takip edebilirsiniz.</p>
                </div>
              </div>
            ) : (
              <form className="portal-form" onSubmit={submit}>
                <section className="portal-step">
                  <header>
                    <b>1</b>
                    <div><h2>Dilekçe metni</h2><p>Talebinizi, adresinizi ve kimlik bilgilerinizi kendi cümlelerinizle yazın.</p></div>
                  </header>
                  <div className="compose-box">
                    <textarea
                      id="dilekce-metni"
                      value={text}
                      disabled={phase === "analyzing"}
                      onChange={(event) => { setText(event.target.value); setUsedSample(null); }}
                      placeholder={PLACEHOLDER}
                    />
                    <div className="compose-meter">
                      <span className={length > 0 && length < MIN_TEXT_LENGTH ? "short" : ""}>{length} karakter</span>
                      <span>En az {MIN_TEXT_LENGTH} karakter</span>
                    </div>
                  </div>
                  <div className="sample-block">
                    <strong><Wand2 size={13} /> Örnek dilekçelerden başlayın</strong>
                    <p>Örnekler yalnız başlangıç metnidir; dilediğiniz gibi değiştirin. Talep türünü her hâlükârda sınıflandırıcı belirler.</p>
                    <div className="sample-chips">
                      {SAMPLES.map((sample) => (
                        <button
                          type="button"
                          key={sample.requestTypeId}
                          className={`chip ${usedSample === sample.requestTypeId ? "active" : ""}`}
                          title={sample.summary}
                          disabled={phase === "analyzing"}
                          onClick={() => useSample(sample)}
                        >
                          {sample.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </section>

                {issues.length > 0 && (
                  <div className="portal-issues">
                    <strong><AlertTriangle size={16} /> Gönderebilmek için</strong>
                    <ul>{issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
                  </div>
                )}
                {error && (
                  <div className="portal-issues">
                    <strong><AlertTriangle size={16} /> Dilekçe gönderilemedi</strong>
                    <ul><li>{error}</li></ul>
                  </div>
                )}

                <div className="portal-actions">
                  <button className="primary-button" type="submit" disabled={phase === "analyzing"}>
                    {phase === "analyzing" ? <LoaderCircle size={17} className="spin" /> : <Send size={17} />}
                    {phase === "analyzing" ? "Çözümleniyor…" : "Dilekçemi gönder"}
                  </button>
                  <p>
                    {phase === "analyzing" && message
                      ? message
                      : "Gönderdiğinizde dilekçeniz kurum kaydına alınır, yapay zekâ çözümlemesi hemen yanda görünür."}
                  </p>
                </div>
              </form>
            )}

            <aside className="portal-aside">
              <div className="portal-card">
                <h3><Wand2 size={16} /> Yapay zekâ hattı</h3>
                <ol className="pipeline">
                  {STAGES.map((stage, index) => {
                    const state = phase === "write" ? "waiting" : stageState(index);
                    const elapsed = phase === "write" ? null : stageElapsed(index);
                    return (
                      <li key={stage.feature} className={`stage ${state}`}>
                        <span className="stage-state">
                          {state === "done" ? <CheckCircle2 size={15} /> : state === "running" ? <LoaderCircle size={15} className="spin" /> : <CircleDashed size={15} />}
                        </span>
                        <div>
                          <strong>{stage.icon} {stage.title} <em>{stage.feature}</em></strong>
                          <p>{stage.detail}</p>
                          {elapsed !== null && <span className="stage-time"><Timer size={11} /> {seconds(elapsed)}</span>}
                        </div>
                      </li>
                    );
                  })}
                </ol>
                {phase !== "write" && (
                  <div className="pipeline-total"><span>Toplam süre</span><strong>{seconds(totalElapsed)}</strong></div>
                )}
              </div>

              <div className="portal-card">
                <h3><FileSearch size={16} /> Bu dilekçede</h3>
                <div className="portal-summary">
                  <div><span>Sistem</span><strong>CoreAIgent</strong></div>
                  <div><span>Karakter</span><strong>{length}</strong></div>
                  <div><span>Kayıt başlığı</span><strong>{length ? petitionTitle(text) : "—"}</strong></div>
                  <div><span>Kanal</span><strong>Doğrudan dilekçe</strong></div>
                  {record?.state && <div><span>Dosya durumu</span><strong>{record.state}</strong></div>}
                </div>
              </div>

              <div className="portal-card">
                <h3><ShieldCheck size={16} /> Bilgilendirme</h3>
                <ul className="portal-notes">
                  <li>Talep türü ve ilgili birim taksonomiye göre belirlenir; gerekçesi size de gösterilir.</li>
                  <li>Yapay zekâ bir alanı bulamazsa yalnız o alan sorulur, formun tamamı istenmez.</li>
                  <li>Güven eşiği aşılmazsa dosya doğrudan insan incelemesine düşer.</li>
                  <li>Nihai idari karar her zaman yetkili personeldedir.</li>
                </ul>
              </div>
            </aside>
          </div>
        </div>
      </main>
    </div>
  );
}
