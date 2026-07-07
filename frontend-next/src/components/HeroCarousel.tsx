"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import type { BannerOut } from "@/api/client";
import { openLink } from "@/lib/telegram";
import { cn } from "@/lib/cn";

interface Props {
  banners: BannerOut[];
}

export default function HeroCarousel({ banners }: Props) {
  const router = useRouter();
  const trackRef = useRef<HTMLDivElement>(null);
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
    <div className="pt-5 pb-1">
      <div
        ref={trackRef}
        onScroll={onScroll}
        className="flex snap-x snap-mandatory gap-2.5 overflow-x-auto px-7"
      >
        {banners.map((banner) => (
          <button
            key={banner.id}
            onClick={() => openBanner(banner)}
            className="press-scale relative h-[210px] flex-[0_0_84%] snap-center overflow-hidden rounded-lg border border-white/10 p-0 text-left text-white shadow-[0_12px_28px_rgba(0,0,0,0.35)] hover:shadow-[0_14px_32px_rgba(0,0,0,0.4)]"
          >
            <img
              src={banner.image_url}
              alt=""
              loading="lazy"
              className="absolute inset-0 h-full w-full object-cover"
            />
            <div className="absolute inset-0 bg-[image:linear-gradient(0deg,rgba(0,0,0,0.78)_0%,rgba(0,0,0,0.15)_55%,rgba(0,0,0,0.05)_100%)]" />
            <div className="relative flex h-full flex-col justify-end p-4">
              {banner.badge_text && (
                <span className="heading-font mb-2.5 self-start rounded-full bg-[image:var(--brand-gradient)] px-2.5 py-1 text-[11px] font-semibold">
                  {banner.badge_text}
                </span>
              )}
              <span className="heading-font line-clamp-2 text-[19px] font-bold leading-[1.2]">
                {banner.title}
              </span>
              {banner.subtitle && (
                <span className="mt-1 line-clamp-1 text-[13px] leading-[1.3] opacity-[0.85]">
                  {banner.subtitle}
                </span>
              )}
              <span className="mt-3 self-start rounded-full bg-white/[0.94] px-4 py-2 text-[13px] font-semibold text-[#111]">
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
                "h-1.5 rounded-full transition-all duration-200 ease-out",
                i === active ? "w-4 bg-brand-2" : "w-1.5 bg-white/25",
              )}
            />
          ))}
        </div>
      )}
    </div>
  );
}
