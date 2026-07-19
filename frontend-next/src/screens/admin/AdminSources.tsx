"use client";

import { useCallback, useEffect, useState } from "react";

import { adminApi, type AdminSourceStatsOut } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";

/**
 * Воронка привлечения по рекламным меткам (?start=ads_X): пользователи →
 * платящие → выручка. «Органика» = пришли без метки, «referral» = по
 * реф-ссылке. Здесь принимается решение, какой канал рекламы масштабировать.
 */
export default function AdminSources() {
  const [rows, setRows] = useState<AdminSourceStatsOut[] | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    adminApi
      .sources()
      .then(setRows)
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function retry() {
    setError(false);
    setRows(null);
    load();
  }

  if (error) {
    return (
      <Placeholder header="Не удалось загрузить источники" description="Проверьте соединение и попробуйте ещё раз.">
        <Button onClick={retry}>Повторить</Button>
      </Placeholder>
    );
  }

  if (rows === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  function sourceLabel(source: string | null): string {
    if (source === null) return "Органика";
    if (source === "referral") return "Рефералы";
    return source;
  }

  return (
    <List>
      <Section
        header="Источники привлечения"
        footer="Метка задаётся ссылкой t.me/бот?start=ads_название — своя на каждую закупку рекламы. Конверсия = платящие / пользователи."
      >
        {rows.length === 0 && <Cell subtitle="Пока нет ни одного пользователя">—</Cell>}
        {rows.map((r) => {
          const conversion = r.users_count > 0 ? ((r.payers_count / r.users_count) * 100).toFixed(1) : "0.0";
          return (
            <Cell
              key={r.source ?? "__organic__"}
              subtitle={`${r.users_count} польз. · ${r.payers_count} платящих (${conversion}%)`}
              after={`${r.revenue_rub.toFixed(0)}₽`}
            >
              {sourceLabel(r.source)}
            </Cell>
          );
        })}
      </Section>
    </List>
  );
}
