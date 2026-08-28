/**
 * Vatandaş e-Dilekçe portalının metin tarafı.
 *
 * Portal dilekçeyi kurmaz: vatandaş kendi cümleleriyle yazar, talep türünü F-02
 * taksonomi sınıflandırıcısı, alanları F-03 çıkarımı belirler.  Bu dosyada
 * yalnız gönderim öncesi vatandaşa yardımcı olan yerel denetimler ve
 * doğrulama servisinin eksik bulduğu alanı sorabilmek için gereken alan
 * kataloğu bulunur.  Karar her hâlükârda servislerde yeniden verilir; burada
 * yapılan hiçbir kontrol servisin yerine geçmez.
 *
 * Örnek dilekçelerin gerçek sınıflandırıcıya karşı doğrulandığı test:
 * tests/test_citizen_portal_templates.py
 */

import content from "./petition-content.json";
import type { ValidationResult } from "./types";

export type PetitionFieldKind = "text" | "textarea" | "date" | "tckn" | "phone" | "attachment";

export interface PetitionFieldDef {
  id: string;
  label: string;
  kind: PetitionFieldKind;
  placeholder?: string;
  hint?: string;
}

/** Vatandaşa başlangıç metni olarak sunulan örnek dilekçe. */
export interface PetitionSample {
  requestTypeId: string;
  label: string;
  summary: string;
  unitHint: string;
  sampleText: string;
}

export const AUTHORITY: string = content.authority;
export const SAMPLES = content.samples as PetitionSample[];
export const FIELD_CATALOG = content.fieldCatalog as PetitionFieldDef[];
/** Portalın kendi alt sınırı; intake servisi 40 normalleştirilmiş karakter ister. */
export const MIN_TEXT_LENGTH: number = content.minTextLength;
export const MAX_TEXT_LENGTH = 20_000;

export const PETITION_CHANNEL = "citizen-portal";

export function sampleById(requestTypeId: string): PetitionSample | undefined {
  return SAMPLES.find((sample) => sample.requestTypeId === requestTypeId);
}

/**
 * Doğrulama servisinin adıyla andığı alanı vatandaşa sorulabilir hâle getirir.
 *
 * Katalogda olmayan bir alan kimliği hata değil: kayıt defteri portaldan
 * bağımsız büyüyebilir, o durumda alan serbest metin olarak sorulur.
 */
export function fieldDef(fieldId: string, label?: string): PetitionFieldDef {
  const known = FIELD_CATALOG.find((field) => field.id === fieldId);
  if (known) return label && label !== fieldId ? { ...known, label } : known;
  return { id: fieldId, label: label && label !== fieldId ? label : fieldId, kind: "text" };
}

export function validationPreview(validation: ValidationResult | null): {
  availability: "available" | "unavailable";
  fields: PetitionFieldDef[];
} {
  if (!validation) return { availability: "unavailable", fields: [] };
  const fields = new Map<string, PetitionFieldDef>();
  for (const field of [...validation.missingRequiredFields, ...validation.invalidFields]) {
    if (!fields.has(field.id)) fields.set(field.id, fieldDef(field.id, field.label));
  }
  return { availability: "available", fields: [...fields.values()] };
}

/** `2026-08-27` -> `27.08.2026`; doğrulama servisi her iki biçimi de kabul eder. */
export function trDate(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate.trim());
  return match ? `${match[3]}.${match[2]}.${match[1]}` : isoDate.trim();
}

export function todayIso(now: Date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Intake servisinin saydığı biçimde karakter sayısı. */
export function normalizedLength(text: string): number {
  return text.replace(/\s+/g, " ").trim().length;
}

/**
 * T.C. Kimlik No sağlaması.
 *
 * Doğrulama servisinin `valid_tckn` kuralının aynısı.  Amaç servisin yerine
 * geçmek değil: vatandaşa hatasını istek gönderilmeden önce söylemek.
 */
export function validTckn(value: string): boolean {
  const digits = value.trim();
  if (!/^\d{11}$/.test(digits) || digits.startsWith("0")) return false;
  const numbers = [...digits].map(Number);
  const odd = numbers[0] + numbers[2] + numbers[4] + numbers[6] + numbers[8];
  const even = numbers[1] + numbers[3] + numbers[5] + numbers[7];
  if ((odd * 7 - even) % 10 !== numbers[9]) return false;
  return numbers.slice(0, 10).reduce((total, digit) => total + digit, 0) % 10 === numbers[10];
}

export function validTrPhone(value: string): boolean {
  const compact = value.replace(/[ ()-]/g, "");
  const digits = compact.startsWith("+90") ? compact.slice(3) : compact.startsWith("0") ? compact.slice(1) : compact;
  return /^5\d{9}$/.test(digits);
}

/**
 * Gönderim öncesi dilekçe metnine bakan yerel denetim.
 *
 * Yalnız servisin kesin olarak reddedeceği ya da sınıflandırmayı anlamsız
 * kılacak durumları söyler.  Metnin içeriğine karışmaz: hangi kelimeyi
 * yazdığına göre vatandaşı yönlendirmek, sınıflandırmayı portalın yapması
 * demek olurdu.
 */
export function petitionTextIssues(text: string): string[] {
  const issues: string[] = [];
  const length = normalizedLength(text);
  if (length === 0) {
    issues.push("Dilekçe metni boş olamaz.");
    return issues;
  }
  if (length < MIN_TEXT_LENGTH) {
    issues.push(`Dilekçeniz en az ${MIN_TEXT_LENGTH} karakter olmalı; şu an ${length} karakter.`);
  }
  if (length > MAX_TEXT_LENGTH) {
    issues.push(`Dilekçeniz en fazla ${MAX_TEXT_LENGTH.toLocaleString("tr-TR")} karakter olabilir.`);
  }
  if (!/[^\W\d_]{3,}/u.test(text)) {
    issues.push("Dilekçe metni cümlelerden oluşmalıdır.");
  }
  return issues;
}

/**
 * Eksik alan formundaki tek bir yanıtın gönderilmeye hazır olup olmadığı.
 *
 * Doğrulama servisi boş değeri 400 ile reddeder, kimlik ve telefon
 * biçimlerini de kendisi denetler; bunları burada da denetlemek vatandaşa
 * cevabı anında verir.
 */
export function supplementIssue(field: PetitionFieldDef, value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return `${field.label} alanını doldurun.`;
  if (field.kind === "tckn" && !validTckn(trimmed)) {
    return "T.C. Kimlik Numarası 11 haneli olmalı ve doğrulama sağlamasından geçmelidir.";
  }
  if (field.kind === "phone" && !validTrPhone(trimmed)) {
    return "Cep telefonu 05XX XXX XX XX biçiminde olmalıdır.";
  }
  if (field.kind === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return `${field.label} geçerli bir tarih olmalıdır.`;
  }
  return null;
}

/** Doğrulama servisine gönderilecek biçim: telefon bitişik, tarih gg.aa.yyyy. */
export function supplementValue(field: PetitionFieldDef, value: string): string {
  const trimmed = value.trim();
  if (field.kind === "phone") return trimmed.replace(/[ ()-]/g, "");
  if (field.kind === "date") return trDate(trimmed);
  return trimmed.replace(/\s+/g, " ");
}

/**
 * Evrak kaydına yazılacak başlık.
 *
 * Serbest metnin başlığı yoktur; hitap satırı da her dilekçede aynı olduğu için
 * kuyrukta ayırt edici değildir.  Bu yüzden gövdenin ilk cümlesi kullanılır.
 */
export function petitionTitle(text: string): string {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const salutation = /(başkanlığına|makamına|müdürlüğüne|başkanlığı'na)\s*,?\s*$/i;
  const body = lines.find((line) => line.length > 24 && !salutation.test(line));
  const source = body ?? lines[0] ?? "";
  const sentence = source.split(/(?<=[.!?])\s/)[0] ?? source;
  const title = sentence.length > 90 ? `${sentence.slice(0, 87).trimEnd()}…` : sentence;
  return title || "Vatandaş dilekçesi";
}

/** Vatandaşa gösterilecek kısa başvuru referansı. */
export function petitionReference(caseId: string): string {
  const compact = caseId.replace(/-/g, "").toUpperCase();
  return compact.length >= 8 ? `DB-${compact.slice(0, 4)}-${compact.slice(4, 8)}` : caseId.toUpperCase();
}
