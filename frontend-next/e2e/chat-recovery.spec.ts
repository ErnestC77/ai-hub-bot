// Надёжное восстановление ответа чата: закрыл во время генерации -> ответ
// сохранён на сервере (chat_recent) и добирается при открытии, без гонки.
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.use({ viewport: { width: 390, height: 844 } });

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("пропущенный ответ добирается из /api/chat/recent при открытии", async ({ page }) => {
  // Сценарий: юзер спросил и закрыл приложение во время генерации. Вопрос
  // сохранён в локальной истории, ответ -- нет (HTTP оборван), но лежит на
  // сервере в chat_recent.
  await page.route("**/api/chat/recent", (route) =>
    route.fulfill({ json: [{ id: "srv-1", prompt: "сколько будет 2+2", answer: "Будет 4." }] }),
  );
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "aihub.chat.history",
      JSON.stringify([{ role: "user", text: "сколько будет 2+2" }]),
    );
  });

  await page.goto("/chat");

  // Вопрос из локальной истории + добранный с сервера ответ.
  await expect(page.getByText("сколько будет 2+2")).toBeVisible();
  await expect(page.getByText("Будет 4.")).toBeVisible();
});

test("уже показанный ответ (тот же id) не дублируется", async ({ page }) => {
  // recent возвращает ответ, который уже есть в локальной истории с тем же id.
  await page.route("**/api/chat/recent", (route) =>
    route.fulfill({ json: [{ id: "dup-1", prompt: "вопрос", answer: "готовый ответ" }] }),
  );
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "aihub.chat.history",
      JSON.stringify([
        { role: "user", text: "вопрос" },
        { role: "assistant", text: "готовый ответ", id: "dup-1" },
      ]),
    );
  });

  await page.goto("/chat");
  await expect(page.getByText("готовый ответ")).toBeVisible();
  // Ровно один -- дедуп по id сработал.
  await expect(page.getByText("готовый ответ")).toHaveCount(1);
});
