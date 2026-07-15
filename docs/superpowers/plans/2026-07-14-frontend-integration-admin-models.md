# Admin: Models (real AiModel schema — is_active/is_visible + credits/sort_order editing) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the admin «Модели» tab: the «Кредитов» input silently no-ops — it PATCHes `credit_cost`, a field that no longer exists on the real backend `AiModel` (FastAPI/Pydantic ignores unknown body fields, so the PATCH returns 200 with an unchanged model and the admin believes it saved). Rewrite `AdminModelOut` 1:1 against the real backend `AiModelAdminOut`, replace the two dead methods `toggleModel`/`updateModelCreditCost` with one generic `updateModel(code, patch)`, and rewrite `AdminModels.tsx` to edit `is_active`/`is_visible` (toggles) plus `min_credits`/`recommended_credits`/`sort_order` (onBlur number inputs).

**Architecture:** Frontend-only change inside `frontend-next/`. The API client (`src/api/client.ts`) gets `AdminModelOut` corrected to 1:1 match the backend `AiModelAdminOut` and swaps `toggleModel`+`updateModelCreditCost` for a single `updateModel` (same `Partial<Pick<...>>` pattern as the already-merged `adminApi.updatePackage` right below it in the same object). `AdminModels.tsx` is rewritten with the exact code from the spec's section 2 — read-only subtitle `provider · category · tier`, two `Switch` toggles stacked in `after`, three onBlur number inputs (the `AdminPackages.tsx` pattern). The backend (`app/api/routes/admin.py:288+`) is verification-reference only — it is NOT modified.

**Tech Stack:** Next.js 16.2.10, React 19.2.4, TypeScript 5, Playwright e2e, Tailwind 4.

**Spec (ground truth):** `docs/superpowers/specs/2026-07-14-frontend-integration-admin-models-design.md`

## Global Constraints

- **Backend untouched.** No file under `app/` is modified. `GET /api/admin/models` (`app/api/routes/admin.py:322-327`) and `PATCH /api/admin/models/{code}` (`admin.py:341+`) already exist and work; `AiModelUpdateRequest` (`admin.py:330-338`) accepts `is_active`/`is_visible`/`recommended_credits`/`min_credits`/`provider_model_id`/`input_price_usd_per_1m_tokens`/`output_price_usd_per_1m_tokens`/`sort_order`, all optional — our `updateModel` only ever sends the 5 in-scope fields.
- **`AdminModelOut` must match backend `AiModelAdminOut` (`admin.py:288-301`) exactly** — 13 fields, shapes verbatim in Task 1 Step 2. `model_code`/`credit_cost`/`is_premium` are removed (they no longer exist in the API response); `category` becomes an inline `"text" | "image" | "video"` union; `tier` is the same 5-value union already used by `ModelOut`/`ModelPicker.tsx`.
- **The global `ModelCategory` type is NOT touched** (`client.ts:48`, `fast/medium/premium/image/video`) — it stays used by `recommended_category` at `client.ts:87` (`ToolOut`); `AdminModelOut` merely stops referencing it and gets its own inline union (same pattern as `api.models(category)` from the Generate phase).
- **`updateModel` signature is exactly** `updateModel(code: string, patch: Partial<Pick<AdminModelOut, "is_active" | "is_visible" | "min_credits" | "recommended_credits" | "sort_order">>): Promise<AdminModelOut>` — the `Partial<Pick<...>>` deliberately restricts the frontend to the 5 in-scope fields even though the backend accepts more. `adminApi.models()` stays exactly as it is.
- **Russian UI copy, verbatim from the spec's `AdminModels.tsx` code block:** section header «Модели»; toggle labels «Активна» / «Видима»; input headers «Мин. кредитов» / «Реком. кредитов» / «Порядок»; subtitle `` `${m.provider} · ${m.category} · ${m.tier}` ``. Do not "improve" the wording.
- **Error handling is intentionally NOT improved** in this sub-phase: a failing `PATCH` (404/422) surfaces as an unhandled promise rejection in the browser console, same level as before the rewrite and as the rest of the current admin panel. No try/catch, no toasts.
- **`frontend-next/e2e/admin-models.spec.ts` needs ZERO changes** (verified: its single test only asserts the tab label + «Модели» section header counts, which this rewrite keeps verbatim). Do not touch any e2e file in this sub-phase. All `admin-*.spec.ts` are currently red anyway from the known pre-existing Telegram-SDK mock bug (`beforeInteractive` real SDK clobbers mocked initData) — out of scope. Completion criterion per task is `npx tsc --noEmit` + `npm run build` green (Task 2) or the exact expected red list (Task 1), NOT a green Playwright run — same precedent as the Users sub-phase.
- **Task 1 ends with `tsc` intentionally RED**, errors confined to `src/screens/admin/AdminModels.tsx` only (precedent: the Users plan's client.ts-first split, «typecheck осознанно красный»). Task 1's commit is `wip(frontend)`. Task 2 ends fully green.
- **`sort_order` has no `> 0` guard** in the UI — 0 and negative values are valid sort positions, unlike the two credit fields (spec note under the code block). Keep the guards exactly as the spec's code has them.
- **Next.js 16 warning** (`frontend-next/AGENTS.md`): this Next.js version has breaking changes vs training data — consult `node_modules/next/dist/docs/` before writing any non-spec Next.js code. (This plan only uses plain React client components, no new Next.js APIs.)
- All `npx`/`npm` commands below run from `frontend-next/` (bash: `cd frontend-next && <cmd>`).
- Route count in `npm run build` output stays the same (10 app routes, including `/admin`, plus the automatic `/_not-found`); `/admin` is the same single route — only the Models tab's internals change.

## File Map

| File | Action | Task |
|---|---|---|
| `frontend-next/src/api/client.ts` | Modify (rewrite `AdminModelOut`, swap 2 dead methods for `updateModel`) | 1 |
| `frontend-next/src/screens/admin/AdminModels.tsx` | Rewrite (full file replacement, 68 lines currently) | 2 |
| `frontend-next/e2e/admin-models.spec.ts` | **No change** (verified: asserts only tab label + unchanged «Модели» section header) | — |

Line numbers below are verified against the repo as of commit `5abbf4a` (branch `master`).

---

### Task 1: client.ts — real `AdminModelOut` + generic `updateModel`

Swap the dead pre-credit-system-v2 admin models API surface for the real one. After this task `tsc` is EXPECTED red with exactly 10 errors, all in `src/screens/admin/AdminModels.tsx` (it still references the removed `model_code`/`credit_cost`/`is_premium`/`toggleModel`/`updateModelCreditCost` until Task 2 rewrites it). That red state is intentional and verified as a step below.

**Files:**
- Modify: `frontend-next/src/api/client.ts:228-236` (rewrite `AdminModelOut`), `:288-297` (replace `toggleModel`/`updateModelCreditCost` with `updateModel`; the `models:` entry at `:287` stays untouched)

**Interfaces:**
- Consumes: existing `request<T>` helper and `adminApi` object in `client.ts` (unchanged); `adminApi.models` stays exactly as it is; global `ModelCategory` type stays (still used by `client.ts:87`).
- Produces (Task 2 relies on these exact names/signatures):
  - `export interface AdminModelOut { code: string; provider: string; category: "text" | "image" | "video"; tier: "economy" | "standard" | "premium" | "pro" | "ultra"; display_name: string; provider_model_id: string; input_price_usd_per_1m_tokens: number; output_price_usd_per_1m_tokens: number; min_credits: number; recommended_credits: number; is_active: boolean; is_visible: boolean; sort_order: number }`
  - `adminApi.updateModel(code: string, patch: Partial<Pick<AdminModelOut, "is_active" | "is_visible" | "min_credits" | "recommended_credits" | "sort_order">>): Promise<AdminModelOut>`

- [ ] **Step 1: Confirm current dead-code references (baseline "failing test")**

Run from repo root:
```bash
grep -rn "credit_cost\|is_premium\|toggleModel\|updateModelCreditCost" frontend-next/src frontend-next/e2e
```
Expected: exactly 2 files hit — `frontend-next/src/api/client.ts` (lines 233, 235, 288, 293, 296) and `frontend-next/src/screens/admin/AdminModels.tsx` (lines 22, 27, 46, 55, 58). Nothing in `frontend-next/e2e/` matches. If anything else appears, STOP — the repo changed since this plan was verified (commit `5abbf4a`); re-verify before proceeding.

Note: do NOT use bare `model_code` as a dead-symbol probe — it legitimately appears elsewhere in `client.ts` (`default_model_code` at `:55`, generation request bodies at `:133`/`:140`, `AdminTransactionOut.model_code` at `:212`), all of which stay untouched. Only `AdminModelOut.model_code` (`:229`) and the `m.model_code` usages inside `AdminModels.tsx` die in this sub-phase.

- [ ] **Step 2: Rewrite `AdminModelOut` to match backend `AiModelAdminOut`**

In `frontend-next/src/api/client.ts`, replace this block (lines 228-236):

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

with (1:1 with backend `AiModelAdminOut`, `app/api/routes/admin.py:288-301`; field order matches the backend class):

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

(Backend declares `category`/`tier` as `str`, but `_to_model_out` (`admin.py:304-319`) emits `m.category.value`/`m.tier.value` from the DB enums — the narrowed unions are intentional per spec and identical to the ones `ModelOut` already uses. Do NOT remove or edit the global `ModelCategory` type at `client.ts:48` — `recommended_category` at `:87` still uses it.)

- [ ] **Step 3: Replace the 2 dead `adminApi` model methods with one `updateModel`**

In `frontend-next/src/api/client.ts`, inside `adminApi`, replace these lines (were 288-297, directly after the `models:` entry — which stays — and before `packages:`):

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

with:

```ts
  updateModel: (
    code: string,
    patch: Partial<Pick<AdminModelOut, "is_active" | "is_visible" | "min_credits" | "recommended_credits" | "sort_order">>,
  ) => request<AdminModelOut>(`/api/admin/models/${code}`, { method: "PATCH", body: JSON.stringify(patch) }),
```

(One generic method instead of two — the exact `updatePackage` pattern two entries below in the same object, `client.ts:299-300`. The backend `AiModelUpdateRequest` (`admin.py:330-338`) accepts more fields than we edit — `Partial<Pick<...>>` deliberately restricts the frontend to the 5 in-scope fields of this sub-phase. Endpoint path verified against `admin.py:341` (`PATCH /models/{code}`).)

- [ ] **Step 4: Verify ONLY the expected consumer broke (intentional red run)**

```bash
cd frontend-next && npx tsc --noEmit
```
Expected: FAIL with exactly 10 TS2339 errors, ALL in `src/screens/admin/AdminModels.tsx` (list derived by grep against master `5abbf4a` — note line 58 produces two):

```
src/screens/admin/AdminModels.tsx:22 - Property 'toggleModel' does not exist on type '{ ... }'.
src/screens/admin/AdminModels.tsx:23 - Property 'model_code' does not exist on type 'AdminModelOut'.
src/screens/admin/AdminModels.tsx:27 - Property 'updateModelCreditCost' does not exist on type '{ ... }'.
src/screens/admin/AdminModels.tsx:28 - Property 'model_code' does not exist on type 'AdminModelOut'.
src/screens/admin/AdminModels.tsx:44 - Property 'model_code' does not exist on type 'AdminModelOut'.
src/screens/admin/AdminModels.tsx:46 - Property 'is_premium' does not exist on type 'AdminModelOut'.
src/screens/admin/AdminModels.tsx:47 - Property 'model_code' does not exist on type 'AdminModelOut'.
src/screens/admin/AdminModels.tsx:55 - Property 'credit_cost' does not exist on type 'AdminModelOut'.
src/screens/admin/AdminModels.tsx:58 - Property 'credit_cost' does not exist on type 'AdminModelOut'.
src/screens/admin/AdminModels.tsx:58 - Property 'model_code' does not exist on type 'AdminModelOut'.
```

(Exact column numbers and the elided object type in the messages may differ; what matters: 10 errors, all TS2339, all in `AdminModels.tsx`, on those lines/symbols. An error in ANY other file means Step 1's baseline was violated — STOP and investigate. In particular `client.ts` itself must be clean: the only `ModelCategory` consumer left is `:87`, which is untouched.)

- [ ] **Step 5: Intermediate commit (typecheck intentionally red until Task 2)**

```bash
git add frontend-next/src/api/client.ts
git commit -m "wip(frontend): admin models API client v2 -- real AdminModelOut and generic updateModel replacing dead toggleModel/updateModelCreditCost (typecheck red until AdminModels rewrite)"
```

---

### Task 2: Rewrite `AdminModels.tsx` against the new type

Rewrite the Models screen: subtitle becomes `provider · category · tier` (read-only), the single `Switch` in `after` becomes two labeled stacked switches («Активна»/«Видима»), and the single dead «Кредитов» input becomes three onBlur number inputs («Мин. кредитов»/«Реком. кредитов»/«Порядок»). Ends with `tsc` + `lint` + `build` fully green.

**Files:**
- Modify (full rewrite): `frontend-next/src/screens/admin/AdminModels.tsx`

**Interfaces:**
- Consumes (from Task 1, `@/api/client`): `AdminModelOut` (new 13-field shape), `adminApi.updateModel(code, patch)` — exact signatures in Task 1's Produces block; plus unchanged `adminApi.models()`.
- Consumes (existing UI kit, same imports as the current file — no new components): `Cell`, `Input`, `List`, `Placeholder`, `Section`, `Spinner`, `Switch` from `@/components/ui/*`. The stacked two-`Switch` `after` layout is new for this screen but uses only existing primitives (`Switch` + flex), nothing new in the UI kit.
- Produces: default-exported React component `AdminModels` (rendered by the admin tabs in `src/app/admin/page.tsx`, unchanged).

- [ ] **Step 1: Rewrite `frontend-next/src/screens/admin/AdminModels.tsx`**

Replace the ENTIRE file content (68 lines) with exactly this (spec section 2, verbatim):

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

Notes (from spec, do not "improve"):
- `sort_order` intentionally has NO `> 0` guard — 0 and negative values are valid sort positions, unlike the credit fields.
- The keyed toggle helper (`toggle(code, field, value)`) replaces the old single-purpose `toggle(modelCode, isActive)`; `applyUpdate` replaces the two copy-pasted `setModels` map calls.
- No try/catch anywhere — a failing `PATCH` stays an unhandled rejection in the console (Global Constraints), same level as before.
- The `«Модели»` section header is byte-identical to the old file — that keeps `e2e/admin-models.spec.ts`'s two count-assertions valid without touching it.

- [ ] **Step 2: Run tsc to verify it passes**

```bash
cd frontend-next && npx tsc --noEmit
```
Expected: exit 0, no output — in particular, Task 1's ten TS2339 errors are gone and nothing new appeared.

- [ ] **Step 3: Verify no dead-symbol traces remain anywhere**

Run from repo root:
```bash
grep -rn "credit_cost\|is_premium\|toggleModel\|updateModelCreditCost" frontend-next/src frontend-next/e2e
```
Expected: no matches (exit code 1).

```bash
grep -n "model_code\|ModelCategory" frontend-next/src/screens/admin/AdminModels.tsx
```
Expected: no matches (exit code 1). (`model_code` legitimately survives in `client.ts` at `:55`/`:133`/`:140`/`:212` — those are other features' wire fields, untouched; `ModelCategory` survives at `client.ts:48`/`:87` — Global Constraints.)

- [ ] **Step 4: Full verification — typecheck, lint, build**

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
Expected: "✓ Compiled successfully"; route table has the same 10 app routes as before the sub-phase (plus `/_not-found`), including `/admin`.

Do NOT run `npm run test:e2e` as a gate: all `admin-*.spec.ts` are red from the pre-existing Telegram-SDK mock bug (Global Constraints). `admin-models.spec.ts` itself is untouched — its assertions (tab label «Модели» count 1 before click, count 2 after: tab label + Section header) still hold against the rewritten screen.

- [ ] **Step 5: Commit**

```bash
git add frontend-next/src/screens/admin/AdminModels.tsx
git commit -m "feat(frontend): admin Models tab -- edit is_active/is_visible/min_credits/recommended_credits/sort_order against the real AiModel schema"
```

---

## Manual smoke test (after both tasks, real backend, admin account)

Not a task gate (needs a live deployment), but the acceptance pass from the spec's «Тестирование» section:

1. Open the «Модели» tab → it lists the real seeded models (`app/db/seed.py`) with the `provider · category · tier` subtitle (e.g. `openai · text · standard`) — no «premium» suffix, no «Кредитов» field anywhere.
2. Flip «Активна» and «Видима» on a model → each persists; the network tab shows `PATCH /api/admin/models/{code}` with exactly the one toggled field in the body (e.g. `{"is_visible":false}`).
3. Change «Мин. кредитов» / «Реком. кредитов» / «Порядок» and blur each input → each saves onBlur (`PATCH` with the single field visible in the network tab) and the value survives a page reload — unlike the old `credit_cost` field, which returned 200 but never changed anything.

## Known limitations carried forward (from spec, unchanged)

- `provider_model_id` and the per-token USD prices (`input_price_usd_per_1m_tokens`/`output_price_usd_per_1m_tokens`) are present in `AdminModelOut` but NOT editable in this sub-phase — more technical fields, can be added later if needed.
- Payments/Stats/Banners tabs untouched — their own future sub-phases.
- `PATCH` errors (422 on bad input, 404 on a vanished model) not surfaced in the UI — console-only unhandled rejection, consistent with the rest of the current admin panel.
- The stale global `ModelCategory` type (`fast/medium/premium/image/video`) still exists in `client.ts` for `ToolOut.recommended_category` — separate cleanup, out of scope.
