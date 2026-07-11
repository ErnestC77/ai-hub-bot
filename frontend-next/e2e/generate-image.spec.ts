// frontend-next/e2e/generate-image.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("generate-image screen has a dark textarea and a generate button", async ({ page }) => {
  await page.goto("/generate-image");
  const textarea = page.getByPlaceholder("Опишите, что хотите создать");
  await expect(textarea).toBeVisible();
  const bg = await textarea.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg).not.toBe("rgb(255, 255, 255)");

  // Кнопки 1K/2K/4K и aspect-чипы удалены вместе с мёртвой dall-e-3-веткой
  // (фаза 3 generate). Проверяем оставшийся реальный UI -- кнопку генерации
  // в нижней панели (задизейблена без модели/промпта, но видима).
  await expect(page.getByRole("button", { name: "Generate" })).toBeVisible();
});
