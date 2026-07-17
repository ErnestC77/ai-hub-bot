// Баннер «активная генерация» на Home: возврат к незаконченной генерации.
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.use({ viewport: { width: 390, height: 844 } });

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("нет активной генерации -> баннера нет", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("home-credits")).toBeVisible();
  await expect(page.getByTestId("active-generation")).toHaveCount(0);
});

test("идёт генерация -> баннер, по завершении -> «готово», тап ведёт на страницу", async ({ page }) => {
  // Первый опрос -> ещё идёт, второй -> завершено.
  let calls = 0;
  await page.route("**/api/generate/321", (route) => {
    calls += 1;
    route.fulfill({
      json:
        calls < 2
          ? { status: "processing", result_url: null, error_message: null, charged_credits: 0 }
          : { status: "completed", result_url: "https://cdn/out.png", error_message: null, charged_credits: 43 },
    });
  });
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "aihub.pending.image",
      JSON.stringify({ requestId: 321, prompt: "закат над морем", ts: Date.now() }),
    );
  });

  await page.goto("/");
  const banner = page.getByTestId("active-generation");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Идёт генерация фото");
  await expect(banner).toContainText("закат над морем");

  // Дождались завершения -> «готово».
  await expect(banner).toContainText("Фото готово", { timeout: 15000 });

  // Тап ведёт на страницу генерации.
  await banner.click();
  await expect(page).toHaveURL(/\/generate-image$/);
});

test("генерация провалилась -> баннер исчезает и pending чистится", async ({ page }) => {
  await page.route("**/api/generate/777", (route) =>
    route.fulfill({ json: { status: "failed", result_url: null, error_message: "boom", charged_credits: 0 } }),
  );
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "aihub.pending.video",
      JSON.stringify({ requestId: 777, prompt: "танцующий кот", ts: Date.now() }),
    );
  });

  await page.goto("/");
  // Сначала баннер появляется (иначе toHaveCount(0) прошёл бы на стартовом
  // null-состоянии, до поллинга) -- затем по failed исчезает и чистит pending.
  await expect(page.getByTestId("active-generation")).toBeVisible();
  await expect(page.getByTestId("active-generation")).toHaveCount(0, { timeout: 15000 });
  const leftover = await page.evaluate(() => window.localStorage.getItem("aihub.pending.video"));
  expect(leftover).toBeNull();
});
