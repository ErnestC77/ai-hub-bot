"use client";

import { useState } from "react";

/**
 * Превью-плитка для карточек действий на главной. Медиа кладём поверх
 * градиента: если файл не отдался (404/битый), onError прячет его и остаётся
 * исходный градиент карточки -- тот же приём, что в ModelCard/TrendCard.
 */
interface Props {
  src: string;
  kind?: "image" | "video";
  /** Размеры/скругление/рамка бокса задаёт вызывающая карточка. */
  className: string;
  /** CSS-градиент под медиа и фолбэк при ошибке загрузки. */
  gradient: string;
  /** Постер-кадр для видео: виден мгновенно, пока тело видео догружается. */
  poster?: string;
}

export default function ActionThumb({ src, kind = "image", className, gradient, poster }: Props) {
  const [failed, setFailed] = useState(false);

  return (
    <div className={`overflow-hidden ${className}`} style={{ backgroundImage: gradient }} aria-hidden>
      {!failed &&
        (kind === "video" ? (
          <video
            src={src}
            poster={poster}
            autoPlay
            loop
            muted
            playsInline
            preload="metadata"
            onError={() => setFailed(true)}
            className="h-full w-full object-cover"
          />
        ) : (
          <img
            src={src}
            alt=""
            loading="lazy"
            onError={() => setFailed(true)}
            className="h-full w-full object-cover"
          />
        ))}
    </div>
  );
}
