"use client";

import type { ModelOut } from "@/api/client";
import OptionPicker from "./OptionPicker";
import SizeFormatPicker, { isSizeFormatCombo } from "./SizeFormatPicker";

interface Props {
  model: ModelOut | null;
  /** Выбранные коды опций по видам ({quality, aspect_ratio, duration, audio}). */
  value: Record<string, string>;
  onChange: (kind: string, code: string) => void;
}

/**
 * Единый выбор выходных параметров для ЛЮБОЙ модели — фото и видео.
 *
 * Всегда один и тот же порядок и одни заголовки:
 *   Формат кадра → Разрешение → Длительность → Звук.
 * Секции, которых у модели нет, скрываются сами (OptionPicker и
 * SizeFormatPicker возвращают null при отсутствии опций). Поэтому вид не
 * зависит от того, как параметры устроены в fal: qwen/seedream (аспект+размер
 * в одном поле image_size → комбо-матрица) и flux/видео (независимые оси)
 * выглядят одинаково. Контракты провайдера не меняются — это только подача.
 */
export default function OutputOptions({ model, value, onChange }: Props) {
  return (
    <div className="space-y-4">
      {isSizeFormatCombo(model) ? (
        // Комбо-матрица сама рисует обе секции (Формат кадра + Разрешение).
        <SizeFormatPicker
          model={model}
          selected={value.quality}
          onSelect={(code) => onChange("quality", code)}
        />
      ) : (
        <>
          <OptionPicker
            model={model}
            kind="aspect_ratio"
            label="Формат кадра"
            selected={value.aspect_ratio}
            onSelect={(code) => onChange("aspect_ratio", code)}
          />
          <OptionPicker
            model={model}
            kind="quality"
            label="Разрешение"
            selected={value.quality}
            onSelect={(code) => onChange("quality", code)}
          />
        </>
      )}
      <OptionPicker
        model={model}
        kind="duration"
        label="Длительность"
        selected={value.duration}
        onSelect={(code) => onChange("duration", code)}
      />
      <OptionPicker
        model={model}
        kind="audio"
        label="Звук"
        selected={value.audio}
        onSelect={(code) => onChange("audio", code)}
      />
    </div>
  );
}
