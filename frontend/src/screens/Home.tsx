import { Button, Cell, List, Placeholder, Section, Spinner } from "@telegram-apps/telegram-ui";
import { useNavigate } from "react-router-dom";

import { useMe } from "../context/MeContext";

export default function Home() {
  const { me, loading } = useMe();
  const navigate = useNavigate();

  if (loading) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  if (!me) {
    return (
      <Placeholder header="Не удалось загрузить профиль" description="Откройте приложение из Telegram." />
    );
  }

  return (
    <List>
      <Section header="Ваш тариф">
        <Cell subtitle={me.subscription_expires_at ? `до ${new Date(me.subscription_expires_at).toLocaleDateString("ru-RU")}` : "без ограничения по времени"}>
          {me.tariff_name}
        </Cell>
      </Section>

      <Section>
        <Cell after={<Button size="s" onClick={() => navigate("/chat")}>Открыть</Button>}>
          💬 Чат с нейросетью
        </Cell>
        <Cell after={<Button size="s" mode="bezeled" onClick={() => navigate("/tools")}>Открыть</Button>}>
          🧩 Готовые инструменты
        </Cell>
        <Cell after={<Button size="s" mode="bezeled" onClick={() => navigate("/tariffs")}>Открыть</Button>}>
          💳 Тарифы и подписка
        </Cell>
        <Cell after={<Button size="s" mode="bezeled" onClick={() => navigate("/referral")}>Открыть</Button>}>
          🎁 Реферальная программа
        </Cell>
        <Cell after={<Button size="s" mode="bezeled" onClick={() => navigate("/settings")}>Открыть</Button>}>
          ⚙️ Настройки и поддержка
        </Cell>
      </Section>

      {me.is_admin && (
        <Section header="Администрирование">
          <Cell after={<Button size="s" mode="outline" onClick={() => navigate("/admin")}>Открыть</Button>}>
            🛠 Админ-панель
          </Cell>
        </Section>
      )}
    </List>
  );
}
