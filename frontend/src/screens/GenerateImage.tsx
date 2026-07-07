import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { Cell, List, Modal, Section, Spinner, Textarea } from "@telegram-apps/telegram-ui";
import { useNavigate } from "react-router-dom";

import { ApiError, api, type ImageQuality, type ImageSize, type ModelOut } from "../api/client";
import { computeImageCreditCost } from "../lib/imageCost";
import { haptic } from "../lib/telegram";

const SIZE_LABELS: Record<ImageSize, string> = { square: "Квадрат", portrait: "Портрет", landscape: "Альбом" };
const SIZE_ORDER: ImageSize[] = ["square", "portrait", "landscape"];
const QUALITY_LABELS: Record<ImageQuality, string> = { standard: "Standard", hd: "HD" };
const QUALITY_ORDER: ImageQuality[] = ["standard", "hd"];

function chipStyle(active: boolean): CSSProperties {
  return {
    flex: 1,
    padding: "10px 12px",
    borderRadius: 999,
    border: "1px solid var(--border-soft)",
    background: active ? "var(--brand-gradient)" : "var(--surface)",
    color: "#fff",
    fontSize: 13,
    fontWeight: 600,
  };
}

export default function GenerateImage() {
  const navigate = useNavigate();
  const [models, setModels] = useState<ModelOut[] | null>(null);
  const [model, setModel] = useState<ModelOut | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [size, setSize] = useState<ImageSize>("square");
  const [quality, setQuality] = useState<ImageQuality>("standard");
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .models()
      .then((all) => {
        const images = all.filter((m) => m.category === "image");
        setModels(images);
        setModel((prev) => prev ?? images[0] ?? null);
      })
      .catch(() => setModels([]));
  }, []);

  const cost = model ? computeImageCreditCost(model.credit_cost, size, quality) : 0;

  function cycleSize() {
    haptic("light");
    setSize((prev) => SIZE_ORDER[(SIZE_ORDER.indexOf(prev) + 1) % SIZE_ORDER.length]);
  }

  function cycleQuality() {
    haptic("light");
    setQuality((prev) => QUALITY_ORDER[(QUALITY_ORDER.indexOf(prev) + 1) % QUALITY_ORDER.length]);
  }

  async function generate() {
    if (!model || !prompt.trim() || generating) return;
    setGenerating(true);
    setError("");
    setResultUrl(null);
    try {
      const result = await api.generateImage(model.model_code, prompt.trim(), size, quality);
      setResultUrl(result.image_url);
      haptic("medium");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать изображение");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div style={{ minHeight: "100dvh", display: "flex", flexDirection: "column", paddingBottom: 90 }}>
      <div style={{ display: "flex", alignItems: "center", padding: 16, gap: 12 }}>
        <button
          onClick={() => navigate(-1)}
          aria-label="Назад"
          className="press-scale"
          style={{ background: "none", border: "none", color: "#fff", fontSize: 22, padding: 0 }}
        >
          ←
        </button>
        <h2
          className="heading-font"
          style={{ margin: 0, flex: 1, textAlign: "center", fontSize: 18, fontWeight: 700, marginRight: 22 }}
        >
          Generate Image
        </h2>
      </div>

      <div style={{ padding: "0 16px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="glass-card" style={{ padding: 14, position: "relative" }}>
          <Textarea
            placeholder="Опишите, что хотите создать"
            rows={expanded ? 10 : 4}
            maxLength={6000}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            style={{ resize: "none" }}
          />
          <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 8, marginTop: 6 }}>
            <span style={{ fontSize: 12, color: "var(--foreground-muted)" }}>{prompt.length}/6000</span>
            <button
              onClick={() => setExpanded((v) => !v)}
              aria-label={expanded ? "Свернуть поле" : "Развернуть поле"}
              className="press-scale"
              style={{ background: "none", border: "none", color: "var(--foreground-muted)", fontSize: 16, padding: 0 }}
            >
              ⤢
            </button>
          </div>
        </div>

        {model && (
          <div
            className="glass-card press-scale"
            onClick={() => models && models.length > 1 && setPickerOpen(true)}
            style={{
              padding: 14,
              display: "flex",
              alignItems: "center",
              gap: 12,
              cursor: models && models.length > 1 ? "pointer" : "default",
            }}
          >
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: 12,
                background: "var(--brand-gradient)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 18,
                flexShrink: 0,
              }}
            >
              🎨
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 15 }}>{model.display_name}</div>
              <div style={{ fontSize: 12, color: "var(--foreground-muted)" }}>Генерация изображений</div>
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                fontSize: 13,
                color: "var(--foreground-muted)",
                flexShrink: 0,
              }}
            >
              от {computeImageCreditCost(model.credit_cost, "square", "standard")} 💎
              {models && models.length > 1 && <span style={{ marginLeft: 2 }}>›</span>}
            </div>
          </div>
        )}

        <div style={{ display: "flex", gap: 10 }}>
          <button className="press-scale" onClick={cycleQuality} style={chipStyle(quality === "hd")}>
            👑 {QUALITY_LABELS[quality]}
          </button>
          <button className="press-scale" onClick={cycleSize} style={chipStyle(false)}>
            ▦ {SIZE_LABELS[size]}
          </button>
        </div>

        {generating && (
          <div style={{ display: "flex", justifyContent: "center", padding: 24 }}>
            <Spinner size="m" />
          </div>
        )}

        {error && (
          <div style={{ color: "var(--tgui--destructive_text_color)", fontSize: 13, textAlign: "center" }}>
            {error}
          </div>
        )}

        {resultUrl && (
          <div className="glass-card" style={{ padding: 12 }}>
            <img src={resultUrl} alt="" style={{ width: "100%", borderRadius: 14, display: "block" }} />
          </div>
        )}
      </div>

      <div
        style={{
          position: "fixed",
          left: 0,
          right: 0,
          bottom: 0,
          padding: 16,
          background: "rgba(10,10,12,0.85)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
        }}
      >
        <button
          className="brand-button press-scale"
          disabled={!prompt.trim() || generating || !model}
          onClick={generate}
          style={{
            width: "100%",
            padding: "14px 0",
            borderRadius: 999,
            fontSize: 16,
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            opacity: prompt.trim() && model ? 1 : 0.4,
          }}
        >
          ✨ Generate {model && <span>· {cost} 💎</span>}
        </button>
      </div>

      <Modal open={pickerOpen} onOpenChange={setPickerOpen} header={<Modal.Header>Выберите модель</Modal.Header>}>
        <List>
          <Section>
            {(models ?? []).map((m) => (
              <Cell
                key={m.model_code}
                onClick={() => {
                  setModel(m);
                  setPickerOpen(false);
                }}
                after={`от ${m.credit_cost} 💎`}
              >
                {m.display_name}
              </Cell>
            ))}
          </Section>
        </List>
      </Modal>
    </div>
  );
}
