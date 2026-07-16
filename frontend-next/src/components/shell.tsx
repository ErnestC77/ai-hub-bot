"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { initTelegram, tg } from "@/lib/telegram";
import { cn } from "@/lib/cn";

const TABS = [
  { path: "/", text: "Home", icon: "🏠" },
  { path: "/trends", text: "Trends", icon: "✨" },
  { path: "/account", text: "Account", icon: "👤" },
];

const FULLSCREEN_ROUTES = ["/chat", "/generate-image", "/generate-video"];

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
      <div className="min-h-screen" style={{ paddingBottom: isFullscreen ? 0 : 96 }}>
        {children}
      </div>

      {!isFullscreen && (
        <nav
          className="fixed inset-x-4 z-[2] flex items-center gap-1 rounded-[22px] border border-white/10 bg-[rgba(20,14,36,0.6)] p-2 backdrop-blur-[20px]"
          style={{ bottom: "calc(env(safe-area-inset-bottom, 0px) + 16px)" }}
        >
          {TABS.map((tab) => {
            const selected = pathname === tab.path;
            return (
              <button
                key={tab.path}
                onClick={() => router.push(tab.path)}
                className={cn(
                  "press-scale flex flex-1 flex-col items-center gap-[3px] rounded-[15px] py-[7px] text-[11px] font-semibold",
                  selected ? "text-white" : "text-foreground-dim",
                )}
                style={
                  selected
                    ? { background: "linear-gradient(135deg, rgba(139,92,255,0.4), rgba(53,224,230,0.25))" }
                    : undefined
                }
              >
                <span
                  className="text-[17px]"
                  style={selected ? { filter: "drop-shadow(0 0 6px rgba(139,92,255,0.8))" } : undefined}
                >
                  {tab.icon}
                </span>
                <span>{tab.text}</span>
              </button>
            );
          })}
        </nav>
      )}
    </>
  );
}
