// frontend-next/e2e/generate-video.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("generates a video end to end", async ({ page }) => {
  await page.route("**/api/models", (route) =>
    route.fulfill({
      json: [
        { model_code: "piapi-veo3-fast", display_name: "AI Video Fast", category: "video", is_premium: false, credit_cost: 51 },
      ],
    }),
  );

  await page.route("**/api/generate", (route) =>
    route.fulfill({ json: { request_id: 1 } }),
  );

  let pollCount = 0;
  await page.route("**/api/generate/1", (route) => {
    pollCount += 1;
    if (pollCount < 2) {
      return route.fulfill({ json: { status: "processing", result_url: null, error_message: null, credit_cost: 51 } });
    }
    return route.fulfill({
      json: { status: "success", result_url: "https://cdn.example.com/out.mp4", error_message: null, credit_cost: 51 },
    });
  });

  await page.goto("/generate-video");

  await page.getByPlaceholder("Опишите видео, которое хотите создать").fill("a sunset over mountains");
  await page.getByText("Создать видео").click();

  await expect(page.locator("video")).toHaveAttribute("src", "https://cdn.example.com/out.mp4", { timeout: 15000 });
});
