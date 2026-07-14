# Admin: Users (credit adjustment + transactions history) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the admin «Пользователи» tab: remove the two dead subscription buttons («Выдать Pro»/«Отменить подписку» — their endpoints don't exist in credit-system-v2), replace the broken «+100 кредитов» button with a signed credit-adjustment form wired to the real `POST /api/admin/users/{telegram_id}/credits`, and add an «История» button opening a new transactions-history sheet backed by the already-working `GET /api/admin/users/{telegram_id}/transactions`.

**Architecture:** Frontend-only change inside `frontend-next/`. The API client (`src/api/client.ts`) gets `AdminUserOut` corrected to 1:1 match the backend `UserOut`, loses 3 dead methods, gains `adjustCredits`/`userTransactions` + `AdminTransactionOut`. `AdminUsers.tsx` is rewritten with a `UserRow` sub-component owning its own form state (same pattern as `SettingRow` in `AdminSettings.tsx`); a new `UserTransactionsSheet.tsx` follows the `CreditPurchaseSheet.tsx` Sheet pattern and is the first file in the new `src/components/admin/` subdirectory. The backend (`app/api/routes/admin.py:94-215`) is verification-reference only — it is NOT modified.

**Tech Stack:** Next.js 16.2.10, React 19.2.4, TypeScript 5, Playwright e2e, Tailwind 4.

**Spec (ground truth):** `docs/superpowers/specs/2026-07-14-frontend-integration-admin-users-design.md`

## Global Constraints

- **Backend untouched.** No file under `app/` is modified. `POST /api/admin/users/{telegram_id}/credits` (`app/api/routes/admin.py:203-215`, body `AdjustCreditsRequest` at `admin.py:198-200`: `{amount: int, reason: str = "ручная корректировка админом"}`; `amount == 0` → 422; over-debit → 400 «Недостаточно кредитов для списания») and `GET /api/admin/users/{telegram_id}/transactions` (`admin.py:164-195`, returns up to 50 latest `TransactionOut` rows, `admin.py:151-161`) already exist and work.
- **`AdminUserOut` must match backend `UserOut` (`admin.py:94-102`) exactly:** `tariff_code`/`subscription_expires_at` are removed (they no longer exist in the API response); `total_credits_purchased`/`total_credits_spent` are added.
- **`AdminTransactionOut.type` union is the 6 `CreditTxType` values** (`app/db/enums.py:57-63`), verbatim: `"purchase" | "spend" | "refund" | "reserve" | "release" | "admin_adjustment"`.
- **`reason` is optional on the wire:** `adjustCredits` sends `JSON.stringify({ amount, reason })` where `reason` may be `undefined` — `JSON.stringify` then omits the key entirely and the backend applies its Pydantic default `"ручная корректировка админом"`. Do not send `reason: ""` or `reason: null`.
- **Russian UI copy, verbatim from spec:** section headers «Поиск по Telegram ID или username» / `Результаты (${users.length})` / `Последние операции (${transactions.length})`; buttons «Найти», «Заблокировать»/«Разблокировать», «История», «Применить»; input headers «Сумма (± кредиты)», «Причина (необязательно)»; sheet header «История операций»; empty state «Пусто» / «У этого пользователя ещё нет операций.»; `TYPE_LABELS`: Покупка / Списание / Возврат / Резерв / Освобождение резерва / Корректировка админом.
- **Error handling is intentionally NOT improved** in this sub-phase: 400/422 from `POST .../credits` surfaces as an unhandled promise rejection in the browser console, same level as existing `AdminModels.tsx`/`AdminSettings.tsx`. Do not add error toasts/try-catch beyond what the spec's code shows (the `try/finally` blocks reset `busy` only — no `catch`).
- **`frontend-next/e2e/admin-users.spec.ts` needs ZERO changes** (verified: its single test only asserts the «Поиск по Telegram ID или username» section header, which this rewrite keeps verbatim). Do not touch any e2e file in this sub-phase. All `admin-*.spec.ts` are currently red anyway from the known pre-existing Telegram-SDK mock bug (`beforeInteractive` real SDK clobbers mocked initData) — out of scope. Completion criterion per task is `npx tsc --noEmit` + `npm run build` green (Task 2) or the exact expected red list (Task 1), NOT a green Playwright run — same precedent as every prior sub-phase except Generate.
- **Task 1 ends with `tsc` intentionally RED**, errors confined to `src/screens/admin/AdminUsers.tsx` only (precedent: phase-3 plan's client.ts-first split, «typecheck осознанно красный»). Task 1's commit is `wip(frontend)`. Task 2 ends fully green.
- **No pagination** for the transactions history — backend default of the latest 50 rows only (spec: out of scope for MVP).
- **Next.js 16 warning** (`frontend-next/AGENTS.md`): this Next.js version has breaking changes vs training data — consult `node_modules/next/dist/docs/` before writing any non-spec Next.js code. (This plan only uses plain React client components, no new Next.js APIs.)
- All `npx`/`npm` commands below run from `frontend-next/` (bash: `cd frontend-next && <cmd>`).
- Route count in `npm run build` output stays the same (7 routes); `/admin` is the same single route — only the Users tab's internals change.

## File Map

| File | Action | Task |
|---|---|---|
| `frontend-next/src/api/client.ts` | Modify (fix `AdminUserOut`, add `AdminTransactionOut`, swap 3 dead methods for 2 new) | 1 |
| `frontend-next/src/screens/admin/AdminUsers.tsx` | Rewrite (full file replacement) | 2 |
| `frontend-next/src/components/admin/UserTransactionsSheet.tsx` | Create (new `components/admin/` subdirectory) | 2 |
| `frontend-next/e2e/admin-users.spec.ts` | **No change** (verified: asserts only the unchanged search-section header) | — |

Line numbers below are verified against the repo as of commit `6f72b56` (branch `master`).

---

### Task 1: client.ts — real `AdminUserOut`, `adjustCredits`, `AdminTransactionOut`, `userTransactions`

Swap the dead subscription-era admin API surface for the real credit-system-v2 one. After this task `tsc` is EXPECTED red with exactly 5 errors, all in `src/screens/admin/AdminUsers.tsx` (it still references the removed `tariff_code`/`grantSubscription`/`cancelSubscription`/`grantCredits` until Task 2 rewrites it). That red state is intentional and verified as a step below.

**Files:**
- Modify: `frontend-next/src/api/client.ts:194-203` (rewrite `AdminUserOut`), immediately after it insert `AdminTransactionOut`, `:265-276` (replace `grantSubscription`/`cancelSubscription`/`grantCredits` with `adjustCredits`/`userTransactions`)

**Interfaces:**
- Consumes: existing `request<T>` helper and `adminApi` object in `client.ts` (unchanged); `adminApi.users`/`blockUser`/`unblockUser` stay exactly as they are.
- Produces (Task 2 relies on these exact names/signatures):
  - `export interface AdminUserOut { telegram_id: number; username: string | null; first_name: string | null; is_admin: boolean; is_blocked: boolean; credits_balance: number; total_credits_purchased: number; total_credits_spent: number }`
  - `export interface AdminTransactionOut { id: number; type: "purchase" | "spend" | "refund" | "reserve" | "release" | "admin_adjustment"; amount: number; balance_before: number; balance_after: number; provider: string | null; model_code: string | null; request_id: number | null; description: string | null; created_at: string }`
  - `adminApi.adjustCredits(telegramId: number, amount: number, reason?: string): Promise<AdminUserOut>`
  - `adminApi.userTransactions(telegramId: number): Promise<AdminTransactionOut[]>`

- [ ] **Step 1: Confirm current dead-code references (baseline "failing test")**

Run from repo root:
```bash
grep -rn "grantSubscription\|cancelSubscription\|grantCredits\|tariff_code\|subscription_expires_at" frontend-next/src frontend-next/e2e
```
Expected: exactly 2 files hit — `frontend-next/src/api/client.ts` (lines 200, 201, 265, 268, 270, 272) and `frontend-next/src/screens/admin/AdminUsers.tsx` (lines 64, 95, 100, 105, 114). Nothing in `frontend-next/e2e/` matches. If anything else appears, STOP — the repo changed since this plan was verified (commit `6f72b56`); re-verify before proceeding.

- [ ] **Step 2: Rewrite `AdminUserOut` to match backend `UserOut`**

In `frontend-next/src/api/client.ts`, replace this block (lines 194-203):

```ts
export interface AdminUserOut {
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  is_admin: boolean;
  is_blocked: boolean;
  tariff_code: string | null;
  subscription_expires_at: string | null;
  credits_balance: number;
}
```

with (1:1 with backend `UserOut`, `app/api/routes/admin.py:94-102`):

```ts
export interface AdminUserOut {
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  is_admin: boolean;
  is_blocked: boolean;
  credits_balance: number;
  total_credits_purchased: number;
  total_credits_spent: number;
}
```

- [ ] **Step 3: Add `AdminTransactionOut` right after `AdminUserOut`**

Immediately after the rewritten `AdminUserOut` block (before `export interface AdminPaymentOut {`), insert, separated by blank lines:

```ts
export interface AdminTransactionOut {
  id: number;
  type: "purchase" | "spend" | "refund" | "reserve" | "release" | "admin_adjustment";
  amount: number;
  balance_before: number;
  balance_after: number;
  provider: string | null;
  model_code: string | null;
  request_id: number | null;
  description: string | null;
  created_at: string;
}
```

(Shape verified against backend `TransactionOut` at `app/api/routes/admin.py:151-161`. Backend declares `type: str`, but the only values it emits are `tx.type.value` from the `CreditTxType` enum at `app/db/enums.py:57-63` — the narrowed 6-value union is intentional per spec. `created_at` is an ISO string, `tx.created_at.isoformat()`.)

- [ ] **Step 4: Replace the 3 dead `adminApi` methods with `adjustCredits` + `userTransactions`**

In `frontend-next/src/api/client.ts`, inside `adminApi`, replace these lines (were 265-276, directly after the `unblockUser` entry, before `payments`):

```ts
  grantSubscription: (telegramId: number, tariffCode: string) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/grant`, {
      method: "POST",
      body: JSON.stringify({ tariff_code: tariffCode }),
    }),
  cancelSubscription: (telegramId: number) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/cancel-subscription`, { method: "POST" }),
  grantCredits: (telegramId: number, amount: number) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/grant-credits`, {
      method: "POST",
      body: JSON.stringify({ amount }),
    }),
```

with:

```ts
  adjustCredits: (telegramId: number, amount: number, reason?: string) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/credits`, {
      method: "POST",
      body: JSON.stringify({ amount, reason }),
    }),
  userTransactions: (telegramId: number) =>
    request<AdminTransactionOut[]>(`/api/admin/users/${telegramId}/transactions`),
```

(`reason: undefined` inside `JSON.stringify` drops the key from the payload entirely — the backend then applies its Pydantic default `"ручная корректировка админом"`, `admin.py:198-200`. Endpoint paths verified against `admin.py:203` (`POST /users/{telegram_id}/credits`) and `admin.py:164` (`GET /users/{telegram_id}/transactions`).)

- [ ] **Step 5: Verify ONLY the expected consumer broke (intentional red run)**

```bash
cd frontend-next && npx tsc --noEmit
```
Expected: FAIL with exactly 5 TS2339 errors, ALL in `src/screens/admin/AdminUsers.tsx` (list verified by grep against master `6f72b56`):

```
src/screens/admin/AdminUsers.tsx:64 - Property 'tariff_code' does not exist on type 'AdminUserOut'.
src/screens/admin/AdminUsers.tsx:95 - Property 'grantSubscription' does not exist on type '{ ... }'.
src/screens/admin/AdminUsers.tsx:100 - Property 'tariff_code' does not exist on type 'AdminUserOut'.
src/screens/admin/AdminUsers.tsx:105 - Property 'cancelSubscription' does not exist on type '{ ... }'.
src/screens/admin/AdminUsers.tsx:114 - Property 'grantCredits' does not exist on type '{ ... }'.
```

(Exact column numbers and the elided object type in the message may differ; what matters: 5 errors, all in `AdminUsers.tsx`, on those 5 lines/symbols. An error in ANY other file means Step 1's baseline was violated — STOP and investigate.)

- [ ] **Step 6: Intermediate commit (typecheck intentionally red until Task 2)**

```bash
git add frontend-next/src/api/client.ts
git commit -m "wip(frontend): admin users API client v2 -- real AdminUserOut, adjustCredits/userTransactions replacing dead subscription methods (typecheck red until AdminUsers rewrite)"
```

---

### Task 2: Rewrite `AdminUsers.tsx` + create `UserTransactionsSheet.tsx`

Rewrite the Users screen: drop `GRANT_TARIFF` and the dead buttons, extract a `UserRow` sub-component with a local credit-adjustment form (amount ± reason + «Применить»), add an «История» button opening the new transactions sheet. TDD via `tsc`: rewrite `AdminUsers.tsx` first — it imports the not-yet-existing `UserTransactionsSheet`, so `tsc` fails on exactly one TS2307 — then create the sheet to go green. Ends with `tsc` + `npm run build` fully green.

**Files:**
- Modify (full rewrite): `frontend-next/src/screens/admin/AdminUsers.tsx`
- Create: `frontend-next/src/components/admin/UserTransactionsSheet.tsx` (also creates the new `src/components/admin/` directory — first file in it, sibling of `src/components/account/`)

**Interfaces:**
- Consumes (from Task 1, `@/api/client`): `AdminUserOut` (new 8-field shape), `AdminTransactionOut`, `adminApi.adjustCredits(telegramId, amount, reason?)`, `adminApi.userTransactions(telegramId)` — exact signatures in Task 1's Produces block; plus unchanged `adminApi.users(query?)`, `adminApi.blockUser(telegramId)`, `adminApi.unblockUser(telegramId)`.
- Consumes (existing UI kit): `Button`, `Cell`, `Input`, `List`, `Section`, `Spinner` from `@/components/ui/*` (AdminUsers) and `Cell`, `List`, `Placeholder`, `Section`, `Sheet`, `Spinner` (UserTransactionsSheet — same imports and `<Sheet open onOpenChange={...} header={<Sheet.Header>...}>` API as `CreditPurchaseSheet.tsx:9,86`; `Placeholder` supports `header`/`description` props, `src/components/ui/placeholder.tsx:3-11`).
- Produces: default-exported React components `AdminUsers` (rendered by `src/app/admin/page.tsx`, unchanged) and `UserTransactionsSheet({ telegramId: number; onClose: () => void })`.

- [ ] **Step 1: Rewrite `frontend-next/src/screens/admin/AdminUsers.tsx` (failing state)**

Replace the ENTIRE file content with exactly this (spec section 2, verbatim):

```tsx
"use client";

import { useState } from "react";

import { adminApi, type AdminUserOut } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Cell } from "@/components/ui/cell";
import { Input } from "@/components/ui/input";
import { List } from "@/components/ui/list";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";
import UserTransactionsSheet from "@/components/admin/UserTransactionsSheet";

function UserRow({ user, onSaved }: { user: AdminUserOut; onSaved: (u: AdminUserOut) => void }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  async function toggleBlock() {
    setBusy(true);
    try {
      const updated = user.is_blocked
        ? await adminApi.unblockUser(user.telegram_id)
        : await adminApi.blockUser(user.telegram_id);
      onSaved(updated);
    } finally {
      setBusy(false);
    }
  }

  async function applyAdjustment() {
    const value = Number(amount);
    if (!value) return;
    setBusy(true);
    try {
      const updated = await adminApi.adjustCredits(user.telegram_id, value, reason || undefined);
      onSaved(updated);
      setAmount("");
      setReason("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Cell
      multiline
      subtitle={
        `ID ${user.telegram_id} · ${user.credits_balance} кредитов` +
        ` · куплено ${user.total_credits_purchased} · потрачено ${user.total_credits_spent}` +
        (user.is_blocked ? " · ЗАБЛОКИРОВАН" : "")
      }
    >
      <div className="flex flex-col gap-1.5">
        <span>{user.first_name ?? user.username ?? user.telegram_id}</span>
        <div className="flex flex-wrap gap-1.5">
          <Button
            size="s"
            mode={user.is_blocked ? "filled" : "outline"}
            loading={busy}
            onClick={toggleBlock}
          >
            {user.is_blocked ? "Разблокировать" : "Заблокировать"}
          </Button>
          <Button size="s" mode="gray" onClick={() => setHistoryOpen(true)}>
            История
          </Button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Input
            header="Сумма (± кредиты)"
            type="number"
            className="w-[110px]"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <Input
            header="Причина (необязательно)"
            className="min-w-[160px] flex-1"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <Button size="s" mode="bezeled" loading={busy} disabled={!amount} onClick={applyAdjustment}>
            Применить
          </Button>
        </div>
      </div>
      {historyOpen && (
        <UserTransactionsSheet telegramId={user.telegram_id} onClose={() => setHistoryOpen(false)} />
      )}
    </Cell>
  );
}

export default function AdminUsers() {
  const [query, setQuery] = useState("");
  const [users, setUsers] = useState<AdminUserOut[] | null>(null);

  async function search() {
    setUsers(null);
    const result = await adminApi.users(query || undefined);
    setUsers(result);
  }

  return (
    <List>
      <Section header="Поиск по Telegram ID или username">
        <Cell
          after={
            <Button size="s" onClick={search}>
              Найти
            </Button>
          }
        >
          <Input placeholder="Telegram ID или username" value={query} onChange={(e) => setQuery(e.target.value)} />
        </Cell>
      </Section>

      {users === null && (
        <Section>
          <Cell before={<Spinner size="s" />}>Введите запрос и нажмите «Найти»</Cell>
        </Section>
      )}

      {users !== null && (
        <Section header={`Результаты (${users.length})`}>
          {users.map((u) => (
            <UserRow
              key={u.telegram_id}
              user={u}
              onSaved={(updated) =>
                setUsers((prev) => prev?.map((x) => (x.telegram_id === updated.telegram_id ? updated : x)) ?? null)
              }
            />
          ))}
        </Section>
      )}
    </List>
  );
}
```

Notes (from spec, do not "improve"):
- `GRANT_TARIFF` constant and both subscription buttons are gone entirely, including the conditional `{u.tariff_code && (...)}` block.
- The old screen-wide `withBusy`/`busy: number | null` is deliberately replaced by per-row `busy` state inside `UserRow` (same list-item-owns-its-form-state pattern as `SettingRow` in `AdminSettings.tsx:14-38`). Behaviorally equivalent — usually only one row is clicked at a time.
- The `try { ... } finally { setBusy(false) }` blocks intentionally have NO `catch` — 400/422 stays an unhandled rejection in the console (Global Constraints).
- The «История» button is NOT gated on `busy` (`loading` prop absent) — opening the sheet is a pure UI action.

- [ ] **Step 2: Run tsc to verify it fails on exactly the missing sheet module**

```bash
cd frontend-next && npx tsc --noEmit
```
Expected: FAIL with exactly one error:
```
src/screens/admin/AdminUsers.tsx:12:34 - error TS2307: Cannot find module '@/components/admin/UserTransactionsSheet' or its corresponding type declarations.
```
(Column may differ slightly; what matters: a single TS2307 on the `UserTransactionsSheet` import and nothing else — in particular, Task 1's five TS2339 errors are gone.)

- [ ] **Step 3: Create `frontend-next/src/components/admin/UserTransactionsSheet.tsx`**

Create the `src/components/admin/` directory with this as its first file. Exact content (spec section 3, verbatim):

```tsx
"use client";

import { useEffect, useState } from "react";

import { adminApi, type AdminTransactionOut } from "@/api/client";
import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Sheet } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";

const TYPE_LABELS: Record<AdminTransactionOut["type"], string> = {
  purchase: "Покупка",
  spend: "Списание",
  refund: "Возврат",
  reserve: "Резерв",
  release: "Освобождение резерва",
  admin_adjustment: "Корректировка админом",
};

interface Props {
  telegramId: number;
  onClose: () => void;
}

export default function UserTransactionsSheet({ telegramId, onClose }: Props) {
  const [transactions, setTransactions] = useState<AdminTransactionOut[] | null>(null);

  useEffect(() => {
    adminApi.userTransactions(telegramId).then(setTransactions).catch(() => setTransactions([]));
  }, [telegramId]);

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()} header={<Sheet.Header>История операций</Sheet.Header>}>
      {transactions === null && (
        <Placeholder>
          <Spinner size="m" />
        </Placeholder>
      )}
      {transactions !== null && transactions.length === 0 && (
        <Placeholder header="Пусто" description="У этого пользователя ещё нет операций." />
      )}
      {transactions !== null && transactions.length > 0 && (
        <List>
          <Section header={`Последние операции (${transactions.length})`}>
            {transactions.map((tx) => (
              <Cell
                key={tx.id}
                multiline
                subtitle={
                  `${new Date(tx.created_at).toLocaleString("ru-RU")} · баланс ${tx.balance_before}→${tx.balance_after}` +
                  (tx.description ? ` · ${tx.description}` : "")
                }
              >
                {TYPE_LABELS[tx.type]}: {tx.amount > 0 ? "+" : ""}
                {tx.amount}
              </Cell>
            ))}
          </Section>
        </List>
      )}
    </Sheet>
  );
}
```

(The `<Sheet open onOpenChange={...} header={<Sheet.Header>...}>` shape and the `Cell`/`List`/`Section`/`Placeholder`/`Spinner` imports are 1:1 with the established `CreditPurchaseSheet.tsx` pattern. The fetch `.catch(() => setTransactions([]))` collapses errors to the «Пусто» state — same load-error convention as `AdminSettings.tsx:44`, intentional per spec.)

- [ ] **Step 4: Run tsc to verify it passes**

```bash
cd frontend-next && npx tsc --noEmit
```
Expected: exit 0, no output.

- [ ] **Step 5: Verify no dead-symbol traces remain anywhere**

Run from repo root:
```bash
grep -rn "grantSubscription\|cancelSubscription\|grantCredits\|tariff_code\|subscription_expires_at\|GRANT_TARIFF" frontend-next/src frontend-next/e2e
```
Expected: no matches (exit code 1).

- [ ] **Step 6: Full verification — typecheck, lint, build**

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

Do NOT run `npm run test:e2e` as a gate: all `admin-*.spec.ts` are red from the pre-existing Telegram-SDK mock bug (Global Constraints). `admin-users.spec.ts` itself is untouched — its only assertion («Поиск по Telegram ID или username» section header) still holds against the rewritten screen.

- [ ] **Step 7: Commit**

```bash
git add frontend-next/src/screens/admin/AdminUsers.tsx frontend-next/src/components/admin/UserTransactionsSheet.tsx
git commit -m "feat(frontend): admin Users tab -- credit adjustment form and transactions history replacing dead subscription buttons"
```

---

## Manual smoke test (after both tasks, real backend, admin account)

Not a task gate (needs a live deployment), but the acceptance pass from the spec:

1. Find a user by ID/username → the row shows real `credits_balance`/`total_credits_purchased`/`total_credits_spent`; no «тариф»/«подписка» text anywhere.
2. Block/unblock → toggles; button label and «ЗАБЛОКИРОВАН» subtitle marker update in place.
3. Enter `50` in «Сумма (± кредиты)», leave «Причина» empty, press «Применить» → balance grows by 50; the network tab shows `POST /api/admin/users/{id}/credits` with body `{"amount":50}` (no `reason` key — `undefined` is dropped by `JSON.stringify`).
4. Enter `-9999999` (guaranteed above balance) → backend returns 400 «Недостаточно кредитов для списания»; surfaces only as an unhandled rejection in the console (expected, per spec — same level as `AdminModels.tsx`/`AdminSettings.tsx`, not a regression).
5. Press «История» → sheet opens with the transaction list (or «Пусто» for a user without history); closes via swipe/close control.

## Known limitations carried forward (from spec, unchanged)

- Models/Payments/Stats/Banners tabs untouched — their own future sub-phases.
- 400/422 from `POST .../credits` not surfaced in the UI (console-only unhandled rejection), consistent with the rest of the current admin panel.
- Transactions history is not paginated — latest 50 only (backend default), sufficient for MVP.
