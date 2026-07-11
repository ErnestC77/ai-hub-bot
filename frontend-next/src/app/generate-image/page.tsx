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
import { ApiError, ConfirmationRequiredError, api, type ModelOut } from "@/api/client";
import PhotoUploadBox from "@/components/PhotoUploadBox";
import { useMe } from "@/context/MeContext";
import { haptic } from "@/lib/telegram";
import { cn } from "@/lib/cn";

const POLL_INTERVAL_MS = 2000;
const POLL_ATTEMPTS = 60;

interface PendingConfirmation {
  prompt: string;
  modelCode: string;
  imageUrl: string | undefined;
  estimatedCredits: number;
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
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);

  useEffect(() => {
    api
      .models("image")
      .then((list) => {
        setModels(list);
        setModel((prev) => prev ?? list[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);

  const cost = model?.recommended_credits ?? 0;

  async function generate(confirm = false) {
    let question: string;
    let modelCode: string;
    let imageUrl: string | undefined;

    if (confirm) {
      // Повторная отправка после баннера: фото уже загружено при первой
      // попытке (файл лежит на бэкенде), повторный upload не нужен --
      // переиспользуем сохранённый url.
      if (!pendingConfirmation || generating) return;
      question = pendingConfirmation.prompt;
      modelCode = pendingConfirmation.modelCode;
      imageUrl = pendingConfirmation.imageUrl;
      setPendingConfirmation(null);
    } else {
      if (!model || !prompt.trim() || generating) return;
      question = prompt.trim();
      modelCode = model.code;
      // Новый запуск отменяет неподтверждённый предыдущий.
      setPendingConfirmation(null);
    }

    setGenerating(true);
    setError("");
    setResultUrl(null);

    try {
      if (!confirm && photos.length > 0) {
        // Бэкенд принимает один image_url -- используется только ПЕРВОЕ фото
        // (известное упрощение спеки; PhotoUploadBox не трогаем).
        imageUrl = (await api.uploadImage(photos[0])).url;
      }

      const { request_id } = await api.generate(modelCode, question, imageUrl, undefined, confirm);

      for (let i = 0; i < POLL_ATTEMPTS; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const status = await api.generationStatus(request_id);
        if (status.status === "completed") {
          setResultUrl(status.result_url);
          haptic("medium");
          return;
        }
        if (status.status === "failed" || status.status === "refunded") {
          setError(status.error_message ?? "Не удалось сгенерировать изображение");
          return;
        }
        // pending / reserved / processing -- продолжаем поллинг.
      }
      setError("Генерация занимает дольше обычного, попробуйте позже");
    } catch (err) {
      if (err instanceof ConfirmationRequiredError) {
        // Не ошибка: показываем баннер, повторный вызов уйдёт с confirm=true.
        setPendingConfirmation({ prompt: question, modelCode, imageUrl, estimatedCredits: err.estimatedCredits });
      } else {
        setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать изображение");
      }
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
              от {model.min_credits} 💎
              {models && models.length > 1 && <span className="ml-0.5">›</span>}
            </div>
          </div>
        )}

        {generating && (
          <div className="flex justify-center p-6">
            <Spinner size="m" />
          </div>
        )}

        {error && <div className="text-center text-[13px] text-red-400">{error}</div>}

        {pendingConfirmation && (
          <div className="relative overflow-hidden rounded-lg border border-border-soft bg-surface p-[14px]">
            <div className="absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]" />
            <div className="text-[13px]">
              Примерная стоимость: {pendingConfirmation.estimatedCredits} кредитов. Продолжить?
            </div>
            <div className="mt-2.5 flex gap-2">
              <Button size="s" stretched onClick={() => generate(true)}>
                Отправить
              </Button>
              <Button size="s" stretched mode="gray" onClick={() => setPendingConfirmation(null)}>
                Отмена
              </Button>
            </div>
          </div>
        )}

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
          onClick={() => generate()}
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
                key={m.code}
                onClick={() => {
                  setModel(m);
                  setPickerOpen(false);
                }}
                after={`от ${m.min_credits} 💎`}
              >
                {m.display_name}
              </Cell>
            ))}
          </Section>
        </List>
      </Sheet>
    </div>
  );
}
