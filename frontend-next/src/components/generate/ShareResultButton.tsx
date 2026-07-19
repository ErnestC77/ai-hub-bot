"use client";

import { useState } from "react";

import { api } from "@/api/client";
import { haptic, openTelegramLink } from "@/lib/telegram";

/**
 * «Поделиться с другом» под свежим результатом генерации — момент вау лучший
 * для шаринга. Открывает телеграмный share с реф-ссылкой владельца: друг
 * получает welcome-кредиты, оба — реферальный бонус. Ссылку тянем лениво по
 * клику (не грузим /api/referral на каждый рендер результата).
 */
export default function ShareResultButton() {
  const [busy, setBusy] = useState(false);

  async function share() {
    if (busy) return;
    setBusy(true);
    haptic("light");
    try {
      const { link } = await api.referral();
      const text = "Смотри, что я сделал нейросетью в AI Hub! Заходи — получишь бесплатные кредиты 🎁";
      openTelegramLink(
        `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`,
      );
    } catch {
      // не критично: шаринг просто не откроется
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      data-testid="share-result"
      onClick={share}
      className="glass press-scale w-full rounded-[14px] px-4 py-2.5 text-center text-[12.5px] font-semibold text-foreground"
    >
      📤 Поделиться с другом · вам обоим бонус
    </button>
  );
}
