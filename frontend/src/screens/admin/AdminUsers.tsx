import { useState } from "react";
import { Button, Cell, Input, List, Section, Spinner } from "@telegram-apps/telegram-ui";

import { adminApi, type AdminUserOut } from "../../api/client";

const GRANT_TARIFF = "pro";

export default function AdminUsers() {
  const [query, setQuery] = useState("");
  const [users, setUsers] = useState<AdminUserOut[] | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  async function search() {
    setUsers(null);
    const result = await adminApi.users(query || undefined);
    setUsers(result);
  }

  async function withBusy(telegramId: number, action: () => Promise<AdminUserOut>) {
    setBusy(telegramId);
    try {
      const updated = await action();
      setUsers((prev) => prev?.map((u) => (u.telegram_id === telegramId ? updated : u)) ?? null);
    } finally {
      setBusy(null);
    }
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
          <Input
            placeholder="Telegram ID или username"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
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
            <Cell
              key={u.telegram_id}
              multiline
              subtitle={
                `ID ${u.telegram_id}` +
                (u.tariff_code ? ` · тариф ${u.tariff_code}` : " · без подписки") +
                ` · ${u.credits_balance} кредитов` +
                (u.is_blocked ? " · ЗАБЛОКИРОВАН" : "")
              }
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span>{u.first_name ?? u.username ?? u.telegram_id}</span>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {u.is_blocked ? (
                    <Button
                      size="s"
                      loading={busy === u.telegram_id}
                      onClick={() => withBusy(u.telegram_id, () => adminApi.unblockUser(u.telegram_id))}
                    >
                      Разблокировать
                    </Button>
                  ) : (
                    <Button
                      size="s"
                      mode="outline"
                      loading={busy === u.telegram_id}
                      onClick={() => withBusy(u.telegram_id, () => adminApi.blockUser(u.telegram_id))}
                    >
                      Заблокировать
                    </Button>
                  )}
                  <Button
                    size="s"
                    mode="bezeled"
                    loading={busy === u.telegram_id}
                    onClick={() =>
                      withBusy(u.telegram_id, () => adminApi.grantSubscription(u.telegram_id, GRANT_TARIFF))
                    }
                  >
                    Выдать Pro
                  </Button>
                  {u.tariff_code && (
                    <Button
                      size="s"
                      mode="gray"
                      loading={busy === u.telegram_id}
                      onClick={() => withBusy(u.telegram_id, () => adminApi.cancelSubscription(u.telegram_id))}
                    >
                      Отменить подписку
                    </Button>
                  )}
                  <Button
                    size="s"
                    mode="gray"
                    loading={busy === u.telegram_id}
                    onClick={() => withBusy(u.telegram_id, () => adminApi.grantCredits(u.telegram_id, 100))}
                  >
                    +100 кредитов
                  </Button>
                </div>
              </div>
            </Cell>
          ))}
        </Section>
      )}
    </List>
  );
}
