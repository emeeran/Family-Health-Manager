// Service worker for the Health Manager PWA.
//
// IMPORTANT: API responses (/api/*) are deliberately NEVER cached. This is a
// health-records app — serving stale lab results, medication lists, or AI
// insights would be actively harmful. Only the static app shell (HTML/JS/CSS/
// fonts) is cached, so the UI loads fast and survives a flaky network while
// every data request always hits the server.
const CACHE_NAME = "health-keeper-v4";
const PRECACHE_URLS = ["/", "/index.html"];

// Install — precache the app shell. We do NOT call skipWaiting() here: the page
// prompts the user and sends { type: "SKIP_WAITING" } when they accept, so an
// in-flight action isn't disrupted by the app swapping to a new version
// mid-session.
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)));
});

// Activate — evict ALL caches that aren't the current version (this purges
// legacy caches, including the removed /api response cache) and claim clients.
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

// Allow the page to activate a waiting update on demand.
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only handle same-origin GETs.
  if (request.method !== "GET") return;
  if (!request.url.startsWith(self.location.origin)) return;

  // API requests: never intercept — always go to the network.
  if (request.url.includes("/api/")) return;

  // Navigation: network-first, fall back to the cached app shell offline.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(request).then((r) => r || caches.match("/") || caches.match("/index.html"))
      )
    );
    return;
  }

  // Static assets: cache-first, but never cache an HTML fallback as JS/CSS
  // (happens when a hashed chunk is gone after a deploy — serve a 404 so the
  // app can recover via a reload rather than executing HTML as a script).
  if (request.url.match(/\.(js|css|png|jpg|jpeg|gif|svg|ico|woff2?|json|map)$/)) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            const contentType = response.headers.get("content-type") || "";
            if (request.url.match(/\.(js|css)$/) && contentType.includes("text/html")) {
              return new Response("Not Found", { status: 404, statusText: "Not Found" });
            }
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        });
      })
    );
  }
});
