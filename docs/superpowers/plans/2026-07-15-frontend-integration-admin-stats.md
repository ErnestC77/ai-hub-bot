# Admin: Stats (real StatsOut — Phase-6 analytics fields + top-10 lists) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the admin «Статистика» tab: `AdminStatsOut` in `client.ts` (8 fields) has drifted badly behind the real backend `StatsOut` (14 fields including 2 nested arrays) — the Phase-6 analytics backend rebuild added `today_revenue_credits`/`today_revenue_rub_estimated`/`today_margin_rub`/`today_avg_cost_credits`/`model_usage` (top-10)/`top_users_by_spend` (top-10)/`month_credits_purchases_count`, none of which the frontend ever picked up, and the frontend still renders the dead pre-credit-system-v2 field `month_active_subscriptions`, which does not exist on the real response (shows as a blank «Активные подписки: undefined» cell). Rewrite `AdminStatsOut` 1:1 against the real backend `StatsOut`, add two new exported interfaces `ModelUsageOut`/`UserSpendOut`, and rewrite `AdminStats.tsx` to display all 14 fields including two new top-10 list sections.

**Architecture:** Frontend-only change inside `frontend-next/`. The API client (`src/api/client.ts`) gets `AdminStatsOut` corrected to 1:1 match the backend `StatsOut` plus the two new nested interfaces inserted immediately before it; `adminApi.stats()` does not change (same URL, now resolves to the correct type). `AdminStats.tsx` is rewritten with the exact code from the spec's section 2 — «Сегодня» grows to 9 cells, «За месяц» swaps the dead subscriptions cell for `month_credits_purchases_count`, and two new conditional sections render the top-10 lists (hidden entirely when empty via `.length > 0` guards). The backend (`app/api/routes/admin.py:30-89`) is verification-reference only — it is NOT modified.

**Tech Stack:** Next.js 16.2.10, React 19.2.4, TypeScript 5, Playwright e2e, Tailwind 4.

**Spec (ground truth):** `docs/superpowers/specs/2026-07-15-frontend-integration-admin-stats-design.md`

## Global Constraints

- **Backend untouched.** No file under `app/` is modified. `GET /api/admin/stats` (`app/api/routes/admin.py:59-89`) already returns everything needed: backend `ModelUsageOut` (`admin.py:30-34`), `UserSpendOut` (`admin.py:37-39`), `StatsOut` (`admin.py:42-57`) assembled from `get_daily_stats`+`get_monthly_stats`.
- **`AdminStatsOut` must match backend `StatsOut` (`admin.py:42-57`) exactly** — 14 fields, shape verbatim in Task 1 Step 2. `month_active_subscriptions` is removed (it does not exist in the API response); `model_usage: ModelUsageOut[]` and `top_users_by_spend: UserSpendOut[]` are typed by the two new exported interfaces, which must match backend `ModelUsageOut`/`UserSpendOut` (`admin.py:30-39`) exactly — shapes verbatim in Task 1 Step 2.
- **`adminApi.stats` is NOT touched** (`client.ts:277`, `stats: () => request<AdminStatsOut>("/api/admin/stats"),`) — same call, now resolves to the correct type. No other `adminApi` method changes in this sub-phase.
- **Russian UI copy, verbatim from the spec's `AdminStats.tsx` code block:** section headers «Сегодня» / «За месяц» / «Топ моделей (сегодня)» / «Топ пользователей по тратам (сегодня)»; all `subtitle` strings exactly as in Task 2 Step 1's code («Новых пользователей», «Оплат (кол-во / сумма)», «AI-запросов», «Расходы на API», «Ошибки», «Выручка (кредиты)», «Выручка (оценка, ₽)», «Маржа (₽)», «Средняя себестоимость (кредиты)», «Выручка», «Покупок кредитов», and the templated `` `${m.requests} запросов · $${m.cost_usd.toFixed(4)}` ``). Do not "improve" the wording.
- **Empty top-lists hide their section entirely** — the `.length > 0` guard means an empty `model_usage`/`top_users_by_spend` renders NO section (not an empty header). Keep the guards exactly as the spec's code has them.
- **Error handling is intentionally NOT improved** in this sub-phase: the load failure path stays `.catch(() => setStats(null))` (perpetual spinner on failure), no per-field error UI, no try/catch, no toasts — same level as before the rewrite and as the rest of the current admin panel.
- **`frontend-next/e2e/admin-stats.spec.ts` needs ZERO changes** (verified: its single test only asserts the «Статистика» tab click navigates and the text «Сегодня» becomes visible — the rewrite keeps `header="Сегодня"` on the first Section verbatim). Do not touch any e2e file in this sub-phase. All `admin-*.spec.ts` are currently red anyway from the known pre-existing Telegram-SDK mock bug (`beforeInteractive` real SDK clobbers mocked initData) — out of scope. Completion criterion per task is `npx tsc --noEmit` + `npm run build` green (Task 2) or the exact expected red list (Task 1), NOT a green Playwright run — same precedent as every prior admin sub-phase.
- **Task 1 ends with `tsc` intentionally RED**, exactly 1 error, confined to `src/screens/admin/AdminStats.tsx` (precedent: the Users and Models plans' client.ts-first split). Task 1's commit is `wip(frontend)`. Task 2 ends fully green.
- **Next.js 16 warning** (`frontend-next/AGENTS.md`): this Next.js version has breaking changes vs training data — consult `node_modules/next/dist/docs/` before writing any non-spec Next.js code. (This plan only uses plain React client components, no new Next.js APIs.)
- All `npx`/`npm` commands below run from `frontend-next/` (bash: `cd frontend-next && <cmd>`).
- Route count in `npm run build` output stays the same (10 app routes, including `/admin`, plus the automatic `/_not-found`; confirmed unchanged by the prior admin-models plan); `/admin` is the same single route — only the Stats tab's internals change.

## File Map

| File | Action | Task |
|---|---|---|
| `frontend-next/src/api/client.ts` | Modify (rewrite `AdminStatsOut`, insert `ModelUsageOut`/`UserSpendOut` before it) | 1 |
| `frontend-next/src/screens/admin/AdminStats.tsx` | Rewrite (full file replacement, 45 lines currently) | 2 |
| `frontend-next/e2e/admin-stats.spec.ts` | **No change** (verified: asserts only the «Статистика» tab click + «Сегодня» visibility) | — |

Line numbers below are verified against the repo as of commit `05693df` (branch `master`).

---

### Task 1: client.ts — real `AdminStatsOut` + `ModelUsageOut`/`UserSpendOut`

Swap the stale pre-Phase-6 stats shape for the real one. After this task `tsc` is EXPECTED red with exactly 1 error, in `src/screens/admin/AdminStats.tsx` (it still references the removed `month_active_subscriptions` until Task 2 rewrites it). That red state is intentional and verified as a step below.

**Files:**
- Modify: `frontend-next/src/api/client.ts:183-192` (replace the `AdminStatsOut` block with the three interfaces below; `adminApi.stats` at `:277` stays untouched)

**Interfaces:**
- Consumes: existing `request<T>` helper and `adminApi` object in `client.ts` (unchanged); `adminApi.stats` stays exactly as it is.
- Produces (Task 2 relies on these exact names/shapes):
  - `export interface ModelUsageOut { model_code: string; requests: number; credits_spent: number; cost_usd: number }`
  - `export interface UserSpendOut { telegram_id: number; credits_spent: number }`
  - `export interface AdminStatsOut { today_new_users: number; today_payments_count: number; today_payments_amount_rub: number; today_ai_requests: number; today_api_cost_usd: number; today_errors: number; today_revenue_credits: number; today_revenue_rub_estimated: number; today_margin_rub: number; today_avg_cost_credits: number; model_usage: ModelUsageOut[]; top_users_by_spend: UserSpendOut[]; month_revenue_rub: number; month_credits_purchases_count: number }`

- [ ] **Step 1: Confirm current consumers of the old shape (baseline "failing test")**

Run from repo root:
```bash
grep -rn "month_active_subscriptions\|AdminStatsOut" frontend-next/src frontend-next/e2e
```
Expected: exactly 2 files hit —

```
frontend-next/src/api/client.ts:183:export interface AdminStatsOut {
frontend-next/src/api/client.ts:191:  month_active_subscriptions: number;
frontend-next/src/api/client.ts:277:  stats: () => request<AdminStatsOut>("/api/admin/stats"),
frontend-next/src/screens/admin/AdminStats.tsx:5:import { adminApi, type AdminStatsOut } from "@/api/client";
frontend-next/src/screens/admin/AdminStats.tsx:13:  const [stats, setStats] = useState<AdminStatsOut | null>(null);
frontend-next/src/screens/admin/AdminStats.tsx:40:        <Cell subtitle="Активные подписки">{stats.month_active_subscriptions}</Cell>
```

Nothing in `frontend-next/e2e/` matches. If anything else appears, STOP — the repo changed since this plan was verified (commit `05693df`); re-verify before proceeding.

Note why only ONE tsc error is expected after this task: `month_active_subscriptions` is the only field genuinely deleted — everything else in the old `AdminStatsOut` is a strict subset of the new one, so no other property access breaks. Its sole consumer outside `client.ts` is `AdminStats.tsx:40` (the grep above proves it), and the imports at `:5`/`:13` keep resolving because `AdminStatsOut` keeps its name.

- [ ] **Step 2: Rewrite `AdminStatsOut` and add `ModelUsageOut`/`UserSpendOut`**

In `frontend-next/src/api/client.ts`, replace this block (lines 183-192):

```ts
export interface AdminStatsOut {
  today_new_users: number;
  today_payments_count: number;
  today_payments_amount_rub: number;
  today_ai_requests: number;
  today_api_cost_usd: number;
  today_errors: number;
  month_revenue_rub: number;
  month_active_subscriptions: number;
}
```

with (1:1 with backend `ModelUsageOut`/`UserSpendOut`/`StatsOut`, `app/api/routes/admin.py:30-57`; field order matches the backend classes; the two nested interfaces go immediately before `AdminStatsOut` as separate exported interfaces):

```ts
export interface ModelUsageOut {
  model_code: string;
  requests: number;
  credits_spent: number;
  cost_usd: number;
}

export interface UserSpendOut {
  telegram_id: number;
  credits_spent: number;
}

export interface AdminStatsOut {
  today_new_users: number;
  today_payments_count: number;
  today_payments_amount_rub: number;
  today_ai_requests: number;
  today_api_cost_usd: number;
  today_errors: number;
  today_revenue_credits: number;
  today_revenue_rub_estimated: number;
  today_margin_rub: number;
  today_avg_cost_credits: number;
  model_usage: ModelUsageOut[];
  top_users_by_spend: UserSpendOut[];
  month_revenue_rub: number;
  month_credits_purchases_count: number;
}
```

Do NOT touch `adminApi.stats` (`client.ts:277`) — `stats: () => request<AdminStatsOut>("/api/admin/stats"),` stays byte-identical; it now simply resolves to the corrected type.

- [ ] **Step 3: Verify ONLY the expected consumer broke (intentional red run)**

```bash
cd frontend-next && npx tsc --noEmit
```
Expected: FAIL with exactly 1 TS2339 error, in `src/screens/admin/AdminStats.tsx`:

```
src/screens/admin/AdminStats.tsx:40 - Property 'month_active_subscriptions' does not exist on type 'AdminStatsOut'.
```

(Exact column number and message formatting may differ; what matters: 1 error, TS2339, in `AdminStats.tsx`, on `month_active_subscriptions` at line 40. An error in ANY other file — or a second error in this one — means Step 1's baseline was violated — STOP and investigate. In particular `client.ts` itself must be clean.)

- [ ] **Step 4: Intermediate commit (typecheck intentionally red until Task 2)**

```bash
git add frontend-next/src/api/client.ts
git commit -m "wip(frontend): admin stats API client v2 -- real 14-field AdminStatsOut plus ModelUsageOut/UserSpendOut, dead month_active_subscriptions dropped (typecheck red until AdminStats rewrite)"
```

---

### Task 2: Rewrite `AdminStats.tsx` against the new type

Rewrite the Stats screen: «Сегодня» grows from 5 to 9 cells (adds revenue credits / revenue ₽ estimate / margin ₽ / avg cost credits), «За месяц» swaps the dead «Активные подписки» cell for «Покупок кредитов», and two new conditional sections render the top-10 model usage and top-10 user spend lists. Ends with `tsc` + `lint` + `build` fully green.

**Files:**
- Modify (full rewrite): `frontend-next/src/screens/admin/AdminStats.tsx`

**Interfaces:**
- Consumes (from Task 1, `@/api/client`): `AdminStatsOut` (new 14-field shape) — exact shape in Task 1's Produces block (the `ModelUsageOut`/`UserSpendOut` element types are reached through `stats.model_usage`/`stats.top_users_by_spend`, no direct import needed); plus unchanged `adminApi.stats()`.
- Consumes (existing UI kit, same imports as the current file — no new components): `Cell`, `List`, `Placeholder`, `Section`, `Spinner` from `@/components/ui/*`. The conditional top-list sections use only existing primitives — same `Section`+`Cell` list pattern already used by `UserTransactionsSheet.tsx`.
- Produces: default-exported React component `AdminStats` (rendered by the admin tabs in `src/app/admin/page.tsx`, unchanged).

- [ ] **Step 1: Rewrite `frontend-next/src/screens/admin/AdminStats.tsx`**

Replace the ENTIRE file content (45 lines) with exactly this (spec section 2, verbatim):

```tsx
"use client";

import { useEffect, useState } from "react";

import { adminApi, type AdminStatsOut } from "@/api/client";
import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";

export default function AdminStats() {
  const [stats, setStats] = useState<AdminStatsOut | null>(null);

  useEffect(() => {
    adminApi.stats().then(setStats).catch(() => setStats(null));
  }, []);

  if (stats === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <List>
      <Section header="Сегодня">
        <Cell subtitle="Новых пользователей">{stats.today_new_users}</Cell>
        <Cell subtitle="Оплат (кол-во / сумма)">
          {stats.today_payments_count} / {stats.today_payments_amount_rub}₽
        </Cell>
        <Cell subtitle="AI-запросов">{stats.today_ai_requests}</Cell>
        <Cell subtitle="Расходы на API">${stats.today_api_cost_usd.toFixed(4)}</Cell>
        <Cell subtitle="Ошибки">{stats.today_errors}</Cell>
        <Cell subtitle="Выручка (кредиты)">{stats.today_revenue_credits}</Cell>
        <Cell subtitle="Выручка (оценка, ₽)">{stats.today_revenue_rub_estimated.toFixed(2)}₽</Cell>
        <Cell subtitle="Маржа (₽)">{stats.today_margin_rub.toFixed(2)}₽</Cell>
        <Cell subtitle="Средняя себестоимость (кредиты)">{stats.today_avg_cost_credits.toFixed(2)}</Cell>
      </Section>

      <Section header="За месяц">
        <Cell subtitle="Выручка">{stats.month_revenue_rub}₽</Cell>
        <Cell subtitle="Покупок кредитов">{stats.month_credits_purchases_count}</Cell>
      </Section>

      {stats.model_usage.length > 0 && (
        <Section header="Топ моделей (сегодня)">
          {stats.model_usage.map((m) => (
            <Cell key={m.model_code} subtitle={`${m.requests} запросов · $${m.cost_usd.toFixed(4)}`}>
              {m.model_code}: {m.credits_spent} кредитов
            </Cell>
          ))}
        </Section>
      )}

      {stats.top_users_by_spend.length > 0 && (
        <Section header="Топ пользователей по тратам (сегодня)">
          {stats.top_users_by_spend.map((u) => (
            <Cell key={u.telegram_id}>
              tg:{u.telegram_id} — {u.credits_spent} кредитов
            </Cell>
          ))}
        </Section>
      )}
    </List>
  );
}
```

Notes (from spec, do not "improve"):
- Empty top-lists hide their section entirely (`.length > 0` guard) — no empty header with zero rows; UX choice consistent with how `UserTransactionsSheet.tsx` handles its zero case, except the section simply isn't rendered at all.
- No try/catch beyond the existing `.catch(() => setStats(null))` — load failure stays a perpetual spinner (Global Constraints), same level as before.
- The `header="Сегодня"` on the first Section is byte-identical to the old file — that keeps `e2e/admin-stats.spec.ts`'s single visibility assertion valid without touching it.
- `key={m.model_code}` / `key={u.telegram_id}` are safe: the backend aggregates per model / per user, so each appears at most once per list.

- [ ] **Step 2: Run tsc to verify it passes**

```bash
cd frontend-next && npx tsc --noEmit
```
Expected: exit 0, no output — in particular, Task 1's single TS2339 error is gone and nothing new appeared.

- [ ] **Step 3: Verify no dead-symbol traces remain anywhere**

Run from repo root:
```bash
grep -rn "month_active_subscriptions\|Активные подписки" frontend-next/src frontend-next/e2e
```
Expected: no matches (exit code 1).

```bash
grep -rn "ModelUsageOut\|UserSpendOut\|month_credits_purchases_count" frontend-next/src
```
Expected: matches ONLY in `frontend-next/src/api/client.ts` (the two new interface declarations, their two array-field usages inside `AdminStatsOut`, and the `month_credits_purchases_count` field) and `frontend-next/src/screens/admin/AdminStats.tsx` (the `stats.month_credits_purchases_count` cell). `AdminStats.tsx` does not import `ModelUsageOut`/`UserSpendOut` directly — element types flow through `stats.model_usage`/`stats.top_users_by_spend`.

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

Do NOT run `npm run test:e2e` as a gate: all `admin-*.spec.ts` are red from the pre-existing Telegram-SDK mock bug (Global Constraints). `admin-stats.spec.ts` itself is untouched — its single assertion (click «Статистика» → «Сегодня» visible) still holds against the rewritten screen.

- [ ] **Step 5: Commit**

```bash
git add frontend-next/src/screens/admin/AdminStats.tsx
git commit -m "feat(frontend): admin Stats tab -- all 14 real StatsOut fields incl. Phase-6 analytics and top-10 model/user lists, dead subscriptions cell removed"
```

---

## Manual smoke test (after both tasks, real backend, admin account)

Not a task gate (needs a live deployment), but the acceptance pass from the spec's «Тестирование» section:

1. Open the «Статистика» tab → the «Сегодня» section shows all 9 cells (including the 4 new ones: «Выручка (кредиты)», «Выручка (оценка, ₽)», «Маржа (₽)», «Средняя себестоимость (кредиты)») with real numbers — no `undefined` anywhere.
2. The «За месяц» section shows «Выручка» and «Покупок кредитов» — the old «Активные подписки: undefined» row is gone.
3. If there were AI requests today: «Топ моделей (сегодня)» lists up to 10 rows in the format `model_code: N кредитов` with subtitle `N запросов · $X.XXXX`; «Топ пользователей по тратам (сегодня)» lists up to 10 rows `tg:ID — N кредитов`. On a fresh day with no spend, both sections are absent entirely (not empty headers).
4. The network tab shows a single `GET /api/admin/stats` — same request as before the rewrite.

## Known limitations carried forward (from spec, unchanged)

- No charts/graphs — text-only `Cell` lists, the same visualization level as the rest of the admin panel.
- Top-lists are hard-capped at 10 by the backend (not a frontend limit) — pagination is not in scope, there is nothing further to slice.
- Load failure still shows a perpetual spinner (`.catch(() => setStats(null))`) — error UI not improved, consistent with the rest of the current admin panel.
- Payments and Banners tabs were audited in the same investigation and found already fully correct against the real backend — explicitly out of scope, untouched.
- With this sub-phase, the modernization of all 6 admin tabs (Tariffs→Packages+Settings, Users, Models, Payments [verified], Stats, Banners [verified]) is fully complete.
