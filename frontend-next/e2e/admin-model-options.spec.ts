import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  const adminId = Number(process.env.TEST_ADMIN_TELEGRAM_ID);
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token", adminId);
});

test("вкладка Опции открывается и показывает опции модели", async ({ page }) => {
  // Мокаем admin-эндпоинты, чтобы тест не зависел от содержимого БД.
  await page.route("**/api/admin/models", (route) =>
    route.fulfill({
      json: [{
        code: "wan_video", provider: "fal", category: "video", tier: "standard",
        display_name: "Wan Video", provider_model_id: "fal-ai/wan", min_credits: 466,
        recommended_credits: 932, is_active: true, is_visible: true, sort_order: 10,
        input_price_usd_per_1m_tokens: 0, output_price_usd_per_1m_tokens: 0,
      }],
    }),
  );
  await page.route("**/api/admin/models/wan_video/options", (route) =>
    route.fulfill({
      json: [
        { id: 1, model_code: "wan_video", kind: "quality", code: "480p", label: "480p",
          provider_params: { resolution: "480p" }, credits_multiplier: 0.5,
          is_default: false, sort_order: 10, is_active: true },
        { id: 2, model_code: "wan_video", kind: "quality", code: "720p", label: "720p",
          provider_params: { resolution: "720p" }, credits_multiplier: 1.0,
          is_default: true, sort_order: 20, is_active: true },
      ],
    }),
  );

  await page.goto("/admin");
  await page.getByRole("button", { name: "Опции" }).click();

  // .first(): и лейбл, и "(код)", и JSON provider_params содержат подстроку
  // "480p"/"720p" (см. AdminModelOptions.tsx), поэтому getByText матчит
  // несколько узлов -- берём первый, сама видимость текста не ослабляется.
  await expect(page.getByText("480p").first()).toBeVisible();
  await expect(page.getByText("720p").first()).toBeVisible();
  await expect(page.getByText("Качество")).toBeVisible(); // заголовок секции по kind
});

test("переключение активности опции шлёт PATCH", async ({ page }) => {
  await page.route("**/api/admin/models", (route) =>
    route.fulfill({
      json: [{
        code: "wan_video", provider: "fal", category: "video", tier: "standard",
        display_name: "Wan Video", provider_model_id: "fal-ai/wan", min_credits: 466,
        recommended_credits: 932, is_active: true, is_visible: true, sort_order: 10,
        input_price_usd_per_1m_tokens: 0, output_price_usd_per_1m_tokens: 0,
      }],
    }),
  );
  await page.route("**/api/admin/models/wan_video/options", (route) =>
    route.fulfill({
      json: [{ id: 1, model_code: "wan_video", kind: "quality", code: "480p", label: "480p",
        provider_params: { resolution: "480p" }, credits_multiplier: 0.5,
        is_default: false, sort_order: 10, is_active: true }],
    }),
  );

  let patched: unknown = null;
  await page.route("**/api/admin/options/1", (route) => {
    patched = route.request().postDataJSON();
    route.fulfill({
      json: { id: 1, model_code: "wan_video", kind: "quality", code: "480p", label: "480p",
        provider_params: { resolution: "480p" }, credits_multiplier: 0.5,
        is_default: false, sort_order: 10, is_active: false },
    });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Опции" }).click();
  // Тумблер «Активна» -- Radix Switch рендерит role="switch" на самой кнопке;
  // скрытый зеркальный input[type=checkbox] существует только внутри <form>
  // (которого в этом UI нет), поэтому селектор по input[type=checkbox] из
  // черновика брифа ничего не находит. Скоупим по подписи "Активна", которая
  // лежит в одном flex-контейнере со своим свитчем (AdminModelOptions.tsx) --
  // единственная опция в этом тесте, так что подпись встречается один раз.
  await page.getByText("480p").first().scrollIntoViewIfNeeded();
  await page.getByText("Активна").locator("..").getByRole("switch").click();

  await expect.poll(() => patched).toMatchObject({ is_active: false });
});
