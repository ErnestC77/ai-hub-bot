"use client";

import { getTrendStyle } from "@/lib/trendStyles";

interface Props {
  slug: string;
  title: string;
  description?: string;
  width?: number | string;
  height?: number | string;
  onClick: () => void;
}

export default function TrendCard({ slug, title, description, width = 140, height = 180, onClick }: Props) {
  const style = getTrendStyle(slug);

  return (
    <button
      onClick={onClick}
      className="press-scale relative flex shrink-0 overflow-hidden rounded-lg border border-white/12 p-0 text-left text-white shadow-[0_10px_24px_rgba(0,0,0,0.3)] hover:shadow-[0_14px_32px_rgba(0,0,0,0.4)]"
      style={{ width, height, background: style.gradient }}
    >
      <div className="absolute inset-0 bg-[image:linear-gradient(180deg,rgba(0,0,0,0)_40%,rgba(0,0,0,0.55)_100%)]" />
      <div className="relative flex w-full flex-col items-start justify-end p-3.5">
        <span className="mb-2.5 flex h-9 w-9 items-center justify-center rounded-[12px] border border-white/25 bg-white/[0.18] text-xl">
          {style.emoji}
        </span>
        <span className="heading-font text-[15px] leading-[1.2] font-semibold">{title}</span>
        {description && (
          <span className="mt-1 text-xs leading-[1.3] opacity-[0.85]">{description}</span>
        )}
      </div>
    </button>
  );
}
