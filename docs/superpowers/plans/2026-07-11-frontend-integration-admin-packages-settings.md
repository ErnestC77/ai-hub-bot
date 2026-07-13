# Admin: Tariffs → Packages + Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the dead admin «Тарифы» tab (its `GET/PATCH /api/admin/tariffs` endpoint no longer exists) and replace it with two new tabs — «Пакеты» and «Настройки» — backed by the already-working `GET/PATCH /api/admin/packages` and `GET/PATCH /api/admin/settings` endpoints.

**Architecture:** Frontend-only change inside `frontend-next/`. The API client (`src/api/client.ts`) swaps 3 dead exports for 4 new ones; two new screen components copy the established `AdminModels.tsx` pattern (onBlur number inputs + `Switch`, `List`/`Section`/`Cell`); the single-page tab switcher (`src/app/admin/page.tsx`) drops the `tariffs` tab and gains `packages`/`settings` tabs. The backend (`app/api/routes/admin.py:358-480`) is verification-reference only — it is NOT modified.

**Tech Stack:** Next.js 16.2.10, React 19.2.4, TypeScript 5, Playwright e2e, Tailwind 4.

**Spec (ground truth):** `docs/superpowers/specs/2026-07-11-frontend-integration-admin-packages-settings-design.md`

## Global Constraints

- **Backend untouched.** No file under `app/` is modified. `GET/PATCH /api/admin/packages` (`app/api/routes/admin.py:358-411`) and `GET/PATCH /api/admin/settings` (`app/api/routes/admin.py:414-480`) already exist and work.
- **No create-UI.** Packages/settings are read + edit-existing-rows only — the backend has no POST for either resource (GET+PATCH only).
- **Non-editable fields stay non-editable.** `updatePackage` must not allow `title`/`description`/`code` (backend `PackageUpdateRequest`, `admin.py:390-394`, does not accept them); `updateSetting` sends bare `{ value }` only (backend `SettingUpdateRequest`, `admin.py:433-434`; `type`/`description` are frozen at seed time).
- **Russian UI copy, verbatim from spec:** tab labels «Пакеты» / «Настройки»; section headers «Пакеты» / «Настройки»; input headers «Кредитов», «Цена ₽», «Цена ⭐».
- **PATCH error handling is intentionally NOT improved** in this sub-phase: a 422 from `_validate_setting_value` surfaces as an unhandled promise rejection in the browser console, same level as existing `AdminModels.tsx`. Do not add error toasts/try-catch beyond what the spec's code shows.
- **e2e reality check:** ALL `admin-*.spec.ts` (and most other e2e) are currently red because the real Telegram SDK script (`beforeInteractive`) clobbers the mocked initData before `lib/telegram.ts` reads it — a known pre-existing bug, out of scope here. The two new e2e specs must be written to the existing pattern, but the completion criterion for each task is `npx tsc --noEmit` + `npm run build` green, NOT a green Playwright run (same precedent as every prior sub-phase except Generate).
- **Next.js 16 warning** (`frontend-next/AGENTS.md`): this Next.js version has breaking changes vs training data — consult `node_modules/next/dist/docs/` before writing any non-spec Next.js code. (This plan only uses plain React client components, no new Next.js APIs.)
- All `npx`/`npm` commands below run from `frontend-next/` (bash: `cd frontend-next && <cmd>`).
- Route count in `npm run build` output stays the same (7 routes); `/admin` is the same single route — only its internal tabs change.

## File Map

| File | Action | Task |
|---|---|---|
| `frontend-next/src/screens/admin/AdminTariffs.tsx` | Delete | 1 |
| `frontend-next/e2e/admin-tariffs.spec.ts` | Delete | 1 |
| `frontend-next/src/api/client.ts` | Modify (swap 3 dead exports for 4 new) | 1 |
| `frontend-next/src/app/admin/page.tsx` | Modify (Task 1: remove tariffs tab; Task 2: add packages/settings tabs) | 1, 2 |
| `frontend-next/src/screens/admin/AdminPackages.tsx` | Create | 2 |
| `frontend-next/src/screens/admin/AdminSettings.tsx` | Create | 2 |
| `frontend-next/e2e/admin-packages.spec.ts` | Create | 2 |
| `frontend-next/e2e/admin-settings.spec.ts` | Create | 2 |

Line numbers below are verified against the repo as of commit `e167721` (branch `master`).

---

### Task 1: client.ts API swap + delete the dead Tariffs tab

Remove every trace of the dead tariffs admin API and screen, and add the new `packages`/`settings` client API in the same pass (the swap is atomic so `tsc` stays green at the end of the task). After this task `/admin` has 5 tabs and builds green; the new API surface exists but has no UI consumers yet.

**Files:**
- Delete: `frontend-next/src/screens/admin/AdminTariffs.tsx`
- Delete: `frontend-next/e2e/admin-tariffs.spec.ts`
- Modify: `frontend-next/src/api/client.ts:225-236` (delete `AdminTariffOut`), `:251` (insert new types after `BannerWriteFields`), `:286-288` (replace `tariffsAdmin`/`updateTariff` with 4 new methods)
- Modify: `frontend-next/src/app/admin/page.tsx:12` (drop import), `:20` (drop TABS entry), `:51` (drop render line)

**Interfaces:**
- Consumes: existing `request<T>` helper and `adminApi` object in `client.ts` (unchanged).
- Produces (Task 2 relies on these exact names/signatures):
  - `export interface AdminPackageOut { code: string; title: string; credits: number; price_rub: number; price_stars: number; description: string | null; is_active: boolean }`
  - `export interface AdminSettingOut { key: string; value: string; type: "int" | "float" | "bool" | "str"; description: string | null }`
  - `adminApi.packages(): Promise<AdminPackageOut[]>`
  - `adminApi.updatePackage(code: string, patch: Partial<Pick<AdminPackageOut, "credits" | "price_rub" | "price_stars" | "is_active">>): Promise<AdminPackageOut>`
  - `adminApi.settings(): Promise<AdminSettingOut[]>`
  - `adminApi.updateSetting(key: string, value: string): Promise<AdminSettingOut>`

- [ ] **Step 1: Confirm current dead-code references (baseline "failing test")**

Run from repo root:
```bash
grep -rn "AdminTariffOut\|tariffsAdmin\|updateTariff\|AdminTariffs" frontend-next/src frontend-next/e2e
```
Expected: exactly 3 files hit — `frontend-next/src/api/client.ts` (lines 225, 286-288), `frontend-next/src/app/admin/page.tsx` (lines 12, 51), `frontend-next/src/screens/admin/AdminTariffs.tsx` (whole file). Nothing else in `src/` or `e2e/` (other than `e2e/admin-tariffs.spec.ts`, which greps only «Тарифы» text, not these symbols) references them. If anything else appears, STOP — the repo changed since this plan was verified; re-verify before proceeding.

- [ ] **Step 2: Delete the dead screen and its e2e spec**

```bash
git rm frontend-next/src/screens/admin/AdminTariffs.tsx frontend-next/e2e/admin-tariffs.spec.ts
```

- [ ] **Step 3: Delete `AdminTariffOut` from `client.ts`**

In `frontend-next/src/api/client.ts`, delete this entire block (lines 225-236, between `AdminModelOut` and `AdminBannerOut`, plus one of the surrounding blank lines so exactly one blank line remains between `AdminModelOut` and `AdminBannerOut`):

```ts
export interface AdminTariffOut {
  code: string;
  name: string;
  price_rub: number;
  price_stars: number;
  fast_limit: number;
  medium_limit: number;
  premium_limit: number;
  image_limit: number;
  daily_limit: number;
  is_active: boolean;
}
```

- [ ] **Step 4: Add `AdminPackageOut` / `AdminSettingOut` after `BannerWriteFields`**

In `frontend-next/src/api/client.ts`, find (was line 251):

```ts
export type BannerWriteFields = Omit<AdminBannerOut, "id">;
```

Immediately after it (before `export const adminApi = {`), insert, separated by blank lines:

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

(Shapes verified against backend `PackageAdminOut` at `app/api/routes/admin.py:360-367` and `SettingOut` at `admin.py:416-420`. Backend declares `type: str`, but the only values are the four the seed writes and `_validate_setting_value` (`admin.py:437-464`) checks — the narrowed union is intentional per spec.)

- [ ] **Step 5: Replace `tariffsAdmin`/`updateTariff` with the 4 new methods**

In `frontend-next/src/api/client.ts`, inside `adminApi`, replace these three lines (were 286-288, directly after the `updateModelCreditCost` entry, before `banners`):

```ts
  tariffsAdmin: () => request<AdminTariffOut[]>("/api/admin/tariffs"),
  updateTariff: (code: string, patch: Partial<AdminTariffOut>) =>
    request<AdminTariffOut>(`/api/admin/tariffs/${code}`, { method: "PATCH", body: JSON.stringify(patch) }),
```

with:

```ts
  packages: () => request<AdminPackageOut[]>("/api/admin/packages"),
  updatePackage: (code: string, patch: Partial<Pick<AdminPackageOut, "credits" | "price_rub" | "price_stars" | "is_active">>) =>
    request<AdminPackageOut>(`/api/admin/packages/${code}`, { method: "PATCH", body: JSON.stringify(patch) }),
  settings: () => request<AdminSettingOut[]>("/api/admin/settings"),
  updateSetting: (key: string, value: string) =>
    request<AdminSettingOut>(`/api/admin/settings/${key}`, { method: "PATCH", body: JSON.stringify({ value }) }),
```

- [ ] **Step 6: Remove the tariffs tab from `admin/page.tsx`**

In `frontend-next/src/app/admin/page.tsx`, delete these three lines (were 12, 20, 51 — leave everything else untouched; Task 2 adds the replacement tabs):

```tsx
import AdminTariffs from "@/screens/admin/AdminTariffs";
```

```tsx
  { key: "tariffs", label: "Тарифы" },
```

```tsx
      {tab === "tariffs" && <AdminTariffs />}
```

- [ ] **Step 7: Verify no references remain**

```bash
grep -rn "AdminTariffOut\|tariffsAdmin\|updateTariff\|AdminTariffs\|admin/tariffs" frontend-next/src frontend-next/e2e
```
Expected: no matches (exit code 1).

- [ ] **Step 8: Typecheck and build**

```bash
cd frontend-next && npx tsc --noEmit
```
Expected: exit 0, no output.

```bash
cd frontend-next && npm run build
```
Expected: "✓ Compiled successfully", route table includes `/admin`, same 7 routes as before this change.

- [ ] **Step 9: Commit**

```bash
git add frontend-next/src/api/client.ts frontend-next/src/app/admin/page.tsx
git commit -m "refactor(frontend): remove dead admin Tariffs tab, add packages/settings admin API client"
```
(The two `git rm`-ed files from Step 2 are already staged.)

---

### Task 2: AdminPackages + AdminSettings screens, tabs, e2e specs

Add the two new screens (1:1 pattern with `AdminModels.tsx`), wire them into the `/admin` tab switcher, and add the two shallow e2e specs. TDD via `tsc`: wire the tabs first so the compiler fails on the missing modules, then create the screens to make it pass.

**Files:**
- Modify: `frontend-next/src/app/admin/page.tsx` (import block, `TABS`, tab-render block — post-Task-1 state)
- Create: `frontend-next/src/screens/admin/AdminPackages.tsx`
- Create: `frontend-next/src/screens/admin/AdminSettings.tsx`
- Create: `frontend-next/e2e/admin-packages.spec.ts`
- Create: `frontend-next/e2e/admin-settings.spec.ts`

**Interfaces:**
- Consumes (from Task 1, `@/api/client`): `AdminPackageOut`, `AdminSettingOut`, `adminApi.packages()`, `adminApi.updatePackage(code, patch)`, `adminApi.settings()`, `adminApi.updateSetting(key, value)` — exact signatures in Task 1's Produces block.
- Consumes (existing UI kit): `Cell`, `Input`, `List`, `Placeholder`, `Section`, `Spinner`, `Switch` from `@/components/ui/*` (same imports `AdminModels.tsx` uses).
- Produces: default-exported React components `AdminPackages` and `AdminSettings`, rendered by `admin/page.tsx`.

- [ ] **Step 1: Wire the tabs first (failing state)**

In `frontend-next/src/app/admin/page.tsx` (post-Task-1 state), make three edits so the import block, `TABS`, and render block become exactly:

Import block (alphabetical; `AdminPackages` after `AdminModels`, `AdminSettings` after `AdminPayments`):

```tsx
import AdminBanners from "@/screens/admin/AdminBanners";
import AdminModels from "@/screens/admin/AdminModels";
import AdminPackages from "@/screens/admin/AdminPackages";
import AdminPayments from "@/screens/admin/AdminPayments";
import AdminSettings from "@/screens/admin/AdminSettings";
import AdminStats from "@/screens/admin/AdminStats";
import AdminUsers from "@/screens/admin/AdminUsers";
```

`TABS` array:

```tsx
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

Tab-render block (insert the two new lines between the `models` and `banners` lines):

```tsx
      {tab === "stats" && <AdminStats />}
      {tab === "users" && <AdminUsers />}
      {tab === "payments" && <AdminPayments />}
      {tab === "models" && <AdminModels />}
      {tab === "packages" && <AdminPackages />}
      {tab === "settings" && <AdminSettings />}
      {tab === "banners" && <AdminBanners />}
```

- [ ] **Step 2: Run tsc to verify it fails**

```bash
cd frontend-next && npx tsc --noEmit
```
Expected: FAIL with two TS2307 errors:
```
src/app/admin/page.tsx:10:27 - error TS2307: Cannot find module '@/screens/admin/AdminPackages' or its corresponding type declarations.
src/app/admin/page.tsx:12:27 - error TS2307: Cannot find module '@/screens/admin/AdminSettings' or its corresponding type declarations.
```
(Line/column may differ slightly; the two TS2307 errors on the two new imports are what matters.)

- [ ] **Step 3: Create `frontend-next/src/screens/admin/AdminPackages.tsx`**

Exact content (spec section 2, verbatim):

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

- [ ] **Step 4: Create `frontend-next/src/screens/admin/AdminSettings.tsx`**

Exact content (spec section 3, verbatim). `value` renders per `type`: `bool` → `Switch` (string↔boolean mapping), `int`/`float` → number `Input`, `str` → text `Input`; every branch sends the value back as a string (backend stores `value` as `str` and casts on read):

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

Do NOT add error handling around `save()` beyond this — a 422 from the backend intentionally stays an unhandled rejection in the console this sub-phase (Global Constraints).

- [ ] **Step 5: Run tsc to verify it passes**

```bash
cd frontend-next && npx tsc --noEmit
```
Expected: exit 0, no output.

- [ ] **Step 6: Create the two e2e specs**

Same shallow depth as the other `admin-*.spec.ts` (tab renders + section header, no CRUD): the spec's test bodies, completed with the standard import + admin `beforeEach` header that every existing admin spec uses (copied from the deleted `admin-tariffs.spec.ts` / current `admin-banners.spec.ts`).

`frontend-next/e2e/admin-packages.spec.ts`, exact content:

```ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  const adminId = Number(process.env.TEST_ADMIN_TELEGRAM_ID);
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token", adminId);
});

test("admin packages tab renders the packages section", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Пакеты")).toHaveCount(1); // only the tab label
  await page.getByRole("button", { name: "Пакеты" }).click();
  await expect(page.getByText("Пакеты")).toHaveCount(2); // tab label + Section header
});
```

`frontend-next/e2e/admin-settings.spec.ts`, exact content:

```ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  const adminId = Number(process.env.TEST_ADMIN_TELEGRAM_ID);
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token", adminId);
});

test("admin settings tab renders the settings section", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Настройки")).toHaveCount(1); // only the tab label
  await page.getByRole("button", { name: "Настройки" }).click();
  await expect(page.getByText("Настройки")).toHaveCount(2); // tab label + Section header
});
```

Do NOT run `npm run test:e2e` as a gate: all `admin-*.spec.ts` are red from the pre-existing Telegram-SDK mock bug (Global Constraints). These specs exist so the suite covers the new tabs once that bug is fixed.

- [ ] **Step 7: Full verification — typecheck, lint, build**

```bash
cd frontend-next && npx tsc --noEmit
```
Expected: exit 0, no output.

```bash
cd frontend-next && npm run lint
```
Expected: exit 0 (no errors; warnings acceptable only if pre-existing).

```bash
cd frontend-next && npm run build
```
Expected: "✓ Compiled successfully"; route table has the same 7 routes as before the sub-phase, including `/admin`.

- [ ] **Step 8: Commit**

```bash
git add frontend-next/src/screens/admin/AdminPackages.tsx frontend-next/src/screens/admin/AdminSettings.tsx frontend-next/src/app/admin/page.tsx frontend-next/e2e/admin-packages.spec.ts frontend-next/e2e/admin-settings.spec.ts
git commit -m "feat(frontend): admin Packages + Settings tabs replacing dead Tariffs tab"
```

---

## Manual smoke test (after both tasks, real backend, admin account)

Not a task gate (needs a live deployment), but the acceptance pass from the spec:

1. Open `/admin` as an admin → tabs read Статистика / Пользователи / Платежи / Модели / Пакеты / Настройки / Карусель.
2. «Пакеты» tab lists the real seeded `CREDIT_PACKAGES` (`start`/`basic`/`plus`/...). Change `credits` on one and blur → `PATCH /api/admin/packages/{code}` visible in the network tab, value persists after reload.
3. «Настройки» tab lists the 10 seeded rows. Set `rub_per_credit` to a non-numeric value → `PATCH` returns 422 with a Russian `detail`; visible in console only, not in the UI (expected, per spec).

## Known limitations carried forward (from spec, unchanged)

- Users/Models/Payments/Stats/Banners tabs untouched — `AdminUsers.tsx` still calls nonexistent endpoints (`grantSubscription`/`cancelSubscription`/`grantCredits`), `AdminModelOut` still mismatches backend `AiModelAdminOut`; future sub-phases.
- 422 on `PATCH /admin/settings/{key}` not surfaced in UI.
- No create-new-package/setting UI (backend doesn't support it).
