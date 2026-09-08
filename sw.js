/* ============================================
   减盘 · Service Worker
   离线缓存应用壳，使 App 可"安装"到手机主屏幕并离线使用
   （原型为单文件内联 HTML，应用壳只需缓存 index.html + 图标）
   ============================================ */

const CACHE_VERSION = 'jianpan-2.7.16';
const APP_SHELL = [
  './',
  './index.html',
  './assets/icon.png',
  './assets/body_male.png',
  './assets/body_female.png',
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

// 请求拦截：页面导航=网络优先（在线永远拿最新版，杜绝"进去停旧版"）；静态资源=缓存优先
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;

  // 文档/页面导航：网络优先 —— 只要在线就从服务器拿最新 index.html，并回填缓存；离线才回退缓存
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request)
        .then((resp) => {
          if (resp && resp.status === 200) {
            const clone = resp.clone();
            caches.open(CACHE_VERSION).then((cache) => cache.put(e.request, clone));
          }
          return resp;
        })
        .catch(() =>
          caches.match(e.request).then((c) => c || caches.match('./index.html'))
        )
    );
    return;
  }

  // 其余静态资源（js/data/icon 等）：缓存优先
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
          return cached;
        });
    })
  );
});
