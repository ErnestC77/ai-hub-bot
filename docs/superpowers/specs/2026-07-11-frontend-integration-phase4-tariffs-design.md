# Frontend Integration — Phase 4: Tariffs → Credit Packages

## Контекст

Продолжение проекта связывания `frontend-next/` с переписанным бэкендом
credit-system-v2 (см. `phase1-account-api-design.md`, `phase2-chat-design.md`,
`phase3-generate-design.md` — все смёржены). Пользователь выбрал экран
**Tariffs** следующим.

Концепция «тарифов» полностью удалена бэкендом ещё в фазах 1–4 credit-system-v2
rebuild — заменена кредитными пакетами (`CreditPackage`, `/api/credits/packages`,
`/api/payments/credits/{stars,yookassa,crypto}/create`). Backend-роута
`/api/tariffs` больше не существует (файл `app/api/routes/tariffs.py` удалён,
остался только протухший `__pycache__`; `app/api/routes/payments.py` содержит
исключительно `/credits/*`-эндпойнты — см. полный листинг файла).

`frontend-next/src/app/tariffs/page.tsx` и
`frontend-next/src/components/tariffs/PaymentMethodSheet.tsx` всё ещё зовут
`api.tariffs()` → `GET /api/tariffs` (404) и `api.createStarsPayment`/
`api.createYookassaPayment` → несуществующие `/api/payments/{stars,yookassa}/create`
(в `payments.py` есть только их `/credits/...`-варианты). Экран открывается
кнопкой «💳 Тарифы» на Home (`src/app/page.tsx:64`) — единственная точка входа
в приложении, никакой другой навигации на `/tariffs` нет (проверено grep'ом).

При этом на экране Account (фаза 1) уже работает
`frontend-next/src/components/account/CreditPurchaseSheet.tsx` — полный рабочий
цикл «выбор пакета → способ оплаты → поллинг баланса → успех/ошибка» поверх
именно `/api/credits/packages` + `/api/payments/credits/*`. Дублировать эту
логику под второй, отдельно поддерживаемый компонент нет смысла — решение
(подтверждено пользователем): удалить страницу `/tariffs` и её шторку, кнопку
на Home перевести на открытие `CreditPurchaseSheet` — тот же компонент, что и
на Account, просто с другой точки входа.

## Scope

**В скоупе:**
- Удалить `frontend-next/src/app/tariffs/page.tsx` (route `/tariffs` целиком
  исчезает — в Next.js App Router удаление `page.tsx` = удаление маршрута).
- Удалить `frontend-next/src/components/tariffs/PaymentMethodSheet.tsx`
  (единственный потребитель — удаляемая страница).
- Удалить `frontend-next/e2e/tariffs.spec.ts` (проверял текст на теперь
  несуществующем маршруте).
- `frontend-next/src/api/client.ts`: удалить `TariffOut`, `api.tariffs`,
  `api.createStarsPayment`, `api.createYookassaPayment` — используются
  только двумя удаляемыми файлами (проверено grep'ом по всему `src/`).
- `frontend-next/src/app/page.tsx`: кнопка «💳 Тарифы» открывает
  `CreditPurchaseSheet` вместо `router.push("/tariffs")`.

**Вне скоупа:**
- Бэкенд не трогается вообще — обе нужные ручки (`/api/credits/packages`,
  `/api/payments/credits/*`) уже существуют и работают (используются
  `CreditPurchaseSheet` на Account).
- `PaymentStatusOut`/`api.paymentStatus` в `client.ts` — не используются
  нигде в кодовой базе (проверено grep'ом), но это отдельный,
  не связанный с тарифами мёртвый код; не удаляется в этой спеке.
- `AdminTariffOut`/`adminApi.tariffsAdmin`/`adminApi.updateTariff`/
  `src/screens/admin/AdminTariffs.tsx`/`e2e/admin-tariffs.spec.ts` — админ-панель,
  отдельная будущая под-фаза, не трогается.
- `CreditPurchaseSheet.tsx` сам по себе — уже рабочий, не меняется.
- Остальные нерассмотренные экраны (Trends, Referral, Settings) и визуальный
  редизайн — как и раньше, отдельные направления.

## Изменения

### 1. Удаление мёртвых файлов

```bash
git rm frontend-next/src/app/tariffs/page.tsx
git rm frontend-next/src/components/tariffs/PaymentMethodSheet.tsx
git rm frontend-next/e2e/tariffs.spec.ts
```

### 2. `client.ts` — удалить `TariffOut` и три мёртвых метода `api`

Удалить целиком (строки указаны по состоянию клиента на момент спеки, могут
сместиться после мержа фазы 3 — искать по содержимому):

```ts
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
```

и из объекта `api`:

```ts
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
```

`CreatePaymentResponse` остаётся — используется и `createStarsCreditPayment`/
`createYookassaCreditPayment` (рабочие, не трогаются).

### 3. `page.tsx` (Home) — кнопка «Тарифы» открывает `CreditPurchaseSheet`

Паттерн 1:1 с `account/page.tsx:14,19,91` (тот же компонент, тот же способ
открытия):

Добавить импорт и состояние:
```ts
import CreditPurchaseSheet from "@/components/account/CreditPurchaseSheet";
```
```ts
const [buyingCredits, setBuyingCredits] = useState(false);
```

Заменить:
```tsx
<Button size="s" mode="bezeled" onClick={() => router.push("/tariffs")}>
  💳 Тарифы
</Button>
```
на:
```tsx
<Button size="s" mode="bezeled" onClick={() => setBuyingCredits(true)}>
  💳 Тарифы
</Button>
```

Добавить рендер шторки как последний элемент ВНУТРИ корневого
`<div className="pb-6">`, после блока `<div className="flex flex-wrap gap-2.5 px-4">`
с кнопками (тот же уровень вложенности, что и остальной контент — `Sheet`
рендерит свой оверлей через портал/fixed-позиционирование, так что физическое
место в дереве не влияет на визуальный слой, важно лишь что вызов синтаксически
внутри `return (...)`):
```tsx
{buyingCredits && <CreditPurchaseSheet onClose={() => setBuyingCredits(false)} />}
```

`useRouter` в файле остаётся — используется для `/generate-image`, `/referral`,
`/admin`, не убирается.

## Тестирование

- Нет unit-тестов для React-компонентов в проекте (только Playwright e2e) —
  проверка через `npx tsc --noEmit` + `npm run build` (ожидается 11 роутов
  вместо 12 — `/tariffs` пропадает из сборки).
- `frontend-next/e2e/tariffs.spec.ts` удаляется (см. п.1) — тестировал текст
  на несуществующем после этой фазы маршруте.
- `frontend-next/e2e/home.spec.ts` не проверяет кнопку «Тарифы» сейчас и не
  требует правок; как и `account.spec.ts`/`chat.spec.ts`, он блокирован
  предсуществующим багом мока Telegram для реального бэкенда
  ([[ai_hub_bot_e2e_mock_bug]]) — новых сетевых моков эта фаза не добавляет
  (в отличие от фазы 3, где `page.route()`-моки позволяли реальный прогон).
  Критерий готовности — зелёная сборка, как в под-фазах 1–2.
- Ручной smoke-тест (если поднимается реальный бэкенд): открыть Home, нажать
  «💳 Тарифы», убедиться что открывается та же шторка, что и с Account (выбор
  пакета → способ оплаты → поллинг), закрыть — Home под шторкой не сломан.

## Известные ограничения после этой фазы

- `PaymentStatusOut`/`api.paymentStatus` остаются мёртвым кодом в `client.ts`
  (не в скоупе — не связаны с тарифами, отдельная возможная уборка).
- Admin-панель (включая `AdminTariffs.tsx`, всё ещё зовущую старые
  `/api/admin/tariffs`-эндпойнты) и визуальный редизайн — отдельные будущие
  направления, как и раньше.
- Остальные нерассмотренные экраны: Trends, Referral, Settings.
