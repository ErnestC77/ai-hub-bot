"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Placeholder } from "@/components/ui/placeholder";
import { Spinner } from "@/components/ui/spinner";
import { api, type ReferralOut } from "@/api/client";
import { useMe } from "@/context/MeContext";
import { openTelegramLink } from "@/lib/telegram";
import CreditPurchaseSheet from "@/components/account/CreditPurchaseSheet";

const CAPS_LABEL = "px-1 pb-2 text-[10px] uppercase tracking-[0.08em] text-foreground-dim";
const SUPPORT_USERNAME = process.env.NEXT_PUBLIC_SUPPORT_USERNAME as string | undefined;

export default function MyAccount() {
  const { me, loading } = useMe();
  const router = useRouter();
  const [buyingCredits, setBuyingCredits] = useState(false);
  const [referral, setReferral] = useState<ReferralOut | null>(null);

  useEffect(() => {
    api.referral().then(setReferral).catch(() => setReferral(null));
  }, []);

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
    <div className="fade-in p-4">
      <h2 className="heading-font pb-3 pt-2 text-center text-[17px] font-semibold">
        @{me.username ?? me.first_name ?? me.telegram_id}
      </h2>

      {/* Карточка баланса кредитов (планов/тарифов нет -- без прогресса-меры). */}
      <div className="glass relative mb-3.5 overflow-hidden rounded-[20px] p-[17px]">
        <div className="absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]" />
        <div className="text-[10px] uppercase tracking-[0.1em] text-foreground-muted">Баланс</div>
        <div className="heading-font mb-3 mt-1 text-[22px] font-semibold" data-testid="account-balance">
          💎 {me.credits_balance} кредитов
        </div>

        <div className="mb-1.5 flex justify-between text-xs">
          <span className="text-foreground-muted">Куплено всего</span>
          <span data-testid="account-purchased">{me.total_credits_purchased}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-foreground-muted">Потрачено всего</span>
          <span data-testid="account-spent">{me.total_credits_spent}</span>
        </div>

        {me.default_model_code && (
          <div className="mt-3 flex flex-wrap gap-1.5 text-[10.5px]">
            <span className="glass rounded-full px-2.5 py-1" data-testid="account-default-model">
              Модель по умолчанию · {me.default_model_code}
            </span>
          </div>
        )}
      </div>

      {isTrial && (
        <div className="mb-3.5 rounded-[20px] bg-[image:var(--brand-gradient)] p-[18px] shadow-glow">
          <div className="heading-font text-[18px] font-semibold">💎 Купите первый пакет</div>
          <div className="mb-3.5 mt-1 text-[13px] opacity-90">
            Первая покупка открывает доступ к видео-генерации и топовым моделям
          </div>
          <Button stretched mode="white" onClick={() => setBuyingCredits(true)}>
            Выбрать пакет
          </Button>
        </div>
      )}

      {/* Карточка баланса + «+» */}
      <div className="glass mb-4 flex items-center gap-3 rounded-[18px] p-[15px]">
        <div className="text-[22px]">💎</div>
        <div className="flex-1">
          <div className="text-sm font-semibold">{me.credits_balance} кредитов</div>
          <div className="mt-0.5 text-[10.5px] text-foreground-dim">Списываются за каждый запрос к моделям</div>
        </div>
        <button
          type="button"
          onClick={() => setBuyingCredits(true)}
          aria-label="Купить кредиты"
          data-testid="account-buy-credits"
          className="press-scale flex h-[34px] w-[34px] items-center justify-center rounded-[11px] bg-[image:var(--brand-gradient)] text-xl font-semibold text-white shadow-glow"
        >
          +
        </button>
      </div>

      {/* Рефералы */}
      <div className="mb-4">
        <div className={CAPS_LABEL}>Рефералы</div>
        <div className="flex gap-2.5" data-testid="account-referral">
          <div className="glass flex-1 rounded-2xl p-3.5 text-center">
            <div className="heading-font text-[22px] font-semibold">{referral ? referral.referred_count : "—"}</div>
            <div className="mt-1 text-[10px] text-foreground-muted">Приглашено</div>
          </div>
          {/* earned_credits -- реальная сумма заработанных на рефералах кредитов
              (SUM bonus_credits по роли пригласившего). Формат и слово совпадают
              с /referral и HANDOFF §5 «Заработано 140 💎». */}
          <div className="glass flex-1 rounded-2xl p-3.5 text-center">
            <div className="heading-font text-[22px] font-semibold">
              {referral ? `${referral.earned_credits} 💎` : "—"}
            </div>
            <div className="mt-1 text-[10px] text-foreground-muted">Заработано</div>
          </div>
        </div>
      </div>

      {/* Ещё */}
      <div>
        <div className={CAPS_LABEL}>Ещё</div>
        <div className="glass overflow-hidden rounded-2xl">
          <button
            type="button"
            onClick={() => router.push("/referral")}
            className="press-scale flex w-full items-center justify-between border-b border-white/[0.07] px-[15px] py-[13px] text-left text-[13px]"
          >
            <span>🎁 Реферальная программа</span>
            <span className="text-foreground-dim">›</span>
          </button>
          <button
            type="button"
            data-testid="account-support"
            onClick={() =>
              SUPPORT_USERNAME
                ? openTelegramLink(`https://t.me/${SUPPORT_USERNAME}`)
                : router.push("/settings")
            }
            className="press-scale flex w-full items-center justify-between border-b border-white/[0.07] px-[15px] py-[13px] text-left text-[13px]"
          >
            <span>💬 Написать в поддержку</span>
            <span className="text-foreground-dim">›</span>
          </button>
          <button
            type="button"
            onClick={() => router.push("/settings")}
            className="press-scale flex w-full items-center justify-between border-b border-white/[0.07] px-[15px] py-[13px] text-left text-[13px] last:border-b-0"
          >
            <span>⚙️ Настройки</span>
            <span className="text-foreground-dim">›</span>
          </button>
          {me.is_admin && (
            <button
              type="button"
              onClick={() => router.push("/admin")}
              className="press-scale flex w-full items-center justify-between px-[15px] py-[13px] text-left text-[13px]"
            >
              <span>🛠 Админ-панель</span>
              <span className="text-foreground-dim">›</span>
            </button>
          )}
        </div>
      </div>

      {buyingCredits && <CreditPurchaseSheet onClose={() => setBuyingCredits(false)} />}
    </div>
  );
}
