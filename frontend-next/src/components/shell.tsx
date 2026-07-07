"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { initTelegram, tg } from "@/lib/telegram";
import { cn } from "@/lib/cn";

const TABS = [
  { path: "/", text: "Home", icon: "🏠" },
  { path: "/trends", text: "Trends", icon: "✨" },
  { path: "/account", text: "My Account", icon: "👤" },
];

const FULLSCREEN_ROUTES = ["/chat", "/generate-image"];

function Fab() {
  const router = useRouter();
  return (
    <button
      onClick={() => router.push("/chat")}
      aria-label="Открыть чат с нейросетью"
      className="press-scale fixed bottom-20 right-4 z-[2] flex h-[58px] w-[58px] items-center justify-center rounded-full bg-[image:var(--brand-gradient)] text-2xl shadow-glow"
    >
      ✨
    </button>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isFullscreen = FULLSCREEN_ROUTES.includes(pathname);

  useEffect(() => {
    initTelegram();
  }, []);

  useEffect(() => {
    const webApp = tg;
    if (!webApp) return;
    if (pathname === "/") {
      webApp.BackButton.hide();
      return;
    }
    const handleBack = () => router.back();
    webApp.BackButton.show();
    webApp.BackButton.onClick(handleBack);
    return () => {
      webApp.BackButton.offClick(handleBack);
    };
  }, [pathname, router]);

  return (
    <>
      <div className="min-h-screen" style={{ paddingBottom: isFullscreen ? 0 : 64 }}>
        {children}
      </div>

      {!isFullscreen && <Fab />}

      {!isFullscreen && (
        <div className="fixed inset-x-0 bottom-0 z-[2] border-t border-white/[0.08] bg-black/72 backdrop-blur-xl">
          <div className="flex">
            {TABS.map((tab) => {
              const selected = pathname === tab.path;
              return (
                <button
                  key={tab.path}
                  onClick={() => router.push(tab.path)}
                  className="flex flex-1 flex-col items-center gap-0.5 py-2 text-xs text-foreground-muted"
                >
                  <span
                    className={cn("text-xl transition-transform duration-200", selected && "scale-[1.12]")}
                    style={selected ? { filter: "drop-shadow(0 0 8px rgba(255,45,120,0.6))" } : undefined}
                  >
                    {tab.icon}
                  </span>
                  <span className={selected ? "text-foreground" : undefined}>{tab.text}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
