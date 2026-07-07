type InvoiceStatus = "paid" | "cancelled" | "failed" | "pending";

interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
  openLink(url: string, options?: { try_instant_view?: boolean }): void;
  openTelegramLink(url: string): void;
  openInvoice(url: string, callback: (status: InvoiceStatus) => void): void;
  BackButton: {
    show(): void;
    hide(): void;
    onClick(cb: () => void): void;
    offClick(cb: () => void): void;
  };
  HapticFeedback: {
    impactOccurred(style: "light" | "medium" | "heavy"): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
  }
}

export const tg: TelegramWebApp | undefined =
  typeof window !== "undefined" ? window.Telegram?.WebApp : undefined;

export function initTelegram(): void {
  if (!tg) return;
  tg.ready();
  tg.expand();
}

export function getInitData(): string {
  return tg?.initData ?? "";
}

export function openLink(url: string): void {
  if (tg) {
    tg.openLink(url, { try_instant_view: false });
  } else {
    window.open(url, "_blank");
  }
}

export function openTelegramLink(url: string): void {
  if (tg) {
    tg.openTelegramLink(url);
  } else {
    window.open(url, "_blank");
  }
}

export function openInvoice(url: string, onStatus: (status: InvoiceStatus) => void): void {
  if (tg) {
    tg.openInvoice(url, onStatus);
  } else {
    window.open(url, "_blank");
  }
}

export function haptic(style: "light" | "medium" | "heavy" = "light"): void {
  tg?.HapticFeedback.impactOccurred(style);
}
