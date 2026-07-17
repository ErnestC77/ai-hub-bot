"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/api/client";
import { clearPending, readPending, type PendingGeneration } from "@/lib/pendingGeneration";

type Category = "image" | "video";

interface Active extends PendingGeneration {
  category: Category;
  phase: "running" | "done" | "failed";
  resultUrl: string | null;
}

const CATEGORY_ROUTE: Record<Category, string> = {
  image: "/generate-image",
  video: "/generate-video",
};

const POLL_MS = 3000;

/**
 * Баннер «активная генерация» на Home. Если юзер начал генерацию и вышел, не
 * дождавшись, при возврате на главную видит карточку с быстрым возвратом к ней.
 *
 * Читаем незавершённые запросы (localStorage, per-category), берём самый свежий
 * и поллим его статус: пока идёт -- «идёт генерация», завершился -- «готово,
 * открыть». Провал/рефанд -- чистим и прячем. Перечитываем при возврате в
 * приложение (visibilitychange): результат мог прийти, пока Home был свёрнут.
 *
 * Бот-доставка -- отдельная гарантия, что результат не потеряется; этот баннер
 * возвращает генерацию в приложение.
 */
export default function ActiveGenerationBanner() {
  const router = useRouter();
  const [active, setActive] = useState<Active | null>(null);
  const pollRef = useRef<{ current: boolean }>({ current: false });

  const freshestPending = useCallback((): { category: Category; pending: PendingGeneration } | null => {
    const candidates: Array<{ category: Category; pending: PendingGeneration }> = [];
    for (const category of ["image", "video"] as Category[]) {
      const pending = readPending(category);
      if (pending) candidates.push({ category, pending });
    }
    if (candidates.length === 0) return null;
    candidates.sort((a, b) => b.pending.ts - a.pending.ts);
    return candidates[0];
  }, []);

  const scan = useCallback(() => {
    const found = freshestPending();
    if (!found) {
      setActive(null);
      return;
    }
    setActive((prev) =>
      prev && prev.requestId === found.pending.requestId
        ? prev // уже отслеживаем этот запрос -- не сбрасываем phase
        : { ...found.pending, category: found.category, phase: "running", resultUrl: null },
    );
  }, [freshestPending]);

  // Скан на маунт и при каждом возврате в приложение. Синхронный setState на
  // маунте намеренный (fetch-on-mount из localStorage), не каскад производного
  // стейта -- правило тут неприменимо.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    scan();
    const onVisible = () => {
      if (document.visibilityState === "visible") scan();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [scan]);

  // Поллим статус активного запроса, пока он не терминален.
  useEffect(() => {
    if (!active || active.phase !== "running") return;
    pollRef.current = { current: false };
    const ref = pollRef.current;
    (async () => {
      while (!ref.current) {
        await new Promise((r) => setTimeout(r, POLL_MS));
        if (ref.current) return;
        let status;
        try {
          status = await api.generationStatus(active.requestId);
        } catch {
          continue; // сетевой блип -- следующий тик
        }
        if (status.status === "completed") {
          setActive((p) => (p ? { ...p, phase: "done", resultUrl: status.result_url } : p));
          return;
        }
        if (status.status === "failed" || status.status === "refunded") {
          clearPending(active.category);
          setActive(null);
          return;
        }
      }
    })();
    return () => {
      ref.current = true;
    };
  }, [active]);

  if (!active) return null;

  const isVideo = active.category === "video";
  const done = active.phase === "done";

  return (
    <div className="px-4 pt-3">
      <button
        type="button"
        data-testid="active-generation"
        onClick={() => router.push(CATEGORY_ROUTE[active.category])}
        className="press-scale glass flex w-full items-center gap-3 rounded-[18px] p-3 text-left"
      >
        <div
          className={`flex h-10 w-10 flex-none items-center justify-center rounded-[12px] text-[18px] ${
            done
              ? "bg-[image:var(--brand-gradient)]"
              : "bg-white/[0.08]"
          }`}
        >
          {done ? "✅" : isVideo ? "🎬" : "🖼"}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[13.5px] font-semibold">
            {done
              ? `${isVideo ? "Видео" : "Фото"} готово`
              : `Идёт генерация ${isVideo ? "видео" : "фото"}`}
            {!done && (
              <span
                aria-hidden
                className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-1,#8b5cff)]"
              />
            )}
          </div>
          <div className="mt-0.5 truncate text-[11.5px] text-foreground-dim">{active.prompt}</div>
        </div>
        <div className="flex-none text-[12px] font-medium text-foreground-muted">
          {done ? "Открыть" : "Вернуться"} ›
        </div>
      </button>
    </div>
  );
}
