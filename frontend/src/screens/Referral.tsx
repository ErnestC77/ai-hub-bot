import { useEffect, useState } from "react";
import { Button, Cell, List, Placeholder, Section, Spinner } from "@telegram-apps/telegram-ui";

import { api, type ReferralOut } from "../api/client";
import { haptic, openTelegramLink } from "../lib/telegram";

export default function Referral() {
  const [data, setData] = useState<ReferralOut | null>(null);

  useEffect(() => {
    api.referral().then(setData).catch(() => setData(null));
  }, []);

  if (data === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  const { link } = data;

  function share() {
    haptic("light");
    openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(link)}`);
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      haptic("light");
    } catch {
      // буфер обмена недоступен вне защищённого контекста — не критично для MVP
    }
  }

  return (
    <List>
      <Section header="Реферальная программа" footer={data.link}>
        <Cell subtitle="Приглашённые пользователи">{data.referred_count}</Cell>
        <Cell subtitle="Начислены бонусы">{data.bonus_count}</Cell>
      </Section>
      <Section>
        <Cell after={<Button size="s" onClick={share}>Поделиться</Button>}>Пригласить друга</Cell>
        <Cell after={<Button size="s" mode="bezeled" onClick={copy}>Скопировать</Button>}>Ссылка</Cell>
      </Section>
    </List>
  );
}
