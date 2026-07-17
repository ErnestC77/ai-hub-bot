"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Placeholder } from "@/components/ui/placeholder";
import { Spinner } from "@/components/ui/spinner";
import { api, type BannerOut, type ModelOut } from "@/api/client";
import HeroCarousel from "@/components/HeroCarousel";
import ActionThumb from "@/components/ActionThumb";
import ImageStack from "@/components/ImageStack";
import ModelCard from "@/components/ModelCard";
import DragScroll from "@/components/DragScroll";
import { modelStyle, modelVariant } from "@/lib/modelStyles";
import { useMe } from "@/context/MeContext";
import CreditPurchaseSheet from "@/components/account/CreditPurchaseSheet";

type HomeCategory = "text" | "image" | "video";

type HomeModel = ModelOut & { category: HomeCategory };

const CATEGORIES: HomeCategory[] = ["text", "image", "video"];

const CATEGORY_LABEL: Record<HomeCategory, string> = {
  text: "Текст",
  image: "Фото",
  video: "Видео",
};

const CATEGORY_ROUTE: Record<HomeCategory, string> = {
  text: "/chat",
  image: "/generate-image",
  video: "/generate-video",
};

/* Tag pill tint per category (prototype 3a: text — white glass, photo — violet, video — cyan). */
const TAG_CLASSES: Record<HomeCategory, string> = {
  text: "bg-white/20 text-white",
  image: "bg-[rgba(139,92,255,0.7)] text-white",
  video: "bg-[rgba(53,224,230,0.75)] text-[#04252a]",
};

/** Unique brand/display names of loaded models in a category, for card subtitles. */
function categoryNames(models: HomeModel[], category: HomeCategory, limit = 3): string[] {
  const names = models
    .filter((m) => m.category === category)
    .map((m) => modelStyle(m.code).brand ?? m.display_name);
  return [...new Set(names)].slice(0, limit);
}

export default function Home() {
  const { me, loading } = useMe();
  const router = useRouter();
  const [banners, setBanners] = useState<BannerOut[] | null>(null);
  const [models, setModels] = useState<HomeModel[] | null>(null);
  const [buyingCredits, setBuyingCredits] = useState(false);

  useEffect(() => {
    api.banners().then(setBanners).catch(() => setBanners([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled(CATEGORIES.map((category) => api.models(category))).then((results) => {
      if (cancelled) return;
      setModels(
        results.flatMap((result, i) =>
          result.status === "fulfilled"
            ? result.value.map((m) => ({ ...m, category: CATEGORIES[i] }))
            : [],
        ),
      );
    });
    return () => {
      cancelled = true;
    };
  }, []);

  /* «от N 💎» on the photo card: N = min(min_credits) across image models.
     No image models / no positive prices — the fragment is not rendered. */
  const minImageCredits = useMemo(() => {
    const prices = (models ?? [])
      .filter((m) => m.category === "image")
      .map((m) => m.min_credits)
      .filter((v) => Number.isFinite(v) && v > 0);
    return prices.length > 0 ? Math.min(...prices) : null;
  }, [models]);

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

  const textNames = categoryNames(models ?? [], "text");
  const imageNames = categoryNames(models ?? [], "image", 2);
  const videoNames = categoryNames(models ?? [], "video");

  function openModel(model: HomeModel) {
    router.push(`${CATEGORY_ROUTE[model.category]}?model=${encodeURIComponent(model.code)}`);
  }

  return (
    <div className="fade-in pb-6">
      {/* Header: gradient logo + AI Hub, credits pill (real balance) */}
      <div className="flex items-center justify-between px-[18px] pb-3.5 pt-2.5">
        <div className="flex items-center gap-[9px]">
          <div className="h-[30px] w-[30px] rounded-[10px] bg-[image:var(--brand-gradient)] shadow-[0_6px_18px_rgba(139,92,255,0.5)]" />
          <div className="heading-font text-[17px]">AI Hub</div>
        </div>
        <div
          data-testid="home-credits"
          className="glass flex items-center gap-1.5 rounded-full px-[11px] py-1.5 text-[12px] font-semibold"
        >
          {me.credits_balance} 💎
        </div>
      </div>

      {/* Banners (admin-managed, kept by decision) */}
      <HeroCarousel banners={banners ?? []} />

      {/* «Нейросети» — horizontal model carousel from the API */}
      {(models === null || models.length > 0) && (
        <div className="pt-3.5">
          <div className="flex items-baseline justify-between px-[18px] pb-2.5">
            <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(238,240,255,0.78)]">
              Нейросети
            </div>
            <div className="text-[10.5px] text-foreground-dim">листай →</div>
          </div>
          {/* scroll-pl-4 обязателен рядом с px-4: snapport -- это padding box, поэтому
              snap-start первой карточки выравнивается по краю контейнера и прокручивает
              его на величину padding-left, съедая отступ. scroll-padding двигает границу
              snapport внутрь, и отступ остаётся видимым. */}
          <DragScroll
            data-testid="home-models"
            className="flex cursor-grab snap-x scroll-pl-4 gap-[11px] overflow-x-auto px-4 pb-1 select-none active:cursor-grabbing [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          >
            {models === null
              ? [0, 1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="glass h-[150px] w-[118px] flex-none animate-pulse rounded-[18px]"
                  />
                ))
              : models.map((model) => {
                  const { gradient, brand } = modelStyle(model.code);
                  const title = brand ?? model.display_name;
                  // Тег несёт вариант модели, а не повтор заголовка: «DeepSeek» + «V3 · Текст».
                  const variant = brand ? modelVariant(model.display_name, brand) : null;
                  const tag = variant
                    ? `${variant} · ${CATEGORY_LABEL[model.category]}`
                    : CATEGORY_LABEL[model.category];
                  return (
                    <ModelCard
                      key={model.code}
                      title={title}
                      tag={tag}
                      tagClass={TAG_CLASSES[model.category]}
                      gradient={gradient}
                      previewUrl={model.preview_url}
                      onClick={() => openModel(model)}
                    />
                  );
                })}
          </DragScroll>
        </div>
      )}

      {/* 3 action cards (replace the removed FAB) */}
      <div className="mt-3.5 flex flex-col gap-2.5 px-4">
        <button
          data-testid="action-chat"
          onClick={() => router.push("/chat")}
          className="press-scale glass flex w-full items-center gap-3 rounded-[22px] p-[15px] text-left"
        >
          <ActionThumb
            src="/actions/text.jpg"
            gradient="var(--brand-gradient)"
            className="h-12 w-11 flex-none rounded-[12px] shadow-[0_8px_20px_rgba(139,92,255,0.45)]"
          />
          <div className="min-w-0 flex-1">
            <div className="text-[14.5px] font-semibold">Спросить нейросеть</div>
            <div className="mt-0.5 text-[11.5px] text-foreground-muted">
              {textNames.length > 0 ? `${textNames.join(", ")} — ответят за секунды` : "Ответит за секунды"}
            </div>
          </div>
          <div className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-[11px] bg-white/[0.08] text-[16px] text-white">
            →
          </div>
        </button>

        <button
          data-testid="action-image"
          onClick={() => router.push("/generate-image")}
          className="press-scale glass flex w-full items-center gap-3 rounded-[22px] p-[15px] text-left"
        >
          <ImageStack images={["/actions/image.jpg"]} />
          <div className="min-w-0 flex-1">
            <div className="text-[14.5px] font-semibold">Сгенерировать фото</div>
            <div className="mt-0.5 text-[11.5px] text-foreground-muted">
              {imageNames.length > 0 ? imageNames.join(" и ") : "Опишите, что создать"}
              {minImageCredits !== null && (
                <span data-testid="image-price"> — от {minImageCredits} 💎</span>
              )}
            </div>
          </div>
          <div className="flex h-10 w-10 flex-none items-center justify-center rounded-[12px] bg-[image:var(--brand-gradient)] text-[17px] shadow-[0_8px_20px_rgba(139,92,255,0.5)]">
            ✨
          </div>
        </button>

        <button
          data-testid="action-video"
          onClick={() => router.push("/generate-video")}
          className="press-scale glass flex w-full items-center gap-3 rounded-[22px] p-[15px] text-left"
        >
          <ActionThumb
            src="/actions/video.mp4"
            kind="video"
            gradient="linear-gradient(160deg,#35e0e6,#3b2b8f)"
            className="h-12 w-14 flex-none rounded-[11px] border-2 border-[#140c26]"
          />
          <div className="min-w-0 flex-1">
            <div className="text-[14.5px] font-semibold">Сгенерировать видео</div>
            <div className="mt-0.5 text-[11.5px] text-foreground-muted">
              {videoNames.length > 0 ? `${videoNames.join(", ")} — оживи фото` : "Оживи фото"}
            </div>
          </div>
          <div className="flex h-10 w-10 flex-none items-center justify-center rounded-[12px] bg-[image:var(--brand-gradient)] text-[17px] shadow-[0_8px_20px_rgba(139,92,255,0.5)]">
            🎬
          </div>
        </button>
      </div>

      {/* Glass pills: credit packages sheet, referral, (admin) */}
      <div className="flex gap-[9px] px-4 pt-3 text-[12px] font-medium">
        <button
          data-testid="home-tariffs"
          onClick={() => setBuyingCredits(true)}
          className="press-scale glass flex-1 rounded-[14px] py-2.5 text-center"
        >
          💳 Тарифы
        </button>
        <button
          data-testid="home-referral"
          onClick={() => router.push("/referral")}
          className="press-scale glass flex-1 rounded-[14px] py-2.5 text-center"
        >
          🎁 Пригласить
        </button>
        {me.is_admin && (
          <button
            data-testid="home-admin"
            onClick={() => router.push("/admin")}
            className="press-scale glass flex-1 rounded-[14px] py-2.5 text-center text-foreground-dim"
          >
            🛠 Админка
          </button>
        )}
      </div>

      {buyingCredits && <CreditPurchaseSheet onClose={() => setBuyingCredits(false)} />}
    </div>
  );
}
