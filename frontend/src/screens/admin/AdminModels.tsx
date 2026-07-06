import { useEffect, useState } from "react";
import { Cell, List, Placeholder, Section, Spinner, Switch } from "@telegram-apps/telegram-ui";

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
            subtitle={`${m.provider} · ${m.category}${m.is_premium ? " · premium" : ""}`}
            after={<Switch checked={m.is_active} onChange={(e) => toggle(m.model_code, e.target.checked)} />}
          >
            {m.display_name}
          </Cell>
        ))}
      </Section>
    </List>
  );
}
