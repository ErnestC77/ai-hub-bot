import { test, expect } from "@playwright/test";

test("admin tariffs tab renders the tariffs section", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Тарифы")).toHaveCount(1); // only the tab label
  await page.getByRole("button", { name: "Тарифы" }).click();
  await expect(page.getByText("Тарифы")).toHaveCount(2); // tab label + Section header
});
