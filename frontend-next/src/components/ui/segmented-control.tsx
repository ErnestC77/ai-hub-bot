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
        "press-scale flex-1 rounded-[12px] px-3 py-2 text-[12px] font-semibold transition-colors",
        selected ? "bg-[image:var(--brand-gradient)] text-white" : "text-foreground-muted",
      )}
    >
      {children}
    </button>
  );
}

function SegmentedControlRoot({ children }: { children: ReactNode }) {
  return <div className="glass flex gap-1.5 rounded-[16px] p-1">{children}</div>;
}

export const SegmentedControl = Object.assign(SegmentedControlRoot, { Item: SegmentedControlItem });
