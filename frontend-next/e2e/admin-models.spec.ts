import { test, expect } from "@playwright/test";

test("admin models tab renders the models section", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Модели")).toHaveCount(1); // only the tab label, section not mounted yet
  await page.getByRole("button", { name: "Модели" }).click();
  await expect(page.getByText("Модели")).toHaveCount(2); // tab label + Section header
});
