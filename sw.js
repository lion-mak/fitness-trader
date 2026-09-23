/* ============================================
   减盘 · Service Worker
   离线缓存应用壳，使 App 可"安装"到手机主屏幕并离线使用

   ⚠️ 预缓存清单 = 首访必下。加文件前先问「这次访问真的用得到吗」：
   · 1.04 MB 的 icon.png（1024²/未优化）曾在这里，现已换成 180/192/512 三档共 81 KB；
   · 2.43 MB 的 trading-floor-full.png 在交易大厅删除后已零引用，却仍被每次首访下载 —— v2.7.56 移除；
   · 身体成分那两张人体图只有打开对应页面才用得到，改由下面的 fetch 处理器按需缓存。
   ============================================ */

const CACHE_VERSION = 'jianpan-2.7.57';
const APP_SHELL = [
  './',
  './index.html',
  './manifest.json',
  './assets/icon-192.png',
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
