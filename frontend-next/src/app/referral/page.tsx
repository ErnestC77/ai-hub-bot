"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Placeholder } from "@/components/ui/placeholder";
import { Spinner } from "@/components/ui/spinner";
import { api, type ReferralOut } from "@/api/client";
import { haptic, openTelegramLink } from "@/lib/telegram";

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
    <div className="fade-in flex flex-col gap-3.5 px-4 pb-4">
      <h1 className="heading-font pt-1 text-[22px] text-foreground">Приглашай друзей</h1>

      <div
        className="relative overflow-hidden rounded-[22px] border border-white/[0.14] px-[18px] py-[22px] text-center"
        style={{ background: "linear-gradient(135deg, rgba(139,92,255,.35), rgba(53,224,230,.16))" }}
        data-testid="referral-promo"
      >
        <div
          aria-hidden
          className="absolute -right-[20px] -top-[30px] h-[90px] w-[90px] rounded-full"
          style={{ background: "radial-gradient(circle, rgba(53,224,230,.55), transparent 70%)" }}
        />
        <div className="text-[34px]">🎁</div>
        <div className="heading-font mt-2 text-[17px] text-foreground">
          +{data.bonus_amount} 💎 за каждого друга
        </div>
        <div className="mt-1.5 text-[11.5px] leading-[1.4] text-foreground-muted">
          Поделись ссылкой — приглашения и бонусы появятся здесь
        </div>
      </div>

      <div className="flex gap-3">
        <div className="glass flex-1 rounded-[18px] p-4 text-center">
          <div className="heading-font text-[24px] text-foreground" data-testid="referral-invited">
            {data.referred_count}
          </div>
          <div className="mt-0.5 text-[10.5px] text-foreground-muted">Приглашено</div>
        </div>
        <div className="glass flex-1 rounded-[18px] p-4 text-center">
          <div className="heading-font text-[24px] text-foreground" data-testid="referral-earned">
            {data.earned_credits} 💎
          </div>
          <div className="mt-0.5 text-[10.5px] text-foreground-muted">Заработано</div>
        </div>
      </div>

      <button
        type="button"
        onClick={copy}
        aria-label="Скопировать ссылку"
        className="glass press-scale flex w-full items-center justify-between gap-3 rounded-[16px] px-[15px] py-3 text-left"
        data-testid="referral-copy"
      >
        <span className="truncate text-[11.5px] text-foreground-muted" data-testid="referral-link">
          {link}
        </span>
        <span aria-hidden className="shrink-0 text-[15px]">
          📋
        </span>
      </button>

      <Button size="l" stretched onClick={share} data-testid="referral-share">
        Поделиться ссылкой
      </Button>
    </div>
  );
}
