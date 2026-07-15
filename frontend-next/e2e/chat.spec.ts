// frontend-next/e2e/chat.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
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
