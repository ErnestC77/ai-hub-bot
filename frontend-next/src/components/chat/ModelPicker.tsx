"use client";

import { useEffect, useState } from "react";

import { SegmentedControl } from "@/components/ui/segmented-control";
import { Spinner } from "@/components/ui/spinner";
import { api, type ModelOut } from "@/api/client";
import { useMe } from "@/context/MeContext";
import { resolveModel } from "@/lib/resolveModel";

interface Props {
  selectedModel: ModelOut | null;
  onSelect: (model: ModelOut) => void;
  /** Код из ?model= -- юзер тапнул конкретную карточку модели на Home. */
  preferredCode?: string | null;
}

/**
 * Сегмент-переключатель текстовых моделей (дизайн Aurora Glass, chat sheet).
 * Модели приходят из api.models("text") и управляются админкой — ничего не хардкодим.
 * Если моделей больше, чем помещается, ряд скроллится по горизонтали.
 */
export default function ModelPicker({ selectedModel, onSelect, preferredCode }: Props) {
  const { me } = useMe();
  const [models, setModels] = useState<ModelOut[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .models("text")
      .then((list) => {
        if (!cancelled) setModels(list);
      })
      .catch(() => {
        if (!cancelled) setModels([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Авто-выбор: ?model= с Home > default_model_code из /api/me > первая из списка
  // (бэкенд отдаёт список отсортированным по sort_order). См. lib/resolveModel.
  useEffect(() => {
    if (selectedModel || !models || models.length === 0) return;
    const picked = resolveModel(models, preferredCode ?? null, me?.default_model_code);
    if (picked) onSelect(picked);
  }, [models, me, selectedModel, onSelect, preferredCode]);

  if (models === null) {
    return (
      <div className="glass flex justify-center rounded-[16px] p-2" data-testid="chat-model-picker">
        <Spinner size="s" />
      </div>
    );
  }

  // Нет доступных моделей — не рисуем ничего (данных нет, не выдумываем).
  if (models.length === 0) return null;

  return (
    <div className="overflow-x-auto" data-testid="chat-model-picker">
      <div className="w-max min-w-full">
        <SegmentedControl>
          {models.map((m) => (
            <SegmentedControl.Item
              key={m.code}
              selected={selectedModel?.code === m.code}
              onClick={() => onSelect(m)}
            >
              <span className="whitespace-nowrap">{m.display_name}</span>
            </SegmentedControl.Item>
          ))}
        </SegmentedControl>
      </div>
    </div>
  );
}
