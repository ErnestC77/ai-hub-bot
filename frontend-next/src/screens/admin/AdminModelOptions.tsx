"use client";

import { useEffect, useState } from "react";

import { adminApi, type AdminModelOptionOut, type AdminModelOut } from "@/api/client";
import { Cell } from "@/components/ui/cell";
import { Input } from "@/components/ui/input";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Select } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";

const KIND_LABEL: Record<string, string> = {
  quality: "Качество",
  duration: "Длительность",
  audio: "Звук",
};

export default function AdminModelOptions() {
  const [models, setModels] = useState<AdminModelOut[] | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [options, setOptions] = useState<AdminModelOptionOut[] | null>(null);
  const [error, setError] = useState("");

  // Только медиа-модели: у текстовых опций нет.
  useEffect(() => {
    adminApi
      .models()
      .then((all) => {
        const media = all.filter((m) => m.category !== "text");
        setModels(media);
        if (media.length > 0) setSelected(media[0].code);
      })
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    if (!selected) return;
    // Сброс перед перезагрузкой при смене модели -- намеренно, не производное состояние.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOptions(null);
    adminApi
      .modelOptions(selected)
      .then(setOptions)
      .catch(() => setOptions([]));
  }, [selected]);

  function applyUpdate(updated: AdminModelOptionOut) {
    // Смена дефолта могла снять флаг с другой опции -- перечитываем весь список.
    if (updated.is_default) {
      adminApi
        .modelOptions(selected)
        .then(setOptions)
        .catch(() => {});
      return;
    }
    setOptions((prev) => prev?.map((o) => (o.id === updated.id ? updated : o)) ?? null);
  }

  async function patch(
    id: number,
    body: Partial<Pick<AdminModelOptionOut, "label" | "credits_multiplier" | "sort_order" | "is_active" | "is_default">>,
  ) {
    setError("");
    try {
      applyUpdate(await adminApi.updateOption(id, body));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить");
    }
  }

  if (models === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }
  if (models.length === 0) {
    return <Placeholder header="Нет медиа-моделей" description="Опции есть только у фото/видео-моделей." />;
  }

  // Группировка по kind, порядок как пришёл (бэк сортирует по kind, sort_order).
  const byKind: Record<string, AdminModelOptionOut[]> = {};
  for (const o of options ?? []) (byKind[o.kind] ??= []).push(o);

  return (
    <List>
      <Section header="Модель">
        <Cell>
          <Select value={selected} onChange={(e) => setSelected(e.target.value)}>
            {models.map((m) => (
              <option key={m.code} value={m.code}>
                {m.display_name}
              </option>
            ))}
          </Select>
        </Cell>
      </Section>

      <Section header="⚠️ Осторожно с множителями">
        <Cell
          multiline
          subtitle="Множители выведены из реальных списаний провайдера. Ручная правка расходится с фактической себестоимостью -- меняйте только зная, что делаете."
        >
          Множители = цена относительно дефолта
        </Cell>
      </Section>

      {options === null ? (
        <Placeholder>
          <Spinner size="s" />
        </Placeholder>
      ) : options.length === 0 ? (
        <Placeholder header="Опций нет" description="У этой модели нет настраиваемых опций." />
      ) : (
        Object.entries(byKind).map(([kind, opts]) => (
          <Section key={kind} header={KIND_LABEL[kind] ?? kind}>
            {opts.map((o) => (
              <Cell
                key={o.id}
                multiline
                subtitle={o.is_default ? "дефолт" : undefined}
                after={
                  <div className="flex flex-col items-end gap-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-foreground-muted">Активна</span>
                      <Switch checked={o.is_active} onChange={(e) => patch(o.id, { is_active: e.target.checked })} />
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-foreground-muted">Дефолт</span>
                      <Switch checked={o.is_default} onChange={(e) => patch(o.id, { is_default: e.target.checked })} />
                    </div>
                  </div>
                }
              >
                <div className="flex flex-col gap-1.5">
                  <span>
                    {o.label} <span className="text-xs text-foreground-muted">({o.code})</span>
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    <Input
                      header="Множитель"
                      type="number"
                      step="0.001"
                      className="w-[90px]"
                      defaultValue={o.credits_multiplier}
                      onBlur={(e) => {
                        const v = Number(e.target.value);
                        if (v !== o.credits_multiplier && v > 0) patch(o.id, { credits_multiplier: v });
                      }}
                    />
                    <Input
                      header="Порядок"
                      type="number"
                      className="w-[70px]"
                      defaultValue={o.sort_order}
                      onBlur={(e) => {
                        const v = Number(e.target.value);
                        if (v !== o.sort_order) patch(o.id, { sort_order: v });
                      }}
                    />
                  </div>
                  <code className="text-[10px] text-foreground-dim">{JSON.stringify(o.provider_params)}</code>
                </div>
              </Cell>
            ))}
          </Section>
        ))
      )}

      {error && (
        <Section>
          <Cell subtitle={error}>Ошибка</Cell>
        </Section>
      )}
    </List>
  );
}
