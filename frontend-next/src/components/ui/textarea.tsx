import { type TextareaHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  header?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { header, className, ...rest },
  ref,
) {
  return (
    <label className="flex flex-col gap-1.5">
      {header && <span className="text-xs font-medium text-foreground-muted">{header}</span>}
      <textarea
        ref={ref}
        className={cn(
          "w-full rounded-[16px] border border-border-soft bg-white/[0.05] px-3.5 py-2.5 text-[15px] text-foreground placeholder:text-foreground-dim focus:outline-none focus:ring-2 focus:ring-brand-1/70",
          className,
        )}
        {...rest}
      />
    </label>
  );
});
