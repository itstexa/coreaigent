/**
 * Teşekkür sayfası (/dilekce/tesekkurler/<referans>).
 *
 * Gönderim sonrası vatandaşın gördüğü tek ekran.  Bilgi sekme belleğinden
 * okunur; sekme kapanmış ya da bağlantı paylaşılmışsa yalnızca referans
 * gösterilir, başvuru içeriği yeniden üretilmez.
 *
 * Sayfa dosyayı yeniden sorgulamaz: `GET /cases/{case_id}` ADMIN yetkisi
 * ister, vatandaş tarayıcısına böyle bir yetki verilmez.  Bu yüzden gösterilen
 * karar, gönderim anında portalda görülenin aynısıdır -- sonradan personelin
 * yaptığı değişiklikler burada görünmez.
 */

import {
  ArrowLeft, Building2, CheckCircle2, ClipboardCheck, FileText, Languages, MailCheck,
  PenLine, ShieldCheck, Sparkles, Tags,
} from "lucide-react";
import type { ReactNode } from "react";
import { useMemo } from "react";
import { loadReceipt, type PetitionReceipt } from "./petition-receipt";
import { PATHS, navigate } from "./router";

const LANGUAGE_LABELS: Record<string, string> = { tr: "Türkçe", en: "İngilizce", unknown: "Belirlenemedi" };

const COMPLETION_LABELS: Record<NonNullable<PetitionReceipt["completionStatus"]>, string> = {
  complete: "Eksiksiz",
  missing_information: "Eksik bilgi var",
  invalid_information: "Geçersiz bilgi var",
};

interface Step {
  icon: ReactNode;
  title: string;
  detail: string;
}

/**
 * Bundan sonra ne olacağı.
 *
 * Son adım makbuzun doğrulama sonucuna göre değişir: eksiksiz bir dosyada
 * vatandaşa "bilgi istenecek" demek yanlış olur, eksik bir dosyada ise
 * istenmeyecek demek olurdu.
 */
function stepsFor(receipt: PetitionReceipt | null): Step[] {
  const complete = receipt?.completionStatus === "complete";
  return [
    {
      icon: <ClipboardCheck size={17} />,
      title: "Başvurunuz kaydedildi",
      detail: "Dilekçeniz kurum evrak kaydına alındı, talep türü ve ilgili birim metninizden belirlendi.",
    },
    {
      icon: <Building2 size={17} />,
      title: "İlgili birime yönlendirilir",
      detail: receipt?.unitHint
        ? `Dosyanız ${receipt.unitHint} kuyruğuna düşer ve personelin incelemesini bekler.`
        : "Dosyanız sınıflandırma sonucuna göre yetkili birimin kuyruğuna düşer.",
    },
    {
      icon: <PenLine size={17} />,
      title: "Resmî yazı taslağı hazırlanır",
      detail: "Yapay zekâ mevzuat kaynaklarına dayanan bir taslak üretir; içeriği yetkili personel inceleyip onaylar.",
    },
    complete
      ? {
          icon: <MailCheck size={17} />,
          title: "Sonuç tarafınıza bildirilir",
          detail: "Dilekçenizde eksik ya da geçersiz bir alan bulunmadı; işlem sonucu kayıt üzerinden bildirilir.",
        }
      : {
          icon: <MailCheck size={17} />,
          title: "Eksik bilgi istenir",
          detail: "Dosyanızda tamamlanması gereken alanlar var; kurum bu bilgiler için sizinle iletişime geçer.",
        },
  ];
}

function percent(value: number): string {
  return `%${Math.round(value * 100)}`;
}

export function PetitionThanks({ reference }: { reference: string }) {
  const receipt = useMemo(() => loadReceipt(reference), [reference]);
  const steps = useMemo(() => stepsFor(receipt), [receipt]);

  return (
    <div className="portal">
      <header className="portal-header">
        <div className="brand-mark"><Sparkles size={17} /></div>
        <div><strong>Demo Belediye Başkanlığı</strong><small>Vatandaş e-Dilekçe Portalı</small></div>
        <button className="portal-back" onClick={() => navigate(PATHS.landing)}>
          <ArrowLeft size={15} /> Ana sayfa
        </button>
      </header>

      <main className="thanks-main">
        <div className="thanks-card">
          <div className="thanks-icon"><CheckCircle2 size={30} /></div>
          <h1>Dilekçenizi gönderdiğiniz için teşekkür ederiz</h1>
          <p className="lede">
            Başvurunuz kurum kaydına alınmıştır. Aşağıdaki başvuru referansını saklayın;
            başvurunuzla ilgili görüşmelerde bu numara üzerinden işlem yapılır.
          </p>
          <div className="reference-code">
            <span>Başvuru referansı</span>
            <strong>{reference}</strong>
          </div>

          {receipt && (
            <section className="thanks-decision">
              <header>
                <span><Tags size={12} /> Yapay zekânın kararı</span>
                <h2>{receipt.subjectLabel}</h2>
                <p>{receipt.unitHint} birimine yönlendirilecek</p>
              </header>

              {typeof receipt.confidence === "number" && (
                <div className="confidence">
                  <div className="confidence-head">
                    <span>Sınıflandırma güveni</span>
                    <strong>{percent(receipt.confidence)}</strong>
                  </div>
                  <div className="confidence-bar"><i style={{ width: `${Math.round(receipt.confidence * 100)}%` }} /></div>
                  {receipt.reason && <p>{receipt.reason}</p>}
                </div>
              )}

              <div className="decision-facts">
                <div><span><Languages size={13} /> Dil</span><strong>{LANGUAGE_LABELS[receipt.language ?? "unknown"]}</strong></div>
                <div><span><FileText size={13} /> Evrak</span><strong>{receipt.documentId}</strong></div>
                <div>
                  <span><ClipboardCheck size={13} /> Doğrulama</span>
                  <strong>{receipt.completionStatus ? COMPLETION_LABELS[receipt.completionStatus] : "Çalıştırılmadı"}</strong>
                </div>
                <div>
                  <span><Building2 size={13} /> Gönderim</span>
                  <strong>{new Date(receipt.submittedAt).toLocaleString("tr-TR")}</strong>
                </div>
              </div>

              {typeof receipt.fieldCount === "number" && (
                <p className="thanks-fields">
                  Dilekçenizden {receipt.fieldCount} alan çıkarıldı ve kurum kayıt defterindeki kurallarla denetlendi.
                </p>
              )}
            </section>
          )}

          <div className="thanks-timeline">
            <strong>Bundan sonra ne olacak?</strong>
            {steps.map((step) => (
              <div key={step.title}>
                <span>{step.icon}</span>
                <p><strong>{step.title}</strong>{step.detail}</p>
              </div>
            ))}
          </div>

          <div className="thanks-actions">
            <button className="primary-button" onClick={() => navigate(PATHS.petition)}>
              <FileText size={17} /> Yeni dilekçe gönder
            </button>
            <button className="ghost-button" onClick={() => navigate(PATHS.landing)}>Ana sayfaya dön</button>
          </div>
          <p className="thanks-note">
            <ShieldCheck size={13} /> Başvurunuzun içeriği bu sekmenin dışında saklanmaz.
            Nihai idari karar her zaman yetkili personeldedir.
          </p>
        </div>
      </main>
    </div>
  );
}
