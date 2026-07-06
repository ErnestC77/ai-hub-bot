import { getTrendStyle } from "../lib/trendStyles";

interface Props {
  slug: string;
  title: string;
  description?: string;
  width?: number | string;
  height?: number | string;
  onClick: () => void;
}

export default function TrendCard({ slug, title, description, width = 140, height = 180, onClick }: Props) {
  const style = getTrendStyle(slug);

  return (
    <button
      onClick={onClick}
      style={{
        width,
        height,
        flexShrink: 0,
        borderRadius: 16,
        border: "none",
        padding: 12,
        background: style.gradient,
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-end",
        alignItems: "flex-start",
        textAlign: "left",
        cursor: "pointer",
        color: "#fff",
        boxShadow: "0 4px 14px rgba(0,0,0,0.25)",
      }}
    >
      <span style={{ fontSize: 32, marginBottom: 8 }}>{style.emoji}</span>
      <span style={{ fontWeight: 700, fontSize: 15, lineHeight: 1.2 }}>{title}</span>
      {description && (
        <span style={{ fontSize: 12, opacity: 0.85, marginTop: 4, lineHeight: 1.3 }}>{description}</span>
      )}
    </button>
  );
}
