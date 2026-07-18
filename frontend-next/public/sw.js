/**
 * Service Worker мини-аппа: cache-first для превью-медиа и статики, чтобы при
 * повторном открытии тренды/баннеры/картинки не подгружались заново.
 *
 * Работает на Android и в desktop-Telegram. На iOS Telegram (WKWebView) SW не
 * поддерживается вовсе — там он просто не регистрируется (см.
 * ServiceWorkerRegister), и приложение живёт на HTTP-кэше + постер-кадрах.
 *
 * Range-запросы (их шлёт <video>) НЕ трогаем: ответ 206 нельзя положить в Cache
 * (`cache.put` бросает исключение на partial-response). Видео уже сжаты до
 * десятков-сотен КБ и обслуживаются HTTP-кэшем, а мгновенную картинку даёт
 * постер. SW кэширует постеры/картинки/статику — то, что переживает перезаход.
 */
const CACHE = "aihub-static-v1";

// Только статические ассеты одного origin. Не HTML-навигация, не /api/*.
const CACHEABLE = [
  /^\/trends\//,
  /^\/banners\//,
  /^\/actions\//,
  /^\/models\//,
  /^\/structural\//,
  /^\/_next\/static\//,
  /^\/_next\/image/,
];

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  if (request.headers.has("range")) return; // видео с Range -> HTTP-кэш, не SW

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (!CACHEABLE.some((re) => re.test(url.pathname))) return;

  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(request);
      if (cached) {
        // stale-while-revalidate: мгновенно из кэша, тихое обновление в фоне.
        event.waitUntil(
          fetch(request)
            .then((res) => {
              if (res.ok) cache.put(request, res.clone());
            })
            .catch(() => {}),
        );
        return cached;
      }
      const res = await fetch(request);
      if (res.ok) cache.put(request, res.clone());
      return res;
    }),
  );
});
