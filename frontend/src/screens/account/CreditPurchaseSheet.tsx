import { useEffect, useState } from "react";
import { Button, Cell, List, Modal, Section, Spinner } from "@telegram-apps/telegram-ui";

import { ApiError, api, type CreditPackageOut } from "../../api/client";
import { useMe } from "../../context/MeContext";
import { haptic, openInvoice, openLink } from "../../lib/telegram";

type Stage = "pick" | "choose-method" | "waiting" | "success" | "error";

interface Props {
  onClose: () => void;
}

const POLL_INTERVAL_MS = 2000;
const POLL_ATTEMPTS = 15;

export default function CreditPurchaseSheet({ onClose }: Props) {
  const [stage, setStage] = useState<Stage>("pick");
  const [packages, setPackages] = useState<CreditPackageOut[] | null>(null);
  const [selected, setSelected] = useState<CreditPackageOut | null>(null);
  const [errorText, setErrorText] = useState("");
  const { me, refresh } = useMe();

  useEffect(() => {
    api.creditPackages().then(setPackages).catch(() => setPackages([]));
  }, []);

  async function waitForCredit(initialBalance: number) {
    setStage("waiting");
    for (let i = 0; i < POLL_ATTEMPTS; i++) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      try {
        const fresh = await api.me();
        if (fresh.credits_balance > initialBalance) {
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

  async function payWithStars(pkg: CreditPackageOut) {
    try {
      const { invoice_link } = await api.createStarsCreditPayment(pkg.code);
      if (!invoice_link) throw new Error("empty invoice link");
      const initialBalance = me?.credits_balance ?? 0;
      openInvoice(invoice_link, (status) => {
        if (status === "paid") {
          void waitForCredit(initialBalance);
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
      const { confirmation_url } = await api.createYookassaCreditPayment(pkg.code);
      if (!confirmation_url) throw new Error("empty confirmation url");
      openLink(confirmation_url);
      void waitForCredit(me?.credits_balance ?? 0);
    } catch (err) {
      setErrorText(err instanceof ApiError ? err.message : "Не удалось создать платёж");
      setStage("error");
    }
  }

  return (
    <Modal open onOpenChange={(open) => !open && onClose()} header={<Modal.Header>Купить кредиты</Modal.Header>}>
      {stage === "pick" && (
        <List>
          <Section header="Выберите пакет">
            {packages === null && (
              <Cell before={<Spinner size="s" />}>Загрузка…</Cell>
            )}
            {packages?.map((pkg) => (
              <Cell
                key={pkg.code}
                subtitle={`${pkg.price_rub}₽ / ${pkg.price_stars}⭐`}
                onClick={() => {
                  setSelected(pkg);
                  setStage("choose-method");
                }}
              >
                {pkg.name}
              </Cell>
            ))}
          </Section>
        </List>
      )}

      {stage === "choose-method" && selected && (
        <List>
          <Section header={`Оплата: ${selected.name}`}>
            <Cell subtitle="Подходит для оплаты внутри Telegram" onClick={() => payWithStars(selected)}>
              ⭐ Telegram Stars ({selected.price_stars})
            </Cell>
            <Cell subtitle="Оплата на защищённой странице ЮKassa" onClick={() => payWithYookassa(selected)}>
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
            <Cell subtitle="Баланс обновлён">✅ Кредиты начислены</Cell>
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
            <Button stretched mode="bezeled" onClick={() => setStage("pick")}>
              Попробовать снова
            </Button>
          </Section>
        </List>
      )}
    </Modal>
  );
}
