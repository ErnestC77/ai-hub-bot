// frontend-next/e2e/account.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("account screen shows balance and credits", async ({ page }) => {
  await page.goto("/account");
  // Redesign: the english «Credits» section label was removed; the balance card
  // now shows «Баланс» + «💎 N кредитов».
  await expect(page.getByText("Баланс", { exact: true })).toBeVisible();
  await expect(page.getByTestId("account-balance")).toContainText("кредитов");
  await expect(page.getByTestId("account-purchased")).toBeVisible();
  await expect(page.getByTestId("account-spent")).toBeVisible();
  await expect(page.getByTestId("account-buy-credits")).toBeVisible();
});
