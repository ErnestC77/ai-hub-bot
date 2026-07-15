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
