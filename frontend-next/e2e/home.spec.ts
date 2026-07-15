// frontend-next/e2e/home.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

// Aurora Glass redesign: the «Generate Image» hero heading and the FAB are gone.
// Home is now header + credits pill, banner carousel, «Нейросети» model carousel
// and 3 action cards; the image action card leads to /generate-image.
test("home screen renders credits, action cards and navigates to generate-image", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("home-credits")).toBeVisible();
  await expect(page.getByTestId("action-chat")).toBeVisible();
  await expect(page.getByTestId("action-image")).toBeVisible();
  await expect(page.getByTestId("action-video")).toBeVisible();
  await page.getByTestId("action-image").click();
  await expect(page).toHaveURL(/\/generate-image$/);
});
