// frontend-next/e2e/admin-panel.spec.ts
import { test, expect } from "@playwright/test";

test("admin panel blocks non-admin users", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Доступ запрещён")).toBeVisible();
});
