"use client";

import { useEffect, useState } from "react";

import { adminApi, type AdminPaymentOut } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";

export default function AdminPayments() {
  const [payments, setPayments] = useState<AdminPaymentOut[] | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    adminApi.payments().then(setPayments).catch(() => setPayments([]));
  }, []);

  async function doRefund(id: number) {
    setBusy(id);
    try {
      const updated = await adminApi.refundPayment(id);
      setPayments((prev) => prev?.map((p) => (p.id === id ? updated : p)) ?? null);
    } finally {
      setBusy(null);
    }
  }

  if (payments === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <List>
      <Section header="Последние платежи">
        {payments.map((p) => (
          <Cell
            key={p.id}
            subtitle={`${p.provider} · ${p.status} · tg:${p.telegram_id} · ${new Date(p.created_at).toLocaleString("ru-RU")}`}
            after={
              p.status === "succeeded" && (
                <Button size="s" mode="outline" loading={busy === p.id} onClick={() => doRefund(p.id)}>
                  Возврат
                </Button>
              )
            }
          >
            {p.amount} {p.currency}
          </Cell>
        ))}
      </Section>
    </List>
  );
}
