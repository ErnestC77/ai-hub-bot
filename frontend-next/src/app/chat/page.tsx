"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Placeholder } from "@/components/ui/placeholder";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, type ModelOut } from "@/api/client";
import { haptic } from "@/lib/telegram";
import ModelPicker from "@/components/chat/ModelPicker";

interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
}

function ChatScreen() {
  const searchParams = useSearchParams();
  const prefill = searchParams.get("prefill") ?? "";

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
    <div className="flex h-screen flex-col">
      <div className="p-3">
        <ModelPicker selectedModel={model} onSelect={setModel} />
      </div>

      <div className="flex-1 overflow-y-auto px-3">
        {messages.length === 0 && (
          <Placeholder header="Начните диалог" description="Выберите модель и напишите сообщение." />
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`my-2 max-w-[85%] rounded-xl px-3 py-2 whitespace-pre-wrap ${
              m.role === "user"
                ? "ml-auto bg-brand-2 text-white"
                : m.role === "error"
                  ? "bg-surface-strong text-red-400"
                  : "bg-surface-strong text-foreground"
            }`}
          >
            {m.text}
          </div>
        ))}
        {sending && <Spinner size="s" />}
      </div>

      <div className="flex gap-2 p-3">
        <Textarea
          className="flex-1"
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

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ChatScreen />
    </Suspense>
  );
}
