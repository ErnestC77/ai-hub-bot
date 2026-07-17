/**
 * Незавершённая генерация переживает закрытие Mini App: request_id и контекст
 * кладём в localStorage при старте, читаем при повторном открытии страницы и
 * дослеживаем результат. Бот-доставка (backend) -- главная гарантия, что
 * результат не потеряется; это восстановление возвращает картинку/видео прямо
 * в приложение, если юзер вернулся в него.
 *
 * Ключ -- на категорию: незавершённое фото не должно всплыть на видео-странице.
 * TTL страхует от вечного «хвоста» (запрос завис/потерян -> reconcile-джоб
 * вернёт кредиты, а UI не должен крутить поллинг бесконечно).
 */

export interface PendingGeneration {
  requestId: number;
  prompt: string;
  ts: number;
}

const TTL_MS = 10 * 60 * 1000; // 10 мин: дольше живой генерации не бывает

type Category = "image" | "video";

function key(category: Category): string {
  return `aihub.pending.${category}`;
}

export function savePending(category: Category, requestId: number, prompt: string): void {
  if (typeof window === "undefined") return;
  try {
    const value: PendingGeneration = { requestId, prompt, ts: Date.now() };
    window.localStorage.setItem(key(category), JSON.stringify(value));
  } catch {
    // приватный режим / переполнение -- восстановление просто не сработает,
    // бот-доставка всё равно сохранит результат.
  }
}

export function clearPending(category: Category): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key(category));
  } catch {
    /* см. savePending */
  }
}

/** Живой (не протухший) незавершённый запрос этой категории, либо null. */
export function readPending(category: Category): PendingGeneration | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key(category));
    if (!raw) return null;
    const value = JSON.parse(raw) as PendingGeneration;
    if (
      typeof value.requestId !== "number" ||
      typeof value.ts !== "number" ||
      Date.now() - value.ts > TTL_MS
    ) {
      clearPending(category);
      return null;
    }
    return value;
  } catch {
    clearPending(category);
    return null;
  }
}
