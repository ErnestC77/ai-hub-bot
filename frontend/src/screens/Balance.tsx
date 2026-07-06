import { Cell, List, Placeholder, Progress, Section, Spinner } from "@telegram-apps/telegram-ui";

import { useMe } from "../context/MeContext";

const CATEGORY_LABEL: Record<string, string> = {
  fast: "Быстрые запросы",
  medium: "Средние запросы",
  premium: "Премиум запросы",
  image: "Картинки",
};

export default function Balance() {
  const { me, loading } = useMe();

  if (loading) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  if (!me) {
    return <Placeholder header="Не удалось загрузить баланс" />;
  }

  const categories = Object.entries(me.limits.categories).filter(([, v]) => v.limit > 0);

  return (
    <List>
      <Section header="Тариф">
        <Cell
          subtitle={
            me.subscription_expires_at
              ? `действует до ${new Date(me.subscription_expires_at).toLocaleDateString("ru-RU")}`
              : "без ограничения по времени"
          }
        >
          {me.tariff_name}
        </Cell>
      </Section>

      <Section header="Остаток лимитов">
        {categories.length === 0 && <Cell subtitle="На этом тарифе нет доступных категорий">—</Cell>}
        {categories.map(([category, limit]) => (
          <Cell key={category} subtitle={`${limit.used} из ${limit.limit}`} multiline>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, width: "100%" }}>
              <span>{CATEGORY_LABEL[category] ?? category}</span>
              <Progress value={Math.min(100, (limit.used / limit.limit) * 100)} />
            </div>
          </Cell>
        ))}
        <Cell subtitle={`${me.limits.daily_used} из ${me.limits.daily_limit}`}>Дневной лимит</Cell>
      </Section>
    </List>
  );
}
