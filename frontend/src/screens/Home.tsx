import { useEffect, useState } from "react";
import { Button, Placeholder, Spinner, Textarea } from "@telegram-apps/telegram-ui";
import { useNavigate } from "react-router-dom";

import { api, type ToolOut } from "../api/client";
import TrendCard from "../components/TrendCard";
import { useMe } from "../context/MeContext";

export default function Home() {
  const { me, loading } = useMe();
  const navigate = useNavigate();
  const [tools, setTools] = useState<ToolOut[] | null>(null);
  const [prompt, setPrompt] = useState("");

  useEffect(() => {
    api.tools().then(setTools).catch(() => setTools([]));
  }, []);

  if (loading) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  if (!me) {
    return (
      <Placeholder header="Не удалось загрузить профиль" description="Откройте приложение из Telegram." />
    );
  }

  function generate() {
    navigate("/chat", { state: { prefillPrompt: prompt } });
  }

  return (
    <div style={{ paddingBottom: 24 }}>
      <div style={{ padding: "20px 16px 4px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h2 className="heading-font" style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>
            ✨ Trending now
          </h2>
          <span
            className="press-scale"
            style={{ fontSize: 13, color: "var(--foreground-muted)" }}
            onClick={() => navigate("/trends")}
          >
            View all →
          </span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, overflowX: "auto", padding: "8px 16px 16px" }}>
        {(tools ?? []).slice(0, 6).map((tool) => (
          <TrendCard
            key={tool.slug}
            slug={tool.slug}
            title={tool.title}
            width={130}
            height={160}
            onClick={() => navigate("/chat", { state: { prefillPrompt: tool.prompt_prefix } })}
          />
        ))}
      </div>

      <div
        className="glass-card"
        style={{
          margin: "0 16px 20px",
          padding: 18,
        }}
      >
        <h3 className="heading-font" style={{ margin: "0 0 4px", fontSize: 17, fontWeight: 600 }}>
          Generate Image
        </h3>
        <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--foreground-muted)" }}>Опишите, что хотите создать</p>
        <Textarea
          placeholder="Например: кот-космонавт в стиле аниме"
          rows={2}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <div style={{ marginTop: 10 }}>
          <button
            className="brand-button press-scale"
            disabled={!prompt.trim()}
            onClick={generate}
            style={{
              width: "100%",
              padding: "12px 0",
              borderRadius: 12,
              fontSize: 15,
              fontWeight: 600,
              opacity: prompt.trim() ? 1 : 0.4,
              cursor: prompt.trim() ? "pointer" : "not-allowed",
            }}
          >
            ✨ Generate
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 10, padding: "0 16px", flexWrap: "wrap" }}>
        <Button size="s" mode="bezeled" onClick={() => navigate("/tariffs")}>
          💳 Тарифы
        </Button>
        <Button size="s" mode="bezeled" onClick={() => navigate("/referral")}>
          🎁 Пригласить друга
        </Button>
        {me.is_admin && (
          <Button size="s" mode="outline" onClick={() => navigate("/admin")}>
            🛠 Админка
          </Button>
        )}
      </div>
    </div>
  );
}
