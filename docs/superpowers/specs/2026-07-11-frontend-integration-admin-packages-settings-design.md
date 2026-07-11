# Frontend Integration — Admin: Tariffs → Packages + Settings

## Контекст

Продолжение проекта связывания `frontend-next/` с переписанным бэкендом
credit-system-v2. Все обычные пользовательские экраны (Account, Chat,
Generate image/video, Tariffs→Credits) смёржены; Trends/Referral/Settings
проверены и уже рабочие без изменений. Следующее направление — admin-панель
(`frontend-next/src/screens/admin/*`, единая страница `/admin` с вкладками
через `SegmentedControl`), большой отдельный под-проект. Пользователь выбрал
первой под-фазой: заменить вкладку «Тарифы» на «Пакеты» + «Настройки».

`frontend-next/src/screens/admin/AdminTariffs.tsx` зовёт
`adminApi.tariffsAdmin()` → `GET /api/admin/tariffs` — этого эндпойнта в
`app/api/routes/admin.py` больше нет (тарифы полностью заменены кредитными
пакетами в бэкенд-rebuild'е фаз 1-4). Экран редактирует поля
`fast_limit`/`medium_limit`/`premium_limit`/`image_limit`/`daily_limit` —
устаревшая модель категорийных лимитов, у `CreditPackage`/`Setting` таких
полей нет и быть не может.

При этом бэкенд с фазы 5 уже предоставляет рабочие `GET/PATCH
/api/admin/packages` (`app/api/routes/admin.py:358-411`) и `GET/PATCH
/api/admin/settings` (`:414-480`) — на фронте для них до сих пор нет ни
типов в `client.ts`, ни экранов, ни вкладок.

## Scope

**В скоупе:**
- Удалить `frontend-next/src/screens/admin/AdminTariffs.tsx`,
  `frontend-next/e2e/admin-tariffs.spec.ts`.
- `frontend-next/src/api/client.ts`: удалить `AdminTariffOut`,
  `adminApi.tariffsAdmin`, `adminApi.updateTariff`; добавить
  `AdminPackageOut`/`adminApi.packages`/`adminApi.updatePackage` и
  `AdminSettingOut`/`adminApi.settings`/`adminApi.updateSetting`.
- Новый `frontend-next/src/screens/admin/AdminPackages.tsx`.
- Новый `frontend-next/src/screens/admin/AdminSettings.tsx`.
- `frontend-next/src/app/admin/page.tsx`: вкладка `tariffs` → две вкладки
  `packages`/`settings`.
- Новые `frontend-next/e2e/admin-packages.spec.ts`,
  `frontend-next/e2e/admin-settings.spec.ts`.

**Вне скоупа (свои будущие под-фазы):**
- Вкладки Users/Models/Payments/Stats/Banners — не трогаются в этой
  под-фазе, даже там, где уже известны проблемы (`AdminUsers.tsx` зовёт
  несуществующие `adminApi.grantSubscription`/`cancelSubscription`/
  `grantCredits` → `/grant`, `/cancel-subscription`, `/grant-credits`;
  `AdminModelOut` в `client.ts` не совпадает с реальной `AiModelAdminOut`).
- Бэкенд не трогается вообще — `/api/admin/packages` и `/api/admin/settings`
  уже существуют и работают (используются только `credit_service`/
  `settings_service`, без изменений).
- Создание новых пакетов/настроек (только чтение + редактирование уже
  существующих строк — ни один из бэкенд-эндпойнтов не поддерживает POST
  для packages/settings, только GET+PATCH).

## Изменения

### 1. `client.ts` — удалить мёртвое, добавить новое

Удалить `AdminTariffOut` (`client.ts:225-236`) и `adminApi.tariffsAdmin`/
`adminApi.updateTariff` (`client.ts:286-288`).

Добавить рядом с `AdminBannerOut` (после него, перед `adminApi`):

```ts
export interface AdminPackageOut {
  code: string;
  title: string;
  credits: number;
  price_rub: number;
  price_stars: number;
  description: string | null;
  is_active: boolean;
}

export interface AdminSettingOut {
  key: string;
  value: string;
  type: "int" | "float" | "bool" | "str";
  description: string | null;
}
```

(`type` — реальные значения из `app/db/models` / засеянных строк
`app/db/seed.py:10-32`, все текущие строки `int`/`float`, но бэкенд
поддерживает и `bool`/`str` — `_validate_setting_value` в
`app/api/routes/admin.py:437-464` проверяет все четыре.)

В `adminApi`, рядом с `models`/`toggleModel`/`updateModelCreditCost`
(после них, вместо удаляемых `tariffsAdmin`/`updateTariff`):

```ts
  packages: () => request<AdminPackageOut[]>("/api/admin/packages"),
  updatePackage: (code: string, patch: Partial<Pick<AdminPackageOut, "credits" | "price_rub" | "price_stars" | "is_active">>) =>
    request<AdminPackageOut>(`/api/admin/packages/${code}`, { method: "PATCH", body: JSON.stringify(patch) }),
  settings: () => request<AdminSettingOut[]>("/api/admin/settings"),
  updateSetting: (key: string, value: string) =>
    request<AdminSettingOut>(`/api/admin/settings/${key}`, { method: "PATCH", body: JSON.stringify({ value }) }),
```

(`updatePackage`'s `Partial<Pick<...>>` намеренно исключает `title`/
`description`/`code` из редактируемых полей — бэкендовый
`PackageUpdateRequest` их не принимает вообще, см. `admin.py:390-394`;
`updateSetting` шлёт голый `{value}` — `SettingUpdateRequest` не принимает
ничего другого, см. `admin.py:433-434`, `type`/`description` заморожены на
сиде и не редактируются.)

### 2. `AdminPackages.tsx` — список + инлайн-редактирование

Паттерн 1:1 с `AdminModels.tsx` (onBlur-числовые поля + `Switch` для
`is_active`, `List`/`Section`/`Cell`):

```tsx
"use client";

import { useState, useEffect } from "react";

import { adminApi, type AdminPackageOut } from "@/api/client";
import { Cell } from "@/components/ui/cell";
import { Input } from "@/components/ui/input";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";

export default function AdminPackages() {
  const [packages, setPackages] = useState<AdminPackageOut[] | null>(null);

  useEffect(() => {
    adminApi.packages().then(setPackages).catch(() => setPackages([]));
  }, []);

  function applyUpdate(updated: AdminPackageOut) {
    setPackages((prev) => prev?.map((p) => (p.code === updated.code ? updated : p)) ?? null);
  }

  async function updateField(code: string, patch: Partial<Pick<AdminPackageOut, "credits" | "price_rub" | "price_stars">>) {
    applyUpdate(await adminApi.updatePackage(code, patch));
  }

  async function toggle(code: string, isActive: boolean) {
    applyUpdate(await adminApi.updatePackage(code, { is_active: isActive }));
  }

  if (packages === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <List>
      <Section header="Пакеты">
        {packages.map((p) => (
          <Cell
            key={p.code}
            multiline
            subtitle={p.description ?? undefined}
            after={<Switch checked={p.is_active} onChange={(e) => toggle(p.code, e.target.checked)} />}
          >
            <div className="flex flex-col gap-1.5">
              <span>{p.title}</span>
              <div className="flex flex-wrap gap-1.5">
                <Input
                  header="Кредитов"
                  type="number"
                  className="w-[90px]"
                  defaultValue={p.credits}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== p.credits && value > 0) updateField(p.code, { credits: value });
                  }}
                />
                <Input
                  header="Цена ₽"
                  type="number"
                  className="w-[90px]"
                  defaultValue={p.price_rub}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== p.price_rub && value > 0) updateField(p.code, { price_rub: value });
                  }}
                />
                <Input
                  header="Цена ⭐"
                  type="number"
                  className="w-[90px]"
                  defaultValue={p.price_stars}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== p.price_stars && value > 0) updateField(p.code, { price_stars: value });
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

### 3. `AdminSettings.tsx` — список + per-type редактирование значения

`value` рендерится по `type`: `bool` — `Switch` (маппинг строка↔булево),
`int`/`float` — числовой `Input`, `str` — текстовый `Input`. Все ветки шлют
`adminApi.updateSetting(key, value)` со `value`, приведённым обратно к
строке (бэкенд хранит `value` как `str`, кастует сам при чтении).

```tsx
"use client";

import { useEffect, useState } from "react";

import { adminApi, type AdminSettingOut } from "@/api/client";
import { Cell } from "@/components/ui/cell";
import { Input } from "@/components/ui/input";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";

function SettingRow({ setting, onSaved }: { setting: AdminSettingOut; onSaved: (s: AdminSettingOut) => void }) {
  async function save(value: string) {
    onSaved(await adminApi.updateSetting(setting.key, value));
  }

  return (
    <Cell multiline subtitle={setting.description ?? undefined}>
      <div className="flex items-center justify-between gap-2">
        <span>{setting.key}</span>
        {setting.type === "bool" ? (
          <Switch checked={setting.value === "true"} onChange={(e) => save(e.target.checked ? "true" : "false")} />
        ) : (
          <Input
            type={setting.type === "int" || setting.type === "float" ? "number" : "text"}
            className="w-[110px]"
            defaultValue={setting.value}
            onBlur={(e) => {
              if (e.target.value !== setting.value) save(e.target.value);
            }}
          />
        )}
      </div>
    </Cell>
  );
}

export default function AdminSettings() {
  const [settings, setSettings] = useState<AdminSettingOut[] | null>(null);

  useEffect(() => {
    adminApi.settings().then(setSettings).catch(() => setSettings([]));
  }, []);

  if (settings === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <List>
      <Section header="Настройки">
        {settings.map((s) => (
          <SettingRow
            key={s.key}
            setting={s}
            onSaved={(updated) =>
              setSettings((prev) => prev?.map((x) => (x.key === updated.key ? updated : x)) ?? null)
            }
          />
        ))}
      </Section>
    </List>
  );
}
```

(Ошибка `PATCH` — например 422 от `_validate_setting_value` при вводе
нечислового значения в `int`/`float`-поле — не перехватывается отдельно
в этой спеке: `adminApi.updateSetting` бросит `ApiError`, `save()` не
поймает её, React покажет необработанное отклонение промиса в консоли, а
`defaultValue` в некотором расхождении с реальным значением останется до
следующего рефреша страницы. Тот же уровень обработки ошибок, что и в
`AdminModels.tsx`/`AdminTariffs.tsx` уже сейчас — не регрессия, просто не
улучшается в этой под-фазе.)

### 4. `admin/page.tsx` — вкладки

Текущий код, импорты и `TABS` (`frontend-next/src/app/admin/page.tsx:8-22`):

```tsx
import AdminBanners from "@/screens/admin/AdminBanners";
import AdminModels from "@/screens/admin/AdminModels";
import AdminPayments from "@/screens/admin/AdminPayments";
import AdminStats from "@/screens/admin/AdminStats";
import AdminTariffs from "@/screens/admin/AdminTariffs";
import AdminUsers from "@/screens/admin/AdminUsers";

const TABS = [
  { key: "stats", label: "Статистика" },
  { key: "users", label: "Пользователи" },
  { key: "payments", label: "Платежи" },
  { key: "models", label: "Модели" },
  { key: "tariffs", label: "Тарифы" },
  { key: "banners", label: "Карусель" },
] as const;
```

Текущий код, рендер вкладки (`frontend-next/src/app/admin/page.tsx:51`):

```tsx
      {tab === "tariffs" && <AdminTariffs />}
```

Оба блока заменить на:

```tsx
import AdminBanners from "@/screens/admin/AdminBanners";
import AdminModels from "@/screens/admin/AdminModels";
import AdminPackages from "@/screens/admin/AdminPackages";
import AdminPayments from "@/screens/admin/AdminPayments";
import AdminSettings from "@/screens/admin/AdminSettings";
import AdminStats from "@/screens/admin/AdminStats";
import AdminUsers from "@/screens/admin/AdminUsers";

const TABS = [
  { key: "stats", label: "Статистика" },
  { key: "users", label: "Пользователи" },
  { key: "payments", label: "Платежи" },
  { key: "models", label: "Модели" },
  { key: "packages", label: "Пакеты" },
  { key: "settings", label: "Настройки" },
  { key: "banners", label: "Карусель" },
] as const;
```

и:

```tsx
      {tab === "packages" && <AdminPackages />}
      {tab === "settings" && <AdminSettings />}
```

(алфавитный порядок импортов сохраняется; `AdminTariffs`-импорт удаляется
целиком.)

## Тестирование

Нет unit-тестов для React-компонентов в проекте (только Playwright e2e) —
проверка через `npx tsc --noEmit` + `npm run build`. Роутов в сборке
столько же (7), маршрут `/admin` один и тот же, меняются только внутренние
вкладки — количество строк в сводке `npm run build` не меняется.

`e2e/admin-tariffs.spec.ts` удаляется. Новые спеки — тот же уровень
глубины, что у существующих admin-*.spec.ts (рендер вкладки + заголовок
секции, без реальных CRUD-проверок):

```ts
// e2e/admin-packages.spec.ts
test("admin packages tab renders the packages section", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Пакеты")).toHaveCount(1);
  await page.getByRole("button", { name: "Пакеты" }).click();
  await expect(page.getByText("Пакеты")).toHaveCount(2);
});
```
```ts
// e2e/admin-settings.spec.ts
test("admin settings tab renders the settings section", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Настройки")).toHaveCount(1);
  await page.getByRole("button", { name: "Настройки" }).click();
  await expect(page.getByText("Настройки")).toHaveCount(2);
});
```

Как и весь `/admin`-раздел, эти тесты требуют `me.is_admin === true`, что
упирается в [[ai_hub_bot_e2e_mock_bug]] — заблокированы наравне с
остальными `admin-*.spec.ts`, зелёная сборка остаётся критерием готовности
(тот же прецедент, что и во всех прошлых под-фазах кроме Generate).

Ручной smoke-тест (реальный бэкенд): открыть `/admin` под админом, вкладка
«Пакеты» показывает реальные пакеты из `CREDIT_PACKAGES`-сида
(`start`/`basic`/`plus`/...), изменить `credits` у одного — сохраняется
(проверить `PATCH` в network); вкладка «Настройки» показывает 10 засеянных
строк, изменить `rub_per_credit` на нечисловое значение — 422 с русским
`detail` (виден в консоли, не в UI — см. примечание в п.3).

## Известные ограничения после этой фазы

- Users/Models/Payments/Stats/Banners вкладки не тронуты — `AdminUsers.tsx`
  и `AdminModels.tsx` по-прежнему частично или полностью зовут
  несуществующие/несовпадающие бэкенд-эндпойнты, чинится в будущих
  под-фазах.
- Ошибки `PATCH /admin/settings/{key}` (422 на невалидный `value`) не
  показываются пользователю в UI этой под-фазы — только необработанный
  reject в консоли браузера (см. примечание в разделе «Изменения», п.3).
- Создание новых пакетов/настроек не реализуется — бэкенд это не
  поддерживает.
