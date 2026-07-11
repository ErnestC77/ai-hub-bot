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
import { ApiError, ConfirmationRequiredError, api, type ModelOut } from "@/api/client";
import { haptic } from "@/lib/telegram";

const POLL_INTERVAL_MS = 2000;
const POLL_ATTEMPTS = Math.max(60, 20 * 15); // generous ceiling; video can take minutes

interface PendingConfirmation {
  prompt: string;
  modelCode: string;
  estimatedCredits: number;
}

export default function GenerateVideo() {
  const router = useRouter();
  const [models, setModels] = useState<ModelOut[] | null>(null);
  const [model, setModel] = useState<ModelOut | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);

  useEffect(() => {
    api
      .models("video")
      .then((list) => {
        setModels(list);
        setModel((prev) => prev ?? list[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);

  async function generate(confirm = false) {
    let question: string;
    let modelCode: string;

    if (confirm) {
      // Повторная отправка после баннера: берём сохранённые prompt/modelCode.
      if (!pendingConfirmation || generating) return;
      question = pendingConfirmation.prompt;
      modelCode = pendingConfirmation.modelCode;
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
      // duration_seconds в UI этой под-фазы не собирается (слайдера
      // длительности на экране нет и не было) -- бэкенд применит дефолт модели.
      const { request_id } = await api.generate(modelCode, question, undefined, undefined, confirm);

      for (let i = 0; i < POLL_ATTEMPTS; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const status = await api.generationStatus(request_id);
        if (status.status === "completed") {
          setResultUrl(status.result_url);
          haptic("medium");
          return;
        }
        if (status.status === "failed" || status.status === "refunded") {
          setError(status.error_message ?? "Не удалось сгенерировать видео");
          return;
        }
        // pending / reserved / processing -- продолжаем поллинг.
      }
      setError("Генерация занимает дольше обычного, попробуйте позже");
    } catch (err) {
      if (err instanceof ConfirmationRequiredError) {
        // Не ошибка: показываем баннер, повторный вызов уйдёт с confirm=true.
        setPendingConfirmation({ prompt: question, modelCode, estimatedCredits: err.estimatedCredits });
      } else {
        setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать видео");
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

        <Button stretched disabled={!model || !prompt.trim() || generating} onClick={() => generate()}>
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
