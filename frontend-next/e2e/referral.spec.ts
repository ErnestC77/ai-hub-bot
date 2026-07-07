// frontend-next/e2e/referral.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("referral screen shows invite stats and actions", async ({ page }) => {
  await page.goto("/referral");
  await expect(page.getByText("Реферальная программа")).toBeVisible();
  await expect(page.getByRole("button", { name: "Поделиться" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Скопировать" })).toBeVisible();
});
