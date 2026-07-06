import { useEffect, useState } from "react";
import { Placeholder, Spinner } from "@telegram-apps/telegram-ui";
import { useNavigate } from "react-router-dom";

import TrendCard from "../components/TrendCard";
import { api, type ToolOut } from "../api/client";

export default function Trends() {
  const [tools, setTools] = useState<ToolOut[] | null>(null);
  const navigate = useNavigate();

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
    navigate("/chat", { state: { prefillPrompt: tool.prompt_prefix } });
  }

  return (
    <div style={{ padding: 16 }}>
      <h2 className="heading-font" style={{ margin: "0 0 4px", fontSize: 22, fontWeight: 600 }}>
        ✨ Photo & Text Trends
      </h2>
      <p style={{ margin: "0 0 16px", color: "var(--foreground-muted)", fontSize: 14 }}>
        Готовые пресеты промптов — выберите и сразу начните диалог
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
          gap: 12,
        }}
      >
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
