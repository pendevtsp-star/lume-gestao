const LUME_CACHE = "lume-static-v20260721-pwa-security";
const STATIC_ASSETS = [
  "/static/css/app.css?v=20260721-pwa-security",
  "/static/css/quick-actions.css?v=20260721-pwa-security",
  "/static/js/app.js?v=20260721-pwa-security",
  "/static/images/pwa/lume-192.png?v=20260721-pwa-security",
  "/static/images/pwa/lume-512.png?v=20260721-pwa-security",
  "/static/images/lume-favicon.svg?v=20260721-pwa-security",
  "/static/images/website/lume-logo.jpg?v=20260721-pwa-security"
];

function isVersionedStaticAsset(url) {
  return (
    url.origin === self.location.origin
    && url.pathname.startsWith("/static/")
    && url.searchParams.has("v")
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(LUME_CACHE)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .catch(() => undefined)
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== LUME_CACHE).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  if (isVersionedStaticAsset(url)) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request))
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        new Response(
          "<!doctype html><title>Lume offline</title><main style='font-family:system-ui;padding:32px'><h1>Sem conexao</h1><p>Conecte-se novamente para acessar agenda, videos e dados atualizados.</p></main>",
          { headers: { "Content-Type": "text/html; charset=utf-8" } }
        )
      )
    );
  }
});
