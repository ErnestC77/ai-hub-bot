// frontend-next/e2e/trends.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("trends screen lists tool cards and opens chat with a prefilled prompt", async ({ page }) => {
  await page.goto("/trends");
  await expect(page.getByTestId("trends-page")).toBeVisible();
  // Redesign copy: «✨ Photo & Text Trends» → «✨ Тренды».
  await expect(page.getByText("✨ Тренды")).toBeVisible();
  // Cards are now explicit trend-card buttons (the old "first button on the page"
  // locator could hit the bottom navigation).
  await page.getByTestId("trend-card").first().click();
  await expect(page).toHaveURL(/\/chat\?prefill=/);
});
