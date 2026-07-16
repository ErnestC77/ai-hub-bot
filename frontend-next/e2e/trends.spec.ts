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
  // Каждая карточка несёт превью-видео (preview_url из /api/tools).
  await expect(page.getByTestId("trend-video").first()).toBeAttached();
  // Текст-тренд ведёт в чат (recommended_category ни image, ни video).
  await page.getByTestId("trends-text").getByTestId("trend-card").first().click();
  await expect(page).toHaveURL(/\/chat\?prefill=/);
});

test("photo trend routes to the image generator with a prefilled prompt", async ({ page }) => {
  await page.goto("/trends");
  await expect(page.getByTestId("trends-photo")).toBeVisible();
  await page.getByTestId("trends-photo").getByTestId("trend-card").first().click();
  await expect(page).toHaveURL(/\/generate-image\?prefill=/);
  // Префикс должен реально долететь до поля промпта, а не только в URL.
  await expect(page.getByTestId("generate-prompt")).toHaveValue(/.+/);
});

test("video trend routes to the video generator with a prefilled prompt", async ({ page }) => {
  await page.goto("/trends");
  await expect(page.getByTestId("trends-video")).toBeVisible();
  await page.getByTestId("trends-video").getByTestId("trend-card").first().click();
  await expect(page).toHaveURL(/\/generate-video\?prefill=/);
  await expect(page.getByTestId("generate-prompt")).toHaveValue(/.+/);
});
