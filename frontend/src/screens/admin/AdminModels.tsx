import { useEffect, useState } from "react";
import { Cell, Input, List, Placeholder, Section, Spinner, Switch } from "@telegram-apps/telegram-ui";

import { adminApi, type AdminModelOut } from "../../api/client";

export default function AdminModels() {
  const [models, setModels] = useState<AdminModelOut[] | null>(null);

  useEffect(() => {
    adminApi.models().then(setModels).catch(() => setModels([]));
  }, []);

  async function toggle(modelCode: string, isActive: boolean) {
    const updated = await adminApi.toggleModel(modelCode, isActive);
    setModels((prev) => prev?.map((m) => (m.model_code === modelCode ? updated : m)) ?? null);
  }

  async function updateCreditCost(modelCode: string, creditCost: number) {
    const updated = await adminApi.updateModelCreditCost(modelCode, creditCost);
    setModels((prev) => prev?.map((m) => (m.model_code === modelCode ? updated : m)) ?? null);
  }

  if (models === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <List>
      <Section header="Модели">
        {models.map((m) => (
          <Cell
            key={m.model_code}
            multiline
            subtitle={`${m.provider} · ${m.category}${m.is_premium ? " · premium" : ""}`}
            after={<Switch checked={m.is_active} onChange={(e) => toggle(m.model_code, e.target.checked)} />}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span>{m.display_name}</span>
              <Input
                type="number"
                header="Кредитов"
                style={{ width: 70 }}
                defaultValue={m.credit_cost}
                onBlur={(e) => {
                  const value = Number(e.target.value);
                  if (value !== m.credit_cost && value > 0) updateCreditCost(m.model_code, value);
                }}
              />
            </div>
          </Cell>
        ))}
      </Section>
    </List>
  );
}
