// frontend-next/e2e/generate-image.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("generate-image screen has a dark textarea and a generate button", async ({ page }) => {
  await page.goto("/generate-image");
  const textarea = page.getByTestId("generate-prompt");
  await expect(textarea).toBeVisible();
  await expect(textarea).toHaveAttribute("placeholder", "Опишите, что хотите создать");
  const bg = await textarea.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg).not.toBe("rgb(255, 255, 255)");

  // Кнопки 1K/2K/4K и aspect-чипы удалены вместе с мёртвой dall-e-3-веткой
  // (фаза 3 generate). Кнопка генерации внизу («✨ Создать · N 💎» после
  // редизайна; задизейблена без модели/промпта, но видима).
  await expect(page.getByTestId("generate-submit")).toBeVisible();
  await expect(page.getByTestId("generate-submit")).toContainText("Создать");
});

test("рисует секцию качества только когда у модели она есть", async ({ page }) => {
  // nano_banana_pro (реальные коды опций из БД): 1K/2K/4K -- единственная
  // ручка у fal для этой модели. Экран генерации фото рисует только
  // OptionPicker kind="quality" (в отличие от видео, длительности/звука
  // здесь нет вовсе), так что она должна появиться.
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "nano_banana_pro",
          display_name: "Nano Banana Pro",
          tier: "premium",
          min_credits: 345,
          recommended_credits: 345,
          options: [
            { kind: "quality", code: "1k", label: "1K", credits_multiplier: 1, is_default: true, sort_order: 10 },
            { kind: "quality", code: "2k", label: "2K", credits_multiplier: 1, is_default: false, sort_order: 20 },
            { kind: "quality", code: "4k", label: "4K", credits_multiplier: 2, is_default: false, sort_order: 30 },
          ],
          edit_multiplier: 1.5,
        },
      ],
    }),
  );

  await page.goto("/generate-image");

  await expect(page.getByTestId("option-quality")).toBeVisible();
});

test("смена опции меняет цену в CTA", async ({ page }) => {
  // Те же коды и множители, что у nano_banana_pro в БД: recommended_credits
  // 345, 1K/2K x1 (дефолт 1K), 4K x2.
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "nano_banana_pro",
          display_name: "Nano Banana Pro",
          tier: "premium",
          min_credits: 345,
          recommended_credits: 345,
          options: [
            { kind: "quality", code: "1k", label: "1K", credits_multiplier: 1, is_default: true, sort_order: 10 },
            { kind: "quality", code: "2k", label: "2K", credits_multiplier: 1, is_default: false, sort_order: 20 },
            { kind: "quality", code: "4k", label: "4K", credits_multiplier: 2, is_default: false, sort_order: 30 },
          ],
          edit_multiplier: 1.5,
        },
      ],
    }),
  );

  await page.goto("/generate-image");

  await expect(page.getByTestId("generate-submit")).toContainText("345");
  await page.getByTestId("option-quality-4k").click();
  await expect(page.getByTestId("generate-submit")).toContainText("690");
});

test("шлёт коды выбранных опций, а не сырые значения", async ({ page }) => {
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "nano_banana_pro",
          display_name: "Nano Banana Pro",
          tier: "premium",
          min_credits: 345,
          recommended_credits: 345,
          options: [
            { kind: "quality", code: "1k", label: "1K", credits_multiplier: 1, is_default: true, sort_order: 10 },
            { kind: "quality", code: "4k", label: "4K", credits_multiplier: 2, is_default: false, sort_order: 30 },
          ],
          edit_multiplier: 1.5,
        },
      ],
    }),
  );

  let body: Record<string, unknown> | undefined;
  await page.route("**/api/generate", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({ json: { request_id: 1, estimated_credits: 690 } });
  });
  await page.route("**/api/generate/1", (route) =>
    route.fulfill({
      json: {
        status: "completed",
        result_url: "https://cdn.example.com/out.png",
        error_message: null,
        charged_credits: 690,
      },
    }),
  );

  await page.goto("/generate-image");
  await page.getByTestId("generate-prompt").fill("a cat in space");
  await page.getByTestId("option-quality-4k").click();
  await page.getByTestId("generate-submit").click();

  // Ждём фактического завершения запроса, а не произвольную паузу --
  // появление результата гарантирует, что postDataJSON() уже записан.
  await expect(page.getByTestId("generate-result").locator("img")).toHaveAttribute(
    "src",
    "https://cdn.example.com/out.png",
    { timeout: 15000 },
  );

  expect(body?.option_codes).toEqual({ quality: "4k" });
  expect(body).not.toHaveProperty("duration_seconds");
});

test("модель без опций -- ни одной секции", async ({ page }) => {
  // flux_kontext_pro: у fal нет ни одной ручки для этой модели (в
  // model_options нет ни одной строки) -- селектор качества рисоваться
  // не должен.
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "flux_kontext_pro",
          display_name: "Flux Kontext Pro",
          tier: "standard",
          min_credits: 100,
          recommended_credits: 100,
          options: [],
          edit_multiplier: null,
        },
      ],
    }),
  );

  await page.goto("/generate-image");
  await expect(page.getByTestId("generate-prompt")).toBeVisible();

  await expect(page.getByTestId("option-quality")).toHaveCount(0);
  await expect(page.getByTestId("option-duration")).toHaveCount(0);
  await expect(page.getByTestId("option-audio")).toHaveCount(0);
});

// Минимальный валидный 1x1 PNG в памяти -- не читаем файл с диска.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

test("edit-capable модель + фото -- CTA показывает цену с edit_multiplier", async ({ page }) => {
  // nano_banana_pro поддерживает i2i (edit_multiplier: 1.5 с бэка). Без фото
  // CTA = recommended_credits (345); с прикреплённым фото -- x1.5 и ceil:
  // ceil(345 * 1.5) = 518. Это регрессионный тест на баг, из-за которого CTA
  // игнорировал доплату за фото и списывал больше, чем показывал.
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "nano_banana_pro",
          display_name: "Nano Banana Pro",
          tier: "premium",
          min_credits: 345,
          recommended_credits: 345,
          options: [],
          edit_multiplier: 1.5,
        },
      ],
    }),
  );
  await page.route("**/api/upload/image", (route) =>
    route.fulfill({ json: { url: "https://example.com/x.png" } }),
  );

  await page.goto("/generate-image");

  await expect(page.getByTestId("generate-submit")).toContainText("345");

  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles({
    name: "tiny.png",
    mimeType: "image/png",
    buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
  });

  // Превью фото подтверждает, что стейт photos уже обновился, прежде чем
  // проверять пересчитанную цену.
  await expect(page.getByTestId("generate-photo-list")).toBeVisible();
  await expect(page.getByTestId("generate-submit")).toContainText("518");
});

test("модель без edit_multiplier -- фото-бокс не рисуется", async ({ page }) => {
  // qwen_image: edit_multiplier: null -- провайдер i2i не поддерживает,
  // фото-бокс скрыт, доплата не применяется.
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [
        {
          code: "qwen_image",
          display_name: "Qwen Image",
          tier: "standard",
          min_credits: 100,
          recommended_credits: 100,
          options: [],
          edit_multiplier: null,
        },
      ],
    }),
  );

  await page.goto("/generate-image");
  await expect(page.getByTestId("generate-prompt")).toBeVisible();

  await expect(page.getByTestId("generate-photo-upload")).toHaveCount(0);
});
