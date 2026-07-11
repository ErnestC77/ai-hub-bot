# Frontend Integration — Phase 1: API layer + Account screen

## Контекст

Backend `credit-system-v2` rebuild завершён (6 фаз, `docs/superpowers/specs/2026-07-*-credit-system-phase{1..6}-*-design.md`), но `frontend-next/` (Next.js Telegram Mini App в этом же репозитории) не трогался за все 6 фаз и рассинхронизирован с реальным API почти по всем экранам: старая тарифно-подписочная модель (`tariff_code`, `subscription_expires_at`, категорийные лимиты fast/medium/premium/image) полностью удалена на бэкенде ещё в фазе 1 и заменена кредитной системой (`credits_balance`, `total_credits_purchased/spent`, каталог `AiModel` с `tier`), а admin API целиком переписан в фазе 5.

Отдельно на Рабочем столе (`C:\Users\mccaq\Desktop\AI-hub-bot фронт\design_handoff_ai_hub`) есть дизайн-хендофф "Aurora Glass" — статический HTML-прототип с рекомендацией пересобрать экраны на React+Vite+TS. Решение: это отдельная, более поздняя фаза (визуальный редизайн), не блокирует функциональную починку API. Текущий визуал `frontend-next/` остаётся как есть в этой фазе.

`frontend-next/src/api/client.ts` находится в переходном состоянии: часть уже обновлена под кредитную систему (`CreditPackageOut`, `api.creditPackages()`, `api.createStarsCreditPayment`/`createYookassaCreditPayment` — использует их уже готовый `CreditPurchaseSheet.tsx`), а часть всё ещё описывает удалённую тарифную схему (`MeOut.tariff_code/tariff_name/subscription_expires_at/limits`, `TariffOut`, старые admin-эндпойнты и т.д.).

## Scope

Это **первая под-фаза** большого проекта «связать фронтенд с новым бэкендом», декомпозированного пользователем на:
1. **(эта спека)** API-слой (`MeOut`) + экран Account — сквозной end-to-end путь: баланс → покупка пакета.
2. (позже) остальные пользовательские экраны (Chat, Trends, Tariffs, Referral, Settings, generate-image/video sheets) — по одному экрану за раз.
3. (позже) admin-панель `frontend-next/src/screens/admin/*` — отдельная под-фаза внутри этого же проекта (models/packages/users/settings/payments/banners под API фазы 5).
4. (намного позже, отдельный проект) визуальный редизайн "Aurora Glass" поверх уже рабочих экранов.

**В скоупе этой спеки:**
- `frontend-next/src/api/client.ts`: только `MeOut` (+ удаление `CategoryLimitOut`/`LimitsOut`, которые перестают использоваться где-либо ещё).
- `frontend-next/src/components/tariffs/PaymentMethodSheet.tsx`: одна строка, ловящая breaking change типов `MeOut` (иначе `next build` не соберётся целиком — TypeScript ошибка валит всю сборку, не только одну страницу).
- `frontend-next/src/app/account/page.tsx`: рерайт карточки плана под кредитную модель.
- `frontend-next/e2e/account.spec.ts`: обновить проверяемый текст.

**Вне скоупа (сознательно, для будущих под-фаз):**
- Остальные типы/методы `api/client.ts` (models, chat, generate, tariffs, admin*) — остаются как есть, зовут несуществующие/устаревшие эндпойнты. Экраны, которые их используют, продолжат не работать против реального бэкенда до своей очереди.
- `MeContext.tsx` — не типозависим от полей `MeOut` (просто прокидывает объект целиком), изменений не требует.
- Любой визуальный редизайн.

## Изменения

### 1. `api/client.ts` — `MeOut`

Текущее (строки ~43-53):
```ts
export interface MeOut {
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  is_admin: boolean;
  active_model: string | null;
  tariff_code: string;
  tariff_name: string;
  subscription_expires_at: string | null;
  limits: LimitsOut;
  credits_balance: number;
}
```

Новое — 1:1 с реальным `GET /api/me` (`app/api/routes/me.py`, `app/api/schemas.MeOut`):
```ts
export interface MeOut {
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  is_admin: boolean;
  default_model_code: string;
  credits_balance: number;
  total_credits_purchased: number;
  total_credits_spent: number;
}
```

Удалить интерфейсы `CategoryLimitOut`/`LimitsOut` целиком (после этого изменения нигде в кодовой базе не используются — проверено, единственные потребители были сам `MeOut` и друг друга). Тип `ModelCategory` НЕ удалять — используется в `ModelOut`, который вне скоупа этой фазы.

### 2. `PaymentMethodSheet.tsx`

Единственное использование поля из старого `MeOut` за пределами Account — в `waitForActivation()`, которая поллит `/api/me` после оплаты, ожидая смену тарифа как признак успешной активации:
```ts
if (me.tariff_code === tariff.code) {
```
Эта функция уже полностью нерабочая независимо от типов: `payWithStars`/`payWithYookassa` в этом же файле зовут `api.createStarsPayment(tariff.code)`/`api.createYookassaPayment(tariff.code)` — оба эндпойнта удалены на бэкенде ещё в фазе 4 (тарифная система целиком заменена кредитными пакетами). Правка здесь — только устранение ошибки компиляции, не восстановление логики (сам экран Tariffs переписывается в под-фазе 2 на пакеты кредитов). Заменить на:
```ts
// Тарифная система заменена кредитными пакетами (фазы 1-4) -- tariff_code
// в MeOut больше нет, как и эндпойнтов createStars/YookassaPayment(tariff.code)
// чуть ниже в этом файле. Экран целиком переписывается в под-фазе 2 фронтенд-
// интеграции; здесь только компилируемая заглушка условия, не рабочая проверка.
if (me.total_credits_purchased > 0) {
```

### 3. `account/page.tsx`

Убрать целиком:
- Карточку тарифа (заголовок "Current plan", `me.tariff_name`, дневной прогресс-бар, pill'ы категорий `me.limits.categories`, дата `me.subscription_expires_at`).
- Условный CTA "🚀 Go Premium" на `isFree = me.tariff_code === "free"`.

Заменить на карточку кредитов (в том же визуальном стиле — стекло, градиентная полоска сверху, как было у карточки тарифа):
- Заголовок "Баланс" вместо "Current plan".
- Крупное число `me.credits_balance` кредитов.
- Две строки-показателя: "Всего куплено" (`me.total_credits_purchased`), "Всего потрачено" (`me.total_credits_spent`).
- Если `me.total_credits_purchased === 0` (триал): баннер-приглашение вместо "Go Premium" — например "💎 Купите первый пакет" / текст про доступ к видео и топовым моделям после первой покупки (соответствует реальному антифрод-гейту фазы 5: video и ultra-модели недоступны до `total_credits_purchased > 0`), кнопка открывает `CreditPurchaseSheet` (тот же компонент, что уже используется у "+"), а не переход на `/tariffs`.

Секция `Section header="Settings"` (Настройки/Рефералка/Админ-панель) и сам `CreditPurchaseSheet` — без изменений по логике, только по месту в разметке, если потребуется из-за удаления блока лимитов.

### 4. `e2e/account.spec.ts`

```ts
test("account screen shows balance and credits", async ({ page }) => {
  await page.goto("/account");
  await expect(page.getByText("Баланс")).toBeVisible();
  await expect(page.getByText("Credits")).toBeVisible();
  await expect(page.getByText(/кредитов/)).toBeVisible();
});
```
(точный текст заголовка карточки — то, что реально выберет реализация в п.3; тест подгоняется под финальную копию, не наоборот).

Уточнение по прогону: этот e2e-тест не мокает `/api/me` (в отличие от типового Playwright-паттерна с перехватом роутов) — он полагается на реально работающий бэкенд по адресу из `playwright.config`. Проверить перед прогоном, что локальный бэкенд поднят и доступен (или что тест уже имеет механизм поднятия/мока, если он появился в этом файле после последнего просмотра) — не в скоупе спеки чинить это, если оно уже так работало для других e2e до этой фазы.

## Тестирование

- `npm run build` (в `frontend-next/`) должен пройти чисто (typecheck) — это единственная проверка, которая ловит поломку из-за смены `MeOut` в других файлах прямо сейчас (кроме уже учтённого `PaymentMethodSheet.tsx`).
- `npm run test:e2e -- account.spec.ts` — с реальным бэкендом (см. уточнение выше).
- Ручная проверка: `npm run dev`, открыть `/account` через Telegram Mini App (или мок `mockTelegramWebApp`), убедиться что баланс/цифры покупки/траты отображаются и кнопка "+" открывает `CreditPurchaseSheet`.

## Не в скоупе / известные ограничения после этой фазы

- `frontend-next` в целом всё ещё не работает как приложение против реального бэкенда — заработает только экран Account. Остальные экраны (включая навигацию с них на Account) могут падать при попытке загрузить свои данные — это ожидаемо и чинится в следующих под-фазах.
- Само наличие рабочего `next build` не означает, что все остальные экраны функциональны в браузере — только что они не ломают компиляцию.
