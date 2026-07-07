// Тонкая типизированная обёртка над Telegram WebApp JS SDK (грузится в index.html).
// Вне Telegram (обычный браузер при `npm run dev`) window.Telegram не определён —
// все хелперы деградируют, не роняя UI.

type InvoiceStatus = "paid" | "cancelled" | "failed" | "pending";

interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
  openLink(url: string, options?: { try_instant_view?: boolean }): void;
  openTelegramLink(url: string): void;
  openInvoice(url: string, callback: (status: InvoiceStatus) => void): void;
  onEvent(event: "themeChanged", cb: () => void): void;
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

export const tg: TelegramWebApp | undefined = window.Telegram?.WebApp;

// Telegram задаёт --tg-theme-* CSS-переменные под реальную тему клиента (может быть светлой).
// @telegram-apps/telegram-ui резолвит все свои --tgui--* цвета как var(--tg-theme-*, тёмный фолбэк),
// поэтому реальная светлая тема клиента перебивает AppRoot appearance="dark". Фиксируем свои
// значения поверх — это единственный способ гарантировать тёмный UI независимо от темы клиента.
const FORCED_DARK_THEME_VARS: Record<string, string> = {
  "--tg-theme-bg-color": "#17171b",
  "--tg-theme-secondary-bg-color": "#0e0e12",
  "--tg-theme-section-bg-color": "#17171b",
  "--tg-theme-header-bg-color": "#050506",
  "--tg-theme-text-color": "#f5f5f7",
  "--tg-theme-hint-color": "#96979f",
  "--tg-theme-subtitle-text-color": "#96979f",
  "--tg-theme-section-header-text-color": "#96979f",
  "--tg-theme-link-color": "#ff2d78",
  "--tg-theme-button-color": "#ff2d78",
  "--tg-theme-button-text-color": "#ffffff",
};

function forceDarkTheme(): void {
  const root = document.documentElement.style;
  for (const [name, value] of Object.entries(FORCED_DARK_THEME_VARS)) {
    root.setProperty(name, value);
  }
}

export function initTelegram(): void {
  forceDarkTheme();
  if (!tg) return;
  tg.ready();
  tg.expand();
  tg.onEvent("themeChanged", forceDarkTheme);
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
