// frontend-next/e2e/trends.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("trends screen lists tool cards and opens chat with a prefilled prompt", async ({ page }) => {
  await page.goto("/trends");
  await expect(page.getByTestId("trends-page")).toBeVisible();
  // Redesign copy: «✨ Photo & Text Trends» → «✨ Тренды».
  await expect(page.getByText("✨ Тренды")).toBeVisible();
  // Каждая карточка несёт превью-видео (preview_url из /api/tools).
  await expect(page.getByTestId("trend-video").first()).toBeAttached();
  // Текст-тренд ведёт в чат (recommended_category ни image, ни video).
  await page.getByTestId("trends-text").getByTestId("trend-card").first().click();
  await expect(page).toHaveURL(/\/chat\?prefill=/);
});

test("photo trend routes to the image generator with a prefilled prompt", async ({ page }) => {
  await page.goto("/trends");
  await expect(page.getByTestId("trends-photo")).toBeVisible();
  await page.getByTestId("trends-photo").getByTestId("trend-card").first().click();
  await expect(page).toHaveURL(/\/generate-image\?prefill=/);
  // Префикс должен реально долететь до поля промпта, а не только в URL.
  await expect(page.getByTestId("generate-prompt")).toHaveValue(/.+/);
});

test("video trend routes to the video generator with a prefilled prompt", async ({ page }) => {
  await page.goto("/trends");
  await expect(page.getByTestId("trends-video")).toBeVisible();
  await page.getByTestId("trends-video").getByTestId("trend-card").first().click();
  await expect(page).toHaveURL(/\/generate-video\?prefill=/);
  await expect(page.getByTestId("generate-prompt")).toHaveValue(/.+/);
});

test.describe("mouse drag-to-scroll", () => {
  // Узкий вьюпорт: на десктопе карточки помещаются целиком и переполнения нет.
  test.use({ viewport: { width: 390, height: 844 } });

  test("carousel scrolls by mouse drag and a drag does not open a card", async ({ page }) => {
    await page.goto("/trends");
    // Текстовая секция самая длинная (14 карточек) -- гарантированно переполняет.
    const row = page.getByTestId("trends-text").locator(":scope > div").last();
    await expect(row).toBeVisible();
    const before = await row.evaluate((el) => (el as HTMLElement).scrollLeft);
    const box = await row.boundingBox();
    if (!box) throw new Error("no bounding box");
    const y = box.y + box.height / 2;
    await page.mouse.move(box.x + box.width - 20, y);
    await page.mouse.down();
    await page.mouse.move(box.x + 20, y, { steps: 8 });
    await page.mouse.up();
    // Прокрутилось вправо...
    await expect.poll(() => row.evaluate((el) => (el as HTMLElement).scrollLeft)).toBeGreaterThan(before);
    // ...и перетаскивание не открыло карточку (остались на /trends).
    await expect(page).toHaveURL(/\/trends$/);
  });
});
