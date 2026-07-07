import { test, expect } from "@playwright/test";

test("admin payments tab shows recent payments", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Платежи" }).click();
  await expect(page.getByText("Последние платежи")).toBeVisible();
});
