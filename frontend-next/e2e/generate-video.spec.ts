// frontend-next/e2e/generate-video.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("generates a video end to end", async ({ page }) => {
  // "**/api/models*" (с хвостовой звёздочкой): экран теперь ходит на
  // /api/models?category=video; glob без "*" query-string не матчит,
  // а "?" -- glob-метасимвол, буквально в паттерн не вписывается.
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "veo3_fast",
          display_name: "AI Video Fast",
          tier: "standard",
          min_credits: 51,
          recommended_credits: 51,
        },
      ],
    }),
  );

  await page.route("**/api/generate", (route) =>
    route.fulfill({ json: { request_id: 1, estimated_credits: 51 } }),
  );

  let pollCount = 0;
  await page.route("**/api/generate/1", (route) => {
    pollCount += 1;
    if (pollCount < 2) {
      return route.fulfill({
        json: { status: "processing", result_url: null, error_message: null, charged_credits: 0 },
      });
    }
    return route.fulfill({
      json: {
        status: "completed",
        result_url: "https://cdn.example.com/out.mp4",
        error_message: null,
        charged_credits: 51,
      },
    });
  });

  await page.goto("/generate-video");

  await page.getByPlaceholder("Опишите видео, которое хотите создать").fill("a sunset over mountains");
  await page.getByText("Создать видео").click();

  await expect(page.locator("video")).toHaveAttribute("src", "https://cdn.example.com/out.mp4", { timeout: 15000 });
});
