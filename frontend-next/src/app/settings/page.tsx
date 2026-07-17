"use client";

import DefaultModelSetting from "@/components/settings/DefaultModelSetting";
import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Section } from "@/components/ui/section";
import { openTelegramLink } from "@/lib/telegram";

const SUPPORT_USERNAME = process.env.NEXT_PUBLIC_SUPPORT_USERNAME as string | undefined;

/*
 * Секция «Предпочтения» из макета (язык ответов, тумблер уведомлений) намеренно
 * не рисуется: соответствующих API/полей на бэкенде нет (спека §4).
 */
export default function Settings() {
  return (
    <div className="fade-in">
      <h1 className="heading-font px-4 pb-3.5 pt-1 text-[22px] text-foreground">Настройки</h1>
      <List>
        <Section header="Модель по умолчанию" footer="С неё открывается чат, если вы не выбрали другую">
          <DefaultModelSetting />
        </Section>
        <Section header="Поддержка">
          <div data-testid="settings-support">
            <Cell
              onClick={() => SUPPORT_USERNAME && openTelegramLink(`https://t.me/${SUPPORT_USERNAME}`)}
              subtitle={SUPPORT_USERNAME ? `@${SUPPORT_USERNAME}` : "скоро появится"}
              after={<span className="text-foreground-dim">›</span>}
            >
              Написать в поддержку
            </Cell>
          </div>
        </Section>
        <Section header="О приложении">
          <div data-testid="settings-about">
            <Cell
              before={
                <div
                  aria-hidden
                  className="h-[30px] w-[30px] shrink-0 rounded-[9px] bg-[image:var(--brand-gradient)]"
                />
              }
              subtitle="Все нейросети в одном месте"
            >
              AI Hub
            </Cell>
          </div>
        </Section>
      </List>
    </div>
  );
}
