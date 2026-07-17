"use client";

import { useEffect, useState } from "react";

import { adminApi, type AdminModelOut } from "@/api/client";
import { Cell } from "@/components/ui/cell";
import { Input } from "@/components/ui/input";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import ActionError from "@/components/admin/ActionError";
import { useActionError } from "@/components/admin/useActionError";

export default function AdminModels() {
  const [models, setModels] = useState<AdminModelOut[] | null>(null);
  const { error, run } = useActionError();

  useEffect(() => {
    adminApi.models().then(setModels).catch(() => setModels([]));
  }, []);

  function applyUpdate(updated: AdminModelOut) {
    setModels((prev) => prev?.map((m) => (m.code === updated.code ? updated : m)) ?? null);
  }

  async function updateField(
    code: string,
    patch: Partial<Pick<AdminModelOut, "min_credits" | "recommended_credits" | "sort_order">>,
  ) {
    await run(async () => {
      applyUpdate(await adminApi.updateModel(code, patch));
    });
  }

  async function toggle(code: string, field: "is_active" | "is_visible", value: boolean) {
    await run(async () => {
      applyUpdate(await adminApi.updateModel(code, { [field]: value }));
    });
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
      <ActionError error={error} />
      <Section header="Модели">
        {models.map((m) => (
          <Cell
            key={m.code}
            multiline
            subtitle={`${m.provider} · ${m.category} · ${m.tier}`}
            after={
              <div className="flex flex-col items-end gap-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-foreground-muted">Активна</span>
                  <Switch checked={m.is_active} onChange={(e) => toggle(m.code, "is_active", e.target.checked)} />
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-foreground-muted">Видима</span>
                  <Switch checked={m.is_visible} onChange={(e) => toggle(m.code, "is_visible", e.target.checked)} />
                </div>
              </div>
            }
          >
            <div className="flex flex-col gap-1.5">
              <span>{m.display_name}</span>
              <div className="flex flex-wrap gap-1.5">
                <Input
                  header="Мин. кредитов"
                  type="number"
                  className="w-[90px]"
                  defaultValue={m.min_credits}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== m.min_credits && value > 0) updateField(m.code, { min_credits: value });
                  }}
                />
                <Input
                  header="Реком. кредитов"
                  type="number"
                  className="w-[90px]"
                  defaultValue={m.recommended_credits}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== m.recommended_credits && value > 0)
                      updateField(m.code, { recommended_credits: value });
                  }}
                />
                <Input
                  header="Порядок"
                  type="number"
                  className="w-[70px]"
                  defaultValue={m.sort_order}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== m.sort_order) updateField(m.code, { sort_order: value });
                  }}
                />
              </div>
            </div>
          </Cell>
        ))}
      </Section>
    </List>
  );
}
