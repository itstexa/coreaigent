/**
 * Panel kuyruğunun ve dosya görünümünün sınanması.
 *
 * Buradaki asıl iddia birleştirme sırasıdır: dosya detayı sunucudan geleni
 * tarayıcı belleğine tercih etmezse, vatandaşın kendi telefonundan gönderdiği
 * dilekçe operatörün ekranında boş görünür -- panelin en pahalı hatası buydu.
 */

import { describe, expect, it } from "vitest";
import {
  PAGE_SIZE,
  QUEUE_FILTERS,
  caseView,
  channelLabel,
  confidenceTone,
  initials,
  languageLabel,
  relativeAge,
} from "./queue";
import type { CaseDocument, CaseListItem, CaseRecord } from "./types";

const NOW = Date.parse("2026-08-27T12:00:00Z");

function minutesAgo(minutes: number): string {
  return new Date(NOW - minutes * 60_000).toISOString();
}

function row(overrides: Partial<CaseListItem> = {}): CaseListItem {
  return {
    case_id: "case-1",
    case_revision: 3,
    state: "draft_prepared",
    completed_steps: ["F-01", "F-02", "F-03"],
    last_error_code: null,
    priority: { level: "normal", score: 40, reason: "Öncelik sinyali bulunmadı" },
    updated_at: minutesAgo(4),
    validation_status: "complete",
    routing_status: "routed",
    document_id: "DOC-2026-0001",
    request_type_id: "cop-toplama",
    request_type_label: "Çöp toplama talebi",
    department_id: "temizlik",
    department_label: "Temizlik İşleri Müdürlüğü",
    unit_id: "cop-birimi",
    unit_label: "Çöp Toplama Birimi",
    classification_status: "classified",
    classification_confidence: 0.94,
    classification_reason: "3 sinyal eşleşti: çöp, konteyner, toplanmadı",
    applicant_name: "Ayşe Yılmaz",
    title: "Konteyner boşaltılmıyor",
    channel: "citizen-portal",
    language: "tr",
    created_at: minutesAgo(9),
    ...overrides,
  };
}

function record(overrides: Partial<CaseRecord> = {}): CaseRecord {
  return {
    caseId: "case-1",
    documentId: "LOCAL-DOC",
    workflowId: "wf-1",
    title: "Yerel başlık",
    createdAt: minutesAgo(30),
    sourceType: "text",
    sourceText: "Yerel kayıttaki metin",
    implementation: "real",
    ...overrides,
  };
}

function document(overrides: Partial<CaseDocument> = {}): CaseDocument {
  return {
    case_id: "case-1",
    document_id: "DOC-2026-0001",
    source_type: "text",
    language: "tr",
    title: "Konteyner boşaltılmıyor",
    channel: "citizen-portal",
    created_at: minutesAgo(9),
    text: "Demo Belediye Başkanlığına, sokağımızdaki konteyner iki haftadır boşaltılmıyor.",
    ...overrides,
  };
}

describe("kuyruk sekmeleri", () => {
  it("ilk sekme filtresiz toplamı ister", () => {
    expect(QUEUE_FILTERS[0].value).toBe("");
  });

  it("her sekme tek bir durumu temsil eder", () => {
    const values = QUEUE_FILTERS.map((item) => item.value);
    expect(new Set(values).size).toBe(values.length);
  });

  it("her sekmenin vatandaş diliyle bir etiketi vardır", () => {
    for (const item of QUEUE_FILTERS) {
      expect(item.label.trim()).not.toBe("");
      expect(item.short.trim()).not.toBe("");
      expect(item.short.length).toBeLessThanOrEqual(14);
    }
  });

  it("sayfalama adımı sorgu limitiyle aynıdır", () => {
    // Farklı olsalar ikinci sayfa satır atlar ya da satırı iki kez gösterirdi.
    expect(PAGE_SIZE).toBe(25);
  });
});

describe("bekleme süresi", () => {
  it("bir dakikadan yenisini süre olarak yazmaz", () => {
    expect(relativeAge(minutesAgo(0), NOW)).toBe("az önce");
  });

  it("saat sınırına kadar dakika gösterir", () => {
    expect(relativeAge(minutesAgo(18), NOW)).toBe("18 dk");
    expect(relativeAge(minutesAgo(59), NOW)).toBe("59 dk");
  });

  it("saat ve gün eşiklerini geçer", () => {
    expect(relativeAge(minutesAgo(150), NOW)).toBe("3 sa");
    expect(relativeAge(minutesAgo(60 * 40), NOW)).toBe("2 gün");
  });

  it("gelecekteki bir zamanı negatif göstermez", () => {
    expect(relativeAge(new Date(NOW + 600_000).toISOString(), NOW)).toBe("az önce");
  });

  it("eksik ya da bozuk tarihte tire döner", () => {
    expect(relativeAge(null, NOW)).toBe("—");
    expect(relativeAge("belirsiz", NOW)).toBe("—");
  });
});

describe("güven eşiği", () => {
  it("F-02'nin 0,80 eşiğini paylaşır", () => {
    // `status_for_score` yalnız 0.80'in üstünü `classified` sayar; tabloda da
    // tam 0.80 uyarı rengiyle durmalı.
    expect(confidenceTone(0.81)).toBe("high");
    expect(confidenceTone(0.8)).toBe("mid");
  });

  it("yarının altını düşük sayar", () => {
    expect(confidenceTone(0.5)).toBe("mid");
    expect(confidenceTone(0.49)).toBe("low");
  });

  it("puan yoksa renk üretmez", () => {
    expect(confidenceTone(null)).toBe("none");
    expect(confidenceTone(undefined)).toBe("none");
  });
});

describe("satır etiketleri", () => {
  it("başvuran adının baş harflerini Türkçe büyütür", () => {
    expect(initials("Ayşe Yılmaz")).toBe("AY");
    expect(initials("ilker deniz kaya")).toBe("İD");
  });

  it("ad yoksa soru işareti gösterir", () => {
    expect(initials(null)).toBe("?");
    expect(initials("   ")).toBe("?");
  });

  it("kanalı ve dili Türkçeye çevirir, bilinmeyeni olduğu gibi bırakır", () => {
    expect(channelLabel("citizen-portal")).toBe("Dilekçe ekranı");
    expect(channelLabel("sms-gateway")).toBe("sms-gateway");
    expect(channelLabel(null)).toBeNull();
    expect(languageLabel("tr")).toBe("Türkçe");
    expect(languageLabel(null)).toBe("Belirlenemedi");
  });
});

describe("dosya görünümü", () => {
  it("sunucu satırı yerel kaydın etiketlerini geçersiz kılar", () => {
    const view = caseView(
      record({ classification: { requestType: { id: "x", label: "Eski etiket" }, confidence: 0.2 } as CaseRecord["classification"] }),
      row(),
      null,
    );
    expect(view.requestTypeLabel).toBe("Çöp toplama talebi");
    expect(view.unitLabel).toBe("Çöp Toplama Birimi");
    expect(view.confidence).toBe(0.94);
    expect(view.applicantName).toBe("Ayşe Yılmaz");
  });

  it("özgün dilekçe metni kurum kaydından okunur", () => {
    const view = caseView(record(), row(), document());
    expect(view.text).toContain("konteyner iki haftadır boşaltılmıyor");
    expect(view.textOrigin).toBe("server");
  });

  it("yalnızca yerel kayıt varken metnin kaynağını gizlemez", () => {
    const view = caseView(record(), null, null);
    expect(view.text).toBe("Yerel kayıttaki metin");
    expect(view.textOrigin).toBe("local");
  });

  it("başka bir cihazdan gönderilen dosyada yerel kayıt olmadan da doluyor", () => {
    const view = caseView(undefined, row(), document());
    expect(view.title).toBe("Konteyner boşaltılmıyor");
    expect(view.documentId).toBe("DOC-2026-0001");
    expect(view.language).toBe("tr");
    expect(view.channel).toBe("citizen-portal");
    expect(view.text).not.toBeNull();
  });

  it("sunucu puanı boşsa yerel sınıflandırmaya düşer", () => {
    const view = caseView(
      record({ classification: { confidence: 0.62, classificationReason: "yerel gerekçe" } as CaseRecord["classification"] }),
      row({ classification_confidence: null, classification_reason: null }),
      null,
    );
    expect(view.confidence).toBe(0.62);
    expect(view.reason).toBe("yerel gerekçe");
  });

  it("hiçbir kaynak yokken uydurmaz", () => {
    const view = caseView(undefined, null, null);
    expect(view.title).toBe("Case detayı");
    expect(view.text).toBeNull();
    expect(view.textOrigin).toBeNull();
    expect(view.confidence).toBeNull();
    expect(view.requestTypeLabel).toBeNull();
  });

  it("sınıflandırıcı sürümü yalnızca yerel kayıttan gelir", () => {
    // Kuyruk projeksiyonu sürüm yayımlamıyor; olmayan bir sürümü göstermek
    // izlenebilirlik iddiasını uydurmak olurdu.
    expect(caseView(undefined, row(), null).classifierVersion).toBeNull();
  });
});
