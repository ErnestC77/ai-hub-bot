"use client";

import { useEffect, useRef, useState } from "react";

import { getTrendStyle } from "@/lib/trendStyles";

interface Props {
  slug: string;
  title: string;
  description?: string;
  /** Small pill top-right (recommended category / model). */
  badge?: string;
  /** 3-сек превью-луп; при ошибке загрузки остаётся градиент+эмодзи. */
  previewUrl?: string;
  onClick: () => void;
}

/**
 * Aurora Glass trend card: 132×172, radius 18, bottom scrim, badge top-right,
 * title + subtitle at the bottom. All overlays are pointer-events:none so the
 * tap always reaches the button itself.
 */
export default function TrendCard({ slug, title, description, badge, previewUrl, onClick }: Props) {
  const style = getTrendStyle(slug);
  const [videoFailed, setVideoFailed] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Играет только видимая в карусели карточка: 12 одновременных autoplay-лупов
  // тяжелы на мобильных. Невидимые -- на паузе (preload="metadata" оставляет
  // отрисованным первый кадр, так что карточка не пустая).
  useEffect(() => {
    const el = videoRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) el.play().catch(() => {});
        else el.pause();
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [previewUrl, videoFailed]);

  return (
    <button
      data-testid="trend-card"
      onClick={onClick}
      className="press-scale relative h-[172px] w-[132px] shrink-0 snap-start overflow-hidden rounded-[18px] border border-white/10 p-0 text-left text-white shadow-[0_10px_24px_rgba(0,0,0,0.3)]"
      style={{ background: style.gradient }}
    >
      {/* Плейсхолдер-эмодзи под видео: виден, пока видео не загрузилось или упало. */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-[42px] flex justify-center text-[30px] drop-shadow-[0_4px_14px_rgba(5,3,12,0.45)]"
      >
        {style.emoji}
      </span>

      {/* Превью-видео поверх градиента+эмодзи; play/pause -- по видимости (см.
          IntersectionObserver выше), поэтому autoPlay не ставим. muted нужен для
          политики автоплея. onError -> скрываем, плейсхолдер снизу остаётся. */}
      {previewUrl && !videoFailed && (
        <video
          ref={videoRef}
          data-testid="trend-video"
          src={previewUrl}
          poster={`/trends/posters/${slug}.webp`}
          loop
          muted
          playsInline
          preload="metadata"
          onError={() => setVideoFailed(true)}
          className="pointer-events-none absolute inset-0 h-full w-full object-cover"
        />
      )}

      {/* Bottom scrim */}
      <div className="pointer-events-none absolute inset-0 bg-[image:linear-gradient(to_top,rgba(5,3,12,0.88),rgba(5,3,12,0.05)_55%,transparent)]" />

      {badge && (
        <span className="pointer-events-none absolute top-[11px] right-[11px] rounded-full bg-black/45 px-[7px] py-[3px] text-[9px] leading-none font-semibold">
          {badge}
        </span>
      )}

      <div className="pointer-events-none absolute right-3 bottom-[11px] left-3">
        <div className="heading-font text-[12.5px] leading-[1.2] font-semibold">{title}</div>
        {description && (
          <div className="mt-0.5 text-[10px] leading-[1.3] text-white/80">{description}</div>
        )}
      </div>
    </button>
  );
}
