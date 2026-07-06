import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { BannerOut } from "../api/client";
import { openLink } from "../lib/telegram";

interface Props {
  banners: BannerOut[];
}

export default function HeroCarousel({ banners }: Props) {
  const navigate = useNavigate();
  const trackRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);

  if (banners.length === 0) return null;

  function openBanner(banner: BannerOut) {
    if (banner.action_type === "link") {
      openLink(banner.action_value);
    } else {
      navigate("/chat", { state: { prefillPrompt: banner.action_value } });
    }
  }

  function onScroll() {
    const track = trackRef.current;
    if (!track) return;
    const cardWidth = track.scrollWidth / banners.length;
    setActive(Math.round(track.scrollLeft / cardWidth));
  }

  return (
    <div style={{ padding: "20px 0 4px" }}>
      <div
        ref={trackRef}
        onScroll={onScroll}
        style={{
          display: "flex",
          gap: 10,
          overflowX: "auto",
          scrollSnapType: "x mandatory",
          padding: "0 28px",
        }}
      >
        {banners.map((banner) => (
          <button
            key={banner.id}
            onClick={() => openBanner(banner)}
            className="trend-card press-scale"
            style={{
              flex: "0 0 84%",
              scrollSnapAlign: "center",
              position: "relative",
              height: 210,
              borderRadius: 20,
              border: "1px solid rgba(255,255,255,0.1)",
              padding: 0,
              overflow: "hidden",
              textAlign: "left",
              color: "#fff",
              boxShadow: "0 12px 28px rgba(0,0,0,0.35)",
            }}
          >
            <img
              src={banner.image_url}
              alt=""
              loading="lazy"
              style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
            />
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: "linear-gradient(0deg, rgba(0,0,0,0.78) 0%, rgba(0,0,0,0.15) 55%, rgba(0,0,0,0.05) 100%)",
              }}
            />
            <div
              style={{
                position: "relative",
                height: "100%",
                display: "flex",
                flexDirection: "column",
                justifyContent: "flex-end",
                padding: 16,
              }}
            >
              {banner.badge_text && (
                <span
                  className="heading-font"
                  style={{
                    alignSelf: "flex-start",
                    fontSize: 11,
                    fontWeight: 600,
                    padding: "4px 10px",
                    borderRadius: 999,
                    background: "var(--brand-gradient)",
                    marginBottom: 10,
                  }}
                >
                  {banner.badge_text}
                </span>
              )}
              <span
                className="heading-font"
                style={{
                  fontSize: 19,
                  fontWeight: 700,
                  lineHeight: 1.2,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {banner.title}
              </span>
              {banner.subtitle && (
                <span
                  style={{
                    fontSize: 13,
                    opacity: 0.85,
                    marginTop: 4,
                    lineHeight: 1.3,
                    display: "-webkit-box",
                    WebkitLineClamp: 1,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {banner.subtitle}
                </span>
              )}
              <span
                style={{
                  alignSelf: "flex-start",
                  marginTop: 12,
                  fontSize: 13,
                  fontWeight: 600,
                  padding: "8px 16px",
                  borderRadius: 999,
                  background: "rgba(255,255,255,0.94)",
                  color: "#111",
                }}
              >
                {banner.cta_text}
              </span>
            </div>
          </button>
        ))}
      </div>

      {banners.length > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 6, marginTop: 12 }}>
          {banners.map((b, i) => (
            <span
              key={b.id}
              style={{
                width: i === active ? 16 : 6,
                height: 6,
                borderRadius: 999,
                background: i === active ? "var(--brand-2)" : "rgba(255,255,255,0.25)",
                transition: "all 200ms var(--ease-out)",
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
