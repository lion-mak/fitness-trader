/**
 * mp_rail_measure.js —— 量「我的」页段位卡廊的真实几何（改前 / 改后各跑一次，用真数对比）。
 *
 * 为什么：Mak 报「只有一张卡的可视宽度、滑到某张卡反而缩小」。要分清是
 *   ① 结构层 —— scroll-view 在 .profile-head（align-items:center 的 flex 列）里宽度塌陷
 *   ② 定位层 —— scroll-left 目标公式与实际前导空白不一致，焦点卡错位
 * 只能量真值，不能靠读 CSS 猜。
 *
 * ⚠️ 必须 reLaunch：me 是 tab 页且常驻，switchTab 回去不重跑 onLoad ⇒ 会量到旧 data。
 * ⚠️ element 取几何要用 wx.createSelectorQuery（automator 的 Element 上没有 boundingBox）。
 * ⚠️ 每段独立 evaluate：一次做太多会报 `An object could not be cloned` 且定位不到是哪段。
 *
 * 用法：python promo/_mp_run.py mp_rail_measure.js
 */
const automator = require('miniprogram-automator');

const WS = process.env.MP_WS || 'ws://127.0.0.1:9420';
const ROUTE = process.argv[2] || '/pages/me/me';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const mp = await automator.connect({ wsEndpoint: WS, timeout: 300000 });
  await sleep(1200);

  await mp.callWxMethod('reLaunch', { url: ROUTE });
  await sleep(2800);
  try { await mp.switchTab(ROUTE); } catch (e) { /* 非 tab 页跳过 */ }
  await sleep(1600);

  /* ① 结构 + 几何：纯 boundingClientRect，返回值全是数字/布尔 */
  const geo = await mp.evaluate(function () {
    return new Promise(function (done) {
      var q = wx.createSelectorQuery();
      q.select('.rail').boundingClientRect();
      q.select('.rail-track').boundingClientRect();
      q.select('.profile-head').boundingClientRect();
      q.selectAll('.rail-card').boundingClientRect();
      q.exec(function (r) {
        var out = {
          rail: r[0] ? [r[0].width, r[0].height, r[0].left] : null,
          track: r[1] ? [r[1].width, r[1].height, r[1].left] : null,
          head: r[2] ? [r[2].width, r[2].height, r[2].left] : null,
          cards: [],
        };
        var cs = r[3] || [];
        for (var i = 0; i < cs.length; i++) {
          out.cards.push([
            Math.round(cs[i].left * 10) / 10,
            Math.round(cs[i].width * 10) / 10,
            Math.round(cs[i].height * 10) / 10,
          ]);
        }
        done(JSON.stringify(out));
      });
    });
  });
  const g = JSON.parse(geo || '{}');
  console.log('HAS_RAIL=' + !!g.rail + (g.rail ? ' railW=' + g.rail[0] : ''));
  console.log('TRACK=' + JSON.stringify(g.track));
  console.log('HEAD=' + JSON.stringify(g.head));
  const cards = g.cards || [];
  console.log('CARD_COUNT=' + cards.length + '  [left, w, h]');
  for (let i = 0; i < cards.length; i++) {
    console.log('  CARD[' + i + '] ' + JSON.stringify(cards[i]));
  }

  /* ② 焦点卡判定：用 automator 的 Element.attribute('class') 逐张读类名 */
  const els = await mp.currentPage().then((p) => p.$$('.rail-card'));
  console.log('ELEMENT_CARDS=' + (els ? els.length : 0));
  if (els && els.length) {
    for (let i = 0; i < els.length; i++) {
      let cls = '';
      try { cls = await els[i].attribute('class'); } catch (e) { cls = 'ERR:' + ((e && e.message) || e); }
      console.log('  CLASS[' + i + '] ' + cls);
    }
  }

  /* ③ 数据层：定位参数 + src 是否仍为 cloud://（= 云图没回退 ⇒ 存储读权限通） */
  try {
    const page = await mp.currentPage();
    const d = await page.data();
    console.log('DATA railPad=' + d.railPad + ' railLeft=' + d.railLeft +
      ' railFocusIdx=' + d.railFocusIdx + ' windowWidth=' + d.stW);
    const rows = d.rail || [];
    for (let i = 0; i < rows.length; i++) {
      const s = rows[i].src || '';
      const kind = s.indexOf('cloud://') === 0 ? 'CLOUD'
        : (s.indexOf('/images/') === 0 ? 'LOCAL' : 'OTHER');
      console.log('  SRC[' + i + '] ' + kind + ' ' + s.slice(0, 72));
    }
  } catch (e) {
    console.log('DATA_ERR=' + ((e && e.message) || e));
  }

  await mp.disconnect();
  process.exit(0);
})().catch((e) => {
  console.error('FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
