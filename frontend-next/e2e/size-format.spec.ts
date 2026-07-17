// Матрица «размер x формат» (qwen/seedream): два ряда поверх одной оси
// комбо-кодов <size>__<fmt>; выбор склеивается, цена -- от размера.
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.use({ viewport: { width: 390, height: 844 } });

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("два ряда: смена размера держит формат, цена растёт от размера", async ({ page }) => {
  // Матрица qwen_image как в сиде: 1k x1 (дефолт 1k__1_1), 2k x4.
  const combos: Array<Record<string, unknown>> = [];
  let so = 10;
  for (const [size, mult] of [["1k", 1], ["2k", 4]] as const) {
    for (const fmt of ["1_1", "16_9", "9_16", "4_3", "3_4"]) {
      combos.push({
        kind: "quality", code: `${size}__${fmt}`,
        label: `${size.toUpperCase()} · ${fmt.replaceAll("_", ":")}`,
        credits_multiplier: mult, is_default: size === "1k" && fmt === "1_1",
        sort_order: (so += 2),
      });
    }
  }
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [{
        code: "qwen_image", display_name: "Qwen Image", tier: "economy",
        min_credits: 29, recommended_credits: 29, min_charge_credits: 29,
        options: combos, edit_multiplier: null,
      }],
    }),
  );

  let generateBody: Record<string, unknown> | undefined;
  await page.route("**/api/generate", async (route) => {
    generateBody = route.request().postDataJSON();
    await route.fulfill({ json: { request_id: 1, estimated_credits: 116 } });
  });
  await page.route("**/api/generate/1", (route) =>
    route.fulfill({
      json: { status: "completed", result_url: "https://cdn.example.com/out.png",
              error_message: null, charged_credits: 116 },
    }),
  );

  await page.goto("/generate-image");

  // Оба ряда видны, единой строки-солянки нет.
  await expect(page.getByTestId("option-size")).toBeVisible();
  await expect(page.getByTestId("option-format")).toBeVisible();
  await expect(page.getByTestId("option-quality")).toHaveCount(0);
  await expect(page.getByTestId("generate-submit")).toContainText("29");

  // Формат 16:9 -- цена не меняется (формат бесплатный).
  await page.getByTestId("option-format-16_9").click();
  await expect(page.getByTestId("generate-submit")).toContainText("29");

  // Размер 2K -- формат СОХРАНЯЕТСЯ, цена x4.
  await page.getByTestId("option-size-2k").click();
  await expect(page.getByTestId("generate-submit")).toContainText("116");

  // На бэк уходит один комбо-код с обоими выборами.
  await page.getByTestId("generate-prompt").fill("кот в космосе");
  await page.getByTestId("generate-submit").click();
  // src-атрибут, не toBeVisible: фейковый URL мока не грузится, у img нулевая высота.
  await expect(page.getByTestId("generate-result").locator("img")).toHaveAttribute(
    "src", "https://cdn.example.com/out.png", { timeout: 15000 },
  );
  expect(generateBody?.option_codes).toEqual({ quality: "2k__16_9" });
});
