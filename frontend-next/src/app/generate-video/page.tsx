"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { SegmentedControl } from "@/components/ui/segmented-control";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ApiError, ConfirmationRequiredError, api, type ModelOut } from "@/api/client";
import PhotoUploadBox from "@/components/PhotoUploadBox";
import OptionPicker from "@/components/generate/OptionPicker";
import { defaultOptionCodes, estimatedCredits } from "@/lib/optionPricing";
import { haptic } from "@/lib/telegram";
import { resolveModel } from "@/lib/resolveModel";
import { useMe } from "@/context/MeContext";

const POLL_INTERVAL_MS = 2000;
const POLL_ATTEMPTS = Math.max(60, 20 * 15); // generous ceiling; video can take minutes

interface PendingConfirmation {
  prompt: string;
  modelCode: string;
  imageUrl: string | undefined;
  optionCodes: Record<string, string>;
  estimatedCredits: number;
}

function GenerateVideoScreen() {
  const router = useRouter();
  const { me, refresh } = useMe();
  // ?model= ставят карточки моделей на Home; резолв приоритетов -- в lib/resolveModel.
  // ?prefill= приходит от видео-трендов (/trends) -- стартовый текст промпта.
  const searchParams = useSearchParams();
  const preferredModelCode = searchParams.get("model");
  const [models, setModels] = useState<ModelOut[] | null>(null);
  const [model, setModel] = useState<ModelOut | null>(null);
  const [photos, setPhotos] = useState<File[]>([]);
  const [prompt, setPrompt] = useState(searchParams.get("prefill") ?? "");
  const [optionCodes, setOptionCodes] = useState<Record<string, string>>({});
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  // Отмена поллинга при размонтировании: видео поллится до 10 минут, иначе цикл
  // продолжал бы бить API и делать setState на закрытом экране.
  const pollCancelledRef = useRef(false);
  useEffect(() => () => { pollCancelledRef.current = true; }, []);
  const [error, setError] = useState("");
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  // Модель приходит асинхронно; отслеживаем последний код, для которого уже
  // выставлены дефолтные опции, чтобы пересчитать их при смене модели.
  const [optionCodesForModel, setOptionCodesForModel] = useState<string | undefined>(undefined);

  useEffect(() => {
    api
      .models("video")
      .then((list) => {
        setModels(list);
        setModel((prev) => prev ?? resolveModel(list, preferredModelCode, me?.default_model_code));
      })
      .catch(() => setModels([]));
  }, [preferredModelCode, me?.default_model_code]);

  // Дефолтные коды опций выставляем во время рендера, а не в эффекте --
  // это derived state (React docs: "Adjusting state when a prop changes"),
  // без него смена модели на кадр показывала бы опции старой модели.
  if (model?.code !== optionCodesForModel) {
    setOptionCodesForModel(model?.code);
    setOptionCodes(defaultOptionCodes(model));
  }

  // Единственный источник отображаемых цен -- выбранная модель с бэкенда
  // (ModelOut.recommended_credits) x произведение множителей выбранных
  // опций. Точную сумму списания даёт 409-гейт (ConfirmationRequiredError.
  // estimatedCredits). Формулу duration×quality из макета НЕ переносим --
  // она выдумана дизайнером.
  const cost = estimatedCredits(model, optionCodes);

  async function generate(confirm = false) {
    let question: string;
    let modelCode: string;
    let imageUrl: string | undefined;
    let codes: Record<string, string>;

    if (confirm) {
      // Повторная отправка после баннера -- тот же самый вызов с confirm=true:
      // фото уже загружено при первой попытке (url сохранён), коды опций
      // тоже берём сохранённые, чтобы подтверждалась ровно та же цена --
      // смена опций после появления баннера не должна утечь в подтверждённый вызов.
      if (!pendingConfirmation || generating) return;
      question = pendingConfirmation.prompt;
      modelCode = pendingConfirmation.modelCode;
      imageUrl = pendingConfirmation.imageUrl;
      codes = pendingConfirmation.optionCodes;
      setPendingConfirmation(null);
    } else {
      if (!model || !prompt.trim() || generating) return;
      question = prompt.trim();
      modelCode = model.code;
      codes = optionCodes;
      // Новый запуск отменяет неподтверждённый предыдущий.
      setPendingConfirmation(null);
    }

    setGenerating(true);
    setError("");
    setResultUrl(null);
    try {
      if (!confirm && photos.length > 0) {
        // «Оживить фото»: бэкенд принимает один image_url.
        imageUrl = (await api.uploadImage(photos[0])).url;
      }

      const { request_id } = await api.generate(modelCode, question, imageUrl, codes, confirm);
      pollCancelledRef.current = false;
      // Резерв уже списал кредиты -- перечитываем профиль, иначе баланс на
      // экранах живёт до перезапуска приложения.
      void refresh();

      for (let i = 0; i < POLL_ATTEMPTS; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        if (pollCancelledRef.current) return;  // экран закрыли -- не трогаем стейт
        let status;
        try {
          status = await api.generationStatus(request_id);
        } catch {
          // Сетевой блип: генерация идёт и кредиты УЖЕ списаны. Не падаем в
          // "failed" (иначе повторный "Создать" -> двойное списание) -- пробуем
          // следующий тик; устойчивый сбой дойдёт до нейтрального таймаута.
          continue;
        }
        if (status.status === "completed") {
          setResultUrl(status.result_url);
          void refresh(); // settle мог вернуть часть резерва
          haptic("medium");
          return;
        }
        if (status.status === "failed" || status.status === "refunded") {
          setError(status.error_message ?? "Не удалось сгенерировать видео");
          void refresh(); // рефанд вернул кредиты
          return;
        }
        // pending / reserved / processing -- продолжаем поллинг.
      }
      setError("Генерация занимает дольше обычного, попробуйте позже");
    } catch (err) {
      if (err instanceof ConfirmationRequiredError) {
        // Не ошибка: показываем баннер, повторный вызов уйдёт с confirm=true.
        setPendingConfirmation({
          prompt: question,
          modelCode,
          imageUrl,
          optionCodes: codes,
          estimatedCredits: err.estimatedCredits,
        });
      } else {
        setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать видео");
      }
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="flex min-h-[100dvh] flex-col">
      {/* Роут, одетый шторкой (spec §1.4): хват-полоска, шапка с ✕=router.back(),
          верхний радиус 26, sheetUp-вход. Циановая подложка -- видео-вариант
          из макета; полупрозрачная, аврора-фон body остаётся виден. */}
      <div className="sheet-up mt-3 flex flex-1 flex-col rounded-t-[26px] border-t border-white/[0.12] bg-[linear-gradient(180deg,rgba(11,42,58,0.7),rgba(10,7,22,0.28)_50%,rgba(10,7,22,0)_100%)] px-4 pt-2.5 pb-8">
        <div aria-hidden className="mx-auto mb-3.5 h-1 w-[38px] rounded-full bg-white/20" />

        <div className="mb-3.5 flex items-center gap-2.5">
          <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-[linear-gradient(135deg,#35e0e6,#1b8fa0)] text-[16px] shadow-glow-cyan">
            🎬
          </div>
          <div className="min-w-0 flex-1">
            <div className="heading-font truncate text-[15px] font-semibold">
              {model?.display_name ?? "Генерация видео"}
            </div>
            <div className="text-[11px] text-foreground-dim">Генерация видео</div>
          </div>
          <button
            onClick={() => router.back()}
            aria-label="Закрыть"
            className="press-scale flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-full border-none bg-white/[0.08] text-[13px] text-foreground"
          >
            ✕
          </button>
        </div>

        <div className="flex flex-col gap-3.5">
          <PhotoUploadBox
            photos={photos}
            onChange={setPhotos}
            maxPhotos={1}
            label="Добавить фото для оживления"
            hint="Одно фото, до 30 МБ"
          />

          <Textarea
            data-testid="generate-prompt"
            placeholder="Опишите видео, которое хотите создать"
            rows={4}
            maxLength={2000}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="resize-none"
          />

          <div>
            <div className="mb-2 flex items-baseline justify-between px-1">
              <span className="text-[10px] font-semibold tracking-[.08em] text-foreground-dim uppercase">Модель</span>
              {model && (
                <span data-testid="generate-price" className="glass rounded-full px-2.5 py-1 text-[10.5px] font-semibold">
                  от {model.min_credits} 💎
                </span>
              )}
            </div>
            {models === null ? (
              <div className="flex justify-center p-3">
                <Spinner size="s" />
              </div>
            ) : models.length > 0 ? (
              <div data-testid="generate-model">
                <SegmentedControl>
                  {models.map((m) => (
                    <SegmentedControl.Item key={m.code} selected={m.code === model?.code} onClick={() => setModel(m)}>
                      {m.display_name}
                    </SegmentedControl.Item>
                  ))}
                </SegmentedControl>
              </div>
            ) : null}
          </div>

          <OptionPicker
            model={model}
            kind="quality"
            label="Качество"
            selected={optionCodes.quality}
            onSelect={(code) => setOptionCodes((p) => ({ ...p, quality: code }))}
          />
          <OptionPicker
            model={model}
            kind="aspect_ratio"
            label="Формат кадра"
            selected={optionCodes.aspect_ratio}
            onSelect={(code) => setOptionCodes((p) => ({ ...p, aspect_ratio: code }))}
          />
          <OptionPicker
            model={model}
            kind="duration"
            label="Длительность"
            selected={optionCodes.duration}
            onSelect={(code) => setOptionCodes((p) => ({ ...p, duration: code }))}
          />
          <OptionPicker
            model={model}
            kind="audio"
            label="Звук"
            selected={optionCodes.audio}
            onSelect={(code) => setOptionCodes((p) => ({ ...p, audio: code }))}
          />

          {pendingConfirmation && (
            <div data-testid="generate-confirm" className="glass relative overflow-hidden rounded-[16px] p-[14px]">
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

          <Button
            data-testid="generate-submit"
            size="l"
            stretched
            glow="cyan"
            loading={generating}
            disabled={!model || !prompt.trim() || generating}
            onClick={() => generate()}
          >
            🎬 Создать{model ? ` · ${cost} 💎` : ""}
          </Button>

          {error && (
            <div data-testid="generate-error" className="text-center text-[13px] text-red-400">
              {error}
            </div>
          )}

          {resultUrl && (
            <div data-testid="generate-result" className="glass rounded-[18px] p-3">
              <video controls src={resultUrl} className="block w-full rounded-[14px]" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// useSearchParams требует Suspense-границы при статическом пререндере
// (тот же приём, что в app/chat/page.tsx).
export default function Page() {
  return (
    <Suspense fallback={null}>
      <GenerateVideoScreen />
    </Suspense>
  );
}
