import { type InputHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  header?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { header, className, ...rest },
  ref,
) {
  return (
    <label className="flex flex-col gap-1.5">
      {header && <span className="text-xs font-medium text-foreground-muted">{header}</span>}
      <input
        ref={ref}
        className={cn(
          // 16px минимум: поля мельче 16px iOS зумит при фокусе (второй рубеж
          // обороны после viewport maximum-scale=1 в layout.tsx).
          "w-full rounded-[16px] border border-border-soft bg-white/[0.05] px-3.5 py-2.5 text-[16px] text-foreground placeholder:text-foreground-dim focus:outline-none focus:ring-2 focus:ring-brand-1/70",
          className,
        )}
        {...rest}
      />
    </label>
  );
});
