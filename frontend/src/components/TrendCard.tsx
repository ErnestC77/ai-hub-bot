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
      className="trend-card press-scale"
      style={{
        width,
        height,
        flexShrink: 0,
        borderRadius: 20,
        border: "1px solid rgba(255,255,255,0.12)",
        padding: 0,
        position: "relative",
        overflow: "hidden",
        background: style.gradient,
        display: "flex",
        textAlign: "left",
        color: "#fff",
        boxShadow: "0 10px 24px rgba(0,0,0,0.3)",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "linear-gradient(180deg, rgba(0,0,0,0) 40%, rgba(0,0,0,0.55) 100%)",
        }}
      />
      <div
        style={{
          position: "relative",
          width: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-end",
          alignItems: "flex-start",
          padding: 14,
        }}
      >
        <span
          style={{
            fontSize: 20,
            marginBottom: 10,
            width: 36,
            height: 36,
            borderRadius: 12,
            background: "rgba(255,255,255,0.18)",
            border: "1px solid rgba(255,255,255,0.25)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {style.emoji}
        </span>
        <span className="heading-font" style={{ fontWeight: 600, fontSize: 15, lineHeight: 1.2 }}>
          {title}
        </span>
        {description && (
          <span style={{ fontSize: 12, opacity: 0.85, marginTop: 4, lineHeight: 1.3 }}>{description}</span>
        )}
      </div>
    </button>
  );
}
