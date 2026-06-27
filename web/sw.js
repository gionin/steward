const CACHE = "steward-v5";

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(async c => {
      const heavy = [
        "./vendor/sql-wasm.wasm",
        "./icons/icon-192.png",
        "./icons/icon-512.png",
      ];
      await Promise.allSettled(heavy.map(a => c.add(a).catch(() => {})));
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
  const url = e.request.url;
  if (/\.(wasm|png)$/.test(url)) {
    // Cache-first: large files that rarely change
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request).then(r2 => {
        if (r2.ok) caches.open(CACHE).then(c => c.put(e.request, r2.clone()));
        return r2;
      }))
    );
  } else {
    // Network-first: HTML/JS/manifest always fetched fresh, cache as offline fallback
    e.respondWith(
      fetch(e.request)
        .then(r => {
          if (r.ok) caches.open(CACHE).then(c => c.put(e.request, r.clone()));
          return r;
        })
        .catch(() => caches.match(e.request))
    );
  }
});
