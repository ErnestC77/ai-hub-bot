import { useEffect, useState } from "react";
import { Button, Placeholder, Spinner, Textarea } from "@telegram-apps/telegram-ui";
import { useNavigate } from "react-router-dom";

import { api, type BannerOut } from "../api/client";
import HeroCarousel from "../components/HeroCarousel";
import { useMe } from "../context/MeContext";

export default function Home() {
  const { me, loading } = useMe();
  const navigate = useNavigate();
  const [banners, setBanners] = useState<BannerOut[] | null>(null);
  const [prompt, setPrompt] = useState("");

  useEffect(() => {
    api.banners().then(setBanners).catch(() => setBanners([]));
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
      <HeroCarousel banners={banners ?? []} />

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
