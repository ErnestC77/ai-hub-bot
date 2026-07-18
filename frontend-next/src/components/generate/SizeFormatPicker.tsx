"use client";

import { SegmentedControl } from "@/components/ui/segmented-control";
import type { ModelOut } from "@/api/client";
import { optionsOfKind } from "@/lib/optionPricing";

/**
 * Два ряда (Размер / Формат кадра) поверх ОДНОЙ оси quality с комбо-кодами
 * `<size>__<fmt>` (qwen_image, seedream: аспект и размер -- одно поле
 * image_size у провайдера, поэтому в БД -- полная матрица комбинаций, а не
 * две оси). Выбор склеивается в один код: тап по размеру сохраняет формат,
 * тап по формату -- размер. Цену несёт комбо-опция целиком, так что CTA
 * работает без изменений.
 */

/** Комбо-код? Матрица использует `__`, обычные коды (1k, 480p) -- нет. */
export function isSizeFormatCombo(model: ModelOut | null): boolean {
  const options = optionsOfKind(model, "quality");
  return options.length > 0 && options.every((o) => o.code.includes("__"));
}

function sizeLabel(size: string): string {
  return size.toUpperCase(); // "1k" -> "1K"
}

function formatLabel(fmt: string): string {
  return fmt.replaceAll("_", ":"); // "16_9" -> "16:9"
}

interface Props {
  model: ModelOut | null;
  /** Текущий комбо-код ("2k__16_9"); undefined до автовыбора дефолта. */
  selected: string | undefined;
  onSelect: (comboCode: string) => void;
}

export default function SizeFormatPicker({ model, selected, onSelect }: Props) {
  const options = optionsOfKind(model, "quality");
  if (options.length === 0 || !isSizeFormatCombo(model)) return null;

  // Порядок рядов -- порядок первого появления в sort_order.
  const sizes: string[] = [];
  const formats: string[] = [];
  for (const o of options) {
    const [size, fmt] = o.code.split("__");
    if (!sizes.includes(size)) sizes.push(size);
    if (!formats.includes(fmt)) formats.push(fmt);
  }

  const [selSize, selFmt] = (selected ?? options[0].code).split("__");

  function pick(size: string, fmt: string) {
    const exact = options.find((o) => o.code === `${size}__${fmt}`);
    // Матрица полная, но если админ отключил комбинацию -- берём первую
    // живую с тем же размером, а не шлём несуществующий код (400 на бэке).
    const fallback = options.find((o) => o.code.startsWith(`${size}__`));
    const picked = exact ?? fallback;
    if (picked) onSelect(picked.code);
  }

  // Порядок и заголовки едины со всеми моделями (см. OutputOptions):
  // «Формат кадра» сверху, «Разрешение» снизу. Так qwen/seedream (комбо) и
  // flux/видео (независимые оси) выглядят одинаково.
  return (
    <>
      <div data-testid="option-format">
        <div className="mb-2 px-1 text-[10px] font-semibold tracking-[.08em] text-foreground-dim uppercase">
          Формат кадра
        </div>
        <div className="overflow-x-auto">
          <div className="w-max min-w-full">
            <SegmentedControl>
              {formats.map((fmt) => (
                <SegmentedControl.Item
                  key={fmt}
                  selected={selFmt === fmt}
                  onClick={() => pick(selSize, fmt)}
                >
                  <span className="whitespace-nowrap" data-testid={`option-format-${fmt}`}>
                    {formatLabel(fmt)}
                  </span>
                </SegmentedControl.Item>
              ))}
            </SegmentedControl>
          </div>
        </div>
      </div>
      <div data-testid="option-size">
        <div className="mb-2 px-1 text-[10px] font-semibold tracking-[.08em] text-foreground-dim uppercase">
          Разрешение
        </div>
        <SegmentedControl>
          {sizes.map((size) => (
            <SegmentedControl.Item
              key={size}
              selected={selSize === size}
              onClick={() => pick(size, selFmt)}
            >
              <span className="whitespace-nowrap" data-testid={`option-size-${size}`}>
                {sizeLabel(size)}
              </span>
            </SegmentedControl.Item>
          ))}
        </SegmentedControl>
      </div>
    </>
  );
}
