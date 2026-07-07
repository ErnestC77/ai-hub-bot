// frontend-next/e2e/mock-telegram.ts
import crypto from "node:crypto";
import type { Page } from "@playwright/test";

function signInitData(botToken: string, telegramId: number): string {
  const authDate = Math.floor(Date.now() / 1000);
  const user = JSON.stringify({ id: telegramId, first_name: "Test", username: "test_user" });
  const params: Record<string, string> = {
    auth_date: String(authDate),
    query_id: "test_query_id",
    user,
  };
  const dataCheckString = Object.keys(params)
    .sort()
    .map((k) => `${k}=${params[k]}`)
    .join("\n");
  const secretKey = crypto.createHmac("sha256", "WebAppData").update(botToken).digest();
  const hash = crypto.createHmac("sha256", secretKey).update(dataCheckString).digest("hex");
  const search = new URLSearchParams({ ...params, hash });
  return search.toString();
}

export async function mockTelegramWebApp(page: Page, botToken: string, telegramId = 999999): Promise<void> {
  const initData = signInitData(botToken, telegramId);
  await page.addInitScript((data) => {
    (window as unknown as { Telegram: unknown }).Telegram = {
      WebApp: {
        initData: data,
        ready: () => {},
        expand: () => {},
        openLink: () => {},
        openTelegramLink: () => {},
        openInvoice: () => {},
        BackButton: { show: () => {}, hide: () => {}, onClick: () => {}, offClick: () => {} },
        HapticFeedback: { impactOccurred: () => {}, notificationOccurred: () => {} },
      },
    };
  }, initData);
}
