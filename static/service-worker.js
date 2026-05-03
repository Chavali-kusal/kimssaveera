const CACHE_NAME = "kimssaveera-pwa-v3";
const APP_SHELL = [
  "/m/login",
  "/offline.html",
  "/manifest.json",
  "/static/css/style.css",
  "/static/css/app-ui.css",
  "/static/js/app-ui.js",
  "/static/icons/icon-192x192.png",
  "/static/icons/icon-512x512.png",
  "/static/icons/maskable-192x192.png",
  "/static/icons/maskable-512x512.png",
  "/static/icons/Saveera-Hospital_logo-removebg-preview.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .catch(() => null)
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((key) => (key !== CACHE_NAME ? caches.delete(key) : null)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() =>
          caches.match(request)
            .then((cached) => cached || caches.match("/m/login") || caches.match("/offline.html"))
        )
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      return cached || fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);
    })
  );
});
