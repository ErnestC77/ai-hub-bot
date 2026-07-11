"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Cell } from "@/components/ui/cell";
import { IconButton } from "@/components/ui/icon-button";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";
import { useMe } from "@/context/MeContext";
import CreditPurchaseSheet from "@/components/account/CreditPurchaseSheet";

export default function MyAccount() {
  const { me, loading } = useMe();
  const router = useRouter();
  const [buyingCredits, setBuyingCredits] = useState(false);

  if (loading) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  if (!me) {
    return <Placeholder header="Не удалось загрузить профиль" description="Откройте приложение из Telegram." />;
  }

  // Антифрод-гейт фазы 5: video и ultra-модели недоступны до первой покупки.
  const isTrial = me.total_credits_purchased === 0;

  return (
    <div className="p-4">
      <h2 className="heading-font mt-2 mb-5 text-center text-[19px] font-semibold">
        @{me.username ?? me.first_name ?? me.telegram_id}
      </h2>

      <div className="relative mb-4 overflow-hidden rounded-lg border border-border-soft bg-surface p-[18px]">
        <div className="absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]" />
        <div className="text-xs uppercase tracking-[0.4px] text-foreground-muted">Баланс</div>
        <div className="heading-font mt-1 mb-3 text-[28px] font-semibold">💎 {me.credits_balance} кредитов</div>

        <div className="flex justify-between text-[13px]">
          <span className="text-foreground-muted">Всего куплено</span>
          <span>{me.total_credits_purchased}</span>
        </div>
        <div className="mt-1.5 flex justify-between text-[13px]">
          <span className="text-foreground-muted">Всего потрачено</span>
          <span>{me.total_credits_spent}</span>
        </div>
      </div>

      {isTrial && (
        <div className="press-scale mb-4 rounded-lg bg-[image:var(--brand-gradient)] p-[18px] shadow-glow">
          <div className="heading-font text-[18px] font-semibold">💎 Купите первый пакет</div>
          <div className="mt-1 mb-3.5 text-[13px] opacity-90">
            Первая покупка открывает доступ к видео-генерации и топовым моделям
          </div>
          <Button stretched mode="white" onClick={() => setBuyingCredits(true)}>
            Выбрать пакет
          </Button>
        </div>
      )}

      <div className="my-2 text-xs uppercase text-foreground-muted">Credits</div>
      <List>
        <Section>
          <Cell
            subtitle="Списываются за каждый запрос к моделям"
            after={
              <IconButton onClick={() => setBuyingCredits(true)} aria-label="Купить кредиты">
                +
              </IconButton>
            }
          >
            💎 {me.credits_balance} кредитов
          </Cell>
        </Section>

        <Section header="Settings">
          <Cell onClick={() => router.push("/settings")}>⚙️ Настройки и поддержка</Cell>
          <Cell onClick={() => router.push("/referral")}>🎁 Реферальная программа</Cell>
          {me.is_admin && <Cell onClick={() => router.push("/admin")}>🛠 Админ-панель</Cell>}
        </Section>
      </List>

      {buyingCredits && <CreditPurchaseSheet onClose={() => setBuyingCredits(false)} />}
    </div>
  );
}
