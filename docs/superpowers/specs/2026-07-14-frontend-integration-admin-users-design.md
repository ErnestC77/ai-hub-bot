# Frontend Integration — Admin: Users

## Контекст

Продолжение проекта модернизации admin-панели (`frontend-next/src/screens/admin/*`,
единая страница `/admin` с вкладками). Первая под-фаза (Tariffs → Packages +
Settings) смёржена. Пользователь выбрал вкладку **Users** следующей.

`AdminUsers.tsx` частично сломан устаревшей концепцией подписок/тарифов,
которой в credit-system-v2 больше не существует:

- «Выдать Pro» зовёт `adminApi.grantSubscription()` → `POST
  /api/admin/users/{id}/grant` — эндпойнта нет.
- «Отменить подписку» зовёт `adminApi.cancelSubscription()` → `POST
  /api/admin/users/{id}/cancel-subscription` — эндпойнта нет; вдобавок кнопка
  условная (`u.tariff_code && ...`), а поля `tariff_code` в реальном ответе
  `GET /admin/users` больше нет вообще — кнопка никогда не рендерится.
- «+100 кредитов» зовёт `adminApi.grantCredits()` → `POST
  /api/admin/users/{id}/grant-credits` — тоже несуществующий путь. Реальный
  рабочий эндпойнт — `POST /api/admin/users/{telegram_id}/credits` (`app/api/
  routes/admin.py:198-215`) с телом `{amount: int, reason?: str}` (`amount` —
  со знаком, отрицательное значение списывает; `reason` по умолчанию на
  бэкенде "ручная корректировка админом"; `amount == 0` → 422; списание больше
  баланса → 400 «Недостаточно кредитов для списания»).

Поиск/список (`GET /admin/users?query=`), блокировка/разблокировка (`POST
.../block`, `.../unblock`) — рабочие, эндпойнты существуют и совпадают.

Отдельно обнаружен рабочий, но нигде не используемый эндпойнт `GET
/api/admin/users/{telegram_id}/transactions` (`admin.py:151-195`,
возвращает до 50 последних `CreditTransaction` пользователя: `type` — одно
из `purchase/spend/refund/reserve/release/admin_adjustment`
(`app/db/enums.py:57-63`), `amount`, `balance_before/after`, `provider`,
`model_code`, `request_id`, `description`, `created_at`).

## Scope

**В скоупе:**
- `client.ts`: исправить `AdminUserOut` под реальный `UserOut`; удалить
  `grantSubscription`/`cancelSubscription`; заменить `grantCredits` на
  `adjustCredits(telegramId, amount, reason?)` с правильным URL/телом; новый
  `AdminTransactionOut` + `adminApi.userTransactions(telegramId)`.
- `AdminUsers.tsx`: убрать кнопки «Выдать Pro»/«Отменить подписку» и
  константу `GRANT_TARIFF` целиком; заменить «+100 кредитов» на инлайн-форму
  (сумма со знаком + необязательная причина + кнопка «Применить»); добавить
  кнопку «История», открывающую новый компонент со списком транзакций.
- Новый `frontend-next/src/components/admin/UserTransactionsSheet.tsx`.

**Вне скоупа:**
- Остальные вкладки (Models/Payments/Stats/Banners) — свои будущие
  под-фазы.
- Пагинация истории транзакций (`limit`/`offset` за пределами дефолтных
  50 последних) — не нужна для MVP-вида истории.
- Изменение самой бизнес-логики начисления/списания на бэкенде — не
  трогается, эндпойнт уже работает.

## Изменения

### 1. `client.ts` — `AdminUserOut`, `adjustCredits`, `AdminTransactionOut`

Текущий код (`client.ts:194-203`):

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

заменить на (1:1 с реальным `UserOut`, `admin.py:94-102`):

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

Новый тип, рядом с `AdminUserOut`:

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

В `adminApi` (`client.ts:261-276`) удалить `grantSubscription`/
`cancelSubscription`, заменить `grantCredits` и добавить `userTransactions`:

Текущий код:

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

заменить на:

```ts
  adjustCredits: (telegramId: number, amount: number, reason?: string) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/credits`, {
      method: "POST",
      body: JSON.stringify({ amount, reason }),
    }),
  userTransactions: (telegramId: number) =>
    request<AdminTransactionOut[]>(`/api/admin/users/${telegramId}/transactions`),
```

(`reason: undefined` в `JSON.stringify` опускает ключ целиком — бэкенд
подставит дефолт `"ручная корректировка админом"` сам, `Pydantic`-поле имеет
`= "..."` по умолчанию, `admin.py:198-200`.)

### 2. `AdminUsers.tsx` — убрать мёртвое, починить credits, добавить историю

Удалить константу `GRANT_TARIFF` и обе кнопки «Выдать Pro»/«Отменить
подписку» (включая условный блок `{u.tariff_code && (...)}`).

Извлечь строку пользователя в под-компонент `UserRow` (тот же паттерн, что
`SettingRow` в `AdminSettings.tsx` — локальный `draft`-стейт для формы
корректировки):

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

(Убран прежний общий `withBusy`/`busy: number | null` для всего списка —
каждая строка теперь owns свой `busy`, что и позволяет открыть форму
корректировки у одного пользователя, не блокируя остальные визуально;
поведенчески эквивалентно старому — одновременно кликается обычно один ряд.)

### 3. `UserTransactionsSheet.tsx` — история операций

Новый файл `frontend-next/src/components/admin/UserTransactionsSheet.tsx`:

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

(`Sheet`/`Cell`/`List`/`Section`/`Placeholder`/`Spinner` — те же импорты,
что уже используются в `CreditPurchaseSheet.tsx`/`AdminSettings.tsx`; новый
компонент лежит в `components/admin/` — по аналогии с `components/account/
CreditPurchaseSheet.tsx`, первый файл в этой новой поддиректории.)

## Тестирование

`npx tsc --noEmit` + `npm run build` (без unit-тестов React в проекте).
e2e (`admin-users.spec.ts`, если существует — проверить содержимое перед
правкой) остаётся на том же уровне (`[[ai_hub_bot_e2e_mock_bug]]` блокирует
весь `admin-*` e2e), критерий готовности — зелёная сборка, как во всех
предыдущих под-фазах кроме Generate.

Ручной smoke-тест (реальный бэкенд, админ-аккаунт):
1. Найти пользователя по ID/username — список показывает реальные
   `credits_balance`/`total_credits_purchased`/`total_credits_spent`, без
   «тариф»/«подписка» текста.
2. Заблокировать/разблокировать — переключается, кнопка/подпись обновляются.
3. Ввести `+50` в поле суммы, оставить причину пустой, «Применить» —
   баланс увеличивается на 50, в network виден `POST .../credits` с
   `{amount: 50, reason: undefined}` (ключ `reason` в реальном запросе
   отсутствует).
4. Ввести `-9999999` (заведомо больше баланса) — бэкенд вернёт 400
   «Недостаточно кредитов для списания», `ApiError.message` — эта строка
   (в UI ошибка не перехватывается отдельно — тот же уровень, что у
   `AdminModels.tsx`/`AdminSettings.tsx`, необработанный reject в консоли,
   это осознанное решение, не регрессия).
5. «История» — открывается шторка со списком транзакций (или «Пусто» для
   пользователя без истории), закрывается свайпом/крестиком.

## Известные ограничения после этой фазы

- Models/Payments/Stats/Banners вкладки не тронуты — свои будущие
  под-фазы.
- Ошибки `POST .../credits` (400/422) не показываются в UI отдельным
  тостом — только необработанный reject в консоли (тот же уровень, что
  везде в этой админ-панели сейчас).
- История транзакций не пагинируется — только последние 50 (дефолт
  бэкенда), достаточно для MVP.
