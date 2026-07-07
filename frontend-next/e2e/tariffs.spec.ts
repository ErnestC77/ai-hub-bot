// frontend-next/e2e/tariffs.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("tariffs screen lists plans under the Тарифы section", async ({ page }) => {
  await page.goto("/tariffs");
  await expect(page.getByText("Тарифы")).toBeVisible();
});
