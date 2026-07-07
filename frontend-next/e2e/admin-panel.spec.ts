// frontend-next/e2e/admin-panel.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("admin panel blocks non-admin users", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Доступ запрещён")).toBeVisible();
});
