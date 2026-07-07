"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Section } from "@/components/ui/section";
import { Sheet } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { api, type ModelOut } from "@/api/client";

const CATEGORY_LABEL: Record<string, string> = {
  fast: "Быстрые",
  medium: "Средние",
  premium: "Премиум",
  image: "Картинки",
};

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

  const grouped = (models ?? []).reduce<Record<string, ModelOut[]>>((acc, model) => {
    (acc[model.category] ??= []).push(model);
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
            {Object.entries(grouped).map(([category, items]) => (
              <Section key={category} header={CATEGORY_LABEL[category] ?? category}>
                {items.map((model) => (
                  <Cell
                    key={model.model_code}
                    onClick={() => {
                      onSelect(model);
                      setOpen(false);
                    }}
                    after={model.is_premium ? "⭐" : undefined}
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
