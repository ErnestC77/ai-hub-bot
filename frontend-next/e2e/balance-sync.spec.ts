// Баланс должен обновляться сразу после операций, без перезапуска приложения
// (профиль грузится один раз на старте -- баг: пилюля жила до рестарта).
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.use({ viewport: { width: 390, height: 844 } });

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("чат обновляет баланс на Home без перезагрузки", async ({ page }) => {
  await page.route("**/api/me", (route) =>
    route.fulfill({
      json: {
        telegram_id: 1, username: "u", first_name: "U", is_admin: false,
        default_model_code: "deepseek_v3", credits_balance: 500,
        total_credits_purchased: 0, total_credits_spent: 0,
      },
    }),
  );
  await page.route("**/api/chat", (route) =>
    route.fulfill({ json: { answer: "Привет!", charged_credits: 3, balance_after: 497 } }),
  );

  await page.goto("/");
  await expect(page.getByTestId("home-credits")).toContainText("500");

  // SPA-переход (не goto -- иначе новый mount перечитал бы мок и спрятал баг).
  await page.getByTestId("action-chat").click();
  await page.getByTestId("chat-input").fill("привет");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-bubble").last()).toContainText("Баланс: 497");

  await page.getByTestId("chat-close").click();
  await expect(page.getByTestId("home-credits")).toContainText("497");
});

test("генерация перечитывает баланс после резерва и завершения", async ({ page }) => {
  // /api/me: до генерации 1000, после (резерв списал) -- 655.
  let meCalls = 0;
  await page.route("**/api/me", (route) => {
    meCalls += 1;
    route.fulfill({
      json: {
        telegram_id: 1, username: "u", first_name: "U", is_admin: false,
        default_model_code: "deepseek_v3", credits_balance: meCalls === 1 ? 1000 : 655,
        total_credits_purchased: 1, total_credits_spent: 0,
      },
    });
  });
  await page.route("**/api/models*", (route) =>
    route.fulfill({
      json: [{
        code: "nano_banana_pro", display_name: "Nano Banana Pro", tier: "premium",
        min_credits: 345, recommended_credits: 345, min_charge_credits: 345,
        options: [
          { kind: "quality", code: "1k", label: "1K", credits_multiplier: 1, is_default: true, sort_order: 10 },
        ],
        edit_multiplier: 1.5,
      }],
    }),
  );
  await page.route("**/api/generate", (route) =>
    route.fulfill({ json: { request_id: 7, estimated_credits: 345 } }),
  );
  await page.route("**/api/generate/7", (route) =>
    route.fulfill({
      json: { status: "completed", result_url: "https://cdn.example.com/out.png",
              error_message: null, charged_credits: 345 },
    }),
  );

  await page.goto("/generate-image");
  await expect(page.getByText("Баланс: 1000")).toBeVisible();

  await page.getByTestId("generate-prompt").fill("кот в космосе");
  await page.getByTestId("generate-submit").click();
  // src-атрибут, не toBeVisible: фейковый URL мока не грузится, у img нулевая высота.
  await expect(page.getByTestId("generate-result").locator("img")).toHaveAttribute(
    "src", "https://cdn.example.com/out.png", { timeout: 15000 },
  );

  await expect(page.getByText("Баланс: 655")).toBeVisible();
});
