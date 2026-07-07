// frontend-next/e2e/tariffs.spec.ts
import { test, expect } from "@playwright/test";

test("tariffs screen lists plans under the Тарифы section", async ({ page }) => {
  await page.goto("/tariffs");
  await expect(page.getByText("Тарифы")).toBeVisible();
});
