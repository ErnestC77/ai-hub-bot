// frontend-next/e2e/chat.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("chat screen renders input and model picker", async ({ page }) => {
  await page.goto("/chat");
  await expect(page.getByPlaceholder("Сообщение...")).toBeVisible();
});
