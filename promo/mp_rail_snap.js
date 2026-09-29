/**
 * mp_rail_snap.js —— 验证滑动/吸附逻辑：跳到第 i 张后，那张卡是否真的停在视口正中。
 *
 * Mak 的原话是「滑动到某张卡片就自动缩小展示，逻辑不对」——
 * 根因是前导留白双份 ⇒ 焦点判定 round(sl/190) 与视觉错位。
 * 修完必须逐张验证：任意 i 走 _railGo(i) 后，该卡中心 === 视口中心(195)。
 *
 * 用法：python promo/_mp_run.py mp_rail_snap.js
 */
const automator = require('miniprogram-automator');

const WS = process.env.MP_WS || 'ws://127.0.0.1:9420';
const ROUTE = process.argv[2] || '/pages/me/me';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PROBE = [0, 1, 4, 7, 9];

(async () => {
  const mp = await automator.connect({ wsEndpoint: WS, timeout: 300000 });
  await sleep(1200);
  await mp.callWxMethod('reLaunch', { url: ROUTE });
  await sleep(2800);
  try { await mp.switchTab(ROUTE); } catch (e) { /* 非 tab 页跳过 */ }
  await sleep(1600);

  const raw = await mp.evaluate(function (probes) {
    return new Promise(function (done) {
      var pages = getCurrentPages();
      var page = pages[pages.length - 1];
      var out = [];
      var k = 0;
      function step() {
        if (k >= probes.length) { done(JSON.stringify(out)); return; }
        var i = probes[k++];
        page._railGo(i, true);
        setTimeout(function () {
          var q = wx.createSelectorQuery();
          q.selectAll('.rail-card').boundingClientRect();
          q.exec(function (r) {
            var cards = r[0] || [];
            var f = cards[i];
            out.push({
              i: i,
              center: f ? Math.round((f.left + f.width / 2) * 10) / 10 : null,
              left: f ? Math.round(f.left * 10) / 10 : null,
              w: f ? f.width : null,
              focusIdx: page.data.railFocusIdx,
              scrollLeft: page.data.railLeft,
            });
            step();
          });
        }, 500);
      }
      step();
    });
  }, PROBE);

  const rows = JSON.parse(raw || '[]');
  let bad = 0;
  console.log('VIEW_W=390  VIEW_CENTER=195  (容差 ±2px)');
  for (let n = 0; n < rows.length; n++) {
    const r = rows[n];
    const off = r.center == null ? 999 : Math.abs(r.center - 195);
    const ok = off <= 2 && r.focusIdx === r.i;
    if (!ok) bad++;
    console.log('  i=' + r.i + ' left=' + r.left + ' w=' + r.w +
      ' center=' + r.center + ' 偏差=' + (off === 999 ? 'N/A' : off.toFixed(1)) +
      ' focusIdx=' + r.focusIdx + ' scrollLeft=' + r.scrollLeft + '  ' + (ok ? 'OK' : 'BAD'));
  }
  console.log('BAD_COUNT=' + bad);
  await mp.disconnect();
  process.exit(bad === 0 ? 0 : 3);
})().catch((e) => {
  console.error('FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
