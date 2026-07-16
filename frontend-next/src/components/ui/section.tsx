import type { ReactNode } from "react";

export function Section({
  header,
  footer,
  children,
}: {
  header?: string;
  footer?: string;
  children: ReactNode;
}) {
  return (
    <div>
      {header && (
        <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-foreground-dim">
          {header}
        </div>
      )}
      <div className="glass overflow-hidden rounded-[16px]">{children}</div>
      {footer && <div className="px-3 pt-1.5 text-xs text-foreground-dim">{footer}</div>}
    </div>
  );
}
