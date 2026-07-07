"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Cell } from "@/components/ui/cell";
import { IconButton } from "@/components/ui/icon-button";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Progress } from "@/components/ui/progress";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";
import { useMe } from "@/context/MeContext";
import CreditPurchaseSheet from "@/components/account/CreditPurchaseSheet";

const CATEGORY_LABEL: Record<string, string> = {
  fast: "Быстрые запросы",
  medium: "Средние запросы",
  premium: "Премиум запросы",
  image: "Картинки",
};

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

  const categories = Object.entries(me.limits.categories).filter(([, v]) => v.limit > 0);
  const isFree = me.tariff_code === "free";

  return (
    <div className="p-4">
      <h2 className="heading-font mt-2 mb-5 text-center text-[19px] font-semibold">
        @{me.username ?? me.first_name ?? me.telegram_id}
      </h2>

      <div className="relative mb-4 overflow-hidden rounded-lg border border-border-soft bg-surface p-[18px]">
        <div className="absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]" />
        <div className="text-xs uppercase tracking-[0.4px] text-foreground-muted">Current plan</div>
        <div className="heading-font mt-1 mb-3 text-[22px] font-semibold">{me.tariff_name}</div>

        <div className="mb-1.5 flex justify-between text-[13px]">
          <span className="text-foreground-muted">Дневные запросы</span>
          <span>
            {me.limits.daily_used} / {me.limits.daily_limit}
          </span>
        </div>
        <Progress
          value={me.limits.daily_limit > 0 ? Math.min(100, (me.limits.daily_used / me.limits.daily_limit) * 100) : 0}
        />

        <div className="mt-3 flex flex-wrap gap-1.5">
          {categories.map(([category, limit]) => (
            <span
              key={category}
              className="rounded-full border border-border-soft bg-surface-strong px-2.5 py-1 text-xs"
            >
              {CATEGORY_LABEL[category] ?? category}: {limit.limit - limit.used}/{limit.limit}
            </span>
          ))}
          {me.subscription_expires_at && (
            <span className="text-xs text-foreground-muted">
              до {new Date(me.subscription_expires_at).toLocaleDateString("ru-RU")}
            </span>
          )}
        </div>
      </div>

      {isFree && (
        <div className="press-scale mb-4 rounded-lg bg-[image:var(--brand-gradient)] p-[18px] shadow-glow">
          <div className="heading-font text-[18px] font-semibold">🚀 Go Premium</div>
          <div className="mt-1 mb-3.5 text-[13px] opacity-90">
            Больше запросов, доступ к premium-моделям и генерации картинок
          </div>
          <Button stretched mode="white" onClick={() => router.push("/tariffs")}>
            Unlock Premium
          </Button>
        </div>
      )}

      <div className="my-2 text-xs uppercase text-foreground-muted">Credits</div>
      <List>
        <Section>
          <Cell
            subtitle="Тратятся, когда лимит тарифа исчерпан"
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
