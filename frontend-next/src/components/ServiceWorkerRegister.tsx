"use client";

import { useEffect } from "react";

/**
 * Регистрирует Service Worker (/sw.js) для кэширования превью-медиа и статики.
 *
 * На iOS Telegram (WKWebView) `serviceWorker` в navigator отсутствует — тогда
 * тихо выходим: приложение работает на HTTP-кэше и постер-кадрах. Регистрируем
 * после `load`, чтобы SW не конкурировал за сеть с первичной загрузкой.
 */
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    const register = () => navigator.serviceWorker.register("/sw.js").catch(() => {});
    if (document.readyState === "complete") register();
    else window.addEventListener("load", register, { once: true });
  }, []);

  return null;
}
