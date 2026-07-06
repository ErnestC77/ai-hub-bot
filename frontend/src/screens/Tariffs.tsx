import { useEffect, useState } from "react";
import { Button, Cell, List, Placeholder, Section, Spinner } from "@telegram-apps/telegram-ui";

import { api, type TariffOut } from "../api/client";
import PaymentMethodSheet from "./tariffs/PaymentMethodSheet";

export default function Tariffs() {
  const [tariffs, setTariffs] = useState<TariffOut[] | null>(null);
  const [selected, setSelected] = useState<TariffOut | null>(null);

  useEffect(() => {
    api.tariffs().then(setTariffs).catch(() => setTariffs([]));
  }, []);

  if (tariffs === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <>
      <List>
        <Section header="Тарифы">
          {tariffs.map((tariff) => (
            <Cell
              key={tariff.code}
              subtitle={tariff.description}
              after={
                <Button size="s" mode={tariff.is_current ? "gray" : "filled"} disabled={tariff.is_current} onClick={() => setSelected(tariff)}>
                  {tariff.is_current ? "Активен" : `${tariff.price_rub}₽`}
                </Button>
              }
            >
              {tariff.name}
            </Cell>
          ))}
        </Section>
      </List>

      {selected && <PaymentMethodSheet tariff={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
