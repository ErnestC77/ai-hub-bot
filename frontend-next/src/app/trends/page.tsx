"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Placeholder } from "@/components/ui/placeholder";
import { Spinner } from "@/components/ui/spinner";
import TrendCard from "@/components/TrendCard";
import { api, type ToolOut } from "@/api/client";

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
    <div className="p-4">
      <h2 className="heading-font mb-1 text-[22px] font-semibold">✨ Photo & Text Trends</h2>
      <p className="mb-4 text-sm text-foreground-muted">
        Готовые пресеты промптов — выберите и сразу начните диалог
      </p>

      <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3">
        {tools.map((tool) => (
          <TrendCard
            key={tool.slug}
            slug={tool.slug}
            title={tool.title}
            description={tool.description}
            width="100%"
            height={170}
            onClick={() => openTool(tool)}
          />
        ))}
      </div>
    </div>
  );
}
