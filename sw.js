/* ============================================
   减盘 · Service Worker
   离线缓存应用壳，使 App 可"安装"到手机主屏幕并离线使用
   （原型为单文件内联 HTML，应用壳只需缓存 index.html + 图标）
   ============================================ */

const CACHE_VERSION = 'jianpan-2.1.4';
const APP_SHELL = [
  './',
  './index.html',
  './assets/icon.png',
  './js/nutrition-engine.js',
  './js/food-store.js',
  './data/foods.json',
  './data/py-initials.json'
];

// 安装时缓存应用核心资源
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

// 清理旧缓存
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// 请求拦截：缓存优先 + 运行时缓存
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;

  e.respondWith(
    caches.match(e.request).then((cached) => {
      if (cached) return cached;

      return fetch(e.request)
        .then((resp) => {
          if (resp && resp.status === 200) {
            const clone = resp.clone();
            caches.open(CACHE_VERSION).then((cache) => cache.put(e.request, clone));
          }
          return resp;
        })
        .catch(() => {
          if (e.request.mode === 'navigate') {
            return caches.match('./index.html');
          }
          return cached;
        });
    })
  );
});
