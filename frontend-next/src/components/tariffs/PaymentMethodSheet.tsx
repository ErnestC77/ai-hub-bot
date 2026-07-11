"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Section } from "@/components/ui/section";
import { Sheet } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { ApiError, api, type TariffOut } from "@/api/client";
import { useMe } from "@/context/MeContext";
import { haptic, openInvoice, openLink } from "@/lib/telegram";

type Stage = "choose" | "waiting" | "success" | "error";

interface Props {
  tariff: TariffOut;
  onClose: () => void;
}

const POLL_INTERVAL_MS = 2000;
const POLL_ATTEMPTS = 15;

export default function PaymentMethodSheet({ tariff, onClose }: Props) {
  const [stage, setStage] = useState<Stage>("choose");
  const [errorText, setErrorText] = useState("");
  const { refresh } = useMe();

  async function waitForActivation() {
    setStage("waiting");
    for (let i = 0; i < POLL_ATTEMPTS; i++) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      try {
        const me = await api.me();
        // Тарифная система заменена кредитными пакетами (фазы 1-4) -- tariff_code
        // в MeOut больше нет, как и эндпойнтов createStars/YookassaPayment(tariff.code)
        // чуть ниже в этом файле. Экран целиком переписывается в под-фазе 2 фронтенд-
        // интеграции; здесь только компилируемая заглушка условия, не рабочая проверка.
        if (me.total_credits_purchased > 0) {
          await refresh();
          setStage("success");
          haptic("medium");
          return;
        }
      } catch {
        // временная сетевая ошибка при поллинге -- пробуем ещё раз
      }
    }
    setErrorText("Оплата обрабатывается дольше обычного. Проверьте баланс чуть позже.");
    setStage("error");
  }

  async function payWithStars() {
    try {
      const { invoice_link } = await api.createStarsPayment(tariff.code);
      if (!invoice_link) throw new Error("empty invoice link");
      openInvoice(invoice_link, (status) => {
        if (status === "paid") {
          void waitForActivation();
        } else if (status === "failed" || status === "cancelled") {
          setStage("choose");
        }
      });
    } catch (err) {
      setErrorText(err instanceof ApiError ? err.message : "Не удалось создать платёж");
      setStage("error");
    }
  }

  async function payWithYookassa() {
    try {
      const { confirmation_url } = await api.createYookassaPayment(tariff.code);
      if (!confirmation_url) throw new Error("empty confirmation url");
      openLink(confirmation_url);
      void waitForActivation();
    } catch (err) {
      setErrorText(err instanceof ApiError ? err.message : "Не удалось создать платёж");
      setStage("error");
    }
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()} header={<Sheet.Header>Оплата «{tariff.name}»</Sheet.Header>}>
      {stage === "choose" && (
        <List>
          <Section header="Выберите способ оплаты">
            <Cell subtitle="Подходит для оплаты внутри Telegram" onClick={payWithStars}>
              ⭐ Telegram Stars ({tariff.price_stars})
            </Cell>
            <Cell subtitle="Оплата на защищённой странице ЮKassa" onClick={payWithYookassa}>
              💳 Банковская карта / СБП
            </Cell>
          </Section>
        </List>
      )}

      {stage === "waiting" && (
        <List>
          <Section>
            <Cell before={<Spinner size="s" />} subtitle="Обычно занимает несколько секунд">
              Проверяем оплату…
            </Cell>
          </Section>
        </List>
      )}

      {stage === "success" && (
        <List>
          <Section>
            <Cell subtitle="Доступ активирован">✅ Подписка «{tariff.name}» оформлена</Cell>
            <Button stretched onClick={onClose}>
              Готово
            </Button>
          </Section>
        </List>
      )}

      {stage === "error" && (
        <List>
          <Section>
            <Cell subtitle={errorText}>Не получилось завершить оплату</Cell>
            <Button stretched mode="bezeled" onClick={() => setStage("choose")}>
              Попробовать снова
            </Button>
          </Section>
        </List>
      )}
    </Sheet>
  );
}
