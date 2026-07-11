// frontend-next/e2e/account.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("account screen shows balance and credits", async ({ page }) => {
  await page.goto("/account");
  await expect(page.getByText("Баланс")).toBeVisible();
  await expect(page.getByText("Credits")).toBeVisible();
  await expect(page.getByText(/кредитов/).first()).toBeVisible();
});
