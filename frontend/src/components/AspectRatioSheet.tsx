import { Modal } from "@telegram-apps/telegram-ui";

import type { ImageAspect } from "../api/client";

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
    <Modal open={open} onOpenChange={onOpenChange} header={<Modal.Header>Aspect ratio</Modal.Header>}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, padding: 16 }}>
        {OPTIONS.map((opt) => {
          const active = opt.value === value;
          const box = iconBox(opt.ratio);
          return (
            <button
              key={opt.value}
              className="press-scale"
              onClick={() => {
                onSelect(opt.value);
                onOpenChange(false);
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "12px 14px",
                borderRadius: 14,
                border: `1px solid ${active ? "var(--brand-2)" : "var(--border-soft)"}`,
                background: active ? "rgba(255,45,120,0.12)" : "var(--surface)",
                color: active ? "var(--brand-2)" : "#fff",
                fontWeight: 600,
                fontSize: 14,
              }}
            >
              <span
                style={{
                  width: 22,
                  height: 22,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <span
                  style={{
                    width: box.width,
                    height: box.height,
                    border: `1.5px ${opt.value === "auto" ? "dashed" : "solid"} ${
                      active ? "var(--brand-2)" : "var(--foreground-muted)"
                    }`,
                    borderRadius: 3,
                    display: "block",
                  }}
                />
              </span>
              {opt.label}
            </button>
          );
        })}
      </div>
    </Modal>
  );
}
