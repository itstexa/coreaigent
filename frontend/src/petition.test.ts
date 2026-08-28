/**
 * Serbest metin dilekçenin portal tarafındaki denetimleri.
 *
 * Portal artık dilekçe kurmuyor: bu testler yalnız gönderim öncesi vatandaşa
 * söylenen şeyleri ve doğrulama servisine gidecek biçimi sabitler.  Örnek
 * dilekçelerin gerçekten doğru sınıflandığı, gerçek sınıflandırıcıyla
 * tests/test_citizen_portal_templates.py içinde denetlenir.
 */

import { describe, expect, it } from "vitest";
import {
  FIELD_CATALOG,
  MAX_TEXT_LENGTH,
  MIN_TEXT_LENGTH,
  SAMPLES,
  fieldDef,
  normalizedLength,
  petitionReference,
  petitionTextIssues,
  petitionTitle,
  sampleById,
  supplementIssue,
  supplementValue,
  trDate,
  validationPreview,
  validTckn,
  validTrPhone,
} from "./petition";
import { parseRoute, thanksPath } from "./router";

const PETITION = SAMPLES[0].sampleText;

describe("dilekçe metni denetimi", () => {
  it("örnek dilekçeler portalın alt sınırını kendiliğinden geçer", () => {
    for (const sample of SAMPLES) {
      expect(petitionTextIssues(sample.sampleText), sample.requestTypeId).toEqual([]);
    }
  });

  it("boş metni tek bir cümleyle reddeder", () => {
    expect(petitionTextIssues("   \n  ")).toEqual(["Dilekçe metni boş olamaz."]);
  });

  it("kısa metinde kaç karakter yazıldığını söyler", () => {
    const issues = petitionTextIssues("Gürültüden şikâyetçiyim.");
    expect(issues).toHaveLength(1);
    expect(issues[0]).toContain(String(MIN_TEXT_LENGTH));
    expect(issues[0]).toContain(String(normalizedLength("Gürültüden şikâyetçiyim.")));
  });

  it("harf içermeyen dolguyu cümle saymaz", () => {
    const issues = petitionTextIssues("1234567890 ".repeat(20));
    expect(issues).toContain("Dilekçe metni cümlelerden oluşmalıdır.");
  });

  it("üst sınırı aşan metni reddeder", () => {
    const issues = petitionTextIssues(`${PETITION} ${"a".repeat(MAX_TEXT_LENGTH)}`);
    expect(issues).toHaveLength(1);
    expect(issues[0]).toContain("en fazla");
  });

  it("karakter sayısı intake servisinin saydığı gibi boşlukları teker sayar", () => {
    expect(normalizedLength("  iki   kelime \n\n ")).toBe(10);
  });

  it("metnin içeriğine karışmaz: konu seçimi yoktur", () => {
    // Sınıflandırmaya benzer hiçbir uyarı üretilmemeli; bu portalın kararı değil.
    const unrelated = "Belediyeye bir konu hakkında yazıyorum. ".repeat(6);
    expect(petitionTextIssues(unrelated)).toEqual([]);
  });
});

describe("evrak başlığı", () => {
  it("hitap satırını atlayıp gövdenin ilk cümlesini alır", () => {
    const title = petitionTitle(PETITION);
    expect(title.toLocaleLowerCase("tr")).not.toContain("başkanlığına");
    expect(title.length).toBeGreaterThan(24);
  });

  it("her örnek dilekçe kuyrukta ayırt edilebilir bir başlık üretir", () => {
    const titles = SAMPLES.map((sample) => petitionTitle(sample.sampleText));
    expect(new Set(titles).size).toBe(SAMPLES.length);
    for (const title of titles) expect(title.length).toBeLessThanOrEqual(90);
  });

  it("uzun tek cümleyi kısaltarak bitirir", () => {
    const title = petitionTitle(`${"Uzun bir cümle parçası ".repeat(10)}.`);
    expect(title.length).toBeLessThanOrEqual(90);
    expect(title.length).toBeGreaterThan(80);
    expect(title.endsWith("…")).toBe(true);
  });

  it("başlıksız metinde de bir başlık döndürür", () => {
    expect(petitionTitle("")).toBe("Vatandaş dilekçesi");
  });
});

describe("alan kataloğu", () => {
  it("doğrulama servisinin bildirdiği alanı sorulabilir hâle getirir", () => {
    expect(fieldDef("tckn").kind).toBe("tckn");
    expect(fieldDef("incident-date").kind).toBe("date");
    expect(fieldDef("incident-description").kind).toBe("textarea");
  });

  it("servisin gönderdiği etiketi katalog etiketinin önüne geçirir", () => {
    expect(fieldDef("tckn", "T.C. Kimlik Numarası").label).toBe("T.C. Kimlik Numarası");
    expect(fieldDef("tckn", "tckn").label).toBe(fieldDef("tckn").label);
  });

  it("katalogda olmayan alanı serbest metin olarak sorar", () => {
    expect(fieldDef("gelecekte-eklenen-alan")).toEqual({
      id: "gelecekte-eklenen-alan",
      label: "gelecekte-eklenen-alan",
      kind: "text",
    });
  });

  it("her alan kimliği tek bir tanım taşır", () => {
    const ids = FIELD_CATALOG.map((field) => field.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("örnek dilekçeler kimliğiyle bulunur", () => {
    expect(sampleById(SAMPLES[0].requestTypeId)).toBe(SAMPLES[0]);
    expect(sampleById("olmayan-talep")).toBeUndefined();
  });
});

describe("eksik bilgi yanıtları", () => {
  const tckn = fieldDef("tckn");
  const phone = fieldDef("phone");
  const date = fieldDef("incident-date");
  const address = fieldDef("incident-address");

  it("boş yanıtı alan adıyla birlikte reddeder", () => {
    expect(supplementIssue(address, "  ")).toContain(address.label);
  });

  it("sağlaması geçmeyen kimlik numarasını reddeder", () => {
    expect(validTckn("12345678901")).toBe(false);
    expect(validTckn("14392847570")).toBe(true);
    expect(supplementIssue(tckn, "12345678901")).not.toBeNull();
    expect(supplementIssue(tckn, "14392847570")).toBeNull();
  });

  it("telefonu yalnızca cep biçiminde kabul eder", () => {
    expect(validTrPhone("0532 111 22 33")).toBe(true);
    expect(validTrPhone("+90 532 111 22 33")).toBe(true);
    expect(validTrPhone("0212 111 22 33")).toBe(false);
    expect(supplementIssue(phone, "0212 111 22 33")).not.toBeNull();
  });

  it("tarihi ISO biçiminde bekler, çünkü tarih girişi öyle döner", () => {
    expect(supplementIssue(date, "20.08.2026")).not.toBeNull();
    expect(supplementIssue(date, "2026-08-20")).toBeNull();
  });

  it("servise giden değeri kuralın okuduğu biçime çevirir", () => {
    expect(supplementValue(phone, "0532 111 22 33")).toBe("05321112233");
    expect(supplementValue(date, "2026-08-20")).toBe("20.08.2026");
    expect(supplementValue(address, " Örnek Mahallesi   12. Sokak ")).toBe("Örnek Mahallesi 12. Sokak");
  });
});

describe("BX-06 eksik bilgi ön izlemesi", () => {
  it("geçersiz ek dahil doğrulama sonucundaki her alan etiketini korur", () => {
    const preview = validationPreview({
      schemaVersion: "3.0",
      requestId: "req-1",
      documentId: "doc-1",
      caseId: "case-1",
      workflowId: "workflow-1",
      requestTypeId: "fatura-islemi",
      schemaVersionUsed: "demo-belediyesi-fields-v1",
      extractedFields: [],
      missingRequiredFields: [{ id: "supplier-name", label: "Tedarikçi adı" }],
      invalidFields: [{ id: "invoice-attachment", label: "Fatura eki", code: "attachment_missing" }],
      completionStatus: "invalid_information",
      userActionRequired: true,
    });

    expect(preview.availability).toBe("available");
    expect(preview.fields.map((field) => field.label)).toEqual(["Tedarikçi adı", "Fatura eki"]);
    expect(preview.fields.find((field) => field.id === "invoice-attachment")?.kind).toBe("attachment");
  });

  it("doğrulama yokken alan uydurmaz", () => {
    expect(validationPreview(null)).toEqual({ availability: "unavailable", fields: [] });
  });
});

describe("referans ve yönlendirme", () => {
  it("başvuru referansı case kimliğinden okunabilir biçimde üretilir", () => {
    expect(petitionReference("3f9f9f6e-1111-2222-3333-444455556666")).toBe("DB-3F9F-9F6E");
  });

  it("teşekkür adresi referansı geri verir", () => {
    expect(parseRoute(thanksPath("DB-3F9F-9F6E"))).toEqual({ kind: "thanks", reference: "DB-3F9F-9F6E" });
  });

  it("panel adresleri görünüme çevrilir", () => {
    expect(parseRoute("/")).toEqual({ kind: "landing" });
    expect(parseRoute("/dilekce")).toEqual({ kind: "petition" });
    expect(parseRoute("/panel")).toEqual({ kind: "panel-overview" });
    expect(parseRoute("/panel/yeni")).toEqual({ kind: "panel-intake" });
    expect(parseRoute("/panel/dosya/abc-123")).toEqual({ kind: "panel-case", caseId: "abc-123" });
  });

  it("tanınmayan adres tanıtım sayfasına düşer", () => {
    expect(parseRoute("/bilinmeyen/yol")).toEqual({ kind: "landing" });
  });

  it("tarih gösterimi gün.ay.yıl biçimindedir", () => {
    expect(trDate("2026-08-27")).toBe("27.08.2026");
    expect(trDate("belirsiz")).toBe("belirsiz");
  });
});
