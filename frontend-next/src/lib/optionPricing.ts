import type { ModelOptionKind, ModelOut } from "@/api/client";

/** Коды дефолтных опций модели по всем видам сразу. */
export function defaultOptionCodes(model: ModelOut | null): Record<string, string> {
  if (!model) return {};
  const codes: Record<string, string> = {};
  for (const o of model.options ?? []) {
    if (o.is_default) codes[o.kind] = o.code;
  }
  return codes;
}

/** Опции одного вида, в порядке sort_order. Пусто -- у провайдера нет такой ручки. */
export function optionsOfKind(model: ModelOut | null, kind: ModelOptionKind) {
  if (!model) return [];
  return (model.options ?? [])
    .filter((o) => o.kind === kind)
    .slice()
    .sort((a, b) => a.sort_order - b.sort_order);
}

/**
 * Произведение множителей выбранных опций.
 * Оси независимы и перемножаются -- это подтверждено замерами провайдера:
 * у Veo 4с без звука = $0.80, а 8с со звуком = $3.20 = 0.80 x 2 x 2.
 */
export function optionsMultiplier(model: ModelOut | null, codes: Record<string, string>): number {
  if (!model) return 1;
  let multiplier = 1;
  for (const [kind, code] of Object.entries(codes)) {
    const option = (model.options ?? []).find((o) => o.kind === kind && o.code === code);
    if (option) multiplier *= option.credits_multiplier;
  }
  return multiplier;
}

/**
 * Ориентировочная цена для CTA. Точную сумму даёт 409-гейт бэкенда --
 * здесь только умножение, никаких формул: формула из дизайн-макета
 * (duration x 4 x qMult) выдумана и не совпадает ни с одной моделью.
 *
 * Порядок повторяет бэкенд (app/services/pricing.py: умножить -> ceil -> floor
 * по эффективному полу), а не Math.round без floor -- иначе дробные множители
 * (0.75, 1.988, 0.5) округлялись бы вниз, а дешёвые комбо проваливались бы
 * ниже пола, и CTA показывал бы МЕНЬШЕ, чем спишет бэкенд.
 *
 * Пол берём из min_charge_credits (бэкенд отдаёт его в ModelOut уже с учётом
 * VIDEO_MIN_CREDITS для видео) -- поэтому CTA совпадает со списанием и для
 * дешёвых видео-комбо. Раньше здесь был min_credits без этой константы, и
 * бэкенд списывал больше показанного (баг C1: показывали 466, списывали 500).
 */
export function estimatedCredits(model: ModelOut | null, codes: Record<string, string>): number {
  if (!model) return 0;
  const raw = Math.ceil(model.recommended_credits * optionsMultiplier(model, codes));
  return Math.max(raw, model.min_charge_credits);
}
