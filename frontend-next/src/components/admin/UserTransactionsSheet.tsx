"use client";

import { useEffect, useState } from "react";

import { adminApi, type AdminTransactionOut } from "@/api/client";
import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Sheet } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";

const TYPE_LABELS: Record<AdminTransactionOut["type"], string> = {
  purchase: "Покупка",
  spend: "Списание",
  refund: "Возврат",
  reserve: "Резерв",
  release: "Освобождение резерва",
  admin_adjustment: "Корректировка админом",
};

interface Props {
  telegramId: number;
  onClose: () => void;
}

export default function UserTransactionsSheet({ telegramId, onClose }: Props) {
  const [transactions, setTransactions] = useState<AdminTransactionOut[] | null>(null);

  useEffect(() => {
    adminApi.userTransactions(telegramId).then(setTransactions).catch(() => setTransactions([]));
  }, [telegramId]);

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()} header={<Sheet.Header>История операций</Sheet.Header>}>
      {transactions === null && (
        <Placeholder>
          <Spinner size="m" />
        </Placeholder>
      )}
      {transactions !== null && transactions.length === 0 && (
        <Placeholder header="Пусто" description="У этого пользователя ещё нет операций." />
      )}
      {transactions !== null && transactions.length > 0 && (
        <List>
          <Section header={`Последние операции (${transactions.length})`}>
            {transactions.map((tx) => (
              <Cell
                key={tx.id}
                multiline
                subtitle={
                  `${new Date(tx.created_at).toLocaleString("ru-RU")} · баланс ${tx.balance_before}→${tx.balance_after}` +
                  (tx.description ? ` · ${tx.description}` : "")
                }
              >
                {TYPE_LABELS[tx.type]}: {tx.amount > 0 ? "+" : ""}
                {tx.amount}
              </Cell>
            ))}
          </Section>
        </List>
      )}
    </Sheet>
  );
}
