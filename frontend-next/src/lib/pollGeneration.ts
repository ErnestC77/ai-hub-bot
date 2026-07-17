import { api } from "@/api/client";

export const POLL_INTERVAL_MS = 2000;
export const POLL_ATTEMPTS_IMAGE = 60; // 60 x 2с = 2 мин
export const POLL_ATTEMPTS_VIDEO = 300; // 300 x 2с = 10 мин: видео идёт дольше

export type GenerationOutcome =
  | { kind: "completed"; resultUrl: string | null }
  | { kind: "failed"; message: string | null }
  | { kind: "timeout" }
  | { kind: "cancelled" };

/**
 * Поллит статус генерации до терминального или таймаута. Общий и для сабмита
 * (генерация только стартовала -> ждём перед первой проверкой), и для
 * восстановления после переоткрытия приложения (результат, вероятно, уже
 * готов -> immediate=true проверяет сразу).
 *
 * cancelledRef.current=true (экран закрыли) -> {cancelled}: НЕ трогаем стейт и
 * НЕ чистим localStorage, чтобы восстановление подхватило запрос при возврате.
 * Сетевой блип на одном тике -> continue (генерация идёт, кредиты списаны;
 * падать в failed нельзя -- спровоцировали бы повторный сабмит).
 */
export async function pollGenerationResult(
  requestId: number,
  cancelledRef: { current: boolean },
  { immediate = false, attempts = POLL_ATTEMPTS_IMAGE }: { immediate?: boolean; attempts?: number } = {},
): Promise<GenerationOutcome> {
  for (let i = 0; i < attempts; i++) {
    if (!(immediate && i === 0)) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }
    if (cancelledRef.current) return { kind: "cancelled" };
    let status;
    try {
      status = await api.generationStatus(requestId);
    } catch {
      continue;
    }
    if (status.status === "completed") return { kind: "completed", resultUrl: status.result_url };
    if (status.status === "failed" || status.status === "refunded") {
      return { kind: "failed", message: status.error_message };
    }
  }
  return { kind: "timeout" };
}
