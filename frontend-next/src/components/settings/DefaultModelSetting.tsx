"use client";

import { useEffect, useState } from "react";

import { Cell } from "@/components/ui/cell";
import { Spinner } from "@/components/ui/spinner";
import { api, type ModelOut } from "@/api/client";
import { useMe } from "@/context/MeContext";
import { modelDescription } from "@/lib/modelDescriptions";
import { modelStyle } from "@/lib/modelStyles";

/**
 * Выбор модели по умолчанию для чата. Живёт на экранах Настроек и Аккаунта.
 * Список -- только текстовые модели (дефолт применяется на входе в чат), их же
 * пропускает бэкенд PUT /api/me/default-model. Текущий выбор -- галочка;
 * тап по строке сохраняет и обновляет /api/me.
 */
export default function DefaultModelSetting() {
  const { me, refresh } = useMe();
  const [models, setModels] = useState<ModelOut[] | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .models("text")
      .then((list) => !cancelled && setModels(list))
      .catch(() => !cancelled && setModels([]));
    return () => {
      cancelled = true;
    };
  }, []);

  async function choose(code: string) {
    if (saving || me?.default_model_code === code) return;
    setSaving(code);
    try {
      await api.setDefaultModel(code);
      await refresh();
    } catch {
      // тихо: не критично, юзер может повторить
    } finally {
      setSaving(null);
    }
  }

  if (models === null) {
    return (
      <div className="flex justify-center py-6" data-testid="default-model-loading">
        <Spinner size="s" />
      </div>
    );
  }
  if (models.length === 0) return null;

  return (
    <div data-testid="default-model-setting">
      {models.map((m) => {
        const active = me?.default_model_code === m.code;
        const brand = modelStyle(m.code).brand;
        return (
          <Cell
            key={m.code}
            onClick={() => choose(m.code)}
            multiline
            subtitle={modelDescription(m.code, brand) || undefined}
            after={
              saving === m.code ? (
                <Spinner size="s" />
              ) : active ? (
                <span className="text-[15px] text-[var(--accent,#8b5cff)]" data-testid="default-model-check">
                  ✓
                </span>
              ) : null
            }
          >
            {m.display_name}
          </Cell>
        );
      })}
    </div>
  );
}
