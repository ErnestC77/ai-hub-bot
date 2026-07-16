"use client";

import { useState } from "react";

interface Props {
  title: string;
  tag: string;
  tagClass: string;
  gradient: string;
  /** Превью-фото нейросети; при ошибке загрузки остаётся градиент. */
  previewUrl?: string;
  onClick: () => void;
}

/**
 * Карточка нейросети в карусели «Нейросети» на Home: 118×150, бренд-градиент
 * как фон/фолбэк, поверх -- превью-фото (public/models/<code>.jpg) под нижним
 * скримом ради читаемости заголовка. Все оверлеи pointer-events:none.
 */
export default function ModelCard({ title, tag, tagClass, gradient, previewUrl, onClick }: Props) {
  const [imgFailed, setImgFailed] = useState(false);

  return (
    <button
      data-testid="model-card"
      onClick={onClick}
      className="press-scale relative h-[150px] w-[118px] flex-none snap-start overflow-hidden rounded-[18px] p-0 text-left"
      style={{ background: gradient }}
    >
      {previewUrl && !imgFailed && (
        <img
          src={previewUrl}
          alt=""
          loading="lazy"
          onError={() => setImgFailed(true)}
          className="pointer-events-none absolute inset-0 h-full w-full object-cover"
        />
      )}
      {/* блик оставляем -- он мягко освещает и фото, и голый градиент */}
      <div className="pointer-events-none absolute inset-0 bg-[image:radial-gradient(80%_60%_at_30%_20%,rgba(255,255,255,0.18),transparent)]" />
      {/* нижний скрим: заголовок читается поверх любого фото */}
      <div className="pointer-events-none absolute inset-0 bg-[image:linear-gradient(to_top,rgba(5,3,12,0.85),transparent_55%)]" />
      <div className="absolute inset-x-[11px] bottom-[11px]">
        <div className="text-[13px] font-semibold text-white">{title}</div>
        <div className={`mt-[5px] inline-block rounded-full px-2 py-[3px] text-[9.5px] font-semibold ${tagClass}`}>
          {tag}
        </div>
      </div>
    </button>
  );
}
