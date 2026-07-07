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
      </Section>
      <Section header="За месяц">
        <Cell subtitle="Выручка">{stats.month_revenue_rub}₽</Cell>
        <Cell subtitle="Активные подписки">{stats.month_active_subscriptions}</Cell>
      </Section>
    </List>
  );
}
