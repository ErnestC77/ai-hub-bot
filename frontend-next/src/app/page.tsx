"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Placeholder } from "@/components/ui/placeholder";
import { Spinner } from "@/components/ui/spinner";
import { api, type BannerOut } from "@/api/client";
import HeroCarousel from "@/components/HeroCarousel";
import ImageStack from "@/components/ImageStack";
import { useMe } from "@/context/MeContext";

const GENERATE_IMAGE_STACK = [
  "https://picsum.photos/seed/ai-hub-generate-1/300/400",
  "https://picsum.photos/seed/ai-hub-generate-2/300/400",
  "https://picsum.photos/seed/ai-hub-generate-3/300/400",
];

export default function Home() {
  const { me, loading } = useMe();
  const router = useRouter();
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
    router.push("/generate-image");
  }

  return (
    <div className="pb-6">
      <HeroCarousel banners={banners ?? []} />

      <div className="relative mx-4 mb-5 flex items-center gap-3 rounded-lg border border-border-soft bg-surface p-[18px] backdrop-blur-xl">
        <div className="min-w-0 flex-1 pr-[76px]">
          <h3 className="heading-font mb-1 text-[17px] font-semibold text-white">Generate Image</h3>
          <p className="mb-3.5 text-[13px] text-foreground-muted">Опишите, что хотите создать</p>
          <Button onClick={generate}>✨ Generate</Button>
        </div>

        <div className="absolute right-3.5 -top-[18px]">
          <ImageStack images={GENERATE_IMAGE_STACK} />
        </div>
      </div>

      <div className="flex flex-wrap gap-2.5 px-4">
        <Button size="s" mode="bezeled" onClick={() => router.push("/tariffs")}>
          💳 Тарифы
        </Button>
        <Button size="s" mode="bezeled" onClick={() => router.push("/referral")}>
          🎁 Пригласить друга
        </Button>
        {me.is_admin && (
          <Button size="s" mode="outline" onClick={() => router.push("/admin")}>
            🛠 Админка
          </Button>
        )}
      </div>
    </div>
  );
}
