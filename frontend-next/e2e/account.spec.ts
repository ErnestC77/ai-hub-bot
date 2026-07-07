// frontend-next/e2e/account.spec.ts
import { test, expect } from "@playwright/test";

test("account screen shows plan and credits", async ({ page }) => {
  await page.goto("/account");
  await expect(page.getByText("Current plan")).toBeVisible();
  await expect(page.getByText("Credits")).toBeVisible();
  await expect(page.getByText(/кредитов/)).toBeVisible();
});
