"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Placeholder } from "@/components/ui/placeholder";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, ConfirmationRequiredError, api, type ModelOut } from "@/api/client";
import { haptic } from "@/lib/telegram";
import ModelPicker from "@/components/chat/ModelPicker";

interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
  chargedCredits?: number;
  balanceAfter?: number;
}

interface PendingConfirmation {
  prompt: string;
  modelCode: string;
  estimatedCredits: number;
}

function ChatScreen() {
  const searchParams = useSearchParams();
  const prefill = searchParams.get("prefill") ?? "";

  const [model, setModel] = useState<ModelOut | null>(null);
  const [prompt, setPrompt] = useState(prefill);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);

  async function send(confirm = false) {
    let question: string;
    let modelCode: string;

    if (confirm) {
      // Повторная отправка после баннера: user-бабл уже в истории с первой
      // попытки, не дублируем; берём сохранённые prompt/modelCode.
      if (!pendingConfirmation || sending) return;
      question = pendingConfirmation.prompt;
      modelCode = pendingConfirmation.modelCode;
      setPendingConfirmation(null);
    } else {
      if (!model || !prompt.trim() || sending) return;
      question = prompt.trim();
      modelCode = model.code;
      setMessages((prev) => [...prev, { role: "user", text: question }]);
      setPrompt("");
      // Новый вопрос отменяет неподтверждённый предыдущий.
      setPendingConfirmation(null);
    }

    setSending(true);

    try {
      const result = await api.chat(modelCode, question, confirm);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: result.answer,
          chargedCredits: result.charged_credits,
          balanceAfter: result.balance_after,
        },
      ]);
      haptic("light");
    } catch (err) {
      if (err instanceof ConfirmationRequiredError) {
        // Не ошибка: вопрос реально уйдёт после подтверждения, user-бабл
        // остаётся в истории, error-бабл не добавляется.
        setPendingConfirmation({ prompt: question, modelCode, estimatedCredits: err.estimatedCredits });
      } else {
        const text = err instanceof ApiError ? err.message : "Что-то пошло не так, попробуйте ещё раз.";
        setMessages((prev) => [...prev, { role: "error", text }]);
      }
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
          <div key={i} className={`my-2 max-w-[85%] ${m.role === "user" ? "ml-auto" : ""}`}>
            <div
              className={`rounded-xl px-3 py-2 whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-brand-2 text-white"
                  : m.role === "error"
                    ? "bg-surface-strong text-red-400"
                    : "bg-surface-strong text-foreground"
              }`}
            >
              {m.text}
            </div>
            {m.role === "assistant" && m.chargedCredits !== undefined && m.balanceAfter !== undefined && (
              <div className="mt-1 px-1 text-xs text-foreground-muted">
                Списано: {m.chargedCredits} • Баланс: {m.balanceAfter}
              </div>
            )}
          </div>
        ))}
        {sending && <Spinner size="s" />}
      </div>

      {pendingConfirmation && (
        <div className="relative mx-3 mb-1 overflow-hidden rounded-lg border border-border-soft bg-surface p-[14px]">
          <div className="absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]" />
          <div className="text-[13px]">
            Примерная стоимость: {pendingConfirmation.estimatedCredits} кредитов. Продолжить?
          </div>
          <div className="mt-2.5 flex gap-2">
            <Button size="s" stretched onClick={() => send(true)}>
              Отправить
            </Button>
            <Button size="s" stretched mode="gray" onClick={() => setPendingConfirmation(null)}>
              Отмена
            </Button>
          </div>
        </div>
      )}

      <div className="flex gap-2 p-3">
        <Textarea
          className="flex-1"
          rows={1}
          placeholder="Сообщение..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <Button disabled={!model || !prompt.trim() || sending} onClick={() => send()}>
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
