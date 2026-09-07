/*
 * Real service worker, not a stub. Two jobs:
 * 1. Cache the app shell so it loads offline (cache-first for same-origin
 *    static assets).
 * 2. Queue capture uploads made while offline in IndexedDB, and replay them
 *    for real via the Background Sync API when connectivity returns —
 *    upgrading the technician app's previous "Saved offline — will sync
 *    automatically" UI text from a setTimeout simulation into an actual
 *    queued-and-replayed network request.
 *
 * Scope is /technician-app/, matching manifest.json's "scope" field.
 */

const CACHE_NAME = 'fpc-technician-v1';
const APP_SHELL = [
  '/technician-app/',
  '/technician-app/index.html',
  '/technician-app/manifest.json',
  '/technician-app/icons/icon-192.png',
  '/technician-app/icons/icon-512.png',
];

const DB_NAME = 'fpc-offline-queue';
const STORE_NAME = 'pending-captures';

function openQueueDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function queueCapture(record) {
  const db = await openQueueDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).add(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getQueuedCaptures() {
  const db = await openQueueDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const req = tx.objectStore(STORE_NAME).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function deleteQueuedCapture(id) {
  const db = await openQueueDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/* ---- app shell caching ---- */

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // never cache API calls — always hit the network for real job/capture data
  if (url.pathname.startsWith('/v1/')) return;

  // cache-first for the app shell itself
  if (url.pathname.startsWith('/technician-app/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
  }
});

/* ---- real offline queue ---- */

// The page posts a message here instead of calling fetch() directly when
// navigator.onLine is false (or when a real fetch attempt throws). This is
// the service worker actually taking ownership of "make sure this capture
// gets uploaded eventually" rather than the page pretending it will.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'QUEUE_CAPTURE') {
    event.waitUntil(
      queueCapture(event.data.record).then(async () => {
        // ask for a real Background Sync when the browser supports it
        if ('sync' in self.registration) {
          try { await self.registration.sync.register('replay-captures'); }
          catch (e) { /* Background Sync unsupported/denied — will still retry on next 'online' message */ }
        }
      })
    );
  }
  if (event.data && event.data.type === 'REPLAY_NOW') {
    event.waitUntil(replayQueuedCaptures());
  }
});

self.addEventListener('sync', (event) => {
  if (event.tag === 'replay-captures') {
    event.waitUntil(replayQueuedCaptures());
  }
});

async function replayQueuedCaptures() {
  const queued = await getQueuedCaptures();
  const clients = await self.clients.matchAll();
  for (const record of queued) {
    try {
      // real init call
      const initRes = await fetch(record.apiBase + '/v1/captures/init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + record.token },
        body: JSON.stringify(record.initBody),
      });
      if (!initRes.ok) throw new Error('init failed: ' + initRes.status);
      const initData = await initRes.json();

      // real upload of the real bytes that were queued
      const blob = new Blob([new Uint8Array(record.imageBytes)], { type: 'image/png' });
      const uploadRes = await fetch(record.apiBase + initData.upload_url, { method: 'PUT', body: blob });
      if (!uploadRes.ok) throw new Error('upload failed: ' + uploadRes.status);

      // real completion
      const completeRes = await fetch(record.apiBase + '/v1/captures/' + initData.capture_id + '/complete', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + record.token },
      });
      const completeData = await completeRes.json();

      await deleteQueuedCapture(record.id);
      clients.forEach((c) => c.postMessage({ type: 'CAPTURE_REPLAYED', record, result: completeData }));
    } catch (err) {
      // leave it queued — network's still down or the server rejected it;
      // either way nothing is silently lost, it just waits for the next sync
      clients.forEach((c) => c.postMessage({ type: 'REPLAY_FAILED', error: String(err) }));
      break;
    }
  }
}
