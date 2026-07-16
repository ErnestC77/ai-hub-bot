"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const MAX_SIZE_BYTES = 30 * 1024 * 1024;

interface Props {
  photos: File[];
  onChange: (photos: File[]) => void;
  /** Текст пустой зоны. Видео-экран передаёт «Добавить фото для оживления». */
  label?: string;
  /** Подпись под текстом пустой зоны. */
  hint?: string;
  /** Максимум фото (видео-экран использует 1 — бэкенд принимает один image_url). */
  maxPhotos?: number;
}

export default function PhotoUploadBox({
  photos,
  onChange,
  label = "Добавить фото",
  hint,
  maxPhotos = 10,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");

  const hintText = hint ?? `До ${maxPhotos} фото, до 30 МБ каждое`;

  const previews = useMemo(() => photos.map((file) => URL.createObjectURL(file)), [photos]);
  useEffect(() => {
    return () => previews.forEach((url) => URL.revokeObjectURL(url));
  }, [previews]);

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const incoming = Array.from(files);
    const tooBig = incoming.some((f) => f.size > MAX_SIZE_BYTES);
    const merged = [...photos, ...incoming].slice(0, maxPhotos);
    setError(tooBig ? "Файл больше 30 МБ пропущен" : "");
    onChange(merged.filter((f) => f.size <= MAX_SIZE_BYTES));
  }

  function removeAt(index: number) {
    onChange(photos.filter((_, i) => i !== index));
  }

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple={maxPhotos > 1}
        hidden
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />

      {photos.length === 0 ? (
        <button
          onClick={() => inputRef.current?.click()}
          data-testid="generate-photo-upload"
          className="press-scale flex w-full flex-col items-center justify-center gap-1.5 rounded-[16px] border border-dashed border-white/[0.18] bg-white/[0.04] px-4 py-5 text-center backdrop-blur-[20px]"
        >
          <span className="flex items-center gap-2 text-[13px] font-medium text-foreground-muted">
            <span className="text-[17px]">🖼</span>
            {label}
          </span>
          <span className="text-[10.5px] text-foreground-dim">{hintText}</span>
        </button>
      ) : (
        <div className="flex gap-2.5 overflow-x-auto" data-testid="generate-photo-list">
          {photos.map((file, i) => (
            <div key={`${file.name}-${i}`} className="relative shrink-0">
              <img
                src={previews[i]}
                alt=""
                className="block h-[72px] w-[72px] rounded-[14px] border border-border-soft object-cover"
              />
              <button
                onClick={() => removeAt(i)}
                aria-label="Удалить фото"
                className="press-scale absolute -top-1.5 -right-1.5 flex h-[22px] w-[22px] items-center justify-center rounded-full border border-white/[0.15] bg-black/85 text-[13px] text-white"
              >
                ×
              </button>
            </div>
          ))}
          {photos.length < maxPhotos && (
            <button
              onClick={() => inputRef.current?.click()}
              aria-label="Добавить ещё фото"
              className="press-scale flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-[14px] border border-dashed border-white/[0.18] bg-white/[0.04] text-xl text-foreground-muted"
            >
              +
            </button>
          )}
        </div>
      )}

      {error && <div className="mt-1.5 text-xs text-red-400">{error}</div>}
    </div>
  );
}
