export interface TrendStyle {
  gradient: string;
  emoji: string;
}

const DEFAULT_STYLE: TrendStyle = { gradient: "linear-gradient(160deg, #6a5cf6, #b721ff)", emoji: "✨" };

const STYLES_BY_SLUG: Record<string, TrendStyle> = {
  "write-post": { gradient: "linear-gradient(160deg, #ff9a56, #ff2d78)", emoji: "📝" },
  "reply-client": { gradient: "linear-gradient(160deg, #4facfe, #6a5cf6)", emoji: "💬" },
  translate: { gradient: "linear-gradient(160deg, #38f9d7, #2ecc71)", emoji: "🌐" },
  "write-code": { gradient: "linear-gradient(160deg, #30cfd0, #5433a7)", emoji: "💻" },
  "product-description": { gradient: "linear-gradient(160deg, #fa709a, #ffb347)", emoji: "🛍️" },
  brainstorm: { gradient: "linear-gradient(160deg, #a18cd1, #ff2d78)", emoji: "💡" },
};

export function getTrendStyle(slug: string): TrendStyle {
  return STYLES_BY_SLUG[slug] ?? DEFAULT_STYLE;
}
