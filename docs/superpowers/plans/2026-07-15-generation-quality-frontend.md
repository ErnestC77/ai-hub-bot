# Качество и длительность генерации — фронт — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать пользователю выбирать качество и длительность из того, что модель реально умеет, показывая честную цену.

**Architecture:** Фронт **не знает** ни про разрешения, ни про длительности: он рисует `SegmentedControl` из массива `options`, пришедшего в `ModelOut`, и шлёт обратно **коды** выбранных опций. У модели без опций данного вида секции просто нет. Цена в CTA пересчитывается локально умножением `recommended_credits` на множители выбранных опций; точную сумму по-прежнему даёт 409-гейт.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind v4, Playwright.

**Спек:** `docs/superpowers/specs/2026-07-15-generation-quality-design.md` (этап 6).
**Предыдущие планы:** `2026-07-15-fal-catalog-fix.md` (этап 1, выполнен), `2026-07-15-generation-quality-backend.md` (этапы 2–5, **должен быть выполнен до этого плана**).
**Следующий план:** админка CRUD опций (этап 7) — отдельно, она самостоятельна и этому плану не нужна.

## Global Constraints

- **ВЫКАТЫВАТЬ ТОЛЬКО ВМЕСТЕ С ПЛАНОМ 2.** Тот удаляет `duration_seconds` из `GenerateRequest`; фронт сейчас его шлёт. Между планами генерация видео сломана. Это единый релиз.
- **Фронт не хардкодит ни одного значения качества или длительности.** Ни `1K/2K/4K`, ни `720p/1080p`, ни `2–15 сек`. Всё приходит из `ModelOut.options`. Модель без опций → секции нет. Это не косметика: у `nano_banana` и `flux_kontext_pro` у провайдера **нет ручки размера**, а у `kling` нельзя менять разрешение — нарисовать им селектор значило бы соврать.
- **Цена считается умножением, а не формулой.** `recommended_credits × Π multipliers`. Формулу из дизайн-макета (`duration × 4 × qMult`) НЕ переносить — она выдумана дизайнером и не совпадает с реальностью ни для одной модели.
- **Слайдер длительности 2–15 сек удаляется.** Ни одна модель такого диапазона не принимает: Kling умеет 5 и 10, Veo — 4/6/8, Wan считает кадрами, Ovi не управляется вовсе.
- **`data-testid` на всё, что трогаем** — e2e переведён на testid прошлым редизайном, текстовые селекторы больше не используем.
- Русский текст через существующие строки экрана (i18n в проекте нет — не вводить).
- Ветка `aurora-glass`, рабочее дерево делят с другой сессией: **никогда `git add -A` / `git add .`**.

## Что уже готово на бэкенде (план 2)

- `GET /api/models?category=…` возвращает `ModelOut.options: list[{kind, code, label, credits_multiplier, is_default, sort_order}]`, только активные, отсортированные по `sort_order`. `provider_params` наружу НЕ отдаются.
- `POST /api/generate` принимает `option_codes: {"quality": "4k", "duration": "10s", "audio": "off"} | None`; **`duration_seconds` удалён**. Неизвестный/неактивный код → **400**.
- `kind` бывает `quality`, `duration`, `audio`.

Реальные наборы после плана 2 (для понимания, НЕ для хардкода):

| Модель | quality | duration | audio |
|---|---|---|---|
| `wan_video` | 480p ×0.5 · 580p ×0.75 · **720p** | **5с** · 10с ×1.988 | — |
| `kling_video` | — (у fal нет ручки) | **5с** · 10с ×2.0 | — |
| `veo_video` | **720p** · 1080p ×1.0 · 4k ×2.0 | 4с ×0.5 · 6с ×0.75 · **8с** | **вкл** · выкл ×0.5 |
| `ovi_video` | — | — | — |
| `qwen_image` | **1K** · 2K ×4.0 | — | — |
| `seedream` | **1K** · 2K ×1.0 · 4K ×1.0 | — | — |
| `nano_banana_pro` | **1K** · 2K ×1.0 · 4K ×2.0 | — | — |
| `nano_banana`, `flux_kontext_pro` | — | — | — |

Жирным — дефолт. Обрати внимание: **2K и 1080p часто бесплатны** (×1.0), а `ovi_video` не получит ни одной секции.

---

### Task 1: Типы и API-клиент

**Files:**
- Modify: `frontend-next/src/api/client.ts:61-67` (`ModelOut`), `:136-146` (`api.generate`)

**Interfaces:**
- Consumes: бэкенд плана 2.
- Produces: `ModelOptionOut`, `ModelOut.options`, `api.generate(modelCode, prompt, imageUrl?, optionCodes?, confirm?)` — **сигнатура меняется: `durationSeconds: number` → `optionCodes: Record<string,string>`**. Task 2–3 её вызывают.

- [ ] **Step 1: Обновить типы**

В `frontend-next/src/api/client.ts` заменить `ModelOut`:

```ts
export type ModelOptionKind = "quality" | "duration" | "audio";

export interface ModelOptionOut {
  kind: ModelOptionKind;
  code: string;
  label: string;
  /** Во сколько раз опция дороже дефолта. Выведен из замеров провайдера. */
  credits_multiplier: number;
  is_default: boolean;
  sort_order: number;
}

export interface ModelOut {
  code: string;
  display_name: string;
  tier: "economy" | "standard" | "premium" | "pro" | "ultra";
  min_credits: number;
  recommended_credits: number;
  /** Наборы задаёт модель. Пусто -- у провайдера нет соответствующей ручки. */
  options: ModelOptionOut[];
}
```

- [ ] **Step 2: Обновить `api.generate`**

```ts
  generate: (
    modelCode: string,
    prompt: string,
    imageUrl?: string,
    optionCodes?: Record<string, string>,
    confirm = false,
  ) =>
    request<{ request_id: number; estimated_credits: number }>("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        model_code: modelCode,
        prompt,
        image_url: imageUrl ?? null,
        // Коды опций, не сырые значения: наборы задаёт модель, см. ModelOut.options.
        option_codes: optionCodes ?? null,
        confirm,
      }),
    }),
```

**`duration_seconds` удалить.** Бэкенд его больше не принимает.

- [ ] **Step 3: Проверить typecheck (падение ожидаемо)**

Run: `cd frontend-next && npx tsc --noEmit`
Expected: FAIL — `generate-video/page.tsx` передаёт `durationSeconds`. Это ожидаемо и чинится в Task 3.

- [ ] **Step 4: Коммит**

```bash
git add frontend-next/src/api/client.ts
git commit -m "feat(api-client): option_codes вместо duration_seconds

Наборы качества/длительности задаёт модель -- ModelOut.options. Фронт
шлёт коды, а не сырые значения. duration_seconds удалён: бэкенд его
больше не принимает (слайдер 2-15 не поддерживала ни одна модель)."
```

---

### Task 2: Компонент выбора опций

Один компонент на все три вида — иначе три экрана разойдутся в поведении.

**Files:**
- Create: `frontend-next/src/components/generate/OptionPicker.tsx`
- Create: `frontend-next/src/lib/optionPricing.ts`
- Test: `frontend-next/e2e/` (в Task 4)

**Interfaces:**
- Consumes: `ModelOptionOut`, `ModelOut` (Task 1); `SegmentedControl` (`@/components/ui/segmented-control`, API: `SegmentedControl` + `SegmentedControl.Item({selected, onClick, children})`).
- Produces:
  - `OptionPicker({ model, kind, label, selected, onSelect })` — рисует секцию или `null`.
  - `defaultOptionCodes(model): Record<string,string>` — коды дефолтов по всем видам.
  - `optionsMultiplier(model, codes): number` — произведение множителей.
  - `estimatedCredits(model, codes): number` — `round(recommended_credits × multiplier)`.
  Task 3 использует всё четыре.

- [ ] **Step 1: Написать чистые функции цены**

Создать `frontend-next/src/lib/optionPricing.ts`:

```ts
import type { ModelOptionKind, ModelOut } from "@/api/client";

/** Коды дефолтных опций модели по всем видам сразу. */
export function defaultOptionCodes(model: ModelOut | null): Record<string, string> {
  if (!model) return {};
  const codes: Record<string, string> = {};
  for (const o of model.options) {
    if (o.is_default) codes[o.kind] = o.code;
  }
  return codes;
}

/** Опции одного вида, в порядке sort_order. Пусто -- у провайдера нет такой ручки. */
export function optionsOfKind(model: ModelOut | null, kind: ModelOptionKind) {
  if (!model) return [];
  return model.options
    .filter((o) => o.kind === kind)
    .slice()
    .sort((a, b) => a.sort_order - b.sort_order);
}

/**
 * Произведение множителей выбранных опций.
 * Оси независимы и перемножаются -- это подтверждено замерами провайдера:
 * у Veo 4с без звука = $0.80, а 8с со звуком = $3.20 = 0.80 x 2 x 2.
 */
export function optionsMultiplier(model: ModelOut | null, codes: Record<string, string>): number {
  if (!model) return 1;
  let multiplier = 1;
  for (const [kind, code] of Object.entries(codes)) {
    const option = model.options.find((o) => o.kind === kind && o.code === code);
    if (option) multiplier *= option.credits_multiplier;
  }
  return multiplier;
}

/**
 * Ориентировочная цена для CTA. Точную сумму даёт 409-гейт бэкенда --
 * здесь только умножение, никаких формул: формула из дизайн-макета
 * (duration x 4 x qMult) выдумана и не совпадает ни с одной моделью.
 */
export function estimatedCredits(model: ModelOut | null, codes: Record<string, string>): number {
  if (!model) return 0;
  return Math.round(model.recommended_credits * optionsMultiplier(model, codes));
}
```

- [ ] **Step 2: Написать компонент**

Создать `frontend-next/src/components/generate/OptionPicker.tsx`:

```tsx
"use client";

import { SegmentedControl } from "@/components/ui/segmented-control";
import type { ModelOptionKind, ModelOut } from "@/api/client";
import { optionsOfKind } from "@/lib/optionPricing";

interface Props {
  model: ModelOut | null;
  kind: ModelOptionKind;
  label: string;
  selected: string | undefined;
  onSelect: (code: string) => void;
}

/**
 * Секция выбора опции. Рисует ТО, ЧТО МОДЕЛЬ УМЕЕТ, и ничего не хардкодит:
 * у nano_banana и flux_kontext_pro у fal нет ручки размера, у kling нельзя
 * менять разрешение, у ovi -- ни разрешения, ни длительности. Для них
 * секции просто не будет: нарисовать селектор, которого провайдер не
 * понимает, значит соврать пользователю.
 */
export default function OptionPicker({ model, kind, label, selected, onSelect }: Props) {
  const options = optionsOfKind(model, kind);
  if (options.length === 0) return null;

  return (
    <div data-testid={`option-${kind}`}>
      <div className="mb-2 px-1 text-[10px] font-semibold tracking-[.08em] text-foreground-dim uppercase">
        {label}
      </div>
      <div className="overflow-x-auto">
        <div className="w-max min-w-full">
          <SegmentedControl>
            {options.map((o) => (
              <SegmentedControl.Item
                key={o.code}
                selected={selected === o.code}
                onClick={() => onSelect(o.code)}
              >
                <span className="whitespace-nowrap" data-testid={`option-${kind}-${o.code}`}>
                  {o.label}
                </span>
              </SegmentedControl.Item>
            ))}
          </SegmentedControl>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Проверить typecheck**

Run: `cd frontend-next && npx tsc --noEmit`
Expected: FAIL только на `generate-video/page.tsx` (`durationSeconds`) — новые файлы чистые.

- [ ] **Step 4: Коммит**

```bash
git add frontend-next/src/components/generate/OptionPicker.tsx frontend-next/src/lib/optionPricing.ts
git commit -m "feat(generate): OptionPicker -- секции из того, что модель умеет

Ничего не хардкодит: набор приходит в ModelOut.options. Модель без опций
данного вида -> секции нет (у nano_banana и flux_kontext_pro у fal нет
ручки размера, у ovi -- ни разрешения, ни длительности).
Цена -- умножение множителей, не формула из макета."
```

---

### Task 3: Подключить опции к экранам генерации

**Files:**
- Modify: `frontend-next/src/app/generate-video/page.tsx`
- Modify: `frontend-next/src/app/generate-image/page.tsx`

**Interfaces:**
- Consumes: `api.generate(..., optionCodes, confirm)` (Task 1); `OptionPicker`, `defaultOptionCodes`, `estimatedCredits` (Task 2); `resolveModel` (`@/lib/resolveModel`, уже есть).
- Produces: рабочие экраны. Task 4 их тестирует.

- [ ] **Step 1: Переписать generate-video**

Прочитать файл целиком. Изменения:

1. **Удалить слайдер длительности и его состояние**: константы `DURATION_MIN`/`DURATION_MAX`/`DURATION_DEFAULT`, `const [duration, setDuration]`, весь блок разметки «ДЛИТЕЛЬНОСТЬ» со слайдером. Ни одна модель не принимает 2–15 сек.
2. **Состояние опций**:
```tsx
  const [optionCodes, setOptionCodes] = useState<Record<string, string>>({});
```
3. **Дефолты при выборе модели** — модель приходит асинхронно, поэтому:
```tsx
  useEffect(() => {
    setOptionCodes(defaultOptionCodes(model));
  }, [model]);
```
4. **Секции** вместо слайдера (после селектора модели):
```tsx
          <OptionPicker model={model} kind="quality" label="Качество"
                        selected={optionCodes.quality}
                        onSelect={(code) => setOptionCodes((p) => ({ ...p, quality: code }))} />
          <OptionPicker model={model} kind="duration" label="Длительность"
                        selected={optionCodes.duration}
                        onSelect={(code) => setOptionCodes((p) => ({ ...p, duration: code }))} />
          <OptionPicker model={model} kind="audio" label="Звук"
                        selected={optionCodes.audio}
                        onSelect={(code) => setOptionCodes((p) => ({ ...p, audio: code }))} />
```
5. **Цена**: `const cost = model?.recommended_credits ?? 0;` → `const cost = estimatedCredits(model, optionCodes);`
6. **`PendingConfirmation`**: поле `durationSeconds: number` → `optionCodes: Record<string, string>`. В `generate(confirm)` при `confirm=true` брать сохранённые коды, при `confirm=false` — текущие. **Это важно**: подтверждается ровно та цена, которую показали; смена опций после появления баннера не должна утечь в подтверждённый вызов (тот же приём, что был у длительности).
7. **Вызов**: `api.generate(modelCode, question, imageUrl, durationSeconds, confirm)` → `api.generate(modelCode, question, imageUrl, codes, confirm)`.

- [ ] **Step 2: Переписать generate-image**

Те же изменения, кроме слайдера (его там нет). Добавить только секцию `quality` — у image-моделей нет ни длительности, ни звука, и `OptionPicker` для них вернёт `null` сам, но рисовать заведомо пустые секции не нужно:

```tsx
          <OptionPicker model={model} kind="quality" label="Качество"
                        selected={optionCodes.quality}
                        onSelect={(code) => setOptionCodes((p) => ({ ...p, quality: code }))} />
```

Цена, `PendingConfirmation` и вызов — как в video.

- [ ] **Step 3: Typecheck и сборка**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint && npm run build`
Expected: всё зелёное. Если `build` падает на пререндере — проверить, что `useSearchParams` по-прежнему внутри `<Suspense>` (обёртка `Page` → `…Screen`, уже есть).

- [ ] **Step 4: Коммит**

```bash
git add frontend-next/src/app/generate-video/page.tsx frontend-next/src/app/generate-image/page.tsx
git commit -m "feat(generate): секции опций вместо фейкового слайдера

Слайдер 2-15 сек удалён: Kling умеет 5 и 10, Veo -- 4/6/8, Wan считает
кадрами, Ovi не управляется. Пользователь платил за 15с и получал ~5.
Цена в CTA -- recommended_credits x множители выбранных опций.
Подтверждение 409 несёт сохранённые коды: подтверждается ровно та цена,
которую показали."
```

---

### Task 4: e2e

**Files:**
- Modify: `frontend-next/e2e/generate-video.spec.ts`, `frontend-next/e2e/generate-image.spec.ts`

**Interfaces:**
- Consumes: `data-testid` из Task 2 (`option-quality`, `option-duration`, `option-audio`, `option-<kind>-<code>`) и существующие (`generate-prompt`, `generate-submit`, `generate-price`).
- Produces: регрессия на «фронт рисует только то, что умеет модель».

- [ ] **Step 1: Обновить моки и написать тесты**

Прочитать оба спека — они мокают `**/api/models` и `**/api/generate`. Мок моделей теперь обязан отдавать `options`. Тесты:

```ts
test("рисует только те секции, которые есть у модели", async ({ page }) => {
  // мок: модель с duration, БЕЗ quality (как kling -- у fal нет ручки размера)
  await expect(page.getByTestId("option-duration")).toBeVisible();
  await expect(page.getByTestId("option-quality")).toHaveCount(0);
});

test("смена опции меняет цену в CTA", async ({ page }) => {
  // мок: recommended_credits=3220, опции 5s(x1, default) и 10s(x2)
  await expect(page.getByTestId("generate-submit")).toContainText("3220");
  await page.getByTestId("option-duration-10s").click();
  await expect(page.getByTestId("generate-submit")).toContainText("6440");
});

test("шлёт коды выбранных опций, а не сырые значения", async ({ page }) => {
  let body: any;
  await page.route("**/api/generate", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({ json: { request_id: 1, estimated_credits: 6440 } });
  });
  // ... выбрать 10s, отправить ...
  expect(body.option_codes).toEqual({ duration: "10s" });
  expect(body).not.toHaveProperty("duration_seconds");
});

test("модель без опций -- ни одной секции", async ({ page }) => {
  // мок: options: [] (как ovi_video)
  await expect(page.getByTestId("option-duration")).toHaveCount(0);
  await expect(page.getByTestId("option-quality")).toHaveCount(0);
  await expect(page.getByTestId("option-audio")).toHaveCount(0);
});
```

Существующий тест `generates a video end to end` мокал `duration_seconds: 5` — переписать под `option_codes`. **Слайдер удалён: тесты, которые его двигали, переписать под сегменты, не восстанавливать слайдер.**

- [ ] **Step 2: Прогнать сьют**

Бэкенд поднимается в docker; нужны env `TEST_BOT_TOKEN` (= `BOT_TOKEN` из `../.env`) и `TEST_ADMIN_TELEGRAM_ID` (= первый из `ADMIN_IDS`).

Run:
```bash
cd frontend-next
export TEST_BOT_TOKEN=$(grep -m1 '^BOT_TOKEN=' ../.env | cut -d= -f2- | tr -d '\r"')
export TEST_ADMIN_TELEGRAM_ID=$(grep -m1 '^ADMIN_IDS=' ../.env | cut -d= -f2- | cut -d, -f1 | tr -d '\r" ')
npx playwright test --reporter=line
```
Expected: всё зелёное (базовая линия — 16 passed).

- [ ] **Step 3: Коммит**

```bash
git add frontend-next/e2e/generate-video.spec.ts frontend-next/e2e/generate-image.spec.ts
git commit -m "test(e2e): секции опций, цена от множителей, коды в запросе

Ключевая регрессия: модель без опций не должна получить ни одной секции --
именно так выглядит ovi_video, у которого у fal нет ни одной ручки."
```

---

## Приёмка плана

- [ ] `python -m pytest tests/ -q` — зелёный.
- [ ] `cd frontend-next && npx tsc --noEmit && npm run lint && npm run build` — зелёное.
- [ ] `npx playwright test` — зелёный.
- [ ] `grep -rn "duration_seconds\|DURATION_MIN\|DURATION_MAX" frontend-next/src/` — пусто.
- [ ] `grep -rniE "\"(1K|2K|4K|720p|1080p)\"" frontend-next/src/app/generate-*/` — пусто. Ни одного захардкоженного значения качества: всё приходит из `options`.
- [ ] Ручная проверка в реальном Telegram: у `ovi_video` нет ни одной секции; у `veo_video` три (качество, длительность, звук); смена «Без звука» уполовинивает цену в CTA.

**Админка (этап 7) в этот план НЕ входит** — вынесена в отдельный, потому что самостоятельна: множители и активность опций можно править миграцией, пока UI не готов. Заводить её здесь означало бы протащить в план задачу, для которой у меня не было готового кода, — а план без кода не план.

## Что этот план закрывает

- **Переплату за длительность у Wan и Ovi**: пользователь ставил слайдер на 15 с, платил `ceil(15/5 × recommended)` = тройную цену, а получал ~5 с — у обеих моделей поля длительности нет.
- **Двойную цену за звук Veo**: `generate_audio=true` включался молча, удваивая себестоимость ($0.40/с против $0.20/с). Теперь это выбор пользователя, и он вдвое дешевле.
- **Селектор качества из дизайн-макета** — на моделях, которые его реально поддерживают, с ценами из замеров.

## Известные хвосты

- **`ovi_video`**: влияние `resolution` на цену не измерено ($0.20/видео, тариф плоский). Опций нет, секций не будет.
- **Композиция разрешения со звуком у Veo** не проверена (4k+звук стоил бы $3.20 при остатке $1.43). Умножение — обоснованное допущение: для пары «длительность × звук» оно подтверждено замерами.
- **Пакеты кредитов**: после плана 1 видео подорожало (Kling 850 → 3220), START (1000 кредитов) не покрывает одну генерацию. Продуктовое решение, вне этих планов.
