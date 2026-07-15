// frontend-next/e2e/settings.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("settings screen renders", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByText("AI Hub", { exact: true })).toBeVisible();
});
