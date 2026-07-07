import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface CellProps {
  before?: ReactNode;
  after?: ReactNode;
  subtitle?: string;
  multiline?: boolean;
  onClick?: () => void;
  children?: ReactNode;
  className?: string;
}

export function Cell({ before, after, subtitle, multiline, onClick, children, className }: CellProps) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-3 border-b border-border-soft px-4 py-3 text-left last:border-b-0",
        onClick && "press-scale",
        className,
      )}
    >
      {before}
      <div className={cn("min-w-0 flex-1", multiline ? "" : "truncate")}>
        <div className="truncate text-[15px] text-foreground">{children}</div>
        {subtitle && <div className="truncate text-xs text-foreground-muted">{subtitle}</div>}
      </div>
      {after}
    </Tag>
  );
}
