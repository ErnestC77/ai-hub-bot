import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  const adminId = Number(process.env.TEST_ADMIN_TELEGRAM_ID);
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token", adminId);
});

test("admin payments tab shows recent payments", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Платежи" }).click();
  await expect(page.getByText("Последние платежи")).toBeVisible();
});
