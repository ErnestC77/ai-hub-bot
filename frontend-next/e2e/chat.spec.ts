// frontend-next/e2e/chat.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("ответ модели рендерится как форматированный текст, без сырой разметки", async ({ page }) => {
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      json: {
        answer: "### Заголовок\n\n**Жирный** текст\n\n- пункт один\n- пункт два",
        charged_credits: 3,
        balance_after: 217,
      },
    }),
  );

  await page.goto("/chat");
  await page.getByTestId("chat-input").fill("привет");
  await page.getByTestId("chat-send").click();

  const bubble = page.getByTestId("chat-bubble").last();
  await expect(bubble).toContainText("Заголовок");
  // Сырой разметки не видно...
  await expect(bubble).not.toContainText("###");
  await expect(bubble).not.toContainText("**");
  // ...а элементы реально отрендерены.
  await expect(bubble.locator("strong")).toHaveText("Жирный");
  await expect(bubble.locator("li")).toHaveCount(2);
});

test("chat screen renders input and model picker", async ({ page }) => {
  await page.goto("/chat");
  const input = page.getByTestId("chat-input");
  await expect(input).toBeVisible();
  // Redesign copy: real ellipsis character, not three dots.
  await expect(input).toHaveAttribute("placeholder", "Сообщение…");
  // The «Выбрать модель» button was replaced by an always-visible segmented control.
  await expect(page.getByTestId("chat-model-picker")).toBeVisible();
  await expect(page.getByTestId("chat-send")).toBeVisible();
});
