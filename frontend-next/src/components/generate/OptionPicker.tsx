"use client";

import { SegmentedControl } from "@/components/ui/segmented-control";
import type { ModelOptionKind, ModelOut } from "@/api/client";
import { optionsOfKind } from "@/lib/optionPricing";

interface Props {
  model: ModelOut | null;
  kind: ModelOptionKind;
  label: string;
  selected: string | undefined;
  onSelect: (code: string) => void;
}

/**
 * Секция выбора опции. Рисует ТО, ЧТО МОДЕЛЬ УМЕЕТ, и ничего не хардкодит:
 * у nano_banana и flux_kontext_pro у fal нет ручки размера, у kling нельзя
 * менять разрешение, у ovi -- ни разрешения, ни длительности. Для них
 * секции просто не будет: нарисовать селектор, которого провайдер не
 * понимает, значит соврать пользователю.
 */
export default function OptionPicker({ model, kind, label, selected, onSelect }: Props) {
  const options = optionsOfKind(model, kind);
  if (options.length === 0) return null;

  return (
    <div data-testid={`option-${kind}`}>
      <div className="mb-2 px-1 text-[10px] font-semibold tracking-[.08em] text-foreground-dim uppercase">
        {label}
      </div>
      <div className="overflow-x-auto">
        <div className="w-max min-w-full">
          <SegmentedControl>
            {options.map((o) => (
              <SegmentedControl.Item
                key={o.code}
                selected={selected === o.code}
                onClick={() => onSelect(o.code)}
              >
                <span className="whitespace-nowrap" data-testid={`option-${kind}-${o.code}`}>
                  {o.label}
                </span>
              </SegmentedControl.Item>
            ))}
          </SegmentedControl>
        </div>
      </div>
    </div>
  );
}
