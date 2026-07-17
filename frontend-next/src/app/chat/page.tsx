"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, ConfirmationRequiredError, api, type ModelOut } from "@/api/client";
import { useMe } from "@/context/MeContext";
import { haptic } from "@/lib/telegram";
import ChatMarkdown from "@/components/chat/ChatMarkdown";
import ModelPicker from "@/components/chat/ModelPicker";
import { clearChatHistory, readChatHistory, saveChatHistory } from "@/lib/chatHistory";

interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
  chargedCredits?: number;
  balanceAfter?: number;
  /** id ответа модели -- для дедупа при восстановлении из /api/chat/recent. */
  id?: string;
}

interface PendingConfirmation {
  prompt: string;
  modelCode: string;
  estimatedCredits: number;
}

function ChatScreen() {
  const router = useRouter();
  const { me, applyBalance } = useMe();
  const searchParams = useSearchParams();
  const prefill = searchParams.get("prefill") ?? "";
  // ?model= ставят карточки моделей на Home; резолв приоритетов -- в lib/resolveModel.
  const preferredModelCode = searchParams.get("model");

  const [model, setModel] = useState<ModelOut | null>(null);
  const [prompt, setPrompt] = useState(prefill);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);

  // Восстанавливаем историю при открытии + подтягиваем ответы, сохранённые
  // сервером (chat_recent): если юзер закрыл приложение во время генерации,
  // ответ дошёл до Redis, но не до клиента -- добираем его сюда, дедуп по id.
  // Гонки нет: ответ сохранён в момент генерации, независимо от HTTP-доставки.
  useEffect(() => {
    let cancelled = false;
    const saved = readChatHistory();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (saved.length > 0) setMessages(saved);

    api
      .chatRecent()
      .then((recent) => {
        if (cancelled || recent.length === 0) return;
        setMessages((prev) => {
          const seen = new Set(prev.map((m) => m.id).filter(Boolean));
          // recent приходит newest-first -> разворачиваем, чтобы дописать в конец
          // в хронологическом порядке; берём только неизвестные id.
          const missing = [...recent]
            .reverse()
            .filter((r) => !seen.has(r.id))
            .map((r): ChatMessage => ({ role: "assistant", text: r.answer, id: r.id }));
          return missing.length > 0 ? [...prev, ...missing] : prev;
        });
      })
      .catch(() => {
        /* восстановление -- не критичный путь; тихо */
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Сохраняем на каждое изменение (ошибки отфильтровываются в saveChatHistory).
  useEffect(() => {
    saveChatHistory(messages);
  }, [messages]);

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
          id: result.message_id,
        },
      ]);
      // Глобальный баланс (пилюля на Home, «Баланс» на генерациях) без этого
      // жил до перезапуска приложения: профиль грузится один раз на старте.
      applyBalance(result.balance_after);
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
    // Роут, одетый шторкой (spec §1.4): узкая полоска app-фона сверху + скруглённый
    // «лист» на всю высоту с sheetUp-анимацией. ✕ = router.back(), Telegram BackButton
    // остаётся рабочим (центральная привязка в shell).
    <div className="flex h-dvh flex-col pt-2">
      <div
        className="sheet-up flex min-h-0 flex-1 flex-col rounded-t-[26px] border-t border-white/[0.12] px-4 pb-4 pt-3.5"
        style={{ background: "linear-gradient(180deg, #150d2c, #0b0716)" }}
        data-testid="chat-sheet"
      >
        {/* Хват-полоска */}
        <div className="mx-auto mb-3.5 h-1 w-[38px] flex-none rounded-full bg-white/20" />

        {/* Шапка шторки: иконка + модель + цена + ✕ */}
        <div className="mb-3.5 flex flex-none items-center gap-2.5">
          <div className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-[10px] bg-[image:var(--brand-gradient)] text-[15px] shadow-glow">
            🧠
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[15px] font-semibold" data-testid="chat-model-name">
              {model ? model.display_name : "Чат"}
            </div>
            <div className="text-[11px] text-foreground-dim">
              {model ? `Чат · ${model.min_credits} 💎 за запрос` : "Чат с нейросетью"}
            </div>
          </div>
          {/* Живой остаток кредитов: applyBalance после каждого ответа
              обновляет его прямо во время диалога (та же пилюля, что на Home). */}
          {me && (
            <div
              className="glass flex-none rounded-full px-[10px] py-[5px] text-[11.5px] font-semibold"
              data-testid="chat-balance"
            >
              {me.credits_balance} 💎
            </div>
          )}
          {messages.length > 0 && (
            <button
              aria-label="Новый чат"
              data-testid="chat-new"
              onClick={() => {
                setMessages([]);
                clearChatHistory();
                setPendingConfirmation(null);
              }}
              className="press-scale flex h-[30px] w-[30px] flex-none items-center justify-center rounded-full bg-white/[0.08] text-[13px] text-foreground"
            >
              🗑
            </button>
          )}
          <button
            aria-label="Закрыть"
            data-testid="chat-close"
            onClick={() => router.back()}
            className="press-scale flex h-[30px] w-[30px] flex-none items-center justify-center rounded-full bg-white/[0.08] text-[13px] text-foreground"
          >
            ✕
          </button>
        </div>

        {/* Сегмент-переключатель моделей (реальные данные из api.models) */}
        <div className="mb-3 flex-none">
          <ModelPicker selectedModel={model} onSelect={setModel} preferredCode={preferredModelCode} />
        </div>

        {/* Лента сообщений */}
        <div className="-mx-1 flex min-h-0 flex-1 flex-col gap-[9px] overflow-y-auto px-1 pb-3">
          <div
            className="glass max-w-[84%] self-start rounded-[16px] rounded-bl-[5px] px-[13px] py-2.5 text-[12.5px] leading-[1.4]"
            data-testid="chat-bubble"
          >
            Привет! О чём поговорим?
          </div>
          {messages.map((m, i) => (
            <div
              key={i}
              className={`max-w-[84%] ${m.role === "user" ? "self-end" : "self-start"}`}
              data-testid="chat-bubble"
            >
              <div
                className={`px-[13px] py-2.5 text-[12.5px] leading-[1.4] ${
                  m.role === "user"
                    ? "whitespace-pre-wrap rounded-[16px] rounded-br-[5px] bg-[image:var(--brand-gradient)] text-white"
                    : m.role === "error"
                      ? "whitespace-pre-wrap glass rounded-[16px] rounded-bl-[5px] text-red-400"
                      : "glass rounded-[16px] rounded-bl-[5px] text-foreground"
                }`}
              >
                {/* Ответ модели -- markdown (заголовки, жирный, списки
                    рендерятся, а не торчат звёздочками); юзер и ошибки -- как есть. */}
                {m.role === "assistant" ? <ChatMarkdown text={m.text} /> : m.text}
              </div>
              {m.role === "assistant" && m.chargedCredits !== undefined && m.balanceAfter !== undefined && (
                <div className="mt-1 px-1 text-[10.5px] text-foreground-dim">
                  Списано: {m.chargedCredits} • Баланс: {m.balanceAfter}
                </div>
              )}
            </div>
          ))}
          {sending && (
            <div className="glass flex max-w-[84%] items-center self-start rounded-[16px] rounded-bl-[5px] px-[13px] py-2.5">
              <Spinner size="s" />
            </div>
          )}
        </div>

        {/* 409-гейт: подтверждение стоимости перед дорогим запросом */}
        {pendingConfirmation && (
          <div className="glass relative mb-2.5 flex-none overflow-hidden rounded-[16px] p-[14px]" data-testid="chat-confirm">
            <div className="absolute inset-x-0 top-0 h-[3px] bg-[image:var(--brand-gradient)]" />
            <div className="text-[13px]">
              Примерная стоимость: {pendingConfirmation.estimatedCredits} кредитов. Продолжить?
            </div>
            <div className="mt-2.5 flex gap-2">
              <Button size="s" stretched onClick={() => send(true)} data-testid="chat-confirm-send">
                Отправить
              </Button>
              <Button size="s" stretched mode="gray" onClick={() => setPendingConfirmation(null)} data-testid="chat-confirm-cancel">
                Отмена
              </Button>
            </div>
          </div>
        )}

        {/* Композер: поле ввода + круглая градиентная кнопка отправки */}
        <div className="flex flex-none items-end gap-[9px]">
          <div className="min-w-0 flex-1">
            <Textarea
              data-testid="chat-input"
              rows={3}
              placeholder="Сообщение…"
              className="max-h-[160px] min-h-[76px] resize-none"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </div>
          <Button
            aria-label="Отправить"
            data-testid="chat-send"
            className="h-[42px] w-[42px] flex-none p-0 text-[16px]"
            disabled={!model || !prompt.trim() || sending}
            onClick={() => send()}
          >
            ➤
          </Button>
        </div>
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
