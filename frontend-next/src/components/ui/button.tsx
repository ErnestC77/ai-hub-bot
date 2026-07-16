import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";
import { Spinner } from "@/components/ui/spinner";

export type ButtonMode = "filled" | "bezeled" | "gray" | "outline" | "white" | "plain";
export type ButtonSize = "s" | "m" | "l";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  mode?: ButtonMode;
  size?: ButtonSize;
  stretched?: boolean;
  loading?: boolean;
  /** Glow color for mode="filled" CTAs. "cyan" is the video-CTA variant. Default: "violet". */
  glow?: "violet" | "cyan";
}

const MODE_CLASSES: Record<ButtonMode, string> = {
  filled: "bg-[image:var(--brand-gradient)] text-white border border-transparent",
  bezeled: "glass text-foreground",
  gray: "bg-surface-strong text-foreground border border-transparent",
  outline: "bg-transparent text-foreground border border-border-soft",
  white: "bg-white/[0.92] text-[#160a2e] border border-transparent",
  plain: "bg-transparent text-foreground border border-transparent",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  s: "text-[13px] px-3 py-2 gap-1.5",
  m: "text-[14px] px-4 py-2.5 gap-2",
  l: "text-[16px] px-5 py-3.5 gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { mode = "filled", size = "m", stretched, loading, glow = "violet", disabled, className, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "press-scale inline-flex items-center justify-center rounded-full font-semibold disabled:opacity-40",
        MODE_CLASSES[mode],
        mode === "filled" && (glow === "cyan" ? "shadow-glow-cyan" : "shadow-glow"),
        SIZE_CLASSES[size],
        stretched && "w-full",
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner size="s" /> : children}
    </button>
  );
});
