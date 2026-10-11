/**
 * ⚠️ 这个 Service Worker 故意【不缓存任何东西】。
 *
 * - 安装时不预缓存任何资源；
 * - 收到网络请求直接转发到网络，绝不写入 Cache Storage。
 *
 * 它唯一的作用就是让浏览器认出这是一个「可安装的 PWA」。
 * 千万不要在这里加任何缓存逻辑——否则每次部署新版本后，
 * 用户手机上都会因为缓存而看到旧页面，排查起来非常痛苦。
 */
self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", () => {
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // 网络直通：只对 GET 请求显式转发到网络，不拦截、不缓存。
  // 非 GET 请求不 respondWith，交给浏览器默认处理。
  if (event.request.method === "GET") {
    event.respondWith(fetch(event.request));
  }
});
