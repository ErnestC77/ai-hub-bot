import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import { MeProvider } from "@/context/MeContext";
import { Shell } from "@/components/shell";

export const metadata: Metadata = {
  title: "AI Hub",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>
        {/* Must load and run before any component reads window.Telegram.WebApp.initData --
            beforeInteractive blocks hydration until this script has executed, matching the
            old app's blocking <script> tag in index.html's <head>. */}
        <Script src="https://telegram.org/js/telegram-web-app.js" strategy="beforeInteractive" />
        <MeProvider>
          <Shell>{children}</Shell>
        </MeProvider>
      </body>
    </html>
  );
}
