"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Cell } from "@/components/ui/cell";
import { List } from "@/components/ui/list";
import { Section } from "@/components/ui/section";
import { Sheet } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ApiError, api, type ImageAspect, type ImageResolution, type ModelOut } from "@/api/client";
import AspectRatioSheet from "@/components/AspectRatioSheet";
import PhotoUploadBox from "@/components/PhotoUploadBox";
import { useMe } from "@/context/MeContext";
import { computeImageCreditCost } from "@/lib/imageCost";
import { haptic } from "@/lib/telegram";
import { cn } from "@/lib/cn";

const RESOLUTIONS: ImageResolution[] = ["1k", "2k", "4k"];
const RESOLUTION_LABELS: Record<ImageResolution, string> = { "1k": "1K", "2k": "2K", "4k": "4K" };

function chipClass(active: boolean): string {
  return cn(
    "press-scale flex-1 rounded-full border border-border-soft px-3 py-2.5 text-[13px] font-semibold text-white",
    active ? "bg-[image:var(--brand-gradient)]" : "bg-surface",
  );
}

export default function GenerateImage() {
  const router = useRouter();
  const { me } = useMe();
  const [models, setModels] = useState<ModelOut[] | null>(null);
  const [model, setModel] = useState<ModelOut | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [photos, setPhotos] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [aspect, setAspect] = useState<ImageAspect>("auto");
  const [aspectSheetOpen, setAspectSheetOpen] = useState(false);
  const [resolution, setResolution] = useState<ImageResolution>("1k");
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .models()
      .then((all) => {
        const images = all.filter((m) => m.category === "image");
        setModels(images);
        setModel((prev) => prev ?? images[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);

  const cost = model ? computeImageCreditCost(model.credit_cost, aspect, resolution) : 0;

  const POLL_INTERVAL_MS = 2000;
  const POLL_ATTEMPTS = 60;

  async function generate() {
    if (!model || !prompt.trim() || generating) return;
    setGenerating(true);
    setError("");
    setResultUrl(null);
    try {
      const isDalle3 = model.model_code === "dall-e-3";
      const { request_id } = await api.generate(
        model.model_code,
        prompt.trim(),
        isDalle3 ? { aspect, resolution } : undefined,
      );

      for (let i = 0; i < POLL_ATTEMPTS; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const status = await api.generationStatus(request_id);
        if (status.status === "success") {
          setResultUrl(status.result_url);
          haptic("medium");
          return;
        }
        if (status.status === "error") {
          setError(status.error_message ?? "Не удалось сгенерировать изображение");
          return;
        }
      }
      setError("Генерация занимает дольше обычного, попробуйте позже");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать изображение");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="flex min-h-[100dvh] flex-col pb-[90px]">
      <div className="flex items-center gap-3 p-4">
        <button
          onClick={() => router.back()}
          aria-label="Назад"
          className="press-scale border-none bg-none p-0 text-[22px] text-white"
        >
          ←
        </button>
        <h2 className="heading-font mr-[22px] flex-1 text-center text-lg font-bold">Generate Image</h2>
      </div>

      <div className="flex flex-col gap-3.5 px-4">
        <div className="rounded-lg border border-border-soft bg-surface p-3.5">
          <PhotoUploadBox photos={photos} onChange={setPhotos} />
        </div>

        <div className="relative rounded-lg border border-border-soft bg-surface p-3.5">
          <Textarea
            placeholder="Опишите, что хотите создать"
            rows={expanded ? 10 : 4}
            maxLength={6000}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="resize-none"
          />
          <div className="mt-1.5 flex items-center justify-end gap-2">
            <span className="text-xs text-foreground-muted">{prompt.length}/6000</span>
            <button
              onClick={() => setExpanded((v) => !v)}
              aria-label={expanded ? "Свернуть поле" : "Развернуть поле"}
              className="press-scale border-none bg-none p-0 text-base text-foreground-muted"
            >
              ⤢
            </button>
          </div>
        </div>

        {model && (
          <div
            onClick={() => models && models.length > 1 && setPickerOpen(true)}
            className={cn(
              "press-scale flex items-center gap-3 rounded-lg border border-border-soft bg-surface p-3.5",
              models && models.length > 1 ? "cursor-pointer" : "cursor-default",
            )}
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[image:var(--brand-gradient)] text-lg">
              🎨
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-semibold">{model.display_name}</div>
              <div className="text-xs text-foreground-muted">Генерация изображений</div>
            </div>
            <div className="flex shrink-0 items-center gap-1 text-[13px] text-foreground-muted">
              от {computeImageCreditCost(model.credit_cost, "auto", "1k")} 💎
              {models && models.length > 1 && <span className="ml-0.5">›</span>}
            </div>
          </div>
        )}

        <div className="flex gap-2.5">
          {RESOLUTIONS.map((r) => (
            <button key={r} className={chipClass(resolution === r)} onClick={() => setResolution(r)}>
              {RESOLUTION_LABELS[r]}
            </button>
          ))}
        </div>

        <button className={cn(chipClass(false), "w-full")} onClick={() => setAspectSheetOpen(true)}>
          ▦ {aspect === "auto" ? "Auto" : aspect}
        </button>

        {generating && (
          <div className="flex justify-center p-6">
            <Spinner size="m" />
          </div>
        )}

        {error && <div className="text-center text-[13px] text-red-400">{error}</div>}

        {resultUrl && (
          <div className="rounded-lg border border-border-soft bg-surface p-3">
            <img src={resultUrl} alt="" className="block w-full rounded-[14px]" />
          </div>
        )}
      </div>

      <div className="fixed inset-x-0 bottom-0 bg-[rgba(10,10,12,0.85)] p-4 backdrop-blur-xl">
        <div className="mb-2 text-center text-xs text-foreground-muted">Баланс: {me?.credits_balance ?? 0} 💎</div>
        <Button
          mode="filled"
          stretched
          disabled={!prompt.trim() || generating || !model}
          onClick={generate}
          className="py-3.5 text-base"
          style={{ opacity: prompt.trim() && model ? 1 : 0.4 }}
        >
          ✨ Generate {model && <span>· {cost} 💎</span>}
        </Button>
      </div>

      <Sheet open={pickerOpen} onOpenChange={setPickerOpen} header={<Sheet.Header>Выберите модель</Sheet.Header>}>
        <List>
          <Section>
            {(models ?? []).map((m) => (
              <Cell
                key={m.model_code}
                onClick={() => {
                  setModel(m);
                  setPickerOpen(false);
                }}
                after={`от ${m.credit_cost} 💎`}
              >
                {m.display_name}
              </Cell>
            ))}
          </Section>
        </List>
      </Sheet>

      <AspectRatioSheet
        open={aspectSheetOpen}
        value={aspect}
        onOpenChange={setAspectSheetOpen}
        onSelect={setAspect}
      />
    </div>
  );
}
