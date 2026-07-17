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
import SizeFormatPicker, { isSizeFormatCombo } from "@/components/generate/SizeFormatPicker";
import { defaultOptionCodes, estimatedCredits } from "@/lib/optionPricing";
import { useMe } from "@/context/MeContext";
import { pollGenerationResult } from "@/lib/pollGeneration";
import { clearPending, readPending, savePending } from "@/lib/pendingGeneration";
import { resolveModel } from "@/lib/resolveModel";
import { haptic } from "@/lib/telegram";

interface PendingConfirmation {
  prompt: string;
  modelCode: string;
  imageUrl: string | undefined;
  optionCodes: Record<string, string>;
  estimatedCredits: number;
}

function GenerateImageScreen() {
  const router = useRouter();
  const { me, refresh } = useMe();
  // ?model= ставят карточки моделей на Home; резолв приоритетов -- в lib/resolveModel.
  // ?prefill= приходит от фото-трендов (/trends) -- стартовый текст промпта.
  const searchParams = useSearchParams();
  const preferredModelCode = searchParams.get("model");
  const [models, setModels] = useState<ModelOut[] | null>(null);
  const [model, setModel] = useState<ModelOut | null>(null);
  const [photos, setPhotos] = useState<File[]>([]);
  const [prompt, setPrompt] = useState(searchParams.get("prefill") ?? "");
  const [optionCodes, setOptionCodes] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState(false);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  // Отмена поллинга при размонтировании (закрыли экран): иначе цикл бьёт API до
  // 10 минут и делает setState на размонтированном компоненте.
  const pollCancelledRef = useRef(false);
  useEffect(() => () => { pollCancelledRef.current = true; }, []);
  const [error, setError] = useState("");

  // Восстановление после переоткрытия приложения: если осталась незавершённая
  // генерация -- дослеживаем её результат прямо в приложении (immediate: он,
  // скорее всего, уже готов). Не мешает свежему запуску: как только юзер
  // жмёт «Создать», savePending переписывает запись и восстановление больше
  // не относится к старому request_id.
  useEffect(() => {
    const pending = readPending("image");
    if (!pending) return;
    const recoverRef = { current: false };
    setGenerating(true);
    setPrompt((prev) => prev || pending.prompt);
    (async () => {
      const outcome = await pollGenerationResult(pending.requestId, recoverRef, { immediate: true });
      if (recoverRef.current || outcome.kind === "cancelled") return;
      clearPending("image");
      setGenerating(false);
      if (outcome.kind === "completed") {
        setResultUrl(outcome.resultUrl);
        void refresh();
        haptic("medium");
      } else if (outcome.kind === "failed") {
        setError(outcome.message ?? "Не удалось сгенерировать изображение");
        void refresh();
      } else {
        setError("Генерация ещё идёт — результат придёт в чат с ботом.");
      }
    })();
    return () => {
      recoverRef.current = true;
    };
    // Один раз на маунт: восстанавливаем ровно то, что было при закрытии.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  // Модель приходит асинхронно; отслеживаем последний код, для которого уже
  // выставлены дефолтные опции, чтобы пересчитать их при смене модели.
  const [optionCodesForModel, setOptionCodesForModel] = useState<string | undefined>(undefined);

  useEffect(() => {
    api
      .models("image")
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

  // Модель поддерживает генерацию по фото (i2i), только если бэк прислал
  // edit_multiplier. Для остальных (qwen_image/seedream) фото-бокс не
  // показываем: их провайдер фото не использует, а прежде бэк ещё и брал за
  // него +50%.
  const supportsEdit = model?.edit_multiplier != null;
  const hasPhoto = photos.length > 0;

  // Цена -- recommended_credits x множители опций, а с прикреплённым фото ещё
  // x edit_multiplier (тем же порядком, что бэк: ceil после множителя).
  // Число edit_multiplier -- с бэка, не хардкод. Точную сумму даёт 409-гейт.
  // Остаточное расхождение: бэк добивает edit-цену полом IMAGE_EDIT_MIN_CREDITS
  // (100), а мы его не моделируем. Сегодня спит -- у всех edit-моделей
  // min_credits >= 100, так что base x1.5 всегда выше пола. Если заведут дешёвую
  // edit-модель (min_credits < 67), CTA недо-покажет на <=34 кредита; это ниже
  // порога подтверждения, 409 не сработает. Тогда пол надо будет вывести в API,
  // как и edit_multiplier. То же с VIDEO_MIN_CREDITS для видео.
  const baseCost = estimatedCredits(model, optionCodes);
  const cost =
    supportsEdit && hasPhoto
      ? Math.ceil(baseCost * (model!.edit_multiplier as number))
      : baseCost;

  async function generate(confirm = false) {
    let question: string;
    let modelCode: string;
    let imageUrl: string | undefined;
    let codes: Record<string, string>;

    if (confirm) {
      // Повторная отправка после баннера: фото уже загружено при первой
      // попытке (файл лежит на бэкенде), повторный upload не нужен --
      // переиспользуем сохранённый url; коды опций тоже берём сохранённые,
      // чтобы подтверждалась ровно та цена, которую показали.
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
      if (!confirm && supportsEdit && photos.length > 0) {
        // Фото шлём только edit-capable модели: у прочих провайдер его не берёт.
        // supportsEdit -- страховка на случай, если модель сменили после
        // прикрепления (фото-бокс скрыт, но photos ещё в стейте).
        // Бэкенд принимает один image_url -- берётся только ПЕРВОЕ фото.
        imageUrl = (await api.uploadImage(photos[0])).url;
      }

      const { request_id } = await api.generate(modelCode, question, imageUrl, codes, confirm);
      pollCancelledRef.current = false;
      // Запоминаем незавершённую генерацию: если юзер закроет приложение, при
      // возврате она восстановится (а бот-доставка сохранит результат в любом
      // случае). Резерв уже списал кредиты -- перечитываем профиль.
      savePending("image", request_id, question);
      void refresh();

      const outcome = await pollGenerationResult(request_id, pollCancelledRef);
      if (outcome.kind === "cancelled") return; // экран закрыли -- pending живёт
      clearPending("image");
      if (outcome.kind === "completed") {
        setResultUrl(outcome.resultUrl);
        void refresh(); // settle мог вернуть часть резерва
        haptic("medium");
        return;
      }
      if (outcome.kind === "failed") {
        setError(outcome.message ?? "Не удалось сгенерировать изображение");
        void refresh(); // рефанд вернул кредиты
        return;
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
        setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать изображение");
      }
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="flex min-h-[100dvh] flex-col">
      {/* Роут, одетый шторкой (spec §1.4): хват-полоска, шапка с ✕=router.back(),
          верхний радиус 26, sheetUp-вход. Подложка полупрозрачная -- аврора-фон
          body остаётся виден. */}
      <div className="sheet-up mt-3 flex flex-1 flex-col rounded-t-[26px] border-t border-white/[0.12] bg-[linear-gradient(180deg,rgba(27,17,64,0.7),rgba(10,7,22,0.28)_50%,rgba(10,7,22,0)_100%)] px-4 pt-2.5 pb-[112px]">
        <div aria-hidden className="mx-auto mb-3.5 h-1 w-[38px] rounded-full bg-white/20" />

        <div className="mb-3.5 flex items-center gap-2.5">
          <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-[image:var(--brand-gradient)] text-[16px] shadow-glow">
            🎨
          </div>
          <div className="min-w-0 flex-1">
            <div className="heading-font truncate text-[15px] font-semibold">
              {model?.display_name ?? "Генерация фото"}
            </div>
            <div className="text-[11px] text-foreground-dim">Генерация фото</div>
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
          {/* Фото-бокс -- только для моделей с i2i-маршрутом (edit_multiplier != null).
              Прочим фото не нужно: провайдер его не использует. */}
          {supportsEdit && <PhotoUploadBox photos={photos} onChange={setPhotos} />}

          <div className="flex flex-col gap-1.5">
            <Textarea
              data-testid="generate-prompt"
              placeholder="Опишите, что хотите создать"
              rows={expanded ? 10 : 4}
              maxLength={6000}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className="resize-none"
            />
            <div className="flex items-center justify-end gap-2 px-1">
              <span className="text-[11px] text-foreground-dim">{prompt.length}/6000</span>
              <button
                onClick={() => setExpanded((v) => !v)}
                aria-label={expanded ? "Свернуть поле" : "Развернуть поле"}
                className="press-scale border-none bg-none p-0 text-base text-foreground-muted"
              >
                ⤢
              </button>
            </div>
          </div>

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

          {/* qwen/seedream: размер и формат -- одно поле image_size у провайдера,
              в БД полная матрица комбо-кодов; SizeFormatPicker рисует её двумя
              рядами. Остальные модели -- обычные независимые оси. */}
          {isSizeFormatCombo(model) ? (
            <SizeFormatPicker
              model={model}
              selected={optionCodes.quality}
              onSelect={(code) => setOptionCodes((p) => ({ ...p, quality: code }))}
            />
          ) : (
            <OptionPicker
              model={model}
              kind="quality"
              label="Размер"
              selected={optionCodes.quality}
              onSelect={(code) => setOptionCodes((p) => ({ ...p, quality: code }))}
            />
          )}
          <OptionPicker
            model={model}
            kind="aspect_ratio"
            label="Формат кадра"
            selected={optionCodes.aspect_ratio}
            onSelect={(code) => setOptionCodes((p) => ({ ...p, aspect_ratio: code }))}
          />

          {generating && (
            <div className="flex justify-center p-6">
              <Spinner size="m" />
            </div>
          )}

          {error && (
            <div data-testid="generate-error" className="text-center text-[13px] text-red-400">
              {error}
            </div>
          )}

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

          {resultUrl && (
            <div data-testid="generate-result" className="glass rounded-[18px] p-3">
              <img src={resultUrl} alt="" className="block w-full rounded-[14px]" />
            </div>
          )}
        </div>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-[3] border-t border-white/[0.08] bg-[rgba(10,7,22,0.85)] p-4 backdrop-blur-xl">
        <div className="mb-2 text-center text-[11px] text-foreground-dim">Баланс: {me?.credits_balance ?? 0} 💎</div>
        <Button
          data-testid="generate-submit"
          mode="filled"
          size="l"
          stretched
          disabled={!prompt.trim() || generating || !model}
          onClick={() => generate()}
        >
          ✨ Создать{model ? ` · ${cost} 💎` : ""}
        </Button>
      </div>
    </div>
  );
}

// useSearchParams требует Suspense-границы при статическом пререндере
// (тот же приём, что в app/chat/page.tsx).
export default function Page() {
  return (
    <Suspense fallback={null}>
      <GenerateImageScreen />
    </Suspense>
  );
}
