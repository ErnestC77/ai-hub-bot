"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { ApiError, api, type CreditPackageOut } from "@/api/client";
import { useMe } from "@/context/MeContext";
import { haptic, openInvoice, openLink } from "@/lib/telegram";

type Stage = "pick" | "choose-method" | "waiting" | "success" | "error";

interface Props {
  onClose: () => void;
}

const POLL_INTERVAL_MS = 2000;
// Stars: openInvoice уже подтвердил оплату, ждём только webhook -> 30 сек.
const POLL_ATTEMPTS_STARS = 15;
// ЮKassa: пользователь платит на внешней странице и возвращается сам -> 2 мин.
const POLL_ATTEMPTS_YOOKASSA = 60;

export default function CreditPurchaseSheet({ onClose }: Props) {
  const [stage, setStage] = useState<Stage>("pick");
  const [packages, setPackages] = useState<CreditPackageOut[] | null>(null);
  const [selected, setSelected] = useState<CreditPackageOut | null>(null);
  const [errorText, setErrorText] = useState("");
  const { refresh } = useMe();

  useEffect(() => {
    api.creditPackages().then(setPackages).catch(() => setPackages([]));
  }, []);

  // Поллим статус КОНКРЕТНОГО платежа, а не дельту баланса: рост баланса от
  // реферального бонуса/рефанда во время ожидания давал ложный «успех», а
  // параллельное списание маскировало настоящий.
  async function waitForCredit(paymentId: number, attempts: number) {
    setStage("waiting");
    for (let i = 0; i < attempts; i++) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      try {
        const { status } = await api.paymentStatus(paymentId);
        if (status === "succeeded") {
          await refresh();
          setStage("success");
          haptic("medium");
          return;
        }
        if (status === "canceled" || status === "failed" || status === "refunded") {
          setErrorText("Платёж не был завершён. Попробуйте ещё раз.");
          setStage("error");
          return;
        }
      } catch {
        // временная сетевая ошибка при поллинге -- пробуем ещё раз
      }
    }
    setErrorText("Оплата обрабатывается дольше обычного. Проверьте баланс чуть позже.");
    setStage("error");
  }

  async function payWithStars(pkg: CreditPackageOut) {
    try {
      const { payment_id, invoice_link } = await api.createStarsCreditPayment(pkg.code);
      if (!invoice_link) throw new Error("empty invoice link");
      openInvoice(invoice_link, (status) => {
        if (status === "paid") {
          void waitForCredit(payment_id, POLL_ATTEMPTS_STARS);
        } else if (status === "failed" || status === "cancelled") {
          setStage("choose-method");
        }
      });
    } catch (err) {
      setErrorText(err instanceof ApiError ? err.message : "Не удалось создать платёж");
      setStage("error");
    }
  }

  async function payWithYookassa(pkg: CreditPackageOut) {
    try {
      const { payment_id, confirmation_url } = await api.createYookassaCreditPayment(pkg.code);
      if (!confirmation_url) throw new Error("empty confirmation url");
      openLink(confirmation_url);
      void waitForCredit(payment_id, POLL_ATTEMPTS_YOOKASSA);
    } catch (err) {
      setErrorText(err instanceof ApiError ? err.message : "Не удалось создать платёж");
      setStage("error");
    }
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()} header={<Sheet.Header>Купить кредиты</Sheet.Header>}>
      {stage === "pick" && (
        <div className="flex flex-col gap-3 px-4 pb-6 pt-2">
          <div className="px-1 text-[10px] uppercase tracking-[0.08em] text-foreground-dim">Выберите пакет</div>

          {packages === null && (
            <div className="glass flex items-center justify-center gap-2.5 rounded-[18px] p-4 text-[13px] text-foreground-muted">
              <Spinner size="s" />
              Загрузка…
            </div>
          )}

          {packages?.length === 0 && (
            <div className="glass rounded-[18px] p-4 text-center text-[13px] text-foreground-muted">
              Пакеты временно недоступны
            </div>
          )}

          {packages?.map((pkg) => (
            <button
              key={pkg.code}
              type="button"
              data-testid="package-card"
              onClick={() => {
                setSelected(pkg);
                setStage("choose-method");
              }}
              className="glass press-scale flex w-full items-center gap-3 rounded-[18px] p-[15px] text-left"
            >
              <div className="flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-[14.5px] font-semibold">{pkg.title}</span>
                  {pkg.first_purchase_bonus > 0 && (
                    <span
                      data-testid="first-purchase-bonus"
                      className="rounded-full bg-[image:var(--brand-gradient)] px-2 py-0.5 text-[9.5px] font-bold text-white"
                    >
                      +{pkg.first_purchase_bonus} 🎁
                    </span>
                  )}
                </div>
                <div className="mt-0.5 text-[11px] text-foreground-dim">
                  💎 {pkg.credits} кредитов · ⭐ {pkg.price_stars}
                </div>
                {(pkg.approx_photos > 0 || pkg.approx_videos > 0) && (
                  <div className="mt-1 text-[10.5px] text-foreground-muted">
                    ≈ до {pkg.approx_photos} фото
                    {pkg.approx_videos > 0 && ` · ${pkg.approx_videos} видео`}
                  </div>
                )}
              </div>
              <span className="rounded-full bg-[image:var(--brand-gradient)] px-[15px] py-2 text-[12.5px] font-bold text-white shadow-glow">
                {pkg.price_rub}₽
              </span>
            </button>
          ))}

          <div className="mt-1 text-center text-[10.5px] leading-normal text-foreground-dim">
            Оплата Telegram Stars или картой (ЮKassa)
          </div>
        </div>
      )}

      {stage === "choose-method" && selected && (
        <div className="flex flex-col gap-3 px-4 pb-6 pt-2">
          <div className="px-1 text-[10px] uppercase tracking-[0.08em] text-foreground-dim">
            Оплата: {selected.title}
          </div>
          <button
            type="button"
            data-testid="pay-stars"
            onClick={() => payWithStars(selected)}
            className="glass press-scale w-full rounded-[18px] p-[15px] text-left"
          >
            <div className="text-[13.5px] font-semibold">⭐ Telegram Stars ({selected.price_stars})</div>
            <div className="mt-0.5 text-[11px] text-foreground-dim">Подходит для оплаты внутри Telegram</div>
          </button>
          <button
            type="button"
            data-testid="pay-yookassa"
            onClick={() => payWithYookassa(selected)}
            className="glass press-scale w-full rounded-[18px] p-[15px] text-left"
          >
            <div className="text-[13.5px] font-semibold">💳 Банковская карта / СБП</div>
            <div className="mt-0.5 text-[11px] text-foreground-dim">Оплата на защищённой странице ЮKassa</div>
          </button>
        </div>
      )}

      {stage === "waiting" && (
        <div className="flex flex-col items-center gap-2 px-4 pb-8 pt-4 text-center">
          <Spinner size="m" />
          <div className="mt-1.5 text-sm font-semibold">Проверяем оплату…</div>
          <div className="text-[11px] text-foreground-dim">Обычно занимает несколько секунд</div>
        </div>
      )}

      {stage === "success" && (
        <div className="flex flex-col gap-2 px-4 pb-6 pt-2 text-center">
          <div className="text-[34px]">✅</div>
          <div className="text-sm font-semibold">Кредиты начислены</div>
          <div className="text-[11px] text-foreground-dim">Баланс обновлён</div>
          <Button stretched className="mt-2" onClick={onClose}>
            Готово
          </Button>
        </div>
      )}

      {stage === "error" && (
        <div className="flex flex-col gap-2 px-4 pb-6 pt-2 text-center">
          <div className="text-sm font-semibold">Не получилось завершить оплату</div>
          <div className="text-[11px] text-foreground-dim">{errorText}</div>
          <Button stretched mode="bezeled" className="mt-2" onClick={() => setStage("pick")}>
            Попробовать снова
          </Button>
        </div>
      )}
    </Sheet>
  );
}
