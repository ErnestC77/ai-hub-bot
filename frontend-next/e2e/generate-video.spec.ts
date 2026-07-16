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
  //
  // ModelOut.options теперь обязателен -- без него defaultOptionCodes()
  // упадёт на model.options (undefined), экран уйдёт в бесконечный
  // ре-рендер и React отсоединит узлы от DOM (см. регрессию, поймана
  // прогоном сьюта до этого патча).
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "veo3_fast",
          display_name: "AI Video Fast",
          tier: "standard",
          min_credits: 51,
          recommended_credits: 51,
          options: [
            { kind: "duration", code: "8s", label: "8 сек", credits_multiplier: 1, is_default: true, sort_order: 10 },
          ],
        },
      ],
    }),
  );

  let generateBody: unknown;
  await page.route("**/api/generate", async (route) => {
    generateBody = route.request().postDataJSON();
    await route.fulfill({ json: { request_id: 1, estimated_credits: 51 } });
  });

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

  await page.getByTestId("generate-prompt").fill("a sunset over mountains");
  // Редизайн: кнопка «Создать видео» → «🎬 Создать · N 💎» (testid generate-submit);
  // модель выбирается segmented-контролом автоматически (первая из списка).
  await page.getByTestId("generate-submit").click();

  await expect(page.getByTestId("generate-result").locator("video")).toHaveAttribute(
    "src",
    "https://cdn.example.com/out.mp4",
    { timeout: 15000 },
  );

  // Слайдер длительности удалён вместе с полем duration_seconds -- бэкенд
  // получает код выбранной опции модели, а не сырое число секунд.
  expect(generateBody).toMatchObject({ option_codes: { duration: "8s" } });
  expect(generateBody).not.toHaveProperty("duration_seconds");
});

test("рисует только те секции, которые есть у модели", async ({ page }) => {
  // kling_video (реальные коды опций из БД): у fal нет ручки размера --
  // только duration. Секции quality/audio рисоваться не должны.
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "kling_video",
          display_name: "Kling",
          tier: "standard",
          min_credits: 3220,
          recommended_credits: 3220,
          options: [
            { kind: "duration", code: "5s", label: "5 сек", credits_multiplier: 1, is_default: true, sort_order: 10 },
            { kind: "duration", code: "10s", label: "10 сек", credits_multiplier: 2, is_default: false, sort_order: 20 },
          ],
        },
      ],
    }),
  );

  await page.goto("/generate-video");

  await expect(page.getByTestId("option-duration")).toBeVisible();
  await expect(page.getByTestId("option-quality")).toHaveCount(0);
  await expect(page.getByTestId("option-audio")).toHaveCount(0);
});

test("смена опции меняет цену в CTA", async ({ page }) => {
  // kling_video: recommended_credits=3220, 5s(x1, default) / 10s(x2) --
  // тот же множитель, что в реальной таблице model_options.
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "kling_video",
          display_name: "Kling",
          tier: "standard",
          min_credits: 3220,
          recommended_credits: 3220,
          options: [
            { kind: "duration", code: "5s", label: "5 сек", credits_multiplier: 1, is_default: true, sort_order: 10 },
            { kind: "duration", code: "10s", label: "10 сек", credits_multiplier: 2, is_default: false, sort_order: 20 },
          ],
        },
      ],
    }),
  );

  await page.goto("/generate-video");

  await expect(page.getByTestId("generate-submit")).toContainText("3220");
  await page.getByTestId("option-duration-10s").click();
  await expect(page.getByTestId("generate-submit")).toContainText("6440");
});

test("шлёт коды выбранных опций, а не сырые значения", async ({ page }) => {
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "kling_video",
          display_name: "Kling",
          tier: "standard",
          min_credits: 3220,
          recommended_credits: 3220,
          options: [
            { kind: "duration", code: "5s", label: "5 сек", credits_multiplier: 1, is_default: true, sort_order: 10 },
            { kind: "duration", code: "10s", label: "10 сек", credits_multiplier: 2, is_default: false, sort_order: 20 },
          ],
        },
      ],
    }),
  );

  let body: Record<string, unknown> | undefined;
  await page.route("**/api/generate", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({ json: { request_id: 1, estimated_credits: 6440 } });
  });
  await page.route("**/api/generate/1", (route) =>
    route.fulfill({
      json: {
        status: "completed",
        result_url: "https://cdn.example.com/out.mp4",
        error_message: null,
        charged_credits: 6440,
      },
    }),
  );

  await page.goto("/generate-video");
  await page.getByTestId("generate-prompt").fill("a dragon over mountains");
  await page.getByTestId("option-duration-10s").click();
  await page.getByTestId("generate-submit").click();

  // Ждём фактического завершения запроса, а не произвольную паузу --
  // появление результата гарантирует, что postDataJSON() уже записан.
  await expect(page.getByTestId("generate-result").locator("video")).toHaveAttribute(
    "src",
    "https://cdn.example.com/out.mp4",
    { timeout: 15000 },
  );

  expect(body?.option_codes).toEqual({ duration: "10s" });
  expect(body).not.toHaveProperty("duration_seconds");
});

test("модель без опций -- ни одной секции", async ({ page }) => {
  // ovi_video: у fal нет ни разрешения, ни длительности -- ручек нет вовсе
  // (в model_options для него нет ни одной строки). Это ключевая регрессия
  // плана: селектор, которого нет у провайдера, не должен нарисоваться.
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "ovi_video",
          display_name: "Ovi",
          tier: "economy",
          min_credits: 500,
          recommended_credits: 500,
          options: [],
        },
      ],
    }),
  );

  await page.goto("/generate-video");
  await expect(page.getByTestId("generate-prompt")).toBeVisible();

  await expect(page.getByTestId("option-duration")).toHaveCount(0);
  await expect(page.getByTestId("option-quality")).toHaveCount(0);
  await expect(page.getByTestId("option-audio")).toHaveCount(0);
});
