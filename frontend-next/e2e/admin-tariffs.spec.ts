import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  const adminId = Number(process.env.TEST_ADMIN_TELEGRAM_ID);
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token", adminId);
});

test("admin tariffs tab renders the tariffs section", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Тарифы")).toHaveCount(1); // only the tab label
  await page.getByRole("button", { name: "Тарифы" }).click();
  await expect(page.getByText("Тарифы")).toHaveCount(2); // tab label + Section header
});
