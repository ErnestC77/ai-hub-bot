/**
 * История чата переживает закрытие приложения: сообщения кладём в localStorage,
 * при повторном открытии /chat восстанавливаем -- можно продолжить переписку.
 *
 * Храним последние MAX_MESSAGES, чтобы запись не росла бесконечно. Ошибки чата
 * (role="error") не сохраняем: восстанавливать «что-то пошло не так» смысла нет.
 */

export interface StoredMessage {
  role: "user" | "assistant" | "error";
  text: string;
  chargedCredits?: number;
  balanceAfter?: number;
}

const KEY = "aihub.chat.history";
const MAX_MESSAGES = 50;

export function saveChatHistory(messages: StoredMessage[]): void {
  if (typeof window === "undefined") return;
  try {
    const persistable = messages.filter((m) => m.role !== "error").slice(-MAX_MESSAGES);
    if (persistable.length === 0) {
      window.localStorage.removeItem(KEY);
      return;
    }
    window.localStorage.setItem(KEY, JSON.stringify(persistable));
  } catch {
    // приватный режим / переполнение -- история просто не сохранится
  }
}

export function readChatHistory(): StoredMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (m): m is StoredMessage =>
        m && typeof m.text === "string" && (m.role === "user" || m.role === "assistant"),
    );
  } catch {
    return [];
  }
}

export function clearChatHistory(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* см. saveChatHistory */
  }
}
