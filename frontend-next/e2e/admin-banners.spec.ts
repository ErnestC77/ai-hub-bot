import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  const adminId = Number(process.env.TEST_ADMIN_TELEGRAM_ID);
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token", adminId);
});

test("admin banners tab shows the carousel list and the new-banner form", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Карусель" }).click();
  await expect(page.getByText("Карусель на главной")).toBeVisible();
  await expect(page.getByText("Новый баннер")).toBeVisible();
  await expect(page.getByRole("button", { name: "Добавить баннер" })).toBeVisible();
});
