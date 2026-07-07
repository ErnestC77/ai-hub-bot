import { cn } from "@/lib/cn";

const SIZE_PX: Record<"s" | "m" | "l", number> = { s: 16, m: 24, l: 32 };

export function Spinner({ size = "m", className }: { size?: "s" | "m" | "l"; className?: string }) {
  const px = SIZE_PX[size];
  return (
    <span
      className={cn("inline-block animate-spin rounded-full border-2 border-border-soft border-t-brand-2", className)}
      style={{ width: px, height: px }}
      role="status"
      aria-label="Загрузка"
    />
  );
}
