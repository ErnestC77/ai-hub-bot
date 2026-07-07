import { useEffect, useState } from "react";
import { Button, Placeholder, Spinner } from "@telegram-apps/telegram-ui";
import { useNavigate } from "react-router-dom";

import { api, type BannerOut } from "../api/client";
import HeroCarousel from "../components/HeroCarousel";
import ImageStack from "../components/ImageStack";
import { useMe } from "../context/MeContext";

const GENERATE_IMAGE_STACK = [
  "https://picsum.photos/seed/ai-hub-generate-1/300/400",
  "https://picsum.photos/seed/ai-hub-generate-2/300/400",
  "https://picsum.photos/seed/ai-hub-generate-3/300/400",
];

export default function Home() {
  const { me, loading } = useMe();
  const navigate = useNavigate();
  const [banners, setBanners] = useState<BannerOut[] | null>(null);

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
    navigate("/chat");
  }

  return (
    <div style={{ paddingBottom: 24 }}>
      <HeroCarousel banners={banners ?? []} />

      <div
        className="glass-card"
        style={{
          margin: "0 16px 20px",
          padding: 18,
          position: "relative",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <div style={{ flex: 1, minWidth: 0, paddingRight: 76 }}>
          <h3 className="heading-font" style={{ margin: "0 0 4px", fontSize: 17, fontWeight: 600 }}>
            Generate Image
          </h3>
          <p style={{ margin: "0 0 14px", fontSize: 13, color: "var(--foreground-muted)" }}>
            Опишите, что хотите создать
          </p>
          <button
            className="brand-button press-scale"
            onClick={generate}
            style={{
              padding: "10px 22px",
              borderRadius: 999,
              fontSize: 14,
              fontWeight: 600,
            }}
          >
            ✨ Generate
          </button>
        </div>

        <div style={{ position: "absolute", right: 14, top: -18 }}>
          <ImageStack images={GENERATE_IMAGE_STACK} />
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
