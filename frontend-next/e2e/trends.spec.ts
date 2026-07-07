// frontend-next/e2e/trends.spec.ts
import { test, expect } from "@playwright/test";

test("trends screen lists tool cards and opens chat with a prefilled prompt", async ({ page }) => {
  await page.goto("/trends");
  await expect(page.getByText("✨ Photo & Text Trends")).toBeVisible();
  const firstCard = page.locator("button", { hasText: /.+/ }).first();
  await firstCard.click();
  await expect(page).toHaveURL(/\/chat\?prefill=/);
});
