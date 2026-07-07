import { Modal } from "@telegram-apps/telegram-ui";

import type { ImageResolution } from "../api/client";

const OPTIONS: { value: ImageResolution; label: string; hint: string }[] = [
  { value: "1k", label: "1K", hint: "Стандартное качество" },
  { value: "2k", label: "2K", hint: "Больше деталей (HD)" },
  { value: "4k", label: "4K", hint: "HD + честный 2x апскейл" },
];

interface Props {
  open: boolean;
  value: ImageResolution;
  onOpenChange: (open: boolean) => void;
  onSelect: (value: ImageResolution) => void;
}

export default function ResolutionSheet({ open, value, onOpenChange, onSelect }: Props) {
  return (
    <Modal open={open} onOpenChange={onOpenChange} header={<Modal.Header>Quality</Modal.Header>}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 16 }}>
        {OPTIONS.map((opt) => {
          const active = opt.value === value;
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
                padding: "14px 16px",
                borderRadius: 14,
                border: `1px solid ${active ? "var(--brand-2)" : "var(--border-soft)"}`,
                background: active ? "rgba(255,45,120,0.12)" : "var(--surface)",
                textAlign: "left",
              }}
            >
              <span style={{ fontSize: 20 }}>👑</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 15, color: active ? "var(--brand-2)" : "#fff" }}>
                  {opt.label}
                </div>
                <div style={{ fontSize: 12, color: "var(--foreground-muted)" }}>{opt.hint}</div>
              </div>
            </button>
          );
        })}
      </div>
    </Modal>
  );
}
