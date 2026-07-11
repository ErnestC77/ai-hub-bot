# Frontend Integration Phase 2 — Chat Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вторая под-фаза связывания `frontend-next/` с бэкендом credit-system-v2: экран Chat переезжает на реальные контракты `GET /api/models` (`code/tier/min_credits/recommended_credits`) и `POST /api/chat` (`answer/charged_credits/balance_after`), а общий `request()` в `client.ts` получает `ConfirmationRequiredError` — распознавание confirmation-gate 409 (`{"estimated_credits": N}` без `detail`), с UI-баннером подтверждения в чате.

**Architecture:** Точечная правка API-слоя (`ConfirmationRequiredError` + ветка в `request()`, новые `ModelOut`/`ChatResponse`, `api.chat` с `confirm`), компилируемые заглушки в `generate-image/page.tsx`/`generate-video/page.tsx` (внеплановые, но реальные потребители старого `ModelOut` — прецедент `PaymentMethodSheet` из фазы 1), рерайт `ModelPicker.tsx` на группировку по `tier`, рерайт `chat/page.tsx` — подпись списания под ответом + баннер подтверждения над полем ввода в том же стеклянном стиле, что карточка «Баланс» на Account.

**Tech Stack:** Next.js 16.2.10 (App Router) + React 19.2.4 + TypeScript 5 strict + Tailwind CSS 4 + Playwright 1.61. Бэкенд (не меняется в этой фазе): FastAPI, `POST /api/chat` + `GET /api/models` → `app/api/routes/chat.py:30-77`.

**Design spec (единственный источник истины):** `docs/superpowers/specs/2026-07-11-frontend-integration-phase2-chat-design.md`

## Global Constraints

- **Рабочая директория всех npm-команд — `frontend-next/`** (из корня репо: `cd frontend-next`). Git-команды — из корня репо.
- **Здесь нет pytest.** Проверки этой фазы: быстрая — `npx tsc --noEmit` (typescript в devDependencies, tsconfig strict), канонический гейт — `npm run build` (Next.js гоняет typecheck в составе сборки; отдельного `typecheck`-скрипта в `package.json` нет). Ожидаемый итог сборки — **12 роутов** (11 `page.tsx` + `/_not-found`), как в фазе 1.
- **Задачи 1–4 — один атомарный typecheck-юнит.** После Task 1, 2 и 3 `npx tsc --noEmit` ОЖИДАЕМО красный (это и есть «падающий тест» фазы), с сужающимся списком файлов-ошибок; зелёным он обязан стать ровно в конце Task 4. Промежуточные коммиты задач 1–3 помечаются `wip(frontend)` — это осознанно.
- **Строго только 5 файлов в скоупе:** `frontend-next/src/api/client.ts` (только `ApiError`-блок/`request()`/`ModelOut`/`ChatResponse`/`api.chat`), `frontend-next/src/app/generate-image/page.tsx` (точечные заглушки), `frontend-next/src/app/generate-video/page.tsx` (точечные заглушки), `frontend-next/src/components/chat/ModelPicker.tsx` (рерайт), `frontend-next/src/app/chat/page.tsx` (рерайт). НЕ трогать: `ToolOut`/`api.tools` (экран Trends), сигнатуру `api.generate`/`api.generationStatus`, `adminApi.*`, `TariffOut`/платёжные методы, `e2e/*` (включая `chat.spec.ts` — см. ниже), `mock-telegram.ts`, `playwright.config.ts`, бэкенд `app/api/routes/chat.py`.
- **Отступление от спеки (задокументировано, Task 2):** спека утверждает, что единственный потребитель `ModelOut` — `ModelPicker.tsx`; grep показывает ещё два: `src/app/generate-image/page.tsx` (строки 51, 58, 59, 71, 152, 208, 213) и `src/app/generate-video/page.tsx` (строки 32, 45, 93, 116, 117) используют `category`/`model_code`/`credit_cost`. Без правки они валят гейт `tsc --noEmit`. Решение — компилируемые заглушки по прецеденту `PaymentMethodSheet.tsx` из фазы 1 (эти экраны и так нерабочие против реального бэкенда: `/api/models` теперь отдаёт только text-модели, их фильтры по `category === "image"/"video"` дают пустой список уже сейчас; экраны переписываются в будущей generate-под-фазе). НЕ восстанавливать их логику — только компилируемость.
- **Тип `ModelCategory` (`client.ts:32`) НЕ удалять** — используется `ToolOut.recommended_category` (`client.ts:85`) и `AdminModelOut.category` (`client.ts:223`), оба вне скоупа.
- **`e2e/chat.spec.ts` НЕ меняется** (спека, раздел «Тестирование»): единственная проверка теста — `getByPlaceholder("Сообщение...")`, а текст плейсхолдера в Task 4 сохраняется байт-в-байт. Баннер подтверждения добавляет на страницу вторую кнопку «Отправить», но тест кнопок не касается — strict-mode-конфликта нет. Прогон e2e по-прежнему блокирован предсуществующим багом мока Telegram (`[[ai_hub_bot_e2e_mock_bug]]` в памяти проекта) — чинить его здесь вне скоупа.
- **`onClick={() => send()}`, НЕ `onClick={send}`** — после Task 4 `send` принимает `confirm?: boolean`; передача его напрямую в `onClick` подсунет `MouseEvent` первым аргументом (и даст TS-ошибку несовместимости сигнатур). Оба вызова в JSX — только через стрелку.
- **Различение 409-ов делается по форме тела, не по статусу:** confirmation-gate (`app/api/routes/chat.py:94-97`) возвращает ровно `{"estimated_credits": N}` без ключа `detail`; `RequestInProgressError` (`chat.py:98-99`) — обычный `{"detail": "..."}`. Ветка в `request()` (Task 1) проверяет `res.status === 409 && typeof body.estimated_credits === "number"` и только тогда кидает `ConfirmationRequiredError`; все остальные ошибки (402/403/404/409-in-progress/429/502) идут прежним `ApiError`-путём с готовой русской строкой из `detail`.
- **Стиль баннера подтверждения** — спека предписывает «стиль как у существующих карточек-стёкол»; точные классы берутся из смёрженной карточки «Баланс» (`src/app/account/page.tsx:42-43`): контейнер `relative overflow-hidden rounded-lg border border-border-soft bg-surface` + градиентная полоска `absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]`. Кнопки — существующий `Button` (`src/components/ui/button.tsx`): «Отправить» `mode="filled"` (дефолт), «Отмена» `mode="gray"`, обе `size="s" stretched`. Новых визуальных стилей не выдумывать.
- **Next.js 16 (`frontend-next/AGENTS.md`):** конвенции могут отличаться от training data — но эта фаза не создаёт новых роутов/конвенций, только правит тела существующих файлов; сверяться с `node_modules/next/dist/docs/` нужно лишь при ошибке сборки, не похожей на TS-ошибку типов.
- Номера строк актуальны на master `ce3344f` (2026-07-11). Внутри задачи более ранние правки сдвигают последующие строки — ориентироваться на приведённые якорные сниппеты.
- **Критерий готовности фазы:** `npx tsc --noEmit` и `npm run build` полностью зелёные (12 роутов); `git status` подтверждает, что `e2e/chat.spec.ts` не тронут; ручной smoke-тест чата передан пользователю с инструкцией (реальный бэкенд обязателен, Playwright его не поднимает).

## File Structure

| Файл | Действие |
|---|---|
| `frontend-next/src/api/client.ts` | `ConfirmationRequiredError` + ветка в `request()` (строки 5-30), новые `ModelOut`/`ChatResponse` (строки 45-57), `api.chat` с `confirm` (строки 141-145) — Task 1 |
| `frontend-next/src/app/generate-image/page.tsx` | компилируемые заглушки: фильтр-пустышка + переименования полей — Task 2 |
| `frontend-next/src/app/generate-video/page.tsx` | компилируемые заглушки: фильтр-пустышка + переименования полей — Task 2 |
| `frontend-next/src/components/chat/ModelPicker.tsx` | рерайт: группировка по `tier`, ⭐ для pro/ultra, `model_code`→`code` — Task 3 |
| `frontend-next/src/app/chat/page.tsx` | рерайт: подпись списания под ответом + баннер подтверждения — Task 4 |
| — | финальная верификация: чистый build (12 роутов) + подтверждение нетронутости `chat.spec.ts` + ручной smoke — Task 5 |

---

### Task 1: `client.ts` — `ConfirmationRequiredError`, новые `ModelOut`/`ChatResponse`, `api.chat` с `confirm`

**Files:**
- Modify: `frontend-next/src/api/client.ts:5-30` (блок `ApiError` + `request()`), `frontend-next/src/api/client.ts:45-57` (`ModelOut`/`ChatResponse`), `frontend-next/src/api/client.ts:141-145` (`api.chat`)

**Interfaces:**
- Consumes: реальный контракт бэкенда — `app/api/routes/chat.py:30-47` (`ChatRequest`: `model_code`, `prompt`, `confirm: bool = False`; `ChatResponse`: `answer`, `charged_credits`, `balance_after`; `ModelOut`: `code`, `display_name`, `tier`, `min_credits`, `recommended_credits`) и `app/api/routes/chat.py:94-97` (409 confirmation-gate с телом ровно `{"estimated_credits": N}`, без `detail`).
- Produces (Tasks 2–4 полагаются на ТОЧНЫЕ имена): класс `ConfirmationRequiredError extends Error` с полем `estimatedCredits: number`; `ModelOut.code: string`, `ModelOut.display_name: string`, `ModelOut.tier: "economy" | "standard" | "premium" | "pro" | "ultra"`, `ModelOut.min_credits: number`, `ModelOut.recommended_credits: number`; `ChatResponse.answer: string`, `ChatResponse.charged_credits: number`, `ChatResponse.balance_after: number`; `api.chat(modelCode: string, prompt: string, confirm?: boolean)`. Полей `model_code`/`category`/`is_premium`/`credit_cost` на `ModelOut` и `input_tokens`/`output_tokens` на `ChatResponse` больше НЕТ.

- [ ] **Step 1: `ConfirmationRequiredError` + ветка в `request()`**

Текущий код (`frontend-next/src/api/client.ts`, строки 5–30):

```ts
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData(),
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}) as { detail?: string });
    throw new ApiError(res.status, detail.detail ?? res.statusText);
  }

  return res.json() as Promise<T>;
}
```

Заменить целиком на:

```ts
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export class ConfirmationRequiredError extends Error {
  estimatedCredits: number;

  constructor(estimatedCredits: number) {
    super(`confirmation required: ${estimatedCredits} credits`);
    this.estimatedCredits = estimatedCredits;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData(),
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (res.status === 409 && typeof body.estimated_credits === "number") {
      // Confirmation-gate POST /api/chat (и будущего /api/generate): тело ровно
      // {"estimated_credits": N} БЕЗ ключа "detail" -- в отличие от 409
      // RequestInProgressError, у которого detail есть и который идёт ниже
      // обычным ApiError-путём.
      throw new ConfirmationRequiredError(body.estimated_credits);
    }
    throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
  }

  return res.json() as Promise<T>;
}
```

(Замечание для ревьюера: старый `detail.detail ?? res.statusText` заменён на `typeof body.detail === "string" ? body.detail : res.statusText` — тело теперь типизировано как `Record<string, unknown>`, `??` на `unknown` не сузит тип до `string`, а FastAPI может отдавать `detail` и объектом при 422-валидации.)

- [ ] **Step 2: Новые `ModelOut`/`ChatResponse`**

Текущий код (`frontend-next/src/api/client.ts`, строки 45–57):

```ts
export interface ModelOut {
  model_code: string;
  display_name: string;
  category: ModelCategory;
  is_premium: boolean;
  credit_cost: number;
}

export interface ChatResponse {
  answer: string;
  input_tokens: number;
  output_tokens: number;
}
```

Заменить целиком на (1:1 с `app/api/routes/chat.py:36-47`):

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

Строку `export type ModelCategory = ...` (`client.ts:32`) НЕ трогать — её используют `ToolOut.recommended_category` и `AdminModelOut.category` (вне скоупа).

- [ ] **Step 3: `api.chat` с параметром `confirm`**

Текущий код (`frontend-next/src/api/client.ts`, строки 141–145):

```ts
  chat: (modelCode: string, prompt: string) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ model_code: modelCode, prompt }),
    }),
```

Заменить на:

```ts
  chat: (modelCode: string, prompt: string, confirm = false) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ model_code: modelCode, prompt, confirm }),
    }),
```

Больше НИЧЕГО в `client.ts` не менять (`api.models()` на строке 140 уже возвращает `request<ModelOut[]>("/api/models")` и правок не требует; `ToolOut`, `api.generate`, `adminApi`, `TariffOut` — вне скоупа).

- [ ] **Step 4: Проверить, что сломались ТОЛЬКО ожидаемые потребители (красный прогон)**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: FAIL. Ошибки `Property '...' does not exist on type 'ModelOut'` (и родственные) ТОЛЬКО в четырёх файлах:
- `src/components/chat/ModelPicker.tsx` — `category` (строка 36), `model_code` (57), `is_premium` (62);
- `src/app/chat/page.tsx` — `model_code` (строка 37);
- `src/app/generate-image/page.tsx` — `category` (51), `model_code` (58, 71, 208), `credit_cost` (59, 152, 213);
- `src/app/generate-video/page.tsx` — `category` (32), `model_code` (45, 116), `credit_cost` (93, 117).

Если ошибки есть в каких-либо ДРУГИХ файлах `src/` — СТОП: этот список выверен grep'ом по master `ce3344f`, расхождение нужно разобрать до продолжения. (Посторонний шум от stale-типов в `.next/` лечится `Remove-Item -Recurse -Force .next` и ошибкой потребителей не считается.)

- [ ] **Step 5: Промежуточный коммит (typecheck осознанно красный до Task 4)**

Из корня репо:

```bash
git add frontend-next/src/api/client.ts
git commit -m "wip(frontend): ConfirmationRequiredError в request(), ModelOut/ChatResponse 1:1 с /api/models и /api/chat, api.chat(confirm) (typecheck красный до починки потребителей)"
```

---

### Task 2: `generate-image/page.tsx` + `generate-video/page.tsx` — компилируемые заглушки

**Files:**
- Modify: `frontend-next/src/app/generate-image/page.tsx:47-59,71,152,208,213`
- Modify: `frontend-next/src/app/generate-video/page.tsx:28-37,45,93,116-117`

**Interfaces:**
- Consumes: `ModelOut.code` / `ModelOut.min_credits` из Task 1.
- Produces: ничего нового. ВАЖНО: это НЕ восстановление логики — эти экраны уже нерабочие против реального бэкенда (`GET /api/models` отдаёт только text-модели, фильтры по `category === "image"/"video"` дают `[]` в рантайме уже сейчас), а generate-flow переписывается в будущей под-фазе. Здесь только устранение ошибок компиляции по прецеденту `PaymentMethodSheet.tsx` фазы 1. `min_credits` вместо `credit_cost` — компилируемая подстановка того же смысла «от N кредитов», не рабочая цена.

- [ ] **Step 1: `generate-image/page.tsx` — фильтр-пустышка**

Текущий код (`frontend-next/src/app/generate-image/page.tsx`, строки 47–59, якорь):

```ts
  useEffect(() => {
    api
      .models()
      .then((all) => {
        const images = all.filter((m) => m.category === "image");
        setModels(images);
        setModel((prev) => prev ?? images[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);

  const isDalle3 = model?.model_code === "dall-e-3";
  const cost = model ? (isDalle3 ? computeImageCreditCost(model.credit_cost, aspect, resolution) : model.credit_cost) : 0;
```

Заменить на:

```ts
  useEffect(() => {
    api
      .models()
      .then((all) => {
        // /api/models (credit-system v2) отдаёт только text-модели, у ModelOut
        // больше нет category. Экран переписывается на новый generate-flow в
        // будущей под-фазе; до неё список пуст -- компилируемая заглушка, не логика.
        const images = all.filter(() => false);
        setModels(images);
        setModel((prev) => prev ?? images[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);

  const isDalle3 = model?.code === "dall-e-3";
  const cost = model ? (isDalle3 ? computeImageCreditCost(model.min_credits, aspect, resolution) : model.min_credits) : 0;
```

- [ ] **Step 2: `generate-image/page.tsx` — остальные обращения к полям**

Три точечные замены ниже по файлу:

Строка 71 (внутри `api.generate(...)`) — текущий код:

```ts
        model.model_code,
```

заменить на:

```ts
        model.code,
```

Строка 152 — текущий код:

```tsx
              от {computeImageCreditCost(model.credit_cost, "auto", "1k")} 💎
```

заменить на:

```tsx
              от {computeImageCreditCost(model.min_credits, "auto", "1k")} 💎
```

Строки 208 и 213 (внутри `<Cell>` пикера) — текущий код:

```tsx
                key={m.model_code}
```

```tsx
                after={`от ${m.credit_cost} 💎`}
```

заменить соответственно на:

```tsx
                key={m.code}
```

```tsx
                after={`от ${m.min_credits} 💎`}
```

- [ ] **Step 3: `generate-video/page.tsx` — фильтр-пустышка**

Текущий код (`frontend-next/src/app/generate-video/page.tsx`, строки 28–37):

```ts
  useEffect(() => {
    api
      .models()
      .then((all) => {
        const videos = all.filter((m) => m.category === "video");
        setModels(videos);
        setModel((prev) => prev ?? videos[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);
```

Заменить на:

```ts
  useEffect(() => {
    api
      .models()
      .then((all) => {
        // /api/models (credit-system v2) отдаёт только text-модели, у ModelOut
        // больше нет category. Экран переписывается на новый generate-flow в
        // будущей под-фазе; до неё список пуст -- компилируемая заглушка, не логика.
        const videos = all.filter(() => false);
        setModels(videos);
        setModel((prev) => prev ?? videos[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);
```

- [ ] **Step 4: `generate-video/page.tsx` — остальные обращения к полям**

Строка 45 — текущий код:

```ts
      const { request_id } = await api.generate(model.model_code, prompt.trim());
```

заменить на:

```ts
      const { request_id } = await api.generate(model.code, prompt.trim());
```

Строка 93 — текущий код:

```tsx
        <Cell subtitle={model ? `${model.credit_cost} кредитов` : undefined} onClick={() => setPickerOpen(true)}>
```

заменить на:

```tsx
        <Cell subtitle={model ? `${model.min_credits} кредитов` : undefined} onClick={() => setPickerOpen(true)}>
```

Строки 116–117 — текущий код:

```tsx
                  key={m.model_code}
                  subtitle={`${m.credit_cost} кредитов`}
```

заменить на:

```tsx
                  key={m.code}
                  subtitle={`${m.min_credits} кредитов`}
```

- [ ] **Step 5: Проверить сузившийся красный прогон**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: FAIL, но все оставшиеся ошибки — ТОЛЬКО в `src/components/chat/ModelPicker.tsx` и `src/app/chat/page.tsx` (список полей из Task 1 Step 4). Файлы `generate-image/page.tsx` и `generate-video/page.tsx` в выводе отсутствуют.

- [ ] **Step 6: Промежуточный коммит**

```bash
git add frontend-next/src/app/generate-image/page.tsx frontend-next/src/app/generate-video/page.tsx
git commit -m "wip(frontend): компилируемые заглушки generate-image/video под новый ModelOut (экраны переписываются в generate-под-фазе)"
```

---

### Task 3: `ModelPicker.tsx` — группировка по `tier`, ⭐ для pro/ultra

**Files:**
- Modify: `frontend-next/src/components/chat/ModelPicker.tsx` (переписывается целиком)

**Interfaces:**
- Consumes: `ModelOut.code` / `display_name` / `tier` (Task 1); `api.models()` (без изменений); UI-примитивы `Button`/`Cell`/`List`/`Section`/`Sheet`/`Spinner` из `@/components/ui/*` (существующие пропсы, не меняются).
- Produces: компонент `ModelPicker({ selectedModel, onSelect }: { selectedModel: ModelOut | null; onSelect: (model: ModelOut) => void })` — сигнатура пропсов НЕ меняется, Task 4 продолжает использовать его как раньше. `onSelect` получает модель с полем `.code` (не `.model_code`).

- [ ] **Step 1: Переписать файл целиком**

Заменить всё содержимое `frontend-next/src/components/chat/ModelPicker.tsx` на:

```tsx
"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Section } from "@/components/ui/section";
import { Sheet } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { api, type ModelOut } from "@/api/client";

const TIER_LABEL: Record<string, string> = {
  economy: "Эконом",
  standard: "Стандарт",
  premium: "Премиум",
  pro: "Pro",
  ultra: "Ultra",
};

const STARRED_TIERS = new Set(["pro", "ultra"]);

interface Props {
  selectedModel: ModelOut | null;
  onSelect: (model: ModelOut) => void;
}

export default function ModelPicker({ selectedModel, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const [models, setModels] = useState<ModelOut[] | null>(null);

  useEffect(() => {
    if (open && models === null) {
      api.models().then(setModels).catch(() => setModels([]));
    }
  }, [open, models]);

  // Бэкенд отдаёт список уже отсортированным по sort_order (эконом -> ultra),
  // поэтому порядок секций -- порядок первого появления tier в ответе;
  // второй сортировки на фронте не требуется.
  const grouped = (models ?? []).reduce<Record<string, ModelOut[]>>((acc, model) => {
    (acc[model.tier] ??= []).push(model);
    return acc;
  }, {});

  return (
    <>
      <Button size="s" mode="bezeled" onClick={() => setOpen(true)}>
        {selectedModel ? selectedModel.display_name : "Выбрать модель"}
      </Button>

      <Sheet open={open} onOpenChange={setOpen} header={<Sheet.Header>Выберите модель</Sheet.Header>}>
        {models === null ? (
          <div className="flex justify-center p-6">
            <Spinner size="m" />
          </div>
        ) : (
          <List>
            {Object.entries(grouped).map(([tier, items]) => (
              <Section key={tier} header={TIER_LABEL[tier] ?? tier}>
                {items.map((model) => (
                  <Cell
                    key={model.code}
                    onClick={() => {
                      onSelect(model);
                      setOpen(false);
                    }}
                    after={STARRED_TIERS.has(model.tier) ? "⭐" : undefined}
                  >
                    {model.display_name}
                  </Cell>
                ))}
              </Section>
            ))}
          </List>
        )}
      </Sheet>
    </>
  );
}
```

Что изменилось относительно текущего файла (для ревьюера): `CATEGORY_LABEL` → `TIER_LABEL` (пять tier'ов из спеки), добавлен `STARRED_TIERS`; `grouped` строится по `model.tier` вместо `model.category`; `key={model.model_code}` → `key={model.code}`; `after={model.is_premium ? "⭐" : undefined}` → `after={STARRED_TIERS.has(model.tier) ? "⭐" : undefined}`. Всё остальное (ленивая загрузка по открытию, спиннер, структура Sheet/List/Section/Cell, пропсы компонента) — без изменений.

- [ ] **Step 2: Проверить, что остался только `chat/page.tsx` (красный прогон)**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: FAIL, единственная оставшаяся ошибка — `src/app/chat/page.tsx:37` (`Property 'model_code' does not exist on type 'ModelOut'`). `ModelPicker.tsx` в выводе отсутствует.

- [ ] **Step 3: Промежуточный коммит**

```bash
git add frontend-next/src/components/chat/ModelPicker.tsx
git commit -m "wip(frontend): ModelPicker группирует по tier, звезда для pro/ultra, model_code -> code"
```

---

### Task 4: `chat/page.tsx` — подпись списания + баннер подтверждения

**Files:**
- Modify: `frontend-next/src/app/chat/page.tsx` (переписывается целиком)

**Interfaces:**
- Consumes: `ConfirmationRequiredError` с полем `.estimatedCredits: number`, `ChatResponse.charged_credits`/`.balance_after`, `api.chat(modelCode, prompt, confirm)` (Task 1); `ModelOut.code` и компонент `ModelPicker` с прежней сигнатурой пропсов (Task 3); `Button` (`mode="gray"` и дефолтный `filled` существуют в `src/components/ui/button.tsx:5`), `Placeholder`/`Spinner`/`Textarea` — без изменений; `haptic` из `@/lib/telegram`.
- Produces (Task 5 полагается на ТОЧНЫЙ отображаемый текст): плейсхолдер `Сообщение...` (байт-в-байт как сейчас — контракт `e2e/chat.spec.ts`), подпись `Списано: {N} • Баланс: {M}` под assistant-баблом, баннер `Примерная стоимость: {N} кредитов. Продолжить?` с кнопками «Отправить»/«Отмена».

- [ ] **Step 1: Переписать файл целиком**

Заменить всё содержимое `frontend-next/src/app/chat/page.tsx` на:

```tsx
"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Placeholder } from "@/components/ui/placeholder";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, ConfirmationRequiredError, api, type ModelOut } from "@/api/client";
import { haptic } from "@/lib/telegram";
import ModelPicker from "@/components/chat/ModelPicker";

interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
  chargedCredits?: number;
  balanceAfter?: number;
}

interface PendingConfirmation {
  prompt: string;
  modelCode: string;
  estimatedCredits: number;
}

function ChatScreen() {
  const searchParams = useSearchParams();
  const prefill = searchParams.get("prefill") ?? "";

  const [model, setModel] = useState<ModelOut | null>(null);
  const [prompt, setPrompt] = useState(prefill);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);

  async function send(confirm = false) {
    let question: string;
    let modelCode: string;

    if (confirm) {
      // Повторная отправка после баннера: user-бабл уже в истории с первой
      // попытки, не дублируем; берём сохранённые prompt/modelCode.
      if (!pendingConfirmation || sending) return;
      question = pendingConfirmation.prompt;
      modelCode = pendingConfirmation.modelCode;
      setPendingConfirmation(null);
    } else {
      if (!model || !prompt.trim() || sending) return;
      question = prompt.trim();
      modelCode = model.code;
      setMessages((prev) => [...prev, { role: "user", text: question }]);
      setPrompt("");
      // Новый вопрос отменяет неподтверждённый предыдущий.
      setPendingConfirmation(null);
    }

    setSending(true);

    try {
      const result = await api.chat(modelCode, question, confirm);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: result.answer,
          chargedCredits: result.charged_credits,
          balanceAfter: result.balance_after,
        },
      ]);
      haptic("light");
    } catch (err) {
      if (err instanceof ConfirmationRequiredError) {
        // Не ошибка: вопрос реально уйдёт после подтверждения, user-бабл
        // остаётся в истории, error-бабл не добавляется.
        setPendingConfirmation({ prompt: question, modelCode, estimatedCredits: err.estimatedCredits });
      } else {
        const text = err instanceof ApiError ? err.message : "Что-то пошло не так, попробуйте ещё раз.";
        setMessages((prev) => [...prev, { role: "error", text }]);
      }
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex h-screen flex-col">
      <div className="p-3">
        <ModelPicker selectedModel={model} onSelect={setModel} />
      </div>

      <div className="flex-1 overflow-y-auto px-3">
        {messages.length === 0 && (
          <Placeholder header="Начните диалог" description="Выберите модель и напишите сообщение." />
        )}
        {messages.map((m, i) => (
          <div key={i} className={`my-2 max-w-[85%] ${m.role === "user" ? "ml-auto" : ""}`}>
            <div
              className={`rounded-xl px-3 py-2 whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-brand-2 text-white"
                  : m.role === "error"
                    ? "bg-surface-strong text-red-400"
                    : "bg-surface-strong text-foreground"
              }`}
            >
              {m.text}
            </div>
            {m.role === "assistant" && m.chargedCredits !== undefined && m.balanceAfter !== undefined && (
              <div className="mt-1 px-1 text-xs text-foreground-muted">
                Списано: {m.chargedCredits} • Баланс: {m.balanceAfter}
              </div>
            )}
          </div>
        ))}
        {sending && <Spinner size="s" />}
      </div>

      {pendingConfirmation && (
        <div className="relative mx-3 mb-1 overflow-hidden rounded-lg border border-border-soft bg-surface p-[14px]">
          <div className="absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]" />
          <div className="text-[13px]">
            Примерная стоимость: {pendingConfirmation.estimatedCredits} кредитов. Продолжить?
          </div>
          <div className="mt-2.5 flex gap-2">
            <Button size="s" stretched onClick={() => send(true)}>
              Отправить
            </Button>
            <Button size="s" stretched mode="gray" onClick={() => setPendingConfirmation(null)}>
              Отмена
            </Button>
          </div>
        </div>
      )}

      <div className="flex gap-2 p-3">
        <Textarea
          className="flex-1"
          rows={1}
          placeholder="Сообщение..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <Button disabled={!model || !prompt.trim() || sending} onClick={() => send()}>
          Отправить
        </Button>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ChatScreen />
    </Suspense>
  );
}
```

Что изменилось относительно текущего файла (для ревьюера):
- `ChatMessage` получил опциональные `chargedCredits`/`balanceAfter`; они заполняются из `result.charged_credits`/`result.balance_after` и рендерятся мелкой подписью `Списано: N • Баланс: M` под assistant-баблом (только когда оба заданы). Ради подписи бабл обёрнут во внешний `div` — классы позиционирования (`my-2 max-w-[85%]`, `ml-auto` для user) переехали на обёртку, визуал самих баблов не изменился.
- `send()` принимает `confirm = false`: при `confirm=true` берёт сохранённые `prompt`/`modelCode` из `pendingConfirmation` и НЕ добавляет user-бабл повторно; при `confirm=false` — прежний поток (`model.code` вместо `model.model_code`) плюс сброс неподтверждённого предыдущего запроса.
- `catch` различает `ConfirmationRequiredError` (заполнить `pendingConfirmation`, БЕЗ error-бабла) и прежний `ApiError`-путь (error-бабл с готовой русской строкой с бэкенда — 402/403/404/409-in-progress/429/502 без изменений).
- Баннер подтверждения — над полем ввода, в стеклянном стиле карточки «Баланс» с Account (`border border-border-soft bg-surface` + градиентная полоска `h-[3px] bg-[image:var(--brand-gradient)]`); «Отправить» — дефолтный `filled`-Button, «Отмена» — `mode="gray"`, обе `size="s" stretched`.
- Оба вызова `send` в JSX — через стрелку (`() => send()` / `() => send(true)`): прямая передача `onClick={send}` подсунула бы `MouseEvent` в параметр `confirm`.
- Плейсхолдер `Сообщение...` сохранён байт-в-байт — контракт `e2e/chat.spec.ts`.

- [ ] **Step 2: Typecheck зелёный**

Run (из `frontend-next/`): `npx tsc --noEmit`

Expected: PASS, exit code 0, пустой вывод.

- [ ] **Step 3: Канонический гейт — сборка**

Run (из `frontend-next/`): `npm run build`

Expected: PASS — `Compiled successfully`, без TS-ошибок, 12 роутов (включая `/generate-image`, `/generate-video` с заглушками Task 2 и нетронутые `/trends`, `/tariffs`, `/admin`).

- [ ] **Step 4: Коммит (первый зелёный)**

```bash
git add frontend-next/src/app/chat/page.tsx
git commit -m "feat(frontend): экран Chat на credit-system v2 -- подпись списания, баннер подтверждения стоимости"
```

---

### Task 5: Финальная верификация — чистый build, нетронутый `chat.spec.ts`, ручной smoke

**Files:**
- Никаких правок кода. Только запуск проверок.

**Interfaces:**
- Consumes: всё из Tasks 1–4.
- Produces: критерий готовности фазы.

- [ ] **Step 1: Чистая сборка с нуля**

Run (из `frontend-next/`, PowerShell): `Remove-Item -Recurse -Force .next; npm run build`

Expected: PASS без TS-ошибок, в сводке роутов — 12 строк (`/`, `/_not-found`, `/account`, `/admin`, `/chat`, `/generate-image`, `/generate-video`, `/login-failed`, `/referral`, `/settings`, `/tariffs`, `/trends`). Это обязательная часть; она НЕ требует бэкенда.

- [ ] **Step 2: Подтвердить, что `e2e/chat.spec.ts` не тронут**

Run (из корня репо): `git status --short frontend-next/e2e/ && git log --oneline -1 -- frontend-next/e2e/chat.spec.ts`

Expected: `git status` по `e2e/` пуст (никаких изменений); последний коммит по `chat.spec.ts` — доэтафазный. Почему это корректно (спека, «Тестирование»): единственная проверка теста — `getByPlaceholder("Сообщение...")`, и Task 4 сохранил этот текст байт-в-байт; вторая кнопка «Отправить» из баннера тесту не мешает (тест кнопок не касается). Прогон e2e по-прежнему блокирован предсуществующим багом мока Telegram — чинить вне скоупа, НЕ прогонять как гейт этой фазы.

- [ ] **Step 3: Ручной smoke-тест (требует реального бэкенда; если поднять нельзя — передать пользователю этой инструкцией)**

Предусловия — те же, что в Task 5 фазы 1: бэкенд `python -m uvicorn app.main:app --port 8000` (Postgres 16 + Redis, `FRONTEND_URL=http://localhost:3000`), в `frontend-next/.env.local` — `NEXT_PUBLIC_API_URL=http://localhost:8000`. Затем `npm run dev` и открыть `http://localhost:3000/chat` с моком Telegram (или через реальный Mini App):

1. Открыть пикер моделей: секции сгруппированы по tier с русскими заголовками («Эконом», «Стандарт», «Премиум», «Pro», «Ultra» — присутствуют те, где есть модели), у pro/ultra-моделей — ⭐.
2. Выбрать дешёвую модель, отправить короткий вопрос: под ответом появляется подпись `Списано: N • Баланс: M` с реальными числами.
3. Отправить запрос дороже порога подтверждения (длинный промпт / дорогая модель — порог задаёт бэкенд): вместо ответа появляется стеклянный баннер «Примерная стоимость: N кредитов. Продолжить?»; user-бабл остаётся в истории, error-бабла нет.
4. Нажать «Отмена»: баннер исчезает, ничего не отправлено, user-бабл остаётся. Повторить шаг 3 и нажать «Отправить»: приходит ответ с подписью списания, баннер исчезает, user-бабл НЕ задублирован.
5. Проверить обычную ошибку (например, исчерпать баланс или дёрнуть недоступную модель): красный error-бабл с русским текстом с бэкенда — как раньше.

- [ ] **Step 4: Финальный статус**

Убедиться, что рабочее дерево чистое по файлам фазы (`git status` — нет незакоммиченных правок в `frontend-next/`), все 4 коммита задач на месте (`git log --oneline -4`). Фаза готова; экраны Trends/Tariffs/Referral/Settings, реальный generate-flow (image/video) и admin-панель остаются на старом API до своих под-фаз — это ожидаемо (спека, «Известные ограничения»). `ConfirmationRequiredError` в `request()` уже готов к переиспользованию будущей generate-под-фазой.
