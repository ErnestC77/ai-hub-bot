# Frontend Integration — Admin: Stats

## Контекст

Последняя вкладка админ-панели, требующая рефакторинга. Продолжение
модернизации после Tariffs→Packages+Settings, Users, Models. Аудит трёх
оставшихся вкладок (Payments/Stats/Banners) показал:

- **Payments** и **Banners** уже 1:1 совпадают с реальным бэкендом
  (`AdminPaymentOut`/`AdminBannerOut` в `client.ts` и соответствующие
  `adminApi` методы верны полностью) — верифицированы, без изменений, не
  в скоупе этого спека.
- **Stats** — реальная проблема. `AdminStatsOut` в `client.ts` (8 полей)
  сильно отстал от реального бэкенда `StatsOut` (`app/api/routes/
  admin.py:42-57`, 14 полей включая 2 списка). Бэкендная аналитика Phase 6
  (см. память `ai_hub_bot_project`) добавила
  `today_revenue_credits`/`today_revenue_rub_estimated`/`today_margin_rub`/
  `today_avg_cost_credits`/`model_usage` (топ-10 моделей)/
  `top_users_by_spend` (топ-10 юзеров)/`month_credits_purchases_count` —
  ни одно из этих полей фронтенд никогда не показывал, потому что
  фронтенд-каталог-ап начался уже после того, как бэкенд-ребилд завершился.

Также `AdminStatsOut.month_active_subscriptions` — мёртвое поле, которого
у реального `StatsOut` нет вообще (пережиток системы подписок до
credit-system-v2). У ответа `GET /admin/stats` такого ключа нет — в UI это
рендерится как `undefined` (пустая ячейка), не крэш, но бессмысленная
строка «Активные подписки: undefined».

## Scope

**В скоупе:**
- `client.ts`: переписать `AdminStatsOut` 1:1 под реальный `StatsOut`
  (`admin.py:42-57`), добавить `ModelUsageOut`/`UserSpendOut` под
  бэкендные `ModelUsageOut`/`UserSpendOut` (`admin.py:30-39`).
  `adminApi.stats()` не меняется (уже правильный URL).
- `AdminStats.tsx`: секция «Сегодня» получает 4 новых поля
  (revenue_credits/revenue_rub_estimated/margin_rub/avg_cost_credits);
  секция «За месяц» теряет мёртвый `month_active_subscriptions`, получает
  `month_credits_purchases_count`; две новые секции — «Топ моделей»
  (топ-10 из `model_usage`, формат «код: N запросов · M кредитов · $X»)
  и «Топ пользователей по тратам» (топ-10 из `top_users_by_spend`,
  «tg:ID — N кредитов»), тот же `Section`+`Cell` list-паттерн, что уже
  использует `UserTransactionsSheet.tsx`.

**Вне скоупа:**
- Payments/Banners — уже верны, не трогаются.
- Бэкенд не трогается — `GET /admin/stats` уже отдаёт все нужные поля.
- Пагинация/фильтры для топ-листов — бэкенд и так режет до топ-10,
  дальше резать нечего.
- Графики/визуализация — только текстовые списки, как и весь остальной
  админ-панель на сегодня (тот же уровень, что Users/Models/Packages).

## Изменения

### 1. `client.ts` — `AdminStatsOut` + новые типы

Текущий код (`client.ts:183-192`):

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

заменить на (1:1 с `StatsOut`, `admin.py:42-57`; вставить `ModelUsageOut`/
`UserSpendOut` прямо перед ним, как отдельные экспортируемые интерфейсы):

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

`adminApi.stats` (`client.ts:277`) не меняется — тот же
`request<AdminStatsOut>("/api/admin/stats")`, только теперь резолвится в
правильный тип.

### 2. `AdminStats.tsx` — полный рерайт

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

(Пустые топ-листы прячут свою секцию целиком — `.length > 0` guard —
вместо пустого заголовка без строк; UX-выбор, не диктуется бэкендом,
консистентно с тем, что делает `UserTransactionsSheet.tsx`'s «Пусто»
state для нулевого случая, только без отдельного placeholder-текста,
т.к. секция просто не рендерится вообще при пустом топ-листе.)

## Тестирование

`npx tsc --noEmit` + `npm run build`. `frontend-next/e2e/admin-stats.spec.ts`
(если существует) — проверить, что ассертит только заголовок вкладки/
секции «Сегодня», не конкретные поля; если так — не трогать, тот же
прецедент, что Models/Users. Ручной smoke-тест против реального бэкенда:
вкладка «Статистика» показывает все 9 полей «Сегодня», 2 поля «За месяц»,
и (если за день были траты) две секции топ-листов с реальными данными.

## Известные ограничения после этой фазы

- Никаких графиков — только текстовые Cell-списки, тот же уровень
  визуализации, что весь остальной админ-панель.
- Топ-листы жёстко топ-10 (ограничение бэкенда, не фронтенда) —
  пагинация не в скоупе.
- Admin-панель модернизация всех 6 вкладок (Tariffs→Packages+Settings,
  Users, Models, Payments[verified], Stats, Banners[verified]) полностью
  завершена после этой под-фазы.
