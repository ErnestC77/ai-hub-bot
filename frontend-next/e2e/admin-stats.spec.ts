import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  const adminId = Number(process.env.TEST_ADMIN_TELEGRAM_ID);
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token", adminId);
});

test("admin stats tab shows today's numbers", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Статистика" }).click();
  await expect(page.getByText("Сегодня")).toBeVisible();
});
