"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Section } from "@/components/ui/section";
import { Sheet } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { api, type ModelOut } from "@/api/client";

const TIER_LABEL: Record<string, string> = {
  economy: "Эконом",
  standard: "Стандарт",
  premium: "Премиум",
  pro: "Pro",
  ultra: "Ultra",
};

const STARRED_TIERS = new Set(["pro", "ultra"]);

interface Props {
  selectedModel: ModelOut | null;
  onSelect: (model: ModelOut) => void;
}

export default function ModelPicker({ selectedModel, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const [models, setModels] = useState<ModelOut[] | null>(null);

  useEffect(() => {
    if (open && models === null) {
      api.models().then(setModels).catch(() => setModels([]));
    }
  }, [open, models]);

  // Бэкенд отдаёт список уже отсортированным по sort_order (эконом -> ultra),
  // поэтому порядок секций -- порядок первого появления tier в ответе;
  // второй сортировки на фронте не требуется.
  const grouped = (models ?? []).reduce<Record<string, ModelOut[]>>((acc, model) => {
    (acc[model.tier] ??= []).push(model);
    return acc;
  }, {});

  return (
    <>
      <Button size="s" mode="bezeled" onClick={() => setOpen(true)}>
        {selectedModel ? selectedModel.display_name : "Выбрать модель"}
      </Button>

      <Sheet open={open} onOpenChange={setOpen} header={<Sheet.Header>Выберите модель</Sheet.Header>}>
        {models === null ? (
          <div className="flex justify-center p-6">
            <Spinner size="m" />
          </div>
        ) : (
          <List>
            {Object.entries(grouped).map(([tier, items]) => (
              <Section key={tier} header={TIER_LABEL[tier] ?? tier}>
                {items.map((model) => (
                  <Cell
                    key={model.code}
                    onClick={() => {
                      onSelect(model);
                      setOpen(false);
                    }}
                    after={STARRED_TIERS.has(model.tier) ? "⭐" : undefined}
                  >
                    {model.display_name}
                  </Cell>
                ))}
              </Section>
            ))}
          </List>
        )}
      </Sheet>
    </>
  );
}
