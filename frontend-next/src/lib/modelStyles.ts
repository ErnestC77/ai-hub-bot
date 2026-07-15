/**
 * Бренд-градиенты карточек моделей на Home (spec §2).
 *
 * Коды моделей неизвестны на этапе сборки: список живёт в БД и правится
 * админкой (`AiModel.is_visible` / `sort_order`), поэтому матчим `ModelOut.code`
 * по бренд-паттернам, а не по точному списку.
 *
 * Дизайн-макет рисовал ChatGPT / Claude / Gemini / Flux / Midjourney / Kling /
 * Runway -- воображаемый ростер. Реально в `app/db/seed.py` живут DeepSeek,
 * Llama, Qwen, Mistral, Grok, GPT, Gemini, Claude (текст); Qwen Image, Seedream,
 * Flux Kontext, Nano Banana (фото); Ovi, Wan, Kling, Veo (видео). Паттерны ниже
 * покрывают ОБА набора: из макета -- чтобы дизайн сошёлся, если такие модели
 * заведут; реальные -- чтобы карусель не была одноцветной сегодня.
 */

export const FALLBACK_GRADIENT = "var(--brand-gradient)";

export interface ModelStyle {
  /** CSS background для карточки модели. */
  gradient: string;
  /** Имя бренда ("DeepSeek", "Claude", ...) или null, если бренд не опознан. */
  brand: string | null;
}

// Порядок важен: первый сработавший паттерн выигрывает.
const BRANDS: Array<{ match: RegExp; brand: string; gradient: string }> = [
  // --- реальный ростер (app/db/seed.py) ---
  { match: /deepseek/i, brand: "DeepSeek", gradient: "linear-gradient(135deg,#4d6bfe,#2b47c8)" },
  { match: /llama|meta/i, brand: "Llama", gradient: "linear-gradient(135deg,#0866ff,#0a46b0)" },
  { match: /qwen/i, brand: "Qwen", gradient: "linear-gradient(135deg,#615ced,#3a2fb0)" },
  { match: /mistral/i, brand: "Mistral", gradient: "linear-gradient(135deg,#ff7000,#ffb300)" },
  { match: /grok|xai/i, brand: "Grok", gradient: "linear-gradient(135deg,#5b6472,#1a202c)" },
  { match: /nano[-_]?banana/i, brand: "Nano Banana", gradient: "linear-gradient(135deg,#f5c518,#d08700)" },
  { match: /seedream|seedance/i, brand: "Seedream", gradient: "linear-gradient(135deg,#ff4d8d,#c21c6b)" },
  { match: /veo/i, brand: "Veo", gradient: "linear-gradient(135deg,#4285f4,#1a73e8)" },
  { match: /(^|[-_])ovi([-_]|$)/i, brand: "Ovi", gradient: "linear-gradient(135deg,#00c2a8,#00786a)" },
  { match: /(^|[-_])wan([-_]|$)/i, brand: "Wan", gradient: "linear-gradient(135deg,#ff9f3c,#d1590a)" },

  // --- ростер из дизайн-макета (spec §2) ---
  { match: /chatgpt|gpt|openai/i, brand: "ChatGPT", gradient: "linear-gradient(135deg,#10a37f,#0d7a5f)" },
  { match: /claude|anthropic/i, brand: "Claude", gradient: "linear-gradient(135deg,#d97757,#b85c3f)" },
  { match: /gemini/i, brand: "Gemini", gradient: "linear-gradient(135deg,#4285f4,#9b72f2)" },
  { match: /flux/i, brand: "Flux", gradient: "linear-gradient(135deg,#8b5cff,#5a34c9)" },
  { match: /midjourney|(^|[-_])mj([-_]|$)/i, brand: "Midjourney", gradient: "linear-gradient(135deg,#a86bff,#6b3fd6)" },
  { match: /kling/i, brand: "Kling", gradient: "linear-gradient(135deg,#35e0e6,#1b8fa0)" },
  { match: /runway/i, brand: "Runway", gradient: "linear-gradient(135deg,#22d3ee,#0e7f96)" },
];

/**
 * Стабильный оттенок из кода модели -- для брендов, которых мы не знаем в лицо.
 * Раньше всё неопознанное красилось одним `--brand-gradient`, и карусель из
 * незнакомых моделей выглядела одноцветной. Детерминированный hue делает
 * карточки различимыми и не меняется между рендерами и сборками.
 */
function hashHue(code: string): number {
  let hash = 0;
  for (let i = 0; i < code.length; i++) {
    hash = (hash * 31 + code.charCodeAt(i)) | 0;
  }
  return Math.abs(hash) % 360;
}

export function modelStyle(code: string): ModelStyle {
  for (const { match, brand, gradient } of BRANDS) {
    if (match.test(code)) return { gradient, brand };
  }
  const hue = hashHue(code);
  return {
    gradient: `linear-gradient(135deg,hsl(${hue} 70% 58%),hsl(${(hue + 28) % 360} 62% 38%))`,
    brand: null,
  };
}

export function modelGradient(code: string): string {
  return modelStyle(code).gradient;
}

/** Слова, которые в display_name дублируют категорию, а не называют вариант. */
const CATEGORY_NOUNS = /^(video|image|photo)$/i;

/**
 * Вариант модели -- то, что остаётся от display_name после имени бренда.
 * Карточка на Home показывает бренд заголовком, а вариант тегом (как в макете:
 * «ChatGPT» + «GPT-5 · Текст»). Без этого тег дублировал бы заголовок
 * («DeepSeek» + «DeepSeek V3 · Текст»).
 *
 *   ("DeepSeek V3", "DeepSeek")  -> "V3"
 *   ("Llama 3.1 8B", "Llama")    -> "3.1 8B"
 *   ("Kling Video", "Kling")     -> null  (осталось только слово-категория)
 *   ("Seedream", "Seedream")     -> null  (вариант не отличается от бренда)
 *   ("GPT Mini", "ChatGPT")      -> "GPT Mini"  (бренд не является префиксом -- отдаём как есть)
 *
 * @returns вариант, либо null -- тогда в теге остаётся только категория
 */
export function modelVariant(displayName: string, brand: string | null): string | null {
  if (!brand) return displayName || null;

  if (!displayName.toLowerCase().startsWith(brand.toLowerCase())) {
    // Бренд опознан по коду, но в человекочитаемом имени он звучит иначе
    // (code "gpt_mini" -> бренд "ChatGPT", display "GPT Mini"). Имя информативно, оставляем.
    return displayName || null;
  }

  const rest = displayName.slice(brand.length).trim();
  if (!rest || CATEGORY_NOUNS.test(rest)) return null;
  return rest;
}
