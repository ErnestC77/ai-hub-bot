import type { Metadata, Viewport } from "next";
import Script from "next/script";
import { Onest } from "next/font/google";
import "./globals.css";
import { MeProvider } from "@/context/MeContext";
import { Shell } from "@/components/shell";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";

// Дизайн-хэндофф требует Sora, но у Sora нет кириллического subset'а
// (`subsets?: Array<'latin' | 'latin-ext'>`), а интерфейс русскоязычный -- вся
// кириллица молча падала бы на системный шрифт. Onest -- геометрический гротеск
// того же характера с полной кириллицей. См. docs/superpowers/specs/
// 2026-07-15-aurora-glass-redesign-design.md §3.
const onest = Onest({
  subsets: ["latin", "cyrillic"],
  variable: "--font-onest",
});

export const metadata: Metadata = {
  title: "AI Hub",
};

// maximum-scale=1 обязателен: без него iOS-WebView зумит страницу при фокусе
// в поле ввода, и правый край (кнопка «Отправить», ✕) уезжает за экран.
// Для Mini App внутри Telegram запрет пользовательского зума -- норма, это
// приложение, а не веб-страница.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className={onest.variable}>
        {/* Must load and run before any component reads window.Telegram.WebApp.initData --
            beforeInteractive blocks hydration until this script has executed, matching the
            old app's blocking <script> tag in index.html's <head>. */}
        <Script src="https://telegram.org/js/telegram-web-app.js" strategy="beforeInteractive" />
        <ServiceWorkerRegister />
        <MeProvider>
          <Shell>{children}</Shell>
        </MeProvider>
      </body>
    </html>
  );
}
