// Защита в приложении: незавершённая генерация переживает переоткрытие --
// request_id лежит в localStorage, при возврате результат дослеживается.
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.use({ viewport: { width: 390, height: 844 } });

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [{
        code: "seedream", display_name: "Seedream", tier: "standard",
        min_credits: 43, recommended_credits: 43, min_charge_credits: 43,
        options: [], edit_multiplier: null,
      }],
    }),
  );
});

test("незавершённая генерация восстанавливается после переоткрытия", async ({ page }) => {
  // Симулируем «закрыл во время генерации»: pending-запись уже в localStorage,
  // запрос на бэке к моменту возврата завершён.
  await page.route("**/api/generate/555", (route) =>
    route.fulfill({
      json: { status: "completed", result_url: "https://cdn.example.com/recovered.png",
              error_message: null, charged_credits: 43 },
    }),
  );
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "aihub.pending.image",
      JSON.stringify({ requestId: 555, prompt: "закат над морем", ts: Date.now() }),
    );
  });

  await page.goto("/generate-image");

  // Результат подхватился прямо в приложении, без повторного «Создать».
  await expect(page.getByTestId("generate-result").locator("img")).toHaveAttribute(
    "src", "https://cdn.example.com/recovered.png", { timeout: 15000 },
  );
  // Запись очищена -> повторное открытие не будет заново дослеживать.
  const leftover = await page.evaluate(() => window.localStorage.getItem("aihub.pending.image"));
  expect(leftover).toBeNull();
});

test("протухшая pending-запись (TTL) игнорируется", async ({ page }) => {
  let polled = false;
  await page.route("**/api/generate/999", (route) => {
    polled = true;
    route.fulfill({ json: { status: "completed", result_url: "x", error_message: null, charged_credits: 1 } });
  });
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "aihub.pending.image",
      // ts 20 минут назад -- за пределами TTL (10 мин)
      JSON.stringify({ requestId: 999, prompt: "старьё", ts: Date.now() - 20 * 60 * 1000 }),
    );
  });

  await page.goto("/generate-image");
  await expect(page.getByTestId("generate-submit")).toBeVisible();
  await page.waitForTimeout(1500);
  // Протухшую запись не дослеживаем и чистим.
  expect(polled).toBe(false);
  const leftover = await page.evaluate(() => window.localStorage.getItem("aihub.pending.image"));
  expect(leftover).toBeNull();
});
