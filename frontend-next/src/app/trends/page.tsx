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
 * Design has photo/video carousels; the backend (`/api/tools`) today ships
 * only text presets. Sections are derived from `recommended_category`, so
 * photo/video rows appear automatically once such tools exist — empty
 * sections are not rendered (never invent data).
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
    router.push(`/chat?prefill=${encodeURIComponent(tool.prompt_prefix)}`);
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
