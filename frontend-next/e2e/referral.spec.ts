// frontend-next/e2e/referral.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("referral screen shows invite stats and actions", async ({ page }) => {
  await page.goto("/referral");
  // Redesign: header «Реферальная программа» → H1 «Приглашай друзей»;
  // «Скопировать» is now an icon-only row (testid referral-copy);
  // «Поделиться» → «Поделиться ссылкой».
  await expect(page.getByText("Приглашай друзей")).toBeVisible();
  await expect(page.getByTestId("referral-invited")).toBeVisible();
  await expect(page.getByTestId("referral-earned")).toBeVisible();
  await expect(page.getByTestId("referral-link")).toBeVisible();
  await expect(page.getByTestId("referral-copy")).toBeVisible();
  await expect(page.getByTestId("referral-share")).toBeVisible();
});
