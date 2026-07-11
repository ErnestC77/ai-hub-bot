"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Section } from "@/components/ui/section";
import { List } from "@/components/ui/list";
import { Cell } from "@/components/ui/cell";
import { Sheet } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ApiError, api, type ModelOut } from "@/api/client";
import { haptic } from "@/lib/telegram";

const POLL_INTERVAL_MS = 2000;

export default function GenerateVideo() {
  const router = useRouter();
  const [models, setModels] = useState<ModelOut[] | null>(null);
  const [model, setModel] = useState<ModelOut | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .models()
      .then((all) => {
        // /api/models (credit-system v2) отдаёт только text-модели, у ModelOut
        // больше нет category. Экран переписывается на новый generate-flow в
        // будущей под-фазе; до неё список пуст -- компилируемая заглушка, не логика.
        const videos = all.filter(() => false);
        setModels(videos);
        setModel((prev) => prev ?? videos[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);

  async function generate() {
    if (!model || !prompt.trim() || generating) return;
    setGenerating(true);
    setError("");
    setResultUrl(null);
    try {
      const { request_id } = await api.generate(model.code, prompt.trim());
      const pollAttempts = Math.max(60, 20 * 15); // generous ceiling; video can take minutes

      for (let i = 0; i < pollAttempts; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const status = await api.generationStatus(request_id);
        if (status.status === "success") {
          setResultUrl(status.result_url);
          haptic("medium");
          return;
        }
        if (status.status === "error") {
          setError(status.error_message ?? "Не удалось сгенерировать видео");
          return;
        }
      }
      setError("Генерация занимает дольше обычного, попробуйте позже");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать видео");
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
        <h2 className="heading-font mr-[22px] flex-1 text-center text-lg font-bold">Generate Video</h2>
      </div>

      <div className="flex flex-col gap-3.5 px-4">
        <div className="rounded-lg border border-border-soft bg-surface p-3.5">
          <Textarea
            placeholder="Опишите видео, которое хотите создать"
            rows={4}
            maxLength={2000}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </div>

        <Cell subtitle={model ? `${model.min_credits} кредитов` : undefined} onClick={() => setPickerOpen(true)}>
          {model ? model.display_name : "Выберите модель"}
        </Cell>

        <Button stretched disabled={!model || !prompt.trim() || generating} onClick={generate}>
          {generating ? <Spinner size="s" /> : "Создать видео"}
        </Button>

        {error && <div className="text-sm text-red-400">{error}</div>}

        {resultUrl && (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video controls src={resultUrl} className="w-full rounded-lg" />
        )}
      </div>

      {pickerOpen && (
        <Sheet open onOpenChange={(open) => !open && setPickerOpen(false)} header={<Sheet.Header>Модель</Sheet.Header>}>
          <List>
            <Section>
              {models === null && <Cell before={<Spinner size="s" />}>Загрузка…</Cell>}
              {models?.map((m) => (
                <Cell
                  key={m.code}
                  subtitle={`${m.min_credits} кредитов`}
                  onClick={() => {
                    setModel(m);
                    setPickerOpen(false);
                  }}
                >
                  {m.display_name}
                </Cell>
              ))}
            </Section>
          </List>
        </Sheet>
      )}
    </div>
  );
}
