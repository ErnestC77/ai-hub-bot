import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

function SegmentedControlItem({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "press-scale flex-1 rounded-full px-3 py-2 text-sm font-medium transition-colors",
        selected ? "bg-[image:var(--brand-gradient)] text-white" : "text-foreground-muted",
      )}
    >
      {children}
    </button>
  );
}

function SegmentedControlRoot({ children }: { children: ReactNode }) {
  return <div className="flex gap-1 rounded-full border border-border-soft bg-surface p-1">{children}</div>;
}

export const SegmentedControl = Object.assign(SegmentedControlRoot, { Item: SegmentedControlItem });
