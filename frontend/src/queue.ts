/**
 * Panel kuyruğunun ve dosya detayının saf yardımcıları.
 *
 * Bu dosya bilerek React'ten bağımsız: kuyruk sekmeleri, bekleme süresi, güven
 * eşiği ve dosya görünümünün birleştirme sırası panelin doğruluk taşıyan
 * kısmıdır ve bir tarayıcı ortamı kurmadan sınanabilmesi gerekir.
 */

import type { CaseDocument, CaseListItem, CaseRecord } from "./types";

/** `GET /cases` bir sorguda en çok bu kadar satır ister; sayfalama adımı da bu. */
export const PAGE_SIZE = 25;

/**
 * Kuyruk sekmeleri.
 *
 * Her sekmenin sayısı ayrı bir `GET /cases?limit=1&state=…` çağrısından gelir:
 * gösterilen sayfa 25 satırla sınırlı olduğu için satırlardan sayılan bir
 * toplam, kuyruğun tamamını yanlış anlatırdı.  `""` filtresiz toplamdır.
 */
export const QUEUE_FILTERS: Array<{ value: string; label: string; short: string }> = [
  { value: "", label: "Tümü", short: "Tümü" },
  { value: "needs_review", label: "İnsan incelemesi", short: "İnceleme" },
  { value: "waiting_for_user", label: "Ek bilgi bekleniyor", short: "Ek bilgi" },
  { value: "ready_for_processing", label: "Taslak hazırlanıyor", short: "Hazırlanıyor" },
  { value: "draft_prepared", label: "Taslak hazır", short: "Taslak" },
  { value: "completed", label: "Tamamlandı", short: "Tamamlanan" },
];

/** Filtre değerinden o durumdaki dosya sayısına; `""` filtresiz toplam. */
export type QueueCounts = Record<string, number>;

export const CHANNEL_LABELS: Record<string, string> = {
  "citizen-portal": "Vatandaş portalı",
  "operator-console": "Operatör",
};

export function channelLabel(value?: string | null): string | null {
  return value ? CHANNEL_LABELS[value] ?? value : null;
}

const LANGUAGE_LABELS: Record<string, string> = { tr: "Türkçe", en: "İngilizce", unknown: "Belirlenemedi" };

export function languageLabel(value?: string | null): string {
  return value ? LANGUAGE_LABELS[value] ?? value : "Belirlenemedi";
}

/** Başvuran adının baş harfleri; ad yoksa satır boş bir daire göstermez. */
export function initials(name?: string | null): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return parts.slice(0, 2).map((part) => part.charAt(0).toLocaleUpperCase("tr-TR")).join("");
}

/**
 * Dosyanın kuyrukta bekleme süresi.
 *
 * Bir operatör "22 Ağu 14:30" ile değil "18 dk bekliyor" ile çalışır: hangi
 * dosyanın unutulduğu ancak yaşından okunur.  Kesin tarih tabloda `title`
 * olarak kalır.
 */
export function relativeAge(value?: string | null, now: number = Date.now()): string {
  if (!value) return "—";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "—";
  const minutes = Math.max(0, Math.round((now - then) / 60_000));
  if (minutes < 1) return "az önce";
  if (minutes < 60) return `${minutes} dk`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} sa`;
  return `${Math.round(hours / 24)} gün`;
}

/**
 * Güven puanının rengi.
 *
 * Eşik F-02'nin kendi eşiğidir (`status_for_score` > 0.80): altında kalan dosya
 * `needs_review` olarak açılır, o yüzden tabloda da uyarı rengiyle durur.
 */
export function confidenceTone(value?: number | null): "high" | "mid" | "low" | "none" {
  if (typeof value !== "number") return "none";
  if (value > 0.8) return "high";
  if (value >= 0.5) return "mid";
  return "low";
}

/**
 * Dosya detayının birleşik görünümü.
 *
 * Panel eskiden sınıflandırma etiketlerini, gerekçeyi ve dilekçe metnini
 * yalnızca `localStorage`'dan okuyordu: vatandaş dilekçesini kendi
 * telefonundan gönderdiğinde operatörün ekranında bu alanların hepsi boş
 * kalıyordu.  Artık öncelik sunucudadır -- kuyruk satırı ve
 * `GET /cases/{case_id}/document` yetkili kaynaklardır -- yerel kayıt yalnızca
 * sunucunun yayımlamadığı alanları (sınıflandırıcı sürümü, çıkarılan alan
 * listesi) tamamlar.
 */
export interface CaseView {
  title: string;
  documentId: string | null;
  createdAt: string | null;
  channel: string | null;
  language: string | null;
  applicantName: string | null;
  requestTypeLabel: string | null;
  departmentLabel: string | null;
  unitLabel: string | null;
  confidence: number | null;
  reason: string | null;
  classifierVersion: string | null;
  taxonomyVersion: string | null;
  sourceType: string | null;
  text: string | null;
  textOrigin: "server" | "local" | null;
}

export function caseView(
  record: CaseRecord | undefined,
  row: CaseListItem | null,
  original: CaseDocument | null,
): CaseView {
  const classification = record?.classification;
  return {
    title: original?.title ?? row?.title ?? record?.title ?? "Case detayı",
    documentId: original?.document_id ?? row?.document_id ?? record?.documentId ?? null,
    createdAt: original?.created_at ?? row?.created_at ?? record?.createdAt ?? null,
    channel: original?.channel ?? row?.channel ?? null,
    language: original?.language ?? row?.language ?? record?.language ?? null,
    applicantName: row?.applicant_name ?? null,
    requestTypeLabel: row?.request_type_label ?? classification?.requestType?.label ?? null,
    departmentLabel: row?.department_label ?? classification?.department?.label ?? null,
    unitLabel: row?.unit_label ?? classification?.unit?.label ?? null,
    confidence: row?.classification_confidence ?? classification?.confidence ?? null,
    reason: row?.classification_reason ?? classification?.classificationReason ?? null,
    classifierVersion: classification?.classifierVersion ?? null,
    taxonomyVersion: classification?.taxonomyVersion ?? null,
    sourceType: original?.source_type ?? record?.sourceType ?? null,
    text: original?.text ?? record?.sourceText ?? null,
    textOrigin: original ? "server" : record?.sourceText ? "local" : null,
  };
}
