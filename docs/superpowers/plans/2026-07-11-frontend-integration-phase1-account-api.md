# Frontend Integration Phase 1 — API Layer + Account Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Первая под-фаза связывания `frontend-next/` с переписанным бэкендом credit-system-v2: тип `MeOut` приводится 1:1 к реальному `GET /api/me`, экран Account переезжает с тарифной модели на кредитную (карточка баланса + триал-баннер), e2e-тест обновляется — сквозная проверка «баланс → покупка пакета» на одном экране.

**Architecture:** Точечная правка API-слоя (`MeOut` в `client.ts` + удаление мёртвых `CategoryLimitOut`/`LimitsOut`), однострочная компилируемая заглушка в `PaymentMethodSheet.tsx` (единственный внешний потребитель старых полей `MeOut`), рерайт JSX карточки плана в `account/page.tsx` на карточку кредитов в том же визуальном стиле (стекло + градиентная полоска), обновление under-test текста в `e2e/account.spec.ts`. Всё остальное в `client.ts` (models/chat/tariffs/admin*) сознательно не трогается до следующих под-фаз.

**Tech Stack:** Next.js 16.2.10 (App Router) + React 19.2.4 + TypeScript 5 strict + Tailwind CSS 4 + Playwright 1.61. Бэкенд (не меняется в этой фазе): FastAPI, `GET /api/me` → `app/api/schemas.py:4-12`.

**Design spec (единственный источник истины):** `docs/superpowers/specs/2026-07-11-frontend-integration-phase1-account-api-design.md`

## Global Constraints

- **Рабочая директория всех npm-команд — `frontend-next/`** (из корня репо: `cd frontend-next`). Git-команды — из корня репо.
- **Здесь нет pytest.** Проверки этой фазы: быстрая — `npx tsc --noEmit` (typescript уже в devDependencies, tsconfig strict), канонический гейт — `npm run build` (Next.js гоняет typecheck в составе сборки; отдельного `typecheck`-скрипта в `package.json` нет). Поведенческая — Playwright e2e (Task 5), требует реального бэкенда.
- **Задачи 1–3 — один атомарный typecheck-юнит.** После Task 1 и Task 2 `npm run build` / `npx tsc --noEmit` ОЖИДАЕМО красные (это и есть «падающий тест» фазы); зелёными они обязаны стать ровно в конце Task 3. Промежуточные коммиты задач 1–2 помечаются `wip(frontend)` — это осознанно.
- **Строго только 4 файла в скоупе:** `frontend-next/src/api/client.ts` (только блок `MeOut`/`CategoryLimitOut`/`LimitsOut`), `frontend-next/src/components/tariffs/PaymentMethodSheet.tsx` (одна строка + комментарий), `frontend-next/src/app/account/page.tsx` (рерайт), `frontend-next/e2e/account.spec.ts`. НЕ трогать: `CreditPurchaseSheet.tsx` (уже корректен под новую схему), `MeContext.tsx` (не типозависим от полей `MeOut`), остальные типы/методы `client.ts` (включая `TariffOut`, `api.tariffs`, `createStarsPayment`, `adminApi.*` — они зовут удалённые эндпойнты и чинятся в под-фазах 2–3), `mock-telegram.ts`, `playwright.config.ts`.
- **Тип `ModelCategory` (`client.ts:32`) НЕ удалять** — используется `ModelOut` (вне скоупа). Удаляются только `CategoryLimitOut` (`client.ts:34-37`) и `LimitsOut` (`client.ts:39-43`).
- **`default_model_code: string` (не nullable) в TS** — Pydantic-схема допускает `None` (`app/api/schemas.py:9`), но роут всегда коалесцирует в `"deepseek_v3"` (`app/api/routes/me.py:21`: `user.default_model_code or DEFAULT_MODEL_CODE`), т.е. на проводе поле всегда строка; спека фиксирует `string`.
- **Копирайт e2e-теста подгоняется под финальную копию UI, не наоборот** (спека, п.4). Точные строки в Task 3/Task 4 этого плана уже согласованы: заголовок карточки — «Баланс», крупное число — `💎 {credits_balance} кредитов`, строки — «Всего куплено» / «Всего потрачено».
- **Playwright strict mode:** после Task 3 текст `/кредитов/` встречается на странице дважды (карточка баланса + Cell «💎 N кредитов» с кнопкой «+»), поэтому в e2e обязателен `.first()` — голый `getByText(/кредитов/)` упадёт с strict mode violation.
- **e2e требует реального бэкенда.** `playwright.config.ts` поднимает через `webServer` ТОЛЬКО фронтенд (`npm run dev` на :3000); `next.config.ts` не содержит rewrites, а `API_BASE_URL` в `client.ts:3` берётся из `NEXT_PUBLIC_API_URL`. Полные предусловия прогона — в Task 5; если бэкенд в окружении исполнителя поднять нельзя, Task 5 e2e-шаг передаётся пользователю как ручная инструкция (НЕ выдумывать route-моки — их нет в спеке).
- **Next.js 16 (`frontend-next/AGENTS.md`):** конвенции могут отличаться от training data — но эта фаза не создаёт новых роутов/конвенций, только правит тела существующих файлов; сверяться с `node_modules/next/dist/docs/` нужно лишь если возникнет ошибка сборки, не похожая на TS-ошибку типов.
- Номера строк актуальны на master `1773dcd` (2026-07-11). Внутри задачи более ранние правки сдвигают последующие строки — ориентироваться на приведённые якорные сниппеты.
- **Критерий готовности фазы:** `npm run build` полностью зелёный; `npm run test:e2e -- account.spec.ts` зелёный при поднятом бэкенде (или явно передан пользователю как ручной шаг с полной инструкцией).

## File Structure

| Файл | Действие |
|---|---|
| `frontend-next/src/api/client.ts` | переписать `MeOut` (строки 45-56), удалить `CategoryLimitOut`/`LimitsOut` (строки 34-43) — Task 1 |
| `frontend-next/src/components/tariffs/PaymentMethodSheet.tsx` | заменить строку 36 на компилируемую заглушку + комментарий — Task 2 |
| `frontend-next/src/app/account/page.tsx` | рерайт: карточка баланса + триал-баннер, убрать тарифную карточку и «Go Premium» — Task 3 |
| `frontend-next/e2e/account.spec.ts` | обновить название и проверяемый текст — Task 4 |
| — | финальная верификация: `npm run build` + e2e с реальным бэкендом — Task 5 |

---

### Task 1: `client.ts` — новый `MeOut`, удаление `CategoryLimitOut`/`LimitsOut`

**Files:**
- Modify: `frontend-next/src/api/client.ts:32-56`

**Interfaces:**
- Consumes: реальный контракт `GET /api/me` — `app/api/schemas.py:4-12` (`MeOut`: `telegram_id`, `username`, `first_name`, `is_admin`, `default_model_code`, `credits_balance`, `total_credits_purchased`, `total_credits_spent`) и `app/api/routes/me.py:14-25` (роут, коалесцирующий `default_model_code`).
- Produces (Tasks 2–3 полагаются на ТОЧНЫЕ имена): `MeOut.credits_balance: number`, `MeOut.total_credits_purchased: number`, `MeOut.total_credits_spent: number`, `MeOut.default_model_code: string`. Полей `tariff_code`/`tariff_name`/`subscription_expires_at`/`limits`/`active_model` в `MeOut` больше НЕТ.

- [ ] **Step 1: Переписать блок типов**

Текущий код (`frontend-next/src/api/client.ts`, строки 32–56):

```ts
export type ModelCategory = "fast" | "medium" | "premium" | "image" | "video";

export interface CategoryLimitOut {
  used: number;
  limit: number;
}

export interface LimitsOut {
  daily_used: number;
  daily_limit: number;
  categories: Record<ModelCategory, CategoryLimitOut>;
}

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

Заменить целиком на (первая строка `ModelCategory` сохраняется без изменений):

```ts
export type ModelCategory = "fast" | "medium" | "premium" | "image" | "video";

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

Больше НИЧЕГО в `client.ts` не менять (в т.ч. `ModelOut`, `TariffOut`, `adminApi` — вне скоупа; `api.me()` на строке 152 уже возвращает `request<MeOut>("/api/me")` и правок не требует).

- [ ] **Step 2: Проверить, что сломались ТОЛЬКО ожидаемые потребители (красный прогон)**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: FAIL. Ошибки `Property '...' does not exist on type 'MeOut'` ТОЛЬКО в двух файлах:
- `src/app/account/page.tsx` — `limits` (строки 41, 58, 62), `tariff_code` (42), `tariff_name` (53), `subscription_expires_at` (74, 76);
- `src/components/tariffs/PaymentMethodSheet.tsx` — `tariff_code` (строка 36).

Если ошибки есть в каких-либо ДРУГИХ файлах `src/` — СТОП: спека утверждает, что других потребителей нет, расхождение нужно разобрать до продолжения. (Замечание: `src/screens/admin/AdminUsers.tsx` использует `tariff_code` из ДРУГОГО типа `AdminUserOut` — он не менялся и ошибок не даст. Возможный посторонний шум от stale-типов в `.next/` лечится `Remove-Item -Recurse -Force .next` и не считается ошибкой потребителей.)

- [ ] **Step 3: Промежуточный коммит (build осознанно красный до Task 3)**

Из корня репо:

```bash
git add frontend-next/src/api/client.ts
git commit -m "wip(frontend): MeOut 1:1 c GET /api/me credit-system v2, удалены CategoryLimitOut/LimitsOut (build красный до починки потребителей)"
```

---

### Task 2: `PaymentMethodSheet.tsx` — компилируемая заглушка условия активации

**Files:**
- Modify: `frontend-next/src/components/tariffs/PaymentMethodSheet.tsx:36`

**Interfaces:**
- Consumes: `MeOut.total_credits_purchased: number` из Task 1.
- Produces: ничего нового. ВАЖНО: это НЕ восстановление логики — `payWithStars`/`payWithYookassa` в этом же файле зовут `api.createStarsPayment(tariff.code)`/`api.createYookassaPayment(tariff.code)`, чьи эндпойнты удалены на бэкенде ещё в фазе 4; экран Tariffs целиком переписывается в под-фазе 2. Здесь только устранение ошибки компиляции.

- [ ] **Step 1: Заменить строку условия**

Текущий код (`frontend-next/src/components/tariffs/PaymentMethodSheet.tsx`, строки 34–41, якорь):

```ts
      try {
        const me = await api.me();
        if (me.tariff_code === tariff.code) {
          await refresh();
          setStage("success");
          haptic("medium");
          return;
        }
```

Заменить строку 36 (`if (me.tariff_code === tariff.code) {`) на:

```ts
        // Тарифная система заменена кредитными пакетами (фазы 1-4) -- tariff_code
        // в MeOut больше нет, как и эндпойнтов createStars/YookassaPayment(tariff.code)
        // чуть ниже в этом файле. Экран целиком переписывается в под-фазе 2 фронтенд-
        // интеграции; здесь только компилируемая заглушка условия, не рабочая проверка.
        if (me.total_credits_purchased > 0) {
```

Больше ничего в файле не менять.

- [ ] **Step 2: Проверить, что осталась только ошибка в account/page.tsx**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: FAIL, но все оставшиеся ошибки — ТОЛЬКО в `src/app/account/page.tsx` (тот же список полей, что в Task 1 Step 2). `src/components/tariffs/PaymentMethodSheet.tsx` в выводе отсутствует.

- [ ] **Step 3: Промежуточный коммит**

```bash
git add frontend-next/src/components/tariffs/PaymentMethodSheet.tsx
git commit -m "wip(frontend): компилируемая заглушка waitForActivation вместо tariff_code (экран Tariffs переписывается в под-фазе 2)"
```

---

### Task 3: `account/page.tsx` — карточка баланса + триал-баннер

**Files:**
- Modify: `frontend-next/src/app/account/page.tsx` (переписывается почти целиком)

**Interfaces:**
- Consumes: `MeOut.credits_balance` / `total_credits_purchased` / `total_credits_spent` (Task 1); `useMe()` из `@/context/MeContext` (без изменений — прокидывает объект целиком); `CreditPurchaseSheet` из `@/components/account/CreditPurchaseSheet` (НЕ трогать — уже работает через `api.creditPackages()` + `createStarsCreditPayment`/`createYookassaCreditPayment`; подключается ровно как раньше: рендер по флагу `buyingCredits`, `onClose={() => setBuyingCredits(false)}`); UI-примитивы `Button`/`Cell`/`IconButton`/`List`/`Placeholder`/`Section`/`Spinner` из `@/components/ui/*` (существующие пропсы: `Cell` — `subtitle`/`after`/`onClick`, `Button` — `stretched`/`mode`).
- Produces (Task 4 полагается на ТОЧНЫЙ отображаемый текст): «Баланс» (заголовок карточки, ровно одно вхождение на странице), «💎 {N} кредитов» (карточка И Cell — два вхождения `/кредитов/`), «Credits» (label секции), «Всего куплено», «Всего потрачено», триал-баннер «💎 Купите первый пакет» при `total_credits_purchased === 0`.

- [ ] **Step 1: Переписать файл целиком**

Заменить всё содержимое `frontend-next/src/app/account/page.tsx` на:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Cell } from "@/components/ui/cell";
import { IconButton } from "@/components/ui/icon-button";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";
import { useMe } from "@/context/MeContext";
import CreditPurchaseSheet from "@/components/account/CreditPurchaseSheet";

export default function MyAccount() {
  const { me, loading } = useMe();
  const router = useRouter();
  const [buyingCredits, setBuyingCredits] = useState(false);

  if (loading) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  if (!me) {
    return <Placeholder header="Не удалось загрузить профиль" description="Откройте приложение из Telegram." />;
  }

  // Антифрод-гейт фазы 5: video и ultra-модели недоступны до первой покупки.
  const isTrial = me.total_credits_purchased === 0;

  return (
    <div className="p-4">
      <h2 className="heading-font mt-2 mb-5 text-center text-[19px] font-semibold">
        @{me.username ?? me.first_name ?? me.telegram_id}
      </h2>

      <div className="relative mb-4 overflow-hidden rounded-lg border border-border-soft bg-surface p-[18px]">
        <div className="absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]" />
        <div className="text-xs uppercase tracking-[0.4px] text-foreground-muted">Баланс</div>
        <div className="heading-font mt-1 mb-3 text-[28px] font-semibold">💎 {me.credits_balance} кредитов</div>

        <div className="flex justify-between text-[13px]">
          <span className="text-foreground-muted">Всего куплено</span>
          <span>{me.total_credits_purchased}</span>
        </div>
        <div className="mt-1.5 flex justify-between text-[13px]">
          <span className="text-foreground-muted">Всего потрачено</span>
          <span>{me.total_credits_spent}</span>
        </div>
      </div>

      {isTrial && (
        <div className="press-scale mb-4 rounded-lg bg-[image:var(--brand-gradient)] p-[18px] shadow-glow">
          <div className="heading-font text-[18px] font-semibold">💎 Купите первый пакет</div>
          <div className="mt-1 mb-3.5 text-[13px] opacity-90">
            Первая покупка открывает доступ к видео-генерации и топовым моделям
          </div>
          <Button stretched mode="white" onClick={() => setBuyingCredits(true)}>
            Выбрать пакет
          </Button>
        </div>
      )}

      <div className="my-2 text-xs uppercase text-foreground-muted">Credits</div>
      <List>
        <Section>
          <Cell
            subtitle="Списываются за каждый запрос к моделям"
            after={
              <IconButton onClick={() => setBuyingCredits(true)} aria-label="Купить кредиты">
                +
              </IconButton>
            }
          >
            💎 {me.credits_balance} кредитов
          </Cell>
        </Section>

        <Section header="Settings">
          <Cell onClick={() => router.push("/settings")}>⚙️ Настройки и поддержка</Cell>
          <Cell onClick={() => router.push("/referral")}>🎁 Реферальная программа</Cell>
          {me.is_admin && <Cell onClick={() => router.push("/admin")}>🛠 Админ-панель</Cell>}
        </Section>
      </List>

      {buyingCredits && <CreditPurchaseSheet onClose={() => setBuyingCredits(false)} />}
    </div>
  );
}
```

Что изменилось относительно текущего файла (для ревьюера):
- Удалены: импорт `Progress`, константа `CATEGORY_LABEL`, переменные `categories`/`isFree`, карточка тарифа (`Current plan` / `me.tariff_name` / дневной прогресс-бар / pill'ы категорий / дата подписки), баннер «🚀 Go Premium» с переходом на `/tariffs`.
- Добавлены: карточка «Баланс» в том же визуальном стиле (те же классы стекла `border-border-soft bg-surface` и градиентная полоска `h-[3px] bg-[image:var(--brand-gradient)]`), триал-баннер в стиле старого Go Premium (`press-scale ... shadow-glow`), но открывающий `CreditPurchaseSheet` (`setBuyingCredits(true)`), а НЕ `router.push("/tariffs")`.
- Без изменений: заголовок `@username`, Cell «💎 N кредитов» с «+», обновлён только её subtitle (старый «Тратятся, когда лимит тарифа исчерпан» ссылался на удалённые тарифные лимиты), секция Settings, рендер `CreditPurchaseSheet`. `router` по-прежнему используется (Settings/Referral/Admin).

- [ ] **Step 2: Typecheck зелёный**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: PASS, exit code 0, пустой вывод.

- [ ] **Step 3: Канонический гейт — сборка**

Run (из `frontend-next/`): `npm run build`

Expected: PASS — `Compiled successfully`, без TS-ошибок, все страницы собраны (включая `/tariffs` c `PaymentMethodSheet` и `/admin/*` — они не трогались и обязаны продолжать компилироваться).

- [ ] **Step 4: Коммит (первый зелёный)**

```bash
git add frontend-next/src/app/account/page.tsx
git commit -m "feat(frontend): экран Account на кредитной модели -- карточка баланса, триал-баннер, CreditPurchaseSheet"
```

---

### Task 4: `e2e/account.spec.ts` — обновить under-test текст

**Files:**
- Modify: `frontend-next/e2e/account.spec.ts`

**Interfaces:**
- Consumes: точные строки UI из Task 3: «Баланс» (одно вхождение), «Credits» (одно вхождение), `/кредитов/` (ДВА вхождения — карточка и Cell, поэтому `.first()` обязателен из-за Playwright strict mode). `mockTelegramWebApp` из `./mock-telegram` — без изменений (мокает ТОЛЬКО `window.Telegram.WebApp` с валидно подписанным initData; бэкенд НЕ мокается, `/api/me` идёт в реальный бэкенд).
- Produces: тест `account screen shows balance and credits`, прогоняемый в Task 5.

- [ ] **Step 1: Обновить тест**

Заменить всё содержимое `frontend-next/e2e/account.spec.ts` на:

```ts
// frontend-next/e2e/account.spec.ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});

test("account screen shows balance and credits", async ({ page }) => {
  await page.goto("/account");
  await expect(page.getByText("Баланс")).toBeVisible();
  await expect(page.getByText("Credits")).toBeVisible();
  await expect(page.getByText(/кредитов/).first()).toBeVisible();
});
```

(Отличия от спеки п.4: добавлен `.first()` к `getByText(/кредитов/)` — реализация Task 3 даёт два вхождения, спека сама предписывает подгонять тест под финальную копию; сохранены существующие `beforeEach`/`mockTelegramWebApp`, которых нет в сниппете спеки, но без них initData не подпишется и `/api/me` вернёт 401.)

- [ ] **Step 2: Typecheck по-прежнему зелёный (e2e входит в include tsconfig)**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: PASS, exit code 0.

- [ ] **Step 3: Коммит**

```bash
git add frontend-next/e2e/account.spec.ts
git commit -m "test(frontend): e2e account под кредитную карточку баланса"
```

---

### Task 5: Финальная верификация — чистый build + e2e с реальным бэкендом

**Files:**
- Никаких правок кода. Только запуск проверок.

**Interfaces:**
- Consumes: всё из Tasks 1–4.
- Produces: критерий готовности фазы.

- [ ] **Step 1: Чистая сборка с нуля**

Run (из `frontend-next/`): `npm run build`

Expected: PASS без TS-ошибок. Это обязательная часть; она НЕ требует бэкенда.

- [ ] **Step 2: Предусловия e2e (реальный бэкенд — Playwright его НЕ поднимает)**

`playwright.config.ts` через `webServer` автоматически поднимает ТОЛЬКО фронтенд (`npm run dev`, `http://localhost:3000`, `reuseExistingServer: !process.env.CI`). Бэкенд нужен вручную. Чек-лист:

1. Поднять бэкенд из корня репо (Postgres 16 + Redis должны быть доступны, как для бэкенд-фаз): `python -m uvicorn app.main:app --port 8000` с обычным `.env` проекта, при этом `FRONTEND_URL=http://localhost:3000` (иначе CORS: `app/main.py:53-58` разрешает только `settings.frontend_url`).
2. В `frontend-next/.env.local` должно быть `NEXT_PUBLIC_API_URL=http://localhost:8000` — иначе `client.ts:3` (`API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? ""`) пошлёт запросы на сам :3000, где нет `/api/*` (rewrites в `next.config.ts` отсутствуют).
3. Переменная окружения `TEST_BOT_TOKEN` при запуске Playwright обязана СОВПАДАТЬ с `BOT_TOKEN` бэкенда — `mock-telegram.ts` подписывает initData этим токеном, бэкенд валидирует той же HMAC-схемой; при несовпадении `/api/me` вернёт 401 и страница покажет «Не удалось загрузить профиль».
4. Пользователь `telegram_id=999999` (дефолт `mockTelegramWebApp`) создастся/найдётся на бэкенде при первом `/api/me` — отдельного сидинга не требуется.

Если в окружении исполнителя нет доступного Postgres/Redis/BOT_TOKEN — НЕ выдумывать route-моки (их нет в спеке): зафиксировать Step 1 как выполненный, а Step 3 отдать пользователю ручной инструкцией из этого чек-листа и явно сказать об этом в отчёте.

- [ ] **Step 3: Прогон e2e**

Run (из `frontend-next/`, PowerShell): `$env:TEST_BOT_TOKEN = "<BOT_TOKEN бэкенда>"; npm run test:e2e -- account.spec.ts`

Expected: `1 passed` — тест `account screen shows balance and credits`.

- [ ] **Step 4: Ручная smoke-проверка (опционально, если есть браузер)**

`npm run dev`, открыть `http://localhost:3000/account` с моком Telegram (или через реальный Mini App): карточка «Баланс» показывает `💎 N кредитов`, строки «Всего куплено»/«Всего потрачено» — числа из `/api/me`; при `total_credits_purchased = 0` виден баннер «💎 Купите первый пакет», и его кнопка «Выбрать пакет», как и «+» в секции Credits, открывает `CreditPurchaseSheet` со списком пакетов.

- [ ] **Step 5: Финальный статус**

Убедиться, что рабочее дерево чистое по файлам фазы (`git status` — нет незакоммиченных правок в `frontend-next/`), все 4 коммита задач на месте (`git log --oneline -4`). Фаза готова; экраны Chat/Trends/Tariffs/Referral/Settings и admin-панель остаются нерабочими против реального бэкенда до под-фаз 2–3 — это ожидаемо (спека, «известные ограничения»).
