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
          className="press-scale"
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            gap: 16,
            padding: 0,
            background: "none",
            border: "none",
            textAlign: "left",
            cursor: "pointer",
          }}
        >
          <div
            style={{
              width: 96,
              height: 96,
              flexShrink: 0,
              borderRadius: 16,
              border: "2px dashed var(--border-soft)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: "50%",
                background: "var(--surface-strong)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 22,
                color: "var(--foreground-muted)",
              }}
            >
              +
            </div>
          </div>
          <div>
            <div className="heading-font" style={{ fontWeight: 600, fontSize: 15, color: "#fff" }}>
              Add an image
            </div>
            <div style={{ fontSize: 13, color: "var(--foreground-muted)", marginTop: 2 }}>
              Up to {MAX_PHOTOS} photos, max 30 MB each
            </div>
          </div>
        </button>
      ) : (
        <div style={{ display: "flex", gap: 10, overflowX: "auto" }}>
          {photos.map((file, i) => (
            <div key={`${file.name}-${i}`} style={{ position: "relative", flexShrink: 0 }}>
              <img
                src={previews[i]}
                alt=""
                style={{ width: 72, height: 72, borderRadius: 14, objectFit: "cover", display: "block" }}
              />
              <button
                onClick={() => removeAt(i)}
                aria-label="Удалить фото"
                className="press-scale"
                style={{
                  position: "absolute",
                  top: -6,
                  right: -6,
                  width: 22,
                  height: 22,
                  borderRadius: "50%",
                  border: "none",
                  background: "rgba(0,0,0,0.85)",
                  color: "#fff",
                  fontSize: 13,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                ×
              </button>
            </div>
          ))}
          {photos.length < MAX_PHOTOS && (
            <button
              onClick={() => inputRef.current?.click()}
              aria-label="Добавить ещё фото"
              className="press-scale"
              style={{
                width: 72,
                height: 72,
                flexShrink: 0,
                borderRadius: 14,
                border: "2px dashed var(--border-soft)",
                background: "none",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 20,
                color: "var(--foreground-muted)",
              }}
            >
              +
            </button>
          )}
        </div>
      )}

      {error && <div style={{ color: "var(--tgui--destructive_text_color)", fontSize: 12, marginTop: 6 }}>{error}</div>}
    </div>
  );
}
