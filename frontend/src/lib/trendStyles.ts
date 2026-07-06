// Визуальный стиль карточек-трендов (Trends/Home): без реальных фото —
// градиент + иконка на каждый пресет промпта, подобранные вручную по slug.
export interface TrendStyle {
  gradient: string;
  emoji: string;
}

const DEFAULT_STYLE: TrendStyle = { gradient: "linear-gradient(135deg, #667eea, #764ba2)", emoji: "✨" };

const STYLES_BY_SLUG: Record<string, TrendStyle> = {
  "write-post": { gradient: "linear-gradient(135deg, #ff9a56, #ff6a88)", emoji: "📝" },
  "reply-client": { gradient: "linear-gradient(135deg, #4facfe, #00f2fe)", emoji: "💬" },
  translate: { gradient: "linear-gradient(135deg, #43e97b, #38f9d7)", emoji: "🌐" },
  "write-code": { gradient: "linear-gradient(135deg, #30cfd0, #330867)", emoji: "💻" },
  "product-description": { gradient: "linear-gradient(135deg, #fa709a, #fee140)", emoji: "🛍️" },
  brainstorm: { gradient: "linear-gradient(135deg, #a18cd1, #fbc2eb)", emoji: "💡" },
};

export function getTrendStyle(slug: string): TrendStyle {
  return STYLES_BY_SLUG[slug] ?? DEFAULT_STYLE;
}
