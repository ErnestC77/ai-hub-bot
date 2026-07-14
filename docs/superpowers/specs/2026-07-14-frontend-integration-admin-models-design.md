# Frontend Integration — Admin: Models

## Контекст

Продолжение модернизации admin-панели. Смёржено: Tariffs → Packages +
Settings, Users. Пользователь выбрал вкладку **Models** следующей.

`AdminModels.tsx` частично сломан: список моделей загружается (`GET
/api/admin/models` — URL совпадает с реальным бэкендом), переключение
`is_active` тоже работает (`PATCH /api/admin/models/{code}`, тело
`{is_active}` — поле существует у реального `AiModelUpdateRequest`). Но
поле «Кредитов», которое редактирует `credit_cost`, **тихо ничего не
делает**: у реального `AiModel` такого поля нет вообще (`app/api/routes/
admin.py:288-301`, `AiModelAdminOut`/`_to_model_out`) — вместо него
`min_credits`/`recommended_credits`, как у кредитных пакетов. FastAPI/
Pydantic по умолчанию игнорирует неизвестные поля тела запроса, поэтому
`PATCH .../models/{code}` с `{credit_cost: N}` возвращает 200 с
**неизменённой** моделью — админ видит «сохранено», но ничего не
поменялось.

Также `AdminModelOut.category: ModelCategory` использует устаревший
глобальный тип `ModelCategory` (`fast/medium/premium/image/video` —
пережиток системы до credit-system-v2, всё ещё используется `ToolOut`,
вне скоупа трогать сам этот тип), тогда как реальный `AiModel.category`
теперь — `text/image/video`. `is_premium` тоже не существует у реального
`AiModel` — вместо него `tier` (`economy/standard/premium/pro/ultra`, тот
же union, что уже используют `ModelOut`/`ModelPicker.tsx` для пользовательских
экранов).

Пользователь выбрал добавить для редактирования, помимо `is_active` +
`min_credits`/`recommended_credits`, ещё `is_visible` и `sort_order`.

## Scope

**В скоупе:**
- `client.ts`: переписать `AdminModelOut` 1:1 под реальный `AiModelAdminOut`;
  заменить `toggleModel`/`updateModelCreditCost` на один универсальный
  `updateModel(code, patch)` (тот же паттерн, что `updatePackage` из
  под-фазы Packages+Settings).
- `AdminModels.tsx`: переписать под новый `AdminModelOut` — read-only
  подпись (`provider`/`category`/`tier`), редактируемые `is_active`/
  `is_visible` (переключатели), `min_credits`/`recommended_credits`/
  `sort_order` (числовые поля, onBlur — паттерн `AdminPackages.tsx`).

**Вне скоупа:**
- `provider_model_id`/`input_price_usd_per_1m_tokens`/
  `output_price_usd_per_1m_tokens` — не выводятся для редактирования в
  этой под-фазе (более технические поля, не нужны для повседневного
  админства; можно добавить позже при необходимости).
- Устаревший глобальный тип `ModelCategory` в `client.ts` — не трогается
  (используется `ToolOut`, отдельная уборка вне скоупа); `AdminModelOut`
  вместо него получает собственный инлайн-union `"text" | "image" |
  "video"`, тот же паттерн, что уже применён в `api.models(category)`
  (фаза Generate).
- Payments/Stats/Banners вкладки — свои будущие под-фазы.
- Бэкенд не трогается — `/api/admin/models` (GET/PATCH) уже существует
  и работает.

## Изменения

### 1. `client.ts` — `AdminModelOut` + `updateModel`

Текущий код (`client.ts:228-236`):

```ts
export interface AdminModelOut {
  model_code: string;
  provider: string;
  display_name: string;
  category: ModelCategory;
  credit_cost: number;
  is_active: boolean;
  is_premium: boolean;
}
```

заменить на (1:1 с реальным `AiModelAdminOut`, `admin.py:288-301`):

```ts
export interface AdminModelOut {
  code: string;
  provider: string;
  category: "text" | "image" | "video";
  tier: "economy" | "standard" | "premium" | "pro" | "ultra";
  display_name: string;
  provider_model_id: string;
  input_price_usd_per_1m_tokens: number;
  output_price_usd_per_1m_tokens: number;
  min_credits: number;
  recommended_credits: number;
  is_active: boolean;
  is_visible: boolean;
  sort_order: number;
}
```

В `adminApi` (`client.ts:288-297`) заменить `toggleModel`/
`updateModelCreditCost`:

Текущий код:

```ts
  toggleModel: (modelCode: string, isActive: boolean) =>
    request<AdminModelOut>(`/api/admin/models/${modelCode}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    }),
  updateModelCreditCost: (modelCode: string, creditCost: number) =>
    request<AdminModelOut>(`/api/admin/models/${modelCode}`, {
      method: "PATCH",
      body: JSON.stringify({ credit_cost: creditCost }),
    }),
```

заменить на:

```ts
  updateModel: (
    code: string,
    patch: Partial<Pick<AdminModelOut, "is_active" | "is_visible" | "min_credits" | "recommended_credits" | "sort_order">>,
  ) => request<AdminModelOut>(`/api/admin/models/${code}`, { method: "PATCH", body: JSON.stringify(patch) }),
```

(Один универсальный метод вместо двух — тот же паттерн, что
`adminApi.updatePackage` в уже смёрженной под-фазе Packages+Settings;
`AiModelUpdateRequest` на бэкенде (`admin.py:330-338`) принимает больше
полей, чем мы редактируем — `Partial<Pick<...>>` намеренно ограничивает
набор редактируемых с фронта пятью полями из скоупа этой под-фазы.)

### 2. `AdminModels.tsx` — переписать под новый тип

```tsx
"use client";

import { useEffect, useState } from "react";

import { adminApi, type AdminModelOut } from "@/api/client";
import { Cell } from "@/components/ui/cell";
import { Input } from "@/components/ui/input";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";

export default function AdminModels() {
  const [models, setModels] = useState<AdminModelOut[] | null>(null);

  useEffect(() => {
    adminApi.models().then(setModels).catch(() => setModels([]));
  }, []);

  function applyUpdate(updated: AdminModelOut) {
    setModels((prev) => prev?.map((m) => (m.code === updated.code ? updated : m)) ?? null);
  }

  async function updateField(
    code: string,
    patch: Partial<Pick<AdminModelOut, "min_credits" | "recommended_credits" | "sort_order">>,
  ) {
    applyUpdate(await adminApi.updateModel(code, patch));
  }

  async function toggle(code: string, field: "is_active" | "is_visible", value: boolean) {
    applyUpdate(await adminApi.updateModel(code, { [field]: value }));
  }

  if (models === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <List>
      <Section header="Модели">
        {models.map((m) => (
          <Cell
            key={m.code}
            multiline
            subtitle={`${m.provider} · ${m.category} · ${m.tier}`}
            after={
              <div className="flex flex-col items-end gap-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-foreground-muted">Активна</span>
                  <Switch checked={m.is_active} onChange={(e) => toggle(m.code, "is_active", e.target.checked)} />
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-foreground-muted">Видима</span>
                  <Switch checked={m.is_visible} onChange={(e) => toggle(m.code, "is_visible", e.target.checked)} />
                </div>
              </div>
            }
          >
            <div className="flex flex-col gap-1.5">
              <span>{m.display_name}</span>
              <div className="flex flex-wrap gap-1.5">
                <Input
                  header="Мин. кредитов"
                  type="number"
                  className="w-[90px]"
                  defaultValue={m.min_credits}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== m.min_credits && value > 0) updateField(m.code, { min_credits: value });
                  }}
                />
                <Input
                  header="Реком. кредитов"
                  type="number"
                  className="w-[90px]"
                  defaultValue={m.recommended_credits}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== m.recommended_credits && value > 0)
                      updateField(m.code, { recommended_credits: value });
                  }}
                />
                <Input
                  header="Порядок"
                  type="number"
                  className="w-[70px]"
                  defaultValue={m.sort_order}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== m.sort_order) updateField(m.code, { sort_order: value });
                  }}
                />
              </div>
            </div>
          </Cell>
        ))}
      </Section>
    </List>
  );
}
```

(`sort_order` намеренно без ограничения `> 0` — 0 и отрицательные значения
валидны как порядок сортировки, в отличие от кредитов. Паттерн `after` с
двумя `Switch` в столбик — новый для этого экрана, но использует только
существующие примитивы `Switch`/`flex`, ничего нового в UI-ките.)

## Тестирование

`npx tsc --noEmit` + `npm run build` (без unit-тестов React). Проверено:
`frontend-next/e2e/admin-models.spec.ts` проверяет только вкладку/заголовок
секции «Модели» (не конкретные поля модели) — **не требует правок**, как и
`admin-users.spec.ts` в прошлой под-фазе. Критерий готовности — зелёная
сборка, весь `admin-*` e2e заблокирован `[[ai_hub_bot_e2e_mock_bug]]`.

Ручной smoke-тест (реальный бэкенд, админ-аккаунт):
1. Вкладка «Модели» показывает реальные модели из сида
   (`app/db/seed.py`) с подписью `provider · category · tier`.
2. Переключить «Активна»/«Видима» — сохраняется, в network виден `PATCH`
   с соответствующим полем.
3. Изменить «Мин. кредитов»/«Реком. кредитов»/«Порядок» — сохраняется
   по `onBlur`, значение персистентно после перезагрузки страницы.

## Известные ограничения после этой фазы

- `provider_model_id`/цены за токены не редактируются в этой под-фазе.
- Payments/Stats/Banners вкладки не тронуты — свои будущие под-фазы.
- Ошибки `PATCH` (422 при некорректных данных) не показываются в UI —
  необработанный reject в консоли, тот же уровень, что и везде в этой
  админ-панели сейчас.
