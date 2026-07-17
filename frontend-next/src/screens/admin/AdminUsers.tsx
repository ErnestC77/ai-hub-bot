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
import ActionError from "@/components/admin/ActionError";
import { useActionError } from "@/components/admin/useActionError";

function UserRow({ user, onSaved }: { user: AdminUserOut; onSaved: (u: AdminUserOut) => void }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const { error, run } = useActionError();

  async function toggleBlock() {
    setBusy(true);
    await run(async () => {
      const updated = user.is_blocked
        ? await adminApi.unblockUser(user.telegram_id)
        : await adminApi.blockUser(user.telegram_id);
      onSaved(updated);
    });
    setBusy(false);
  }

  async function applyAdjustment() {
    const value = Number(amount);
    if (!value) return;
    setBusy(true);
    await run(async () => {
      const updated = await adminApi.adjustCredits(user.telegram_id, value, reason || undefined);
      onSaved(updated);
      setAmount("");
      setReason("");
    });
    setBusy(false);
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
        {error && <span className="text-[12px] text-red-400">{error}</span>}
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
  const { error, run } = useActionError();

  async function search() {
    await run(async () => {
      setUsers(null);
      setUsers(await adminApi.users(query || undefined));
    });
  }

  return (
    <List>
      <ActionError error={error} />
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
