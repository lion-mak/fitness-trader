/**
 * mp_rail_height.js —— 量段位卡廊「高度链」的真实几何，定位卡片被上下裁切的元凶。
 *
 * 为什么：Mak 报「卡片没有完整展示，图片被横切了，高度该多留点」。焦点卡完整、
 *   两侧卡被切 ⇒ 要么是某个祖先容器 height 不够 + overflow:hidden（裁切方），
 *   要么是卡片自身 layout 高度 > 视觉高度（scale 不改变布局盒）。
 *   ⛔ 不靠读 CSS 猜：`.rail-card` 有两个规则块、还有 inline-block 基线/vertical-align
 *      的隐性偏移，读源码推不出实际渲染位置，必须量。
 *
 * 量什么：.profile-head → .rail → .rail-track → .rail-inner → 每张 .rail-card → 每个 .rail-img
 *   每层给 [left, top, width, height, bottom]，一眼就能看出「谁的 bottom 超出了谁的 bottom」。
 *
 * ⚠️ 必须 reLaunch：me 是 tab 页且常驻，switchTab 回去不重跑 onLoad ⇒ 量到旧 data。
 * ⚠️ 每段独立 evaluate；一次做太多会报 `An object could not be cloned`。
 *
 * 用法：python promo/_mp_run.py mp_rail_height.js
 */
const automator = require('miniprogram-automator');

const WS = process.env.MP_WS || 'ws://127.0.0.1:9420';
const ROUTE = process.argv[2] || '/pages/me/me';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const box = (b) => (b ? [
  Math.round(b.left), Math.round(b.top),
  Math.round(b.width), Math.round(b.height), Math.round(b.bottom),
] : null);

(async () => {
  const mp = await automator.connect({ wsEndpoint: WS, timeout: 300000 });
  await sleep(1200);

  await mp.callWxMethod('reLaunch', { url: ROUTE });
  await sleep(2800);
  try { await mp.switchTab(ROUTE); } catch (e) { /* 非 tab 页跳过 */ }
  await sleep(1600);

  const raw = await mp.evaluate(function () {
    return new Promise(function (done) {
      var q = wx.createSelectorQuery();
      q.select('.profile-head').boundingClientRect();
      q.select('.rail').boundingClientRect();
      q.select('.rail-track').boundingClientRect();
      q.select('.rail-inner').boundingClientRect();
      q.select('.rail-tip').boundingClientRect();
      q.selectAll('.rail-card').boundingClientRect();
      q.selectAll('.rail-img').boundingClientRect();
      q.exec(function (r) {
        function bx(b) {
          return b ? [
            Math.round(b.left), Math.round(b.top),
            Math.round(b.width), Math.round(b.height), Math.round(b.bottom),
          ] : null;
        }
        var cards = [];
        var cs = r[5] || [];
        for (var i = 0; i < cs.length; i++) cards.push({ i: i, box: bx(cs[i]) });
        var imgs = [];
        var is = r[6] || [];
        for (var j = 0; j < is.length; j++) imgs.push({ i: j, box: bx(is[j]) });
        done(JSON.stringify({
          head: bx(r[0]), rail: bx(r[1]), track: bx(r[2]),
          inner: bx(r[3]), tip: bx(r[4]), cards: cards, imgs: imgs,
        }));
      });
    });
  });

  const g = JSON.parse(raw || '{}');
  const fmt = (b) => (b ? '[L' + b[0] + ' T' + b[1] + ' W' + b[2] + ' H' + b[3] + ' B' + b[4] + ']' : 'null');

  console.log('=== 高度链 [left, top, width, height, bottom] ===');
  console.log('profile-head ' + fmt(g.head));
  console.log('rail         ' + fmt(g.rail));
  console.log('rail-track   ' + fmt(g.track));
  console.log('rail-inner   ' + fmt(g.inner));
  console.log('rail-tip     ' + fmt(g.tip));

  const cards = g.cards || [];
  console.log('=== cards (' + cards.length + ') ===');
  for (const c of cards) console.log('  CARD[' + c.i + '] ' + fmt(c.box));

  const imgs = g.imgs || [];
  console.log('=== imgs (' + imgs.length + ') ===');
  for (const m of imgs) console.log('  IMG[' + m.i + '] ' + fmt(m.box));

  /* 结论段：直接算出「谁裁了谁」 */
  console.log('=== 判读 ===');
  const tr = g.track;
  if (tr && cards.length) {
    const tTop = tr[1], tBot = tr[4];
    console.log('track 可视区 top=' + tTop + ' bottom=' + tBot);
    for (const c of cards) {
      const b = c.box;
      if (!b) continue;
      const overTop = tTop - b[1];
      const overBot = b[4] - tBot;
      console.log('  CARD[' + c.i + '] overflowTop=' + overTop + ' overflowBottom=' + overBot +
        (overTop > 0 || overBot > 0 ? '  <== 被 track 裁切' : '  ok'));
    }
  }
  if (cards.length && imgs.length) {
    for (let i = 0; i < Math.min(cards.length, imgs.length); i++) {
      const cb = cards[i].box, ib = imgs[i].box;
      if (!cb || !ib) continue;
      console.log('  CARD[' + i + '] vs IMG[' + i + ']  dh=' + (cb[3] - ib[3]) + '  dtop=' + (ib[1] - cb[1]));
    }
  }

  /* ===== 硬判据（改动后必看；退出码可被脚本/cron 判定）=====
     判据：每张卡的可视矩形必须完整落在 track 可视区内（top ≥ track.top 且 bottom ≤ track.bottom）。
     ⭐ 为什么必须用几何而不是样式断言：裁切属于「两个各自正确的值相加后越界」——
       height:254 对、卡高 240 对、padding 5/8 也对，加起来却少 10px。
       字符串断言逐条看都是绿的，本次就是这么漏过去的。几何量一次就现形。 */
  let bad = 0;
  const detail = [];
  if (tr && cards.length) {
    for (const c of cards) {
      const b = c.box;
      if (!b) continue;
      if (b[1] < tr[1] || b[4] > tr[4]) {
        bad++;
        detail.push('#' + c.i + '(T' + b[1] + ' B' + b[4] + ')');
      }
    }
  }
  console.log('===== ' + (bad === 0
    ? 'PASS: ' + cards.length + ' 张卡全部完整落在 track 内，无上下裁切'
    : 'FAIL: ' + bad + ' 张卡被 track 裁切 → ' + detail.join(' ')) + ' =====');

  await mp.disconnect();
  process.exit(bad === 0 ? 0 : 1);
})().catch((e) => {
  console.error('FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
