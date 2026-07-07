// frontend-next/e2e/referral.spec.ts
import { test, expect } from "@playwright/test";

test("referral screen shows invite stats and actions", async ({ page }) => {
  await page.goto("/referral");
  await expect(page.getByText("Реферальная программа")).toBeVisible();
  await expect(page.getByRole("button", { name: "Поделиться" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Скопировать" })).toBeVisible();
});
