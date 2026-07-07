import { test, expect } from "@playwright/test";

test("admin users tab shows the search section", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Пользователи" }).click();
  await expect(page.getByText("Поиск по Telegram ID или username")).toBeVisible();
});
