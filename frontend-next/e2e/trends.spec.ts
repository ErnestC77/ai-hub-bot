// frontend-next/e2e/trends.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("trends screen lists tool cards and opens chat with a prefilled prompt", async ({ page }) => {
  await page.goto("/trends");
  await expect(page.getByText("✨ Photo & Text Trends")).toBeVisible();
  const firstCard = page.locator("button", { hasText: /.+/ }).first();
  await firstCard.click();
  await expect(page).toHaveURL(/\/chat\?prefill=/);
});
