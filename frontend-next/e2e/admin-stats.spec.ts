import { test, expect } from "@playwright/test";

test("admin stats tab shows today's numbers", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Статистика" }).click();
  await expect(page.getByText("Сегодня")).toBeVisible();
});
