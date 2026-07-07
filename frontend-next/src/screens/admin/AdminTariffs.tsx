"use client";

import { useEffect, useState } from "react";

import { adminApi, type AdminTariffOut } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Cell } from "@/components/ui/cell";
import { Input } from "@/components/ui/input";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";

const LIMIT_FIELDS: { key: keyof AdminTariffOut; label: string }[] = [
  { key: "fast_limit", label: "Быстрые" },
  { key: "medium_limit", label: "Средние" },
  { key: "premium_limit", label: "Премиум" },
  { key: "image_limit", label: "Картинки" },
  { key: "daily_limit", label: "Дневной" },
];

function TariffRow({ tariff, onSaved }: { tariff: AdminTariffOut; onSaved: (t: AdminTariffOut) => void }) {
  const [draft, setDraft] = useState(tariff);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const updated = await adminApi.updateTariff(tariff.code, {
        fast_limit: draft.fast_limit,
        medium_limit: draft.medium_limit,
        premium_limit: draft.premium_limit,
        image_limit: draft.image_limit,
        daily_limit: draft.daily_limit,
      });
      onSaved(updated);
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(isActive: boolean) {
    const updated = await adminApi.updateTariff(tariff.code, { is_active: isActive });
    setDraft(updated);
    onSaved(updated);
  }

  return (
    <Cell
      multiline
      subtitle={`${tariff.price_rub}₽ / ${tariff.price_stars}⭐`}
      after={<Switch checked={draft.is_active} onChange={(e) => toggleActive(e.target.checked)} />}
    >
      <div className="flex flex-col gap-1.5">
        <span>{tariff.name}</span>
        <div className="flex flex-wrap gap-1.5">
          {LIMIT_FIELDS.map(({ key, label }) => (
            <Input
              key={key}
              header={label}
              type="number"
              className="w-[90px]"
              value={draft[key] as number}
              onChange={(e) => setDraft((d) => ({ ...d, [key]: Number(e.target.value) }))}
            />
          ))}
        </div>
        <Button size="s" loading={saving} onClick={save}>
          Сохранить лимиты
        </Button>
      </div>
    </Cell>
  );
}

export default function AdminTariffs() {
  const [tariffs, setTariffs] = useState<AdminTariffOut[] | null>(null);

  useEffect(() => {
    adminApi.tariffsAdmin().then(setTariffs).catch(() => setTariffs([]));
  }, []);

  if (tariffs === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <List>
      <Section header="Тарифы">
        {tariffs.map((t) => (
          <TariffRow
            key={t.code}
            tariff={t}
            onSaved={(updated) =>
              setTariffs((prev) => prev?.map((x) => (x.code === updated.code ? updated : x)) ?? null)
            }
          />
        ))}
      </Section>
    </List>
  );
}
