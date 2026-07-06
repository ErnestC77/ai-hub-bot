import { useEffect, useState } from "react";
import { Button, Cell, List, Modal, Section, Spinner } from "@telegram-apps/telegram-ui";

import { api, type ModelOut } from "../../api/client";

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
    <Modal
      open={open}
      onOpenChange={setOpen}
      header={<Modal.Header>Выберите модель</Modal.Header>}
      trigger={
        <Button size="s" mode="bezeled">
          {selectedModel ? selectedModel.display_name : "Выбрать модель"}
        </Button>
      }
    >
      {models === null ? (
        <Spinner size="m" />
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
    </Modal>
  );
}
