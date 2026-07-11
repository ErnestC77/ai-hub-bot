# Frontend Integration — Phase 2: Chat screen

## Контекст

Продолжение проекта связывания `frontend-next/` с переписанным бэкендом
credit-system-v2 (см. [`phase1-account-api-design.md`](2026-07-11-frontend-integration-phase1-account-api-design.md),
уже смёржена — `MeOut` приведён к кредитной модели, экран Account рабочий).
Пользователь выбрал экран **Chat** следующим.

`frontend-next/src/app/chat/page.tsx` + `src/components/chat/ModelPicker.tsx`
всё ещё описывают старую схему: `ModelOut.category/is_premium/credit_cost`
(бэкенд `GET /api/models` теперь отдаёт `code/display_name/tier/min_credits/
recommended_credits`, только текстовые модели), `ChatResponse.input_tokens/
output_tokens` (бэкенд `POST /api/chat` теперь отдаёт `answer/charged_credits/
balance_after`).

Отдельно обнаружена архитектурная проблема в общем API-слое: `request()` в
`client.ts` на HTTP-ошибке достаёт только `detail.detail` из тела ответа.
`POST /api/chat`'s confirmation-gate (`app/api/routes/chat.py:94-97`) на 409
возвращает **ровно** `{"estimated_credits": N}`, без ключа `detail` — сейчас
это число теряется, `ApiError.message` падает на `res.statusText` (обычно
просто "Conflict"), и клиент не может отличить «нужно подтверждение» от любой
другой 409-ошибки (`RequestInProgressError`, которая ДЕЙСТВИТЕЛЬНО возвращает
`detail`). Тот же паттерн будет и у `POST /api/generate` (image/video,
будущие под-фазы) — решается один раз здесь.

## Scope

**В скоупе:**
- `frontend-next/src/api/client.ts`: новый экспортируемый класс
  `ConfirmationRequiredError`, распознаваемый внутри общего `request()`;
  исправление `ModelOut`/`ChatResponse`; `api.chat()` получает третий
  параметр `confirm`.
- `frontend-next/src/components/chat/ModelPicker.tsx`: группировка по `tier`.
- `frontend-next/src/app/chat/page.tsx`: подпись списания под ответом,
  обработка `ConfirmationRequiredError` баннером подтверждения.

**Вне скоупа:**
- Остальные потребители `ModelOut`/`api.models()` — в кодовой базе сейчас
  только `ModelPicker.tsx` (проверено, единственный импортёр).
- `ToolOut`/`api.tools()` — используется экраном Trends, не Chat; не трогать.
- `/api/generate` (image/video) сам по себе — только инфраструктурная
  подготовка (`ConfirmationRequiredError`) для будущей под-фазы, использующей
  его повторно; сама точка входа `api.generate()` в этой спеке не меняется.
- Admin-панель, визуальный редизайн — как и раньше, отдельные направления.

## Изменения

### 1. `client.ts` — `ConfirmationRequiredError` в `request()`

```ts
export class ConfirmationRequiredError extends Error {
  estimatedCredits: number;
  constructor(estimatedCredits: number) {
    super(`confirmation required: ${estimatedCredits} credits`);
    this.estimatedCredits = estimatedCredits;
  }
}
```

В `request()`: при `!res.ok` сначала распарсить тело как `Record<string, unknown>`
(тем же `.catch(() => ({}))`, что и сейчас); если `res.status === 409` и
`typeof body.estimated_credits === "number"` — кинуть
`ConfirmationRequiredError(body.estimated_credits)`; иначе — прежнее
поведение (`ApiError` из `body.detail ?? res.statusText`). Другие 409
(`RequestInProgressError`, у которой есть `detail`) продолжают идти обычным
`ApiError`-путём — `estimated_credits` в их теле нет.

### 2. `client.ts` — `ModelOut`/`ChatResponse`/`api.chat`

```ts
export interface ModelOut {
  code: string;
  display_name: string;
  tier: "economy" | "standard" | "premium" | "pro" | "ultra";
  min_credits: number;
  recommended_credits: number;
}

export interface ChatResponse {
  answer: string;
  charged_credits: number;
  balance_after: number;
}
```

`api.chat`:
```ts
chat: (modelCode: string, prompt: string, confirm = false) =>
  request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ model_code: modelCode, prompt, confirm }),
  }),
```

`ModelCategory`/`CategoryLimitOut`-типа `category` больше нет на `ModelOut`
(бэкенд `/api/models` уже фильтрует по `category=text` сам, клиенту это поле
не нужно — как и `provider_model_id`, оно и раньше не отдавалось). Ничего
больше в `client.ts` не менять — `ToolOut`, `adminApi`, `TariffOut` и т.д.
вне скоупа.

### 3. `ModelPicker.tsx` — группировка по `tier`

```ts
const TIER_LABEL: Record<string, string> = {
  economy: "Эконом",
  standard: "Стандарт",
  premium: "Премиум",
  pro: "Pro",
  ultra: "Ultra",
};
const STARRED_TIERS = new Set(["pro", "ultra"]);
```

`grouped` строится по `model.tier` вместо `model.category`; порядок секций —
`Object.entries` в порядке уже отсортированного бэкендом списка (`sort_order`
на бэкенде уже упорядочивает эконом→ultra, второй сортировки на фронте не
требуется). `after={STARRED_TIERS.has(model.tier) ? "⭐" : undefined}` вместо
`model.is_premium`. `model_code` → `code` во всех обращениях (`key`, `onSelect`).

### 4. `chat/page.tsx` — подпись списания + баннер подтверждения

`ChatMessage` (assistant) получает опциональные `chargedCredits`/`balanceAfter`:
```ts
interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
  chargedCredits?: number;
  balanceAfter?: number;
}
```
Под assistant-бабблом (когда оба поля заданы) — мелкая подпись:
`Списано: {chargedCredits} • Баланс: {balanceAfter}`.

Новое состояние: `pendingConfirmation: { prompt: string; modelCode: string;
estimatedCredits: number } | null`. `send()` принимает необязательный
`confirm` (по умолчанию `false`); при `confirm=false` предупреждение НЕ
клонирует уже добавленный user-бабл повторно — `pendingConfirmation` просто
хранит, что переотправить.

Поток:
1. Пользователь пишет и жмёт «Отправить» → `send()` без `confirm` (первая
   попытка), user-бабл добавляется как сейчас, `prompt` очищается.
2. Если `api.chat(...)` бросает `ConfirmationRequiredError` — user-бабл
   остаётся в истории (это НЕ ошибка, вопрос реально будет отправлен после
   подтверждения), `sending=false`, `pendingConfirmation` заполняется
   `{prompt: question, modelCode: model.model_code /* уже переименовано в
   .code, см. п.3 */, estimatedCredits: err.estimatedCredits}`. Никакого
   error-бабла не добавляется.
3. Рендер: если `pendingConfirmation` — баннер над полем ввода (стиль как у
   существующих карточек-стёкол): «Примерная стоимость: N кредитов.
   Продолжить?» + кнопки «Отправить» (→ `send(true)` с сохранёнными
   `prompt`/`modelCode` из `pendingConfirmation`, затем сброс
   `pendingConfirmation`) / «Отмена» (сброс `pendingConfirmation` без
   отправки; user-бабл в истории остаётся как есть — пользователь видит
   свой вопрос, на который решил не платить).
4. Остальные ошибки (`ApiError` — 402/403/429/502/404/409-in-progress) —
   без изменений, `err.message` уже содержит готовую русскую строку с
   бэкенда, экран просто показывает error-бабл как сейчас.

## Тестирование

- Нет unit-тестов для React-компонентов в этом проекте (проверено — только
  Playwright e2e). Проверка — `npx tsc --noEmit` + `npm run build` (как в
  фазе 1), плюс ручной smoke-тест: открыть `/chat` (мок Telegram или реальный
  бэкенд), выбрать модель из каждого tier, отправить дешёвый запрос (проверить
  подпись списания), отправить запрос дороже порога подтверждения (проверить
  баннер и обе кнопки).
- `frontend-next/e2e/chat.spec.ts` уже существует и проверяет только
  `getByPlaceholder("Сообщение...")` — этот текст в разметке не меняется
  этой спекой, так что файл не требует правок. Прогон e2e по-прежнему
  блокирован предсуществующим багом мока Telegram
  ([[ai_hub_bot_e2e_mock_bug]] в памяти проекта) — не в скоупе чинить здесь.

## Известные ограничения после этой фазы

- Остальные экраны (Trends, Tariffs, Referral, Settings, generate-image/video)
  и admin-панель остаются на старом API до своих под-фаз.
- `ConfirmationRequiredError` вводится в `client.ts` как инфраструктура для
  будущего generate-flow (image/video), но сам `api.generate()`/экраны
  генерации в этой спеке не переписываются.
