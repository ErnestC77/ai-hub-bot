"use client";

import { Sheet } from "@/components/ui/sheet";
import type { ImageAspect } from "@/api/client";

const OPTIONS: { value: ImageAspect; label: string; ratio: number | null }[] = [
  { value: "auto", label: "Auto", ratio: null },
  { value: "1:1", label: "1:1", ratio: 1 },
  { value: "3:2", label: "3:2", ratio: 1.5 },
  { value: "2:3", label: "2:3", ratio: 0.667 },
  { value: "4:3", label: "4:3", ratio: 1.333 },
  { value: "3:4", label: "3:4", ratio: 0.75 },
  { value: "4:5", label: "4:5", ratio: 0.8 },
  { value: "5:4", label: "5:4", ratio: 1.25 },
  { value: "9:16", label: "9:16", ratio: 0.5625 },
  { value: "16:9", label: "16:9", ratio: 1.778 },
  { value: "21:9", label: "21:9", ratio: 2.333 },
];

function iconBox(ratio: number | null): { width: number; height: number } {
  if (ratio === null) return { width: 18, height: 18 };
  const max = 20;
  return ratio >= 1 ? { width: max, height: max / ratio } : { width: max * ratio, height: max };
}

interface Props {
  open: boolean;
  value: ImageAspect;
  onOpenChange: (open: boolean) => void;
  onSelect: (value: ImageAspect) => void;
}

export default function AspectRatioSheet({ open, value, onOpenChange, onSelect }: Props) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange} header={<Sheet.Header>Aspect ratio</Sheet.Header>}>
      <div className="grid grid-cols-2 gap-2.5 p-4">
        {OPTIONS.map((opt) => {
          const active = opt.value === value;
          const box = iconBox(opt.ratio);
          return (
            <button
              key={opt.value}
              className="press-scale flex items-center gap-3 rounded-[14px] px-3.5 py-3 text-sm font-semibold"
              onClick={() => {
                onSelect(opt.value);
                onOpenChange(false);
              }}
              style={{
                border: `1px solid ${active ? "var(--color-brand-2)" : "var(--color-border-soft)"}`,
                background: active ? "rgba(255,45,120,0.12)" : "var(--color-surface)",
                color: active ? "var(--color-brand-2)" : "#fff",
              }}
            >
              <span className="flex h-[22px] w-[22px] shrink-0 items-center justify-center">
                <span
                  className="block rounded-[3px]"
                  style={{
                    width: box.width,
                    height: box.height,
                    border: `1.5px ${opt.value === "auto" ? "dashed" : "solid"} ${
                      active ? "var(--color-brand-2)" : "var(--color-foreground-muted)"
                    }`,
                  }}
                />
              </span>
              {opt.label}
            </button>
          );
        })}
      </div>
    </Sheet>
  );
}
