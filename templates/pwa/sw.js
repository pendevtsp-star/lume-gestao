const LUME_CACHE = "lume-shell-v20260712";
const STATIC_ASSETS = [
  "/static/css/app.css?v=20260712-pwa",
  "/static/css/quick-actions.css?v=20260630-quick-actions-compact",
  "/static/js/app.js?v=20260712-pwa",
  "/static/images/lume-favicon.svg",
  "/static/images/website/lume-logo.jpg"
];

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

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        const clone = response.clone();
        caches.open(LUME_CACHE).then((cache) => cache.put(request, clone));
        return response;
      }))
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
