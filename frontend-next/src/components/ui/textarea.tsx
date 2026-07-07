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
          "w-full rounded-md border border-border-soft bg-transparent px-3 py-2.5 text-[15px] text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-brand-2",
          className,
        )}
        {...rest}
      />
    </label>
  );
});
