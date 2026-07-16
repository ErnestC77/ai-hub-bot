import { type SelectHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  header?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { header, className, children, ...rest },
  ref,
) {
  return (
    <label className="flex flex-col gap-1.5">
      {header && <span className="text-xs font-medium text-foreground-muted">{header}</span>}
      <select
        ref={ref}
        className={cn(
          "w-full rounded-[16px] border border-border-soft bg-bg-elevated px-3.5 py-2.5 text-[15px] text-foreground focus:outline-none focus:ring-2 focus:ring-brand-1/70",
          className,
        )}
        {...rest}
      >
        {children}
      </select>
    </label>
  );
});
