// frontend-next/e2e/generate-image.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("generate-image screen has a dark textarea and resolution buttons", async ({ page }) => {
  await page.goto("/generate-image");
  const textarea = page.getByPlaceholder("Опишите, что хотите создать");
  await expect(textarea).toBeVisible();
  const bg = await textarea.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg).not.toBe("rgb(255, 255, 255)");

  await expect(page.getByRole("button", { name: "1K" })).toBeVisible();
  await expect(page.getByRole("button", { name: "2K" })).toBeVisible();
  await expect(page.getByRole("button", { name: "4K" })).toBeVisible();
});
