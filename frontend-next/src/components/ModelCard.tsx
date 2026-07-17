"use client";

import { BRAND_LOGO_PATHS, BRAND_MONOGRAMS } from "@/lib/brandLogos";

interface Props {
  title: string;
  /**
   * Бренд из `modelStyle(code)`. По нему берём официальную марку; если марки
   * нет (или бренд не опознан) -- рисуем монограмму тем же знакоместом, чтобы
   * карусель оставалась единообразной.
   */
  brand: string | null;
  tag: string;
  tagClass: string;
  gradient: string;
  onClick: () => void;
}

/** Запасной знак для брендов без официальной марки. */
function monogram(brand: string | null, title: string): string {
  if (brand && BRAND_MONOGRAMS[brand]) return BRAND_MONOGRAMS[brand];
  return ((brand ?? title).trim()[0] ?? "?").toUpperCase();
}

/**
 * Карточка нейросети в карусели «Нейросети» на Home: 118×150, бренд-градиент
 * фоном, поверх -- официальная марка бренда в стеклянном знакоместе и название.
 * Марка одноцветная (белая) на фирменном градиенте: так карточки читаются как
 * один набор, а не как коллаж из чужих логотипов.
 */
export default function ModelCard({ title, brand, tag, tagClass, gradient, onClick }: Props) {
  const logoPath = brand ? BRAND_LOGO_PATHS[brand] : undefined;

  return (
    <button
      data-testid="model-card"
      onClick={onClick}
      className="press-scale relative h-[150px] w-[118px] flex-none snap-start overflow-hidden rounded-[18px] p-0"
      style={{ background: gradient }}
    >
      <div className="pointer-events-none absolute inset-0 bg-[image:radial-gradient(80%_60%_at_30%_20%,rgba(255,255,255,0.18),transparent)]" />
      <div className="relative flex h-full flex-col items-center justify-center gap-2.5 px-2.5">
        <div className="flex h-[46px] w-[46px] flex-none items-center justify-center rounded-[14px] bg-white/[0.16] ring-1 ring-white/25 ring-inset">
          {logoPath ? (
            <svg viewBox="0 0 24 24" aria-hidden className="h-[26px] w-[26px] fill-white">
              <path d={logoPath} />
            </svg>
          ) : (
            <span aria-hidden className="text-[15px] font-bold tracking-tight text-white">
              {monogram(brand, title)}
            </span>
          )}
        </div>
        <div className="w-full text-center">
          <div className="truncate text-[13px] font-semibold text-white">{title}</div>
          <div
            className={`mt-[5px] inline-block max-w-full truncate rounded-full px-2 py-[3px] text-[9.5px] font-semibold ${tagClass}`}
          >
            {tag}
          </div>
        </div>
      </div>
    </button>
  );
}
