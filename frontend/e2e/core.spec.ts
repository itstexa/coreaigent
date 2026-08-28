import { expect, test } from "@playwright/test";

test.describe("CoreAIgent mock uçtan uca yüzeyleri", () => {
  test("landing sayfasından vatandaş portalına geçer", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Yapay Zekâ ile Kamu Evrakında/i })).toBeVisible();

    await page.getByRole("button", { name: /Dilekçe Gönder/i }).click();
    await expect(page).toHaveURL(/\/dilekce$/);
    await expect(page.getByRole("heading", { name: /Dilekçenizi kendi cümlelerinizle yazın/i })).toBeVisible();
  });

  test("kısa dilekçeyi backend'e göndermeden reddeder", async ({ page }) => {
    await page.goto("/dilekce");
    await page.locator("#dilekce-metni").fill("Kısa metin.");

    const ocrRequests: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/ocr/")) ocrRequests.push(request.url());
    });
    await page.getByRole("button", { name: "Dilekçemi gönder" }).click();

    await expect(page.getByText(/en az 120 karakter olmalı/i)).toBeVisible();
    expect(ocrRequests).toHaveLength(0);
  });

  test("mock stack serbest metin sınırını kullanıcıya açık hata olarak gösterir", async ({ page }) => {
    await page.goto("/dilekce");
    await page.locator("#dilekce-metni").fill(
      "Demo Belediye Başkanlığına, mahallemizde yaşanan sorunun incelenmesini ve gerekli işlemin yapılmasını arz ederim. Başvuru sahibi Ayşe Yılmaz.",
    );
    await page.getByRole("button", { name: "Dilekçemi gönder" }).click();

    await expect(page.getByText(/Mock sözleşme modu yalnızca golden senaryo evraklarını işler/i)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("button", { name: "Dilekçemi gönder" })).toBeEnabled();
  });

  test("admin paneli mock case kuyruğunu ve aramayı gösterir", async ({ page }) => {
    await page.goto("/panel");
    await expect(page.getByRole("heading", { name: /Gelen dilekçeleri tek kuyrukta yönetin/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Dosya kuyruğu" })).toBeVisible();

    await expect(page.locator(".case-table tbody tr").first()).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".case-table tbody tr").first()).toContainText("doc-s01-izin-talebi");

    await page.getByPlaceholder("Evrak no, başvuran, konu…").fill("Personel yıllık izin talebi");
    await expect(page.locator(".case-table tbody tr")).toHaveCount(1);
    await expect(page.locator(".case-table tbody tr").first()).toContainText("Dilekçe");

    await page.locator(".case-table tbody tr").first().click();
    await expect(page).toHaveURL(/\/panel\/dosya\/case-s01-izin-talebi$/);
    await expect(page.getByRole("heading", { name: "Personel yıllık izin talebi" })).toBeVisible({ timeout: 15_000 });
  });
});
