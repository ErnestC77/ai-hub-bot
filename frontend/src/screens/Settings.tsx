import { Cell, List, Section } from "@telegram-apps/telegram-ui";

import { openTelegramLink } from "../lib/telegram";

const SUPPORT_USERNAME = import.meta.env.VITE_SUPPORT_USERNAME as string | undefined;

export default function Settings() {
  return (
    <List>
      <Section header="Поддержка">
        <Cell
          onClick={() => SUPPORT_USERNAME && openTelegramLink(`https://t.me/${SUPPORT_USERNAME}`)}
          subtitle={SUPPORT_USERNAME ? `@${SUPPORT_USERNAME}` : "скоро появится"}
        >
          Написать в поддержку
        </Cell>
      </Section>
      <Section header="О приложении">
        <Cell subtitle="AI Hub — доступ к нескольким нейросетям в одном месте">AI Hub</Cell>
      </Section>
    </List>
  );
}
