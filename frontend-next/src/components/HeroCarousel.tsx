"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import type { BannerOut } from "@/api/client";
import { openLink } from "@/lib/telegram";
import { useDragScroll } from "@/lib/useDragScroll";
import { cn } from "@/lib/cn";

interface Props {
  banners: BannerOut[];
}

export default function HeroCarousel({ banners }: Props) {
  const router = useRouter();
  const trackRef = useRef<HTMLDivElement>(null);
  const drag = useDragScroll(trackRef);
  const [active, setActive] = useState(0);

  if (banners.length === 0) return null;

  function openBanner(banner: BannerOut) {
    if (banner.action_type === "link") {
      openLink(banner.action_value);
    } else {
      router.push(`/chat?prefill=${encodeURIComponent(banner.action_value)}`);
    }
  }

  function onScroll() {
    const track = trackRef.current;
    if (!track) return;
    const cardWidth = track.scrollWidth / banners.length;
    setActive(Math.round(track.scrollLeft / cardWidth));
  }

  return (
    <div className="pb-1" data-testid="home-banners">
      <div
        ref={trackRef}
        onScroll={onScroll}
        {...drag}
        className="flex cursor-grab snap-x snap-mandatory gap-2.5 overflow-x-auto px-4 select-none active:cursor-grabbing"
      >
        {banners.map((banner) => (
          <button
            key={banner.id}
            onClick={() => openBanner(banner)}
            data-testid="banner-card"
            className="press-scale relative h-[200px] flex-[0_0_86%] snap-center overflow-hidden rounded-[24px] border border-white/[0.14] p-0 text-left text-foreground shadow-[0_20px_40px_-18px_rgba(139,92,255,0.6)]"
          >
            <img
              src={banner.image_url}
              alt=""
              loading="lazy"
              className="absolute inset-0 h-full w-full object-cover"
            />
            <div className="absolute inset-0 bg-[image:linear-gradient(0deg,rgba(5,3,12,0.85)_0%,rgba(5,3,12,0.2)_55%,rgba(5,3,12,0.05)_100%)]" />
            <div className="relative flex h-full flex-col justify-end p-4">
              {banner.badge_text && (
                <span className="heading-font mb-2.5 self-start rounded-full bg-[image:var(--brand-gradient)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-white">
                  {banner.badge_text}
                </span>
              )}
              <span className="heading-font line-clamp-2 text-[19px] font-bold leading-[1.15] text-white">
                {banner.title}
              </span>
              {banner.subtitle && (
                <span className="mt-1 line-clamp-1 text-[12.5px] leading-[1.3] text-foreground-muted">
                  {banner.subtitle}
                </span>
              )}
              <span className="mt-3.5 self-start rounded-full bg-white/[0.92] px-[15px] py-[9px] text-[12.5px] font-semibold text-[#160a2e]">
                {banner.cta_text}
              </span>
            </div>
          </button>
        ))}
      </div>

      {banners.length > 1 && (
        <div className="mt-3 flex justify-center gap-1.5">
          {banners.map((b, i) => (
            <span
              key={b.id}
              className={cn(
                "h-1.5 rounded-full transition-all duration-200",
                i === active ? "w-4 bg-[image:var(--brand-gradient)]" : "w-1.5 bg-white/25",
              )}
            />
          ))}
        </div>
      )}
    </div>
  );
}
