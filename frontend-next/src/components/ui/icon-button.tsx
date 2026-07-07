import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

export const IconButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement>>(
  function IconButton({ className, ...rest }, ref) {
    return (
      <button
        ref={ref}
        className={cn(
          "press-scale inline-flex h-8 w-8 items-center justify-center rounded-full bg-surface text-foreground border border-border-soft",
          className,
        )}
        {...rest}
      />
    );
  },
);
