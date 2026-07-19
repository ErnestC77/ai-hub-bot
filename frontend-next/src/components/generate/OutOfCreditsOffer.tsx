"use client";

import { useState } from "react";

import CreditPurchaseSheet from "@/components/account/CreditPurchaseSheet";
import { Button } from "@/components/ui/button";

/**
 * Оффер вместо голого текста ошибки 402 («Недостаточно кредитов» / «Бесплатный
 * лимит исчерпан»): объясняет причину и сразу открывает покупку пакета, не
 * гоняя пользователя искать «Тарифы» на главной. Новичку в шите виден бейдж
 * бонуса первой покупки — сам момент отказа становится точкой конверсии.
 */
export default function OutOfCreditsOffer({ message }: { message: string }) {
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <div
      data-testid="out-of-credits-offer"
      className="glass relative overflow-hidden rounded-[16px] p-[14px] text-center"
    >
      <div className="absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]" />
      <div className="text-[13px] font-semibold">💎 {message}</div>
      <div className="mt-1 text-[11px] text-foreground-dim">
        Пополните баланс, чтобы продолжить генерации
      </div>
      <Button stretched className="mt-3" onClick={() => setSheetOpen(true)}>
        Выбрать пакет
      </Button>
      {sheetOpen && <CreditPurchaseSheet onClose={() => setSheetOpen(false)} />}
    </div>
  );
}
