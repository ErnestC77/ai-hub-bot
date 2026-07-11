# Frontend Integration Phase 4 — Tariffs → Credit Packages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Четвёртая под-фаза связывания `frontend-next/` с бэкендом credit-system-v2: мёртвый экран `/tariffs` (зовёт удалённые бэкендом `GET /api/tariffs` и `POST /api/payments/{stars,yookassa}/create`) удаляется целиком вместе со шторкой оплаты, e2e-спеком и четырьмя мёртвыми экспортами `client.ts`; кнопка «💳 Тарифы» на Home переводится с навигации на удаляемый маршрут на открытие уже рабочего `CreditPurchaseSheet` — тот же компонент, что на Account.

**Architecture:** Чисто фронтендовая и почти чисто субтрактивная фаза: `git rm` трёх файлов (`src/app/tariffs/page.tsx`, `src/components/tariffs/PaymentMethodSheet.tsx`, `e2e/tariffs.spec.ts`), вырезание `TariffOut` + `api.tariffs`/`api.createStarsPayment`/`api.createYookassaPayment` из `src/api/client.ts` (Task 1), затем три точечные правки `src/app/page.tsx` 1:1 по паттерну `account/page.tsx:14,19,91` (Task 2). Бэкенд не трогается вообще — обе нужные ручки (`/api/credits/packages`, `/api/payments/credits/*`) уже существуют и используются `CreditPurchaseSheet` на Account.

**Tech Stack:** Next.js 16.2.10 (App Router, typed routes НЕ включены) + React 19.2.4 + TypeScript 5.9 strict + Tailwind CSS 4 + Playwright 1.61. Бэкенд/pytest/Alembic в этой фазе не участвуют.

**Design spec (единственный источник истины):** `docs/superpowers/specs/2026-07-11-frontend-integration-phase4-tariffs-design.md`

## Global Constraints

- **Только `frontend-next/`.** Ни один файл вне `frontend-next/` не создаётся и не меняется. Никаких миграций, никаких правок `app/*`.
- **Гейты каждой задачи:** `npx tsc --noEmit` (быстрый) и `npm run build` (канонический) из `frontend-next/` — оба зелёные в конце ОБЕИХ задач. Ожидаемая сводка build — **11 роутов** (было 12: `/tariffs` пропадает из сборки).
- **Промежуточного красного typecheck (прецедент фаз 2–3) в этой фазе НЕТ:** typed routes в `next.config.ts` не включены, `useRouter().push` типизирован как `push(href: string, ...)` (проверено по `node_modules/next/dist/shared/lib/app-router-context.shared-runtime.d.ts`), поэтому удаление маршрута компиляцию Home не ломает. Единственная осознанная «дырка» промежуточного состояния — ПОВЕДЕНЧЕСКАЯ: после Task 1 кнопка «💳 Тарифы» на Home ведёт в рантайме на несуществующий `/tariffs` (404) до Task 2. Это отражено в commit-сообщении Task 1.
- **e2e: новых моков НЕ добавлять** (спека, раздел «Тестирование»). Жёсткий e2e-гейт — только `generate-image.spec.ts` + `generate-video.spec.ts` (самодостаточные `page.route()`/DOM-only, прецедент фазы 3). Остальной сьют (`account`/`chat`/`home`/`referral`/`settings`/`trends`/`admin-*`) заблокирован предсуществующим багом мока Telegram (`[[ai_hub_bot_e2e_mock_bug]]`: реальный SDK затирает мок initData) — его падения НЕ чинить и НЕ считать регрессией этой фазы. Критерий готовности фазы — зелёная сборка, как в под-фазах 1–2 (спека).
- **НЕ трогать:**
  - `frontend-next/src/components/account/CreditPurchaseSheet.tsx` — используется как есть, props ровно `{ onClose: () => void }` (`CreditPurchaseSheet.tsx:17-19`);
  - `CreatePaymentResponse` в `client.ts` — остаётся, его используют рабочие `createStarsCreditPayment`/`createYookassaCreditPayment`;
  - `PaymentStatusOut`/`api.paymentStatus` — мёртвый код, но ВНЕ скоупа (спека: отдельная, не связанная с тарифами уборка);
  - `AdminTariffOut`/`adminApi.tariffsAdmin`/`adminApi.updateTariff`/`src/screens/admin/AdminTariffs.tsx`/`e2e/admin-tariffs.spec.ts` — админ-панель, отдельная будущая под-фаза;
  - `useRouter` в `src/app/page.tsx` — остаётся (нужен для `/generate-image`, `/referral`, `/admin`);
  - `e2e/mock-telegram.ts`, `playwright.config.ts`.
- **Grep-инвариант конца фазы:** `git grep -nE "TariffOut|createStarsPayment|createYookassaPayment|/tariffs" -- frontend-next/src frontend-next/e2e` находит ТОЛЬКО `AdminTariffOut`/`/api/admin/tariffs`-совпадения (в `client.ts` и `src/screens/admin/AdminTariffs.tsx`) — они вне скоупа.
- Номера строк актуальны на master `87cced4` (2026-07-11). Внутри задачи более ранние правки сдвигают последующие строки — ориентироваться на якорные сниппеты.
- **Критерий готовности фазы:** `npx tsc --noEmit` зелёный; `npm run build` зелёный с 11 роутами (без `/tariffs`); `npx playwright test generate-image.spec.ts generate-video.spec.ts` — 2 passed; полный прогон сьюта не показывает новых (сверх предсуществующе-заблокированных) падений; ручной smoke Home → шторка кредитов передан пользователю с инструкцией (единственная часть, требующая реального бэкенда).

## File Structure

| Файл | Действие |
|---|---|
| `frontend-next/src/app/tariffs/page.tsx` | УДАЛИТЬ — Task 1 |
| `frontend-next/src/components/tariffs/PaymentMethodSheet.tsx` | УДАЛИТЬ — Task 1 |
| `frontend-next/e2e/tariffs.spec.ts` | УДАЛИТЬ — Task 1 |
| `frontend-next/src/api/client.ts:96-108,181-191` | минус `TariffOut` и `api.tariffs`/`createStarsPayment`/`createYookassaPayment` — Task 1 |
| `frontend-next/src/app/page.tsx:12,23,64,75` | импорт + состояние + ретаргет кнопки + рендер шторки — Task 2 |
| — | финальная верификация: tsc + build (11 роутов) + playwright + ручной smoke — Task 2 |

---

### Task 1: Удаление мёртвого `/tariffs`-слоя — три файла + четыре экспорта `client.ts`

**Files:**
- Delete: `frontend-next/src/app/tariffs/page.tsx`
- Delete: `frontend-next/src/components/tariffs/PaymentMethodSheet.tsx`
- Delete: `frontend-next/e2e/tariffs.spec.ts`
- Modify: `frontend-next/src/api/client.ts:96-108` (интерфейс `TariffOut`), `:181-191` (три метода `api`)

**Interfaces:**
- Consumes: ничего из других задач — стартует прямо с master `87cced4`.
- Produces (Task 2 полагается на это): `client.ts` БЕЗ `TariffOut`/`api.tariffs`/`api.createStarsPayment`/`api.createYookassaPayment`, при этом `CreatePaymentResponse`, `api.creditPackages`, `api.createStarsCreditPayment`, `api.createYookassaCreditPayment`, `api.paymentStatus` — на месте без изменений; маршрута `/tariffs` в сборке больше нет (11 роутов); дерево компилируется зелёным. Кнопка «💳 Тарифы» на Home всё ещё делает `router.push("/tariffs")` — это ЕДИНСТВЕННОЕ оставшееся упоминание `/tariffs` вне admin-скоупа, Task 2 его убирает.

- [ ] **Step 1: Удалить три мёртвых файла**

Из корня репо:

```bash
git rm frontend-next/src/app/tariffs/page.tsx
git rm frontend-next/src/components/tariffs/PaymentMethodSheet.tsx
git rm frontend-next/e2e/tariffs.spec.ts
```

Обоснование каждого (спека): страница зовёт `api.tariffs()` → `GET /api/tariffs` (роут удалён бэкендом, 404); `PaymentMethodSheet.tsx` — единственный потребитель — эта страница, а сам он зовёт `api.createStarsPayment`/`api.createYookassaPayment` → несуществующие `/api/payments/{stars,yookassa}/create`; `tariffs.spec.ts` делал `page.goto("/tariffs")` и проверял текст на маршруте, которого после этой фазы нет. Директории `src/app/tariffs/` и `src/components/tariffs/` после `git rm` остаются пустыми и исчезают сами (git не хранит пустых директорий); если на диске остался пустой хвост — можно удалить, но это не обязательно.

- [ ] **Step 2: `client.ts` — удалить интерфейс `TariffOut`**

Текущий код (`frontend-next/src/api/client.ts`, строки 90–114 — якорь с соседями):

```ts
export interface ReferralOut {
  link: string;
  referred_count: number;
  bonus_count: number;
}

export interface TariffOut {
  code: string;
  name: string;
  description: string | null;
  price_rub: number;
  price_stars: number;
  period_days: number;
  fast_limit: number;
  medium_limit: number;
  premium_limit: number;
  image_limit: number;
  is_current: boolean;
}

export interface CreatePaymentResponse {
  payment_id: number;
  invoice_link?: string | null;
  confirmation_url?: string | null;
}
```

Удалить целиком блок `export interface TariffOut { ... }` (строки 96–108) вместе с одной пустой строкой, чтобы получилось:

```ts
export interface ReferralOut {
  link: string;
  referred_count: number;
  bonus_count: number;
}

export interface CreatePaymentResponse {
  payment_id: number;
  invoice_link?: string | null;
  confirmation_url?: string | null;
}
```

`CreatePaymentResponse` НЕ трогать — его используют `createStarsCreditPayment`/`createYookassaCreditPayment`. НЕ трогать и `AdminTariffOut` ниже по файлу (строка 250 на `87cced4`) — админ-скоуп.

- [ ] **Step 3: `client.ts` — удалить три мёртвых метода из объекта `api`**

Текущий код (строки 179–193 после Step 2 сдвинулись на 14 вверх — искать по якорям `referral:` и `paymentStatus:`):

```ts
  banners: () => request<BannerOut[]>("/api/banners"),
  referral: () => request<ReferralOut>("/api/referral/me"),
  tariffs: () => request<TariffOut[]>("/api/tariffs"),
  createStarsPayment: (tariffCode: string) =>
    request<CreatePaymentResponse>("/api/payments/stars/create", {
      method: "POST",
      body: JSON.stringify({ tariff_code: tariffCode }),
    }),
  createYookassaPayment: (tariffCode: string) =>
    request<CreatePaymentResponse>("/api/payments/yookassa/create", {
      method: "POST",
      body: JSON.stringify({ tariff_code: tariffCode }),
    }),
  paymentStatus: (paymentId: number) => request<PaymentStatusOut>(`/api/payments/${paymentId}/status`),
```

Удалить ровно 11 строк от `tariffs:` до закрывающей `}),` метода `createYookassaPayment` включительно, чтобы получилось:

```ts
  banners: () => request<BannerOut[]>("/api/banners"),
  referral: () => request<ReferralOut>("/api/referral/me"),
  paymentStatus: (paymentId: number) => request<PaymentStatusOut>(`/api/payments/${paymentId}/status`),
```

`paymentStatus` остаётся (вне скоупа, спека), `creditPackages`/`createStarsCreditPayment`/`createYookassaCreditPayment` ниже — без изменений. В `adminApi` ничего не трогать (`tariffsAdmin`/`updateTariff` — админ-скоуп).

- [ ] **Step 4: Grep-проверка — потребителей удалённого не осталось**

Run (из корня репо):

```bash
git grep -nE "TariffOut|createStarsPayment|createYookassaPayment|api\.tariffs\(" -- frontend-next/src frontend-next/e2e
```

Expected: ВСЕ совпадения — только `AdminTariffOut` (в `frontend-next/src/api/client.ts` — интерфейс и `tariffsAdmin`/`updateTariff`, и в `frontend-next/src/screens/admin/AdminTariffs.tsx:5,15,23,78`). Ни одного «голого» `TariffOut`, ни одного `createStarsPayment`/`createYookassaPayment`/`api.tariffs(`. Если нашлось что-то ещё — СТОП, разобрать расхождение до продолжения.

- [ ] **Step 5: Typecheck — зелёный (красного промежутка в этой фазе нет)**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: PASS, exit code 0, пустой вывод. Почему зелёный, хотя Home ещё ссылается на удалённый маршрут: typed routes в `next.config.ts` не включены, `router.push` принимает произвольную `string` — строка `"/tariffs"` компилируется. (Шум от stale-типов в `.next/` лечится `Remove-Item -Recurse -Force .next`.)

- [ ] **Step 6: Канонический гейт — сборка на 11 роутов**

Run (из `frontend-next/`): `npm run build`

Expected: PASS — `Compiled successfully`, в сводке роутов **11 строк**: `/`, `/_not-found`, `/account`, `/admin`, `/chat`, `/generate-image`, `/generate-video`, `/login-failed`, `/referral`, `/settings`, `/trends`. Строки `/tariffs` в сводке НЕТ.

- [ ] **Step 7: Commit**

```bash
git add frontend-next/src/api/client.ts
git commit -m "refactor(frontend): удалён мёртвый экран /tariffs -- страница, PaymentMethodSheet, e2e-спек и TariffOut/api.tariffs/createStars,YookassaPayment из client.ts (кнопка на Home временно ведёт в 404, чинится следующим коммитом)"
```

(`git rm` из Step 1 уже в индексе — коммит заберёт и удаления; сборка зелёная, известная дырка — только рантайм-404 кнопки, зафиксирована в сообщении.)

---

### Task 2: Home — кнопка «💳 Тарифы» открывает `CreditPurchaseSheet` + финальная верификация фазы

**Files:**
- Modify: `frontend-next/src/app/page.tsx:12,23,64,75` (номера на `87cced4`; файл этой фазой ранее не менялся, сдвигов нет)

**Interfaces:**
- Consumes: `client.ts` после Task 1 (без `TariffOut`/трёх методов); `CreditPurchaseSheet` — default-экспорт из `@/components/account/CreditPurchaseSheet`, props ровно `{ onClose: () => void }`, открытие — условный рендер (компонент сам рендерит `<Sheet open ...>`); референс-паттерн — `frontend-next/src/app/account/page.tsx:14` (импорт), `:19` (состояние), `:91` (рендер) — реплицируется 1:1.
- Produces: критерий готовности фазы — Home без единого упоминания `/tariffs`, шторка покупки кредитов открывается с Home тем же компонентом, что и с Account; зелёные tsc/build (11 роутов); e2e-гейт `2 passed`.

- [ ] **Step 1: Добавить импорт `CreditPurchaseSheet`**

Текущий код (`frontend-next/src/app/page.tsx`, строки 9–12):

```ts
import { api, type BannerOut } from "@/api/client";
import HeroCarousel from "@/components/HeroCarousel";
import ImageStack from "@/components/ImageStack";
import { useMe } from "@/context/MeContext";
```

заменить на (новый импорт последним, как в `account/page.tsx:14`):

```ts
import { api, type BannerOut } from "@/api/client";
import HeroCarousel from "@/components/HeroCarousel";
import ImageStack from "@/components/ImageStack";
import { useMe } from "@/context/MeContext";
import CreditPurchaseSheet from "@/components/account/CreditPurchaseSheet";
```

- [ ] **Step 2: Добавить состояние `buyingCredits`**

Текущий код (строка 23; `useState` уже импортирован на строке 3):

```ts
  const [banners, setBanners] = useState<BannerOut[] | null>(null);
```

заменить на:

```ts
  const [banners, setBanners] = useState<BannerOut[] | null>(null);
  const [buyingCredits, setBuyingCredits] = useState(false);
```

- [ ] **Step 3: Ретаргет кнопки «💳 Тарифы»**

Текущий код (строки 64–66):

```tsx
        <Button size="s" mode="bezeled" onClick={() => router.push("/tariffs")}>
          💳 Тарифы
        </Button>
```

заменить на (текст кнопки НЕ меняется):

```tsx
        <Button size="s" mode="bezeled" onClick={() => setBuyingCredits(true)}>
          💳 Тарифы
        </Button>
```

`useRouter` (строка 22) остаётся — им пользуются `/generate-image`, `/referral`, `/admin`.

- [ ] **Step 4: Рендер шторки последним элементом внутри корневого `<div className="pb-6">`**

Текущий код (конец `return`, строки 70–77):

```tsx
        {me.is_admin && (
          <Button size="s" mode="outline" onClick={() => router.push("/admin")}>
            🛠 Админка
          </Button>
        )}
      </div>
    </div>
  );
```

заменить на (спека: после блока `<div className="flex flex-wrap gap-2.5 px-4">` с кнопками, тот же уровень вложенности, что и остальной контент — `Sheet` рисует оверлей fixed-позиционированием, физическое место в дереве на визуальный слой не влияет, важна лишь синтаксическая позиция внутри `return (...)`):

```tsx
        {me.is_admin && (
          <Button size="s" mode="outline" onClick={() => router.push("/admin")}>
            🛠 Админка
          </Button>
        )}
      </div>

      {buyingCredits && <CreditPurchaseSheet onClose={() => setBuyingCredits(false)} />}
    </div>
  );
```

- [ ] **Step 5: Typecheck и grep-инвариант**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: PASS, exit code 0.

Run (из корня репо):

```bash
git grep -n "/tariffs" -- frontend-next/src frontend-next/e2e
```

Expected: ровно два совпадения, оба в `frontend-next/src/api/client.ts` — `"/api/admin/tariffs"` (`tariffsAdmin`) и `` `/api/admin/tariffs/${code}` `` (`updateTariff`), оба админ-скоуп (проверено grep'ом на `87cced4`: других вхождений подстроки `/tariffs` в `src/`+`e2e/` после удалений Task 1 и ретаргета кнопки не остаётся). «Пользовательского» маршрута `/tariffs` не осталось нигде.

- [ ] **Step 6: Канонический гейт — чистая сборка с нуля**

Run (из `frontend-next/`, PowerShell): `Remove-Item -Recurse -Force .next; npm run build`

Expected: PASS — `Compiled successfully`, ровно **11 роутов** (`/`, `/_not-found`, `/account`, `/admin`, `/chat`, `/generate-image`, `/generate-video`, `/login-failed`, `/referral`, `/settings`, `/trends`). Бэкенд не требуется.

- [ ] **Step 7: e2e — жёсткий гейт (2 самодостаточных спека) + полный прогон без новых регрессий**

Run (из `frontend-next/`):

```bash
npx playwright test generate-image.spec.ts generate-video.spec.ts
```

Expected: `2 passed` (самодостаточные `page.route()`/DOM-only тесты фазы 3, бэкенд/докер не нужны; Playwright сам поднимает `npm run dev` через `webServer`, порт 3000 должен быть свободен либо занят нашим dev-сервером).

Затем полный прогон для проверки отсутствия регрессий в остальном сьюте:

```bash
npx playwright test
```

Expected:
- `tariffs.spec.ts` ОТСУТСТВУЕТ в списке выполняемых файлов (удалён в Task 1);
- `generate-image.spec.ts` и `generate-video.spec.ts` — passed;
- падать могут ТОЛЬКО предсуществующе-заблокированные спеки — `account`, `chat`, `home`, `referral`, `settings`, `trends`, `admin-banners`, `admin-models`, `admin-panel`, `admin-payments`, `admin-stats`, `admin-tariffs`, `admin-users` (баг мока Telegram `[[ai_hub_bot_e2e_mock_bug]]`; чинить их — вне скоупа);
- ни в одном сообщении об ошибке нет упоминаний `TariffOut`, `CreditPurchaseSheet` или маршрута `/tariffs` (кроме, возможно, `admin-tariffs.spec.ts` — админ-скоуп). Появление упавшего `generate-*` или ошибок про удалённые символы — регрессия этой фазы, СТОП, НЕ помечать шаг выполненным.

- [ ] **Step 8: Commit**

```bash
git add frontend-next/src/app/page.tsx
git commit -m "feat(frontend): кнопка Тарифы на Home открывает CreditPurchaseSheet (паттерн Account) вместо удалённого /tariffs"
```

- [ ] **Step 9: Финальный статус + ручной smoke (передать пользователю; единственная часть с реальным бэкендом)**

`git status` — чистое дерево по файлам фазы; `git log --oneline -2` — оба коммита задач на месте.

Инструкция ручного smoke-теста (предусловия те же, что в фазах 1–3: бэкенд `python -m uvicorn app.main:app --port 8000` с Postgres 16 + Redis и `FRONTEND_URL=http://localhost:3000`; в `frontend-next/.env.local` — `NEXT_PUBLIC_API_URL=http://localhost:8000`; затем `npm run dev`):

1. Открыть Home, нажать «💳 Тарифы» — открывается ТА ЖЕ шторка «Купить кредиты», что и с Account: список пакетов из `/api/credits/packages` → выбор способа оплаты (⭐ Stars / 💳 ЮKassa) → поллинг баланса.
2. Закрыть шторку свайпом/крестиком — Home под шторкой не сломан, кнопки работают.
3. Прямой заход на `http://localhost:3000/tariffs` — 404 (маршрут удалён, единственная точка входа была кнопка на Home).

Известные ограничения после этой фазы (спека, зафиксировано осознанно): `PaymentStatusOut`/`api.paymentStatus` остаются мёртвым кодом в `client.ts` (отдельная возможная уборка); admin-панель (включая `AdminTariffs.tsx`, всё ещё зовущую старые `/api/admin/tariffs`) и визуальный редизайн — отдельные будущие направления; нерассмотренные экраны — Trends, Referral, Settings.
