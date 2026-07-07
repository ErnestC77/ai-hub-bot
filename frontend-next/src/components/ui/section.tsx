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
        <div className="px-3 pb-1.5 text-xs font-medium uppercase tracking-wide text-foreground-muted">{header}</div>
      )}
      <div className="overflow-hidden rounded-lg border border-border-soft bg-surface">{children}</div>
      {footer && <div className="px-3 pt-1.5 text-xs text-foreground-muted">{footer}</div>}
    </div>
  );
}
