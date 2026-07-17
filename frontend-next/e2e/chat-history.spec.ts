// История чата переживает закрытие приложения (продолжить в приложении).
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.use({ viewport: { width: 390, height: 844 } });

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("переписка сохраняется и восстанавливается при переоткрытии", async ({ page }) => {
  await page.route("**/api/chat", (route) =>
    route.fulfill({ json: { answer: "Отвечаю по существу.", charged_credits: 3, balance_after: 217 } }),
  );

  await page.goto("/chat");
  await page.getByTestId("chat-input").fill("первый вопрос");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-bubble").last()).toContainText("Отвечаю по существу");

  // «Переоткрытие» приложения: та же вкладка, свежая навигация -> новый mount.
  await page.goto("/");
  await page.goto("/chat");

  // Переписка на месте: и вопрос, и ответ.
  await expect(page.getByText("первый вопрос")).toBeVisible();
  await expect(page.getByText("Отвечаю по существу")).toBeVisible();
});

test("«новый чат» очищает историю и она не возвращается", async ({ page }) => {
  await page.route("**/api/chat", (route) =>
    route.fulfill({ json: { answer: "ответ", charged_credits: 3, balance_after: 217 } }),
  );

  await page.goto("/chat");
  await page.getByTestId("chat-input").fill("вопрос");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-bubble").last()).toContainText("ответ");

  await page.getByTestId("chat-new").click();
  // Пузыри пользователя/ответа ушли (остаётся только статичное приветствие).
  await expect(page.getByText("вопрос")).toHaveCount(0);

  await page.goto("/");
  await page.goto("/chat");
  await expect(page.getByText("вопрос")).toHaveCount(0);
  const leftover = await page.evaluate(() => window.localStorage.getItem("aihub.chat.history"));
  expect(leftover).toBeNull();
});
