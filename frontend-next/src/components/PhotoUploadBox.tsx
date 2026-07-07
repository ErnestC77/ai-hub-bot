"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const MAX_PHOTOS = 10;
const MAX_SIZE_BYTES = 30 * 1024 * 1024;

interface Props {
  photos: File[];
  onChange: (photos: File[]) => void;
}

export default function PhotoUploadBox({ photos, onChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");

  const previews = useMemo(() => photos.map((file) => URL.createObjectURL(file)), [photos]);
  useEffect(() => {
    return () => previews.forEach((url) => URL.revokeObjectURL(url));
  }, [previews]);

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const incoming = Array.from(files);
    const tooBig = incoming.some((f) => f.size > MAX_SIZE_BYTES);
    const merged = [...photos, ...incoming].slice(0, MAX_PHOTOS);
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
        multiple
        hidden
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />

      {photos.length === 0 ? (
        <button
          onClick={() => inputRef.current?.click()}
          className="press-scale flex w-full items-center gap-4 border-none bg-none p-0 text-left"
        >
          <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-2xl border-2 border-dashed border-border-soft">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-strong text-[22px] text-foreground-muted">
              +
            </div>
          </div>
          <div>
            <div className="heading-font text-[15px] font-semibold text-white">Add an image</div>
            <div className="mt-0.5 text-[13px] text-foreground-muted">
              Up to {MAX_PHOTOS} photos, max 30 MB each
            </div>
          </div>
        </button>
      ) : (
        <div className="flex gap-2.5 overflow-x-auto">
          {photos.map((file, i) => (
            <div key={`${file.name}-${i}`} className="relative shrink-0">
              <img src={previews[i]} alt="" className="block h-[72px] w-[72px] rounded-[14px] object-cover" />
              <button
                onClick={() => removeAt(i)}
                aria-label="Удалить фото"
                className="press-scale absolute -top-1.5 -right-1.5 flex h-[22px] w-[22px] items-center justify-center rounded-full border-none bg-black/85 text-[13px] text-white"
              >
                ×
              </button>
            </div>
          ))}
          {photos.length < MAX_PHOTOS && (
            <button
              onClick={() => inputRef.current?.click()}
              aria-label="Добавить ещё фото"
              className="press-scale flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-[14px] border-2 border-dashed border-border-soft bg-none text-xl text-foreground-muted"
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
