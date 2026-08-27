/**
 * Teşekkür sayfasının gösterdiği başvuru bilgisi.
 *
 * Vatandaş tarafında kalıcı bir kayıt tutulmaz: bilgi yalnızca sekme ömrü
 * boyunca `sessionStorage` içinde durur.  Sayfa yenilendiğinde referans
 * kaybolmasın diye saklanır, ancak paylaşılan bir bilgisayarda sekme
 * kapandığında başvuru içeriği geride bırakılmaz.
 */

const PREFIX = "coreaigent.petition.";

export interface PetitionReceipt {
  reference: string;
  caseId: string;
  documentId: string;
  subjectLabel: string;
  unitHint: string;
  submittedAt: string;
  state?: string;
  /**
   * Yapay zekânın verdiği kararın vatandaşa kalan özeti.
   *
   * Teşekkür sayfası dosyayı yeniden sorgulamaz -- ADMIN yetkisi gerektirir --
   * bu yüzden gösterdiği güven puanı, gerekçe ve doğrulama sonucu gönderim
   * anında görülenin aynısıdır.
   */
  confidence?: number;
  reason?: string;
  completionStatus?: "complete" | "missing_information" | "invalid_information";
  fieldCount?: number;
  language?: string;
}

export function saveReceipt(receipt: PetitionReceipt): void {
  try {
    window.sessionStorage.setItem(PREFIX + receipt.reference, JSON.stringify(receipt));
  } catch {
    // Depolama kapalıysa akış durmaz; teşekkür sayfası referansı adresten okur.
  }
}

export function loadReceipt(reference: string): PetitionReceipt | null {
  try {
    const raw = window.sessionStorage.getItem(PREFIX + reference);
    if (!raw) return null;
    const value = JSON.parse(raw) as PetitionReceipt;
    return value && typeof value.caseId === "string" ? value : null;
  } catch {
    return null;
  }
}
