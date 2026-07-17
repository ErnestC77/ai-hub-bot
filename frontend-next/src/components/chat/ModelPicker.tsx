"use client";

import { useEffect, useState } from "react";

import DragScroll from "@/components/DragScroll";
import { Spinner } from "@/components/ui/spinner";
import { api, type ModelOut } from "@/api/client";
import { useMe } from "@/context/MeContext";
import { cn } from "@/lib/cn";
import { modelDescription } from "@/lib/modelDescriptions";
import { modelStyle } from "@/lib/modelStyles";
import { resolveModel } from "@/lib/resolveModel";

interface Props {
  selectedModel: ModelOut | null;
  onSelect: (model: ModelOut) => void;
  /** Код из ?model= -- юзер тапнул конкретную карточку модели на Home. */
  preferredCode?: string | null;
}

/**
 * Переключатель текстовых моделей в чате (Aurora Glass). Модели приходят из
 * api.models("text") и управляются админкой -- ничего не хардкодим. Ряд
 * скроллится по горизонтали, мышью тоже (DragScroll -- иначе на десктопе его
 * не потащить). Под рядом -- описание выбранной модели и кнопка сделать её
 * моделью по умолчанию.
 */
export default function ModelPicker({ selectedModel, onSelect, preferredCode }: Props) {
  const { me, refresh } = useMe();
  const [models, setModels] = useState<ModelOut[] | null>(null);
  const [savingDefault, setSavingDefault] = useState(false);

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

  // Нет доступных моделей -- не рисуем ничего (данных нет, не выдумываем).
  if (models.length === 0) return null;

  const isDefault = !!selectedModel && me?.default_model_code === selectedModel.code;
  const description = selectedModel
    ? modelDescription(selectedModel.code, modelStyle(selectedModel.code).brand)
    : "";

  async function makeDefault() {
    if (!selectedModel || savingDefault) return;
    setSavingDefault(true);
    try {
      await api.setDefaultModel(selectedModel.code);
      await refresh();
    } catch {
      // тихо: не критично, юзер может повторить
    } finally {
      setSavingDefault(false);
    }
  }

  return (
    <div data-testid="chat-model-picker">
      <DragScroll
        data-testid="chat-model-row"
        className="flex cursor-grab select-none gap-1.5 overflow-x-auto rounded-[16px] bg-white/[0.05] p-1 active:cursor-grabbing [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {models.map((m) => (
          <button
            key={m.code}
            data-testid="chat-model-item"
            onClick={() => onSelect(m)}
            className={cn(
              "press-scale flex-none whitespace-nowrap rounded-[12px] px-3 py-2 text-[12px] font-semibold transition-colors",
              selectedModel?.code === m.code
                ? "bg-[image:var(--brand-gradient)] text-white"
                : "text-foreground-muted",
            )}
          >
            {m.display_name}
          </button>
        ))}
      </DragScroll>

      {/* Описание выбранной модели + кнопка «по умолчанию». Пустое описание
          (незнакомый код) строку не рисует -- не оставляем висящий блок. */}
      {selectedModel && (description || !isDefault) && (
        <div className="mt-1.5 flex items-center gap-2 px-1">
          {description && (
            <span className="min-w-0 flex-1 truncate text-[11px] text-foreground-dim">
              {description}
            </span>
          )}
          {isDefault ? (
            <span className="flex-none text-[10.5px] text-foreground-dim" data-testid="chat-is-default">
              ★ по умолчанию
            </span>
          ) : (
            <button
              type="button"
              data-testid="chat-make-default"
              onClick={makeDefault}
              disabled={savingDefault}
              className="press-scale flex-none rounded-full bg-white/[0.08] px-2.5 py-1 text-[10.5px] font-medium text-foreground-muted disabled:opacity-50"
            >
              ☆ сделать по умолчанию
            </button>
          )}
        </div>
      )}
    </div>
  );
}
