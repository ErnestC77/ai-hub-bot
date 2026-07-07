// frontend-next/e2e/settings.spec.ts
import { test, expect } from "@playwright/test";

test("settings screen renders", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByText("AI Hub")).toBeVisible();
});
