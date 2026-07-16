// frontend-next/e2e/generate-image.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("generate-image screen has a dark textarea and a generate button", async ({ page }) => {
  await page.goto("/generate-image");
  const textarea = page.getByTestId("generate-prompt");
  await expect(textarea).toBeVisible();
  await expect(textarea).toHaveAttribute("placeholder", "Опишите, что хотите создать");
  const bg = await textarea.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg).not.toBe("rgb(255, 255, 255)");

  // Кнопки 1K/2K/4K и aspect-чипы удалены вместе с мёртвой dall-e-3-веткой
  // (фаза 3 generate). Кнопка генерации внизу («✨ Создать · N 💎» после
  // редизайна; задизейблена без модели/промпта, но видима).
  await expect(page.getByTestId("generate-submit")).toBeVisible();
  await expect(page.getByTestId("generate-submit")).toContainText("Создать");
});
