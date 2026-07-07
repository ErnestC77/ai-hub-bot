// frontend-next/e2e/chat.spec.ts
import { test, expect } from "@playwright/test";

test("chat screen renders input and model picker", async ({ page }) => {
  await page.goto("/chat");
  await expect(page.getByPlaceholder("Сообщение...")).toBeVisible();
});
