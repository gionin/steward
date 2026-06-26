const CACHE = "steward-v2";
const ASSETS = [
  "./",
  "./index.html",
  "./manifest.json",
  "./js/engine.js",
  "./js/storage.js",
  "./js/api.js",
  "./vendor/sql-wasm.js",
  "./vendor/sql-wasm.wasm",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(async c => {
      await Promise.allSettled(ASSETS.map(a => c.add(a).catch(() => {})));
      await self.skipWaiting();
    })
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
