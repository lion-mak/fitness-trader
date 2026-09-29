/**
 * mp_upload_ach_bytes.js —— 把成就像素画的**字节**直接塞进云函数调用参数，上传到云存储。
 *
 * 为什么不走「云函数自己出公网拉图」那条通路（uploadAchAssets 的通路 B）：
 *   本环境云函数出公网拉 GitHub Pages 抖动极大 —— 默认 3 秒超时下**单张也会随机超时**
 *   （实测一批 10 张、每片 1 张，仍有 4 张撞 FUNCTIONS_TIME_LIMIT_EXCEEDED）。
 *   把字节塞进 `event.items` 后云函数**完全不出公网**，一次调用只剩 uploadFile ⇒ 稳定。
 *
 * 用法：node mp_upload_ach_bytes.js <icon,icon,...>
 *   env ACH_DIR 本地 assets/ach 目录（默认 PWA 仓库那个）
 *   env MP_WS    模拟器自动化端口（默认 ws://127.0.0.1:9420）
 * 输出：FN_RESULT={...}   退出码 0=云函数返回 ok
 */
const fs = require('fs');
const path = require('path');
const automator = require('miniprogram-automator');

const NAMES = String(process.argv[2] || '').split(',').filter(Boolean);
const DIR = process.env.ACH_DIR || 'E:\\WorkBuddy\\jianpan-ghpages\\assets\\ach';
const WS = process.env.MP_WS || 'ws://127.0.0.1:9420';

if (!NAMES.length) {
  console.error('用法：node mp_upload_ach_bytes.js <icon,icon,...>');
  process.exit(2);
}

/* ⛔ 传字节前先做本地存在性检查：路径写错会以「云函数返回空内容」的形式暴露，难查 */
const items = NAMES.map(function (n) {
  const p = path.join(DIR, 'ach-' + n + '.png');
  if (!fs.existsSync(p)) throw new Error('本地缺图：' + p);
  return { name: n, b64: fs.readFileSync(p).toString('base64') };
});

(async () => {
  const mp = await automator.connect({ wsEndpoint: WS, timeout: 300000 });
  await new Promise((r) => setTimeout(r, 1200));

  const t0 = Date.now();
  const res = await mp.evaluate(function (fnName, payload) {
    return new Promise(function (done) {
      wx.cloud.callFunction({
        name: fnName,
        data: { items: payload },
        success: function (r) { done({ ok: true, result: r.result }); },
        fail: function (e) { done({ ok: false, errMsg: (e && e.errMsg) || String(e) }); },
      });
    });
  }, 'uploadAchAssets', items);

  console.log('ELAPSED_MS=' + (Date.now() - t0));
  console.log('FN_RESULT=' + JSON.stringify(res));
  await mp.disconnect();
  process.exit(res && res.ok ? 0 : 4);
})().catch((e) => {
  console.error('FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
