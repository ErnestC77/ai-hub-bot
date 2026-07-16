"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Placeholder } from "@/components/ui/placeholder";
import { Spinner } from "@/components/ui/spinner";
import TrendCard from "@/components/TrendCard";
import { api, type ToolOut } from "@/api/client";

interface Section {
  key: string;
  testId: string;
  label: string;
  badge: string;
  match: (tool: ToolOut) => boolean;
}

/**
 * Design has photo/video/text carousels. Sections are derived from a tool's
 * `recommended_category` ('image' / 'video' / anything else → text); empty
 * sections are not rendered (never invent data), so a row appears only while
 * the catalog actually ships tools of that category.
 */
const SECTIONS: Section[] = [
  {
    key: "photo",
    testId: "trends-photo",
    label: "🖼 Фото-тренды",
    badge: "Фото",
    match: (tool) => tool.recommended_category === "image",
  },
  {
    key: "video",
    testId: "trends-video",
    label: "🎬 Видео-тренды",
    badge: "Видео",
    match: (tool) => tool.recommended_category === "video",
  },
  {
    key: "text",
    testId: "trends-text",
    label: "💬 Текст-тренды",
    badge: "Текст",
    match: (tool) => tool.recommended_category !== "image" && tool.recommended_category !== "video",
  },
];

// Категория пресета определяет экран: фото/видео-тренды ведут на свои
// генераторы (prefill в prompt), остальные (текст) -- в чат.
const PATH_BY_CATEGORY: Record<string, string> = {
  image: "/generate-image",
  video: "/generate-video",
};

export default function Trends() {
  const [tools, setTools] = useState<ToolOut[] | null>(null);
  const router = useRouter();

  useEffect(() => {
    api.tools().then(setTools).catch(() => setTools([]));
  }, []);

  if (tools === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  function openTool(tool: ToolOut) {
    const path = PATH_BY_CATEGORY[tool.recommended_category] ?? "/chat";
    router.push(`${path}?prefill=${encodeURIComponent(tool.prompt_prefix)}`);
  }

  return (
    <div className="fade-in py-4" data-testid="trends-page">
      <div className="px-[18px]">
        <h2 className="heading-font text-[22px] font-semibold">✨ Тренды</h2>
        <p className="mt-1 text-xs text-foreground-muted">
          Что сейчас вирусится — тапни и повтори
        </p>
      </div>

      {SECTIONS.map((section) => {
        const sectionTools = tools.filter(section.match);
        if (sectionTools.length === 0) return null;

        return (
          <section key={section.key} data-testid={section.testId}>
            <div className="flex items-baseline justify-between px-[18px] pt-4 pb-2.5">
              <div className="text-xs font-semibold">{section.label}</div>
              <div className="text-[10.5px] text-foreground-dim">листай →</div>
            </div>
            {/* scroll-pl-4 обязателен рядом с px-4: snapport -- это padding box, поэтому
                snap-start первой карточки выравнивается по краю контейнера и прокручивает
                его на величину padding-left, съедая отступ (у HeroCarousel этого нет --
                там snap-center). */}
            <div className="flex snap-x scroll-pl-4 gap-[11px] overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {sectionTools.map((tool) => (
                <TrendCard
                  key={tool.slug}
                  slug={tool.slug}
                  title={tool.title}
                  description={tool.description}
                  badge={section.badge}
                  previewUrl={tool.preview_url}
                  onClick={() => openTool(tool)}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
