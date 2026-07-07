import type { ReactNode } from "react";

export function Placeholder({
  header,
  description,
  children,
}: {
  header?: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-8 text-center">
      {children}
      {header && <h2 className="heading-font text-lg font-semibold text-foreground">{header}</h2>}
      {description && <p className="text-sm text-foreground-muted">{description}</p>}
    </div>
  );
}
