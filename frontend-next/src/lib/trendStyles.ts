export interface TrendStyle {
  gradient: string;
  emoji: string;
}

/**
 * Aurora Glass card backdrops. The backend (`/api/tools`) has no preview
 * images yet, so each trend gets a brand-adjacent gradient + emoji as a
 * tasteful placeholder (per design handoff: no image-slot in production).
 */
const DEFAULT_STYLE: TrendStyle = { gradient: "linear-gradient(150deg, #8b5cff, #35e0e6)", emoji: "✨" };

const STYLES_BY_SLUG: Record<string, TrendStyle> = {
  "write-post": { gradient: "linear-gradient(150deg, #ff8fb1, #8b5cff)", emoji: "📝" },
  "reply-client": { gradient: "linear-gradient(150deg, #4facfe, #6b3fd6)", emoji: "💬" },
  translate: { gradient: "linear-gradient(150deg, #5fd0c5, #2a6f8f)", emoji: "🌐" },
  "write-code": { gradient: "linear-gradient(150deg, #7a5cff, #20123f)", emoji: "💻" },
  "product-description": { gradient: "linear-gradient(150deg, #c9a06a, #5c4326)", emoji: "🛍️" },
  brainstorm: { gradient: "linear-gradient(150deg, #a86bff, #35205f)", emoji: "💡" },
  // Фото-тренды
  "ai-avatar": { gradient: "linear-gradient(150deg, #ff9a6b, #7a2fd6)", emoji: "🧑‍🎨" },
  "restyle-photo": { gradient: "linear-gradient(150deg, #35e0e6, #6b3fd6)", emoji: "🖼️" },
  "product-photo": { gradient: "linear-gradient(150deg, #ffd36b, #b5622a)", emoji: "📸" },
  // Видео-тренды
  "animate-photo": { gradient: "linear-gradient(150deg, #8b5cff, #1c1040)", emoji: "🎞️" },
  "talking-avatar": { gradient: "linear-gradient(150deg, #4facfe, #2a1f6f)", emoji: "🗣️" },
  "short-clip": { gradient: "linear-gradient(150deg, #ff6fae, #5c1f8f)", emoji: "🎬" },
};

export function getTrendStyle(slug: string): TrendStyle {
  return STYLES_BY_SLUG[slug] ?? DEFAULT_STYLE;
}
