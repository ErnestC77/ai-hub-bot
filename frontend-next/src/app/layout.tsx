import type { Metadata } from "next";
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
        <MeProvider>
          <Shell>{children}</Shell>
        </MeProvider>
      </body>
    </html>
  );
}
