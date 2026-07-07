import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  const adminId = Number(process.env.TEST_ADMIN_TELEGRAM_ID);
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token", adminId);
});

test("admin users tab shows the search section", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Пользователи" }).click();
  await expect(page.getByText("Поиск по Telegram ID или username")).toBeVisible();
});
