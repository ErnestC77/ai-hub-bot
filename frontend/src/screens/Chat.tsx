import { useState } from "react";
import { Button, Placeholder, Spinner, Textarea } from "@telegram-apps/telegram-ui";
import { useLocation } from "react-router-dom";

import { ApiError, api, type ModelOut } from "../api/client";
import { haptic } from "../lib/telegram";
import ModelPicker from "./chat/ModelPicker";

interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
}

export default function Chat() {
  const location = useLocation();
  const prefill = (location.state as { prefillPrompt?: string } | null)?.prefillPrompt ?? "";

  const [model, setModel] = useState<ModelOut | null>(null);
  const [prompt, setPrompt] = useState(prefill);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);

  async function send() {
    if (!model || !prompt.trim() || sending) return;

    const question = prompt.trim();
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setPrompt("");
    setSending(true);

    try {
      const result = await api.chat(model.model_code, question);
      setMessages((prev) => [...prev, { role: "assistant", text: result.answer }]);
      haptic("light");
    } catch (err) {
      const text = err instanceof ApiError ? err.message : "Что-то пошло не так, попробуйте ещё раз.";
      setMessages((prev) => [...prev, { role: "error", text }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: 12 }}>
        <ModelPicker selectedModel={model} onSelect={setModel} />
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "0 12px" }}>
        {messages.length === 0 && (
          <Placeholder header="Начните диалог" description="Выберите модель и напишите сообщение." />
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              margin: "8px 0",
              padding: "8px 12px",
              borderRadius: 12,
              background: m.role === "user" ? "var(--tgui--link_color)" : "var(--tgui--secondary_bg_color)",
              color: m.role === "user" ? "#fff" : m.role === "error" ? "var(--tgui--destructive_text_color)" : "inherit",
              maxWidth: "85%",
              marginLeft: m.role === "user" ? "auto" : 0,
              whiteSpace: "pre-wrap",
            }}
          >
            {m.text}
          </div>
        ))}
        {sending && <Spinner size="s" />}
      </div>

      <div style={{ display: "flex", gap: 8, padding: 12 }}>
        <Textarea
          style={{ flex: 1 }}
          rows={1}
          placeholder="Сообщение..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <Button disabled={!model || !prompt.trim() || sending} onClick={send}>
          Отправить
        </Button>
      </div>
    </div>
  );
}
