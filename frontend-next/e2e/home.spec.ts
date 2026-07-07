// frontend-next/e2e/home.spec.ts
import { test, expect } from "@playwright/test";

test("home screen renders hero and generate CTA", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Generate Image")).toBeVisible();
  await page.getByRole("button", { name: /Generate/ }).first().click();
  await expect(page).toHaveURL(/\/generate-image$/);
});
