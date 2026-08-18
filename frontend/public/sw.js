const CACHE_NAME = 'valence-grc-v3.12';
const ASSETS = [
  '/',
  '/static/index.html',
  '/static/manifest.json',
  '/static/icon.svg',
  'https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=IBM+Plex+Mono:wght@400;500;600&display=swap',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'
];

// Install Event
self.addEventListener('install', evt => {
  evt.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log('[SW] Caching shell assets');
      return cache.addAll(ASSETS).catch(err => {
        console.warn('[SW] Caching failed on some resources, proceeding anyway:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activate Event
self.addEventListener('activate', evt => {
  evt.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch Event (Network-First Fallback-to-Cache Strategy)
self.addEventListener('fetch', evt => {
  // Avoid caching non-GET requests or API requests
  if (evt.request.method !== 'GET' || evt.request.url.includes('/api/')) {
    return;
  }
  
  evt.respondWith(
    fetch(evt.request)
      .then(res => {
        // Clone response and cache it
        const resClone = res.clone();
        caches.open(CACHE_NAME).then(cache => {
          cache.put(evt.request, resClone);
        });
        return res;
      })
      .catch(() => {
        return caches.match(evt.request);
      })
  );
});
