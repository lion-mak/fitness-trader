/* mp_trade_test.js —— 交易页四块新逻辑的运行时断言（① 净热量分时 / ② 做多·做空 / ③ 今日板块 / ④ 今日成交）
 *
 * 与 mp_market_test.js 同款 mock：凡是能独立算的，都在这里另写一遍现算再比对。
 * 测试策略：复用行情页的 mock 基础设施（global.wx / App / Page / rectQuery / makeInstance /
 *   ctx2d / canvasNode），加载 pages/trade/trade.js，独立现算期望值。
 *
 * 用法：node promo/mp_trade_test.js   退出码 0=全过
 * 报告落盘：promo/_trade_out.txt
 */
'use strict';
const path = require('path');
const fs = require('fs');

const MINI = 'E:\\WeChatProjects\\jianpan\\miniprogram';
const OUT = path.join(__dirname, '_trade_out.txt');

const lines = [];
const out = (s) => lines.push(s === undefined ? '' : s);
let pass = 0;
const fails = [];
function ok(name) { pass++; out('  ✓ ' + name); }
function must(cond, name, detail) {
  if (cond) { ok(name); return true; }
  fails.push(name + (detail ? ' → ' + detail : ''));
  out('  ✗ ' + name + (detail ? ' → ' + detail : ''));
  return false;
}
function sec(t) { out(''); out('=== ' + t + ' ==='); }

/* ============================================================
 * 独立参考实现（故意不复用 calc 的任何函数）
 * ============================================================ */
const pad2 = (n) => String(n).padStart(2, '0');
const dstr = (d) => d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
function D(n) { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n); return dstr(d); }

/* ============================================================
 * mock（与 mp_market_test 同款）
 * ============================================================ */
const storage = {};
const noop = () => {};
const ctxStats = { total: 0, fillText: 0, fillRect: 0, stroke: 0, arc: 0 };
function bump(n) { ctxStats.total++; if (n in ctxStats) ctxStats[n]++; }
function ctx2d() {
  const w = (name) => (...a) => { bump(name); return undefined; };
  return {
    save: w('save'), restore: w('restore'), beginPath: w('beginPath'), closePath: w('closePath'),
    moveTo: w('moveTo'), lineTo: w('lineTo'), arc: w('arc'), arcTo: w('arcTo'), rect: w('rect'),
    fill: w('fill'), stroke: w('stroke'), clip: w('clip'), fillRect: w('fillRect'),
    strokeRect: w('strokeRect'), clearRect: w('clearRect'), fillText: w('fillText'),
    strokeText: w('strokeText'), translate: w('translate'), rotate: w('rotate'), scale: w('scale'),
    setTransform: w('setTransform'), transform: w('transform'), drawImage: w('drawImage'),
    setLineDash: w('setLineDash'), quadraticCurveTo: w('quadraticCurveTo'),
    bezierCurveTo: w('bezierCurveTo'),
    createLinearGradient: () => ({ addColorStop: noop }),
    createRadialGradient: () => ({ addColorStop: noop }),
    createPattern: () => ({}),
    measureText: (t) => { bump('measureText'); return { width: String(t).length * 6 }; },
    getImageData: () => ({ data: [] }), putImageData: noop,
  };
}
const canvasNode = () => ({
  width: 600, height: 400, getContext: () => ctx2d(),
  createImage: () => ({ onload: null, onerror: null, src: '', width: 0, height: 0 }),
  requestAnimationFrame: (f) => setTimeout(f, 0),
});

const BOX = {
  '.trade-page': 430,
  '#intraday-chart': 374,
  '#intraday-canvas': 374,
  'default': 374,
};
function rectQuery() {
  const q = [];
  const r = {
    select: (s) => { q.push(s); return r; },
    selectAll: (s) => { q.push(s); return r; },
    in: () => r,
    fields: () => r,
    boundingClientRect: () => r,
    exec: (cb) => {
      const res = q.map((s) => ({
        left: 0, top: 0, width: (BOX[s] !== undefined ? BOX[s] : BOX['default']), height: 400,
        node: canvasNode(),
      }));
      q.length = 0;
      if (typeof cb === 'function') cb(res);
      return r;
    },
  };
  return r;
}

const calls = [];
global.wx = {
  getStorageSync: (k) => (k in storage ? storage[k] : ''),
  setStorageSync: (k, v) => { storage[k] = v; },
  removeStorageSync: (k) => { delete storage[k]; },
  getStorageInfoSync: () => ({ keys: Object.keys(storage), currentSize: 0, limitSize: 10240 }),
  getWindowInfo: () => ({ statusBarHeight: 54, windowWidth: 430, windowHeight: 932,
                          screenWidth: 430, screenHeight: 932, pixelRatio: 3,
                          safeArea: { top: 54, bottom: 898, left: 0, right: 430 } }),
  getDeviceInfo: () => ({ platform: 'devtools', system: 'iOS 17.0', model: 'iPhone' }),
  getSystemInfoSync: () => global.wx.getWindowInfo(),
  getMenuButtonBoundingClientRect: () => ({ top: 58, bottom: 90, left: 333, right: 420, width: 87, height: 32 }),
  createSelectorQuery: () => rectQuery(),
  nextTick: (fn) => setTimeout(fn, 0),
  showToast: (o) => calls.push(['showToast', o && o.title]),
  showModal: (o) => { calls.push(['showModal', o && o.title]); o && o.success && o.success({ confirm: true, content: '123' }); },
  setNavigationBarTitle: noop, stopPullDownRefresh: noop,
};
const captured = { app: null, pages: [] };
global.App = (o) => { captured.app = o; };
global.Page = (o) => { captured.pages.push(o); };
global.getApp = () => captured.app;
global.getCurrentPages = () => [];
function makeInstance(opt) {
  const inst = Object.create(opt);
  inst.data = Object.assign({}, opt.data || {});
  inst.setData = function (o, cb) {
    Object.keys(o || {}).forEach((k) => {
      const val = o[k];
      if (k.indexOf('.') === -1) { inst.data[k] = val; return; }
      const seg = k.split('.');
      let cur = inst.data;
      for (let i = 0; i < seg.length - 1; i++) {
        if (cur[seg[i]] == null || typeof cur[seg[i]] !== 'object') cur[seg[i]] = {};
        cur = cur[seg[i]];
      }
      cur[seg[seg.length - 1]] = val;
    });
    if (typeof cb === 'function') cb();
  };
  inst.createSelectorQuery = () => rectQuery();
  return inst;
}

/* ============================================================
 * 构造真实感存档
 * ============================================================ */
let SEQ = 0;
const rec = (name, kcal, dateOff, hour) => ({
  id: 'r' + (++SEQ), name: name, kcal: kcal, date: D(dateOff),
  time: pad2(hour) + ':00', ts: null, qty: 1, unit: 'g', gram: 100,
});
function buildSeed() {
  const calc = require(path.join(MINI, 'lib/calc.js'));
  const st = calc.defaultState();
  st.user = Object.assign({}, st.user, {
    userId: 'FT_TEST', weight: 78.4, height: 175, gender: 'male', age: 30, startWeight: 86,
  });
  st.body = Object.assign({}, st.body, {
    bmi: 23.3, bodyFat: 17.4, muscleRate: 41.2, waterRate: 58.6, bodyAge: 28,
    visceralFat: 8, source: 'manual', syncedAt: '08:30',
  });
  st.coins = 1200; st.exp = 300;
  st.weightLog = [-12, -8, -5, -2, 0].map((o, i) => ({ date: D(o), weight: 79.6 - i * 0.3 }));
  const dietDays = [-1, -3, -5, -8, -12, -20, -30, -45, -60, -70];
  st.diet = [rec('米饭', 300, 0, 12), rec('红烧肉', 700, 0, 19)];
  dietDays.forEach((o, i) => { st.diet.push(rec('第' + (i + 1) + '天餐', 400 + i * 37, o, 13)); });
  st.exercise = [rec('跑步', 420, 0, 20)];
  for (let i = 1; i <= 14; i++) st.exercise.push(rec('训练' + i, 120 + i * 30, -i, 21));
  st.bodyLog = [];
  return st;
}

function fresh() {
  Object.keys(storage).forEach((k) => { delete storage[k]; });
  captured.pages.length = 0;
  captured.app = null;
  calls.length = 0;
  Object.keys(require.cache).forEach((k) => { if (k.indexOf(MINI) === 0) delete require.cache[k]; });
}
function boot(state) {
  fresh();
  storage['jianpan_v2'] = state;
  require(path.join(MINI, 'app.js'));
  captured.app.onLaunch.call(captured.app);
  require(path.join(MINI, 'pages/trade/trade.js'));
  const mk = makeInstance(captured.pages[captured.pages.length - 1]);
  mk.onLoad.call(mk, {});
  mk.onReady && mk.onReady.call(mk);
  return mk;
}

/* ============================================================
 * 跑
 * ============================================================ */
const seed = buildSeed();
const mk = boot(seed);
const calc = require(path.join(MINI, 'lib/calc.js'));

out('=== 交易页四块运行时验证 ===');
out('工程：' + MINI);
out('页面内容宽 430 → 卡片内容 374（mock 按真实 WXSS 给出）');

/* ---------------- A. 画布盒尺寸口径 ---------------- */
sec('A. 分时图盒尺寸（按宽撑满 = 容器宽 × 182/340）');
mk.refresh();
const W = 340, H = 182, CARD_PAD = 56;
const avail = 430 - CARD_PAD;
must(mk.data.intradayH === Math.round(avail * H / W),
  '分时图画布高 = 容器宽 × 182/340（与 PWA width:100% height:auto 同口径）',
  '实测 ' + mk.data.intradayH + '，期望 ' + Math.round(avail * H / W));

/* ---------------- B. 净热量分时：徽章 / 状态胶囊 / 事件点 ---------------- */
sec('B. 净热量分时（computeIntraday）');
const t = calc.totals();
const base = Math.max(0, Math.round(t.bmr));
const now = new Date();
const nowMin = now.getHours() * 60 + now.getMinutes();
const trading = nowMin >= 5 * 60 && nowMin <= 23 * 60;
must(mk.data.pillOn === trading, '状态胶囊：交易时段(05:00–23:00)显示「主力控盘中」', 'pillOn=' + mk.data.pillOn);
must(mk.data.pillText === (trading ? '主力控盘中' : '休市中'), '状态胶囊文案正确', mk.data.pillText);

const dietToday = calc.todayDiet(), exToday = calc.todayExercise();
/* ⚠️ 事件点**只画到「现在」为止**（分时图不画未来）：页面里是
     shown = events.filter(ev => ev.min <= lineEnd)，lineEnd = max(OPEN, min(CLOSE, nowMin))
   ⇒ 期望值必须自己带上这条时间窗，否则这条断言会随**跑测试的时刻**在通过/失败之间跳：
     2026-09-23 19:45 跑就挂（种子里的「跑步 20:00」还没到 ⇒ marks=2 而今天记录=3），
     22:00 之后跑又是 3。这是测试自身的缺陷，不是页面坏了。
   这里独立现算一遍（只按规则数，不调页面的任何函数）。 */
const OPEN_M = 5 * 60, CLOSE_M = 23 * 60;
const lineEndM = Math.max(OPEN_M, Math.min(CLOSE_M, nowMin));
const inWindow = (r) => {
  const m = calc.recordMinute(r);
  /* recordMinute 取不到时间时，页面按「现在」算（ev.min = min(nowMin, CLOSE)）⇒ 一样落在窗内 */
  const mm = (m == null) ? Math.min(nowMin, CLOSE_M) : Math.max(OPEN_M, Math.min(CLOSE_M, m));
  return mm <= lineEndM;
};
const allToday = dietToday.concat(exToday);
/* ⚠️ 两个口径别混：
     evCount   = 今天**全部**记录（今日成交列表 / 徽章判空用这个 —— 页面里 badge 走 `!events.length`，
                 events 是未过滤的全部今日记录）
     markCount = 落在 [05:00, 现在] 的条数（**只有分时图的事件点**用这个）
   2026-09-23 一度把两者合成一个变量，结果 B 段对了、E 段「成交笔数」反被带崩（期望 2 实测 3）。 */
const evCount = allToday.length;
const markCount = allToday.filter(inWindow).length;
const clipped = allToday.filter((r) => !inWindow(r));
must(mk._intradayModel && mk._intradayModel.marks.length === markCount,
  '事件点数量 = 今日记录里落在 [05:00, 现在] 的条数（' + markCount + '）',
  '实测 ' + (mk._intradayModel ? mk._intradayModel.marks.length : 'null'));
if (clipped.length) {
  /* 跑测试的时刻恰好给出负控样本时，顺手把它记录在案（不是断言，是证据） */
  out('  ℹ️ 负控样本：时间在「现在」之后的 ' + clipped.length + ' 条没有被画进去 → '
    + clipped.map((r) => r.name + ' ' + r.time).join(' / '));
}

const cumToday = dietToday.reduce((s, d) => s + Math.round(d.kcal || 0), 0)
  - exToday.reduce((s, e) => s + Math.round(e.kcal || 0), 0);
const gap = base - Math.round(cumToday);
if (evCount === 0) {
  must(/待第一笔/.test(mk.data.badgeText), '无记录时徽章走「待第一笔」', mk.data.badgeText);
} else if (gap >= 0) {
  must(/达标/.test(mk.data.badgeText), '有记录且达标时徽章走「达标」', mk.data.badgeText);
  must(mk.data.badgeColor === '#22c584', '达标徽章配色', mk.data.badgeColor);
} else {
  must(/超预算/.test(mk.data.badgeText), '超支时徽章走「超预算」', mk.data.badgeText);
  must(mk.data.badgeColor === '#ff3b47', '超预算徽章配色', mk.data.badgeColor);
}

/* ---------------- C. 做多·做空 统计 ---------------- */
sec('C. 做多·做空 统计（computeStats）');
must(mk.data.intakeText === '+' + dietToday.reduce((s, d) => s + Math.round(d.kcal || 0), 0),
  '做多摄入文本 = 独立算的当日摄入合计', '实测 ' + mk.data.intakeText);
must(mk.data.burnText === '-' + exToday.reduce((s, e) => s + Math.round(e.kcal || 0), 0),
  '做空消耗文本 = 独立算的当日运动合计', '实测 ' + mk.data.burnText);
must(mk.data.intakeCnt === dietToday.length + ' 笔 · 食物库匹配', '做多笔数文案', mk.data.intakeCnt);
must(mk.data.burnCnt === exToday.length + ' 笔 · MET 自动算', '做空笔数文案', mk.data.burnCnt);

/* ---------------- D. 今日板块 ---------------- */
sec('D. 今日板块（computeSectors）');
const net = dietToday.reduce((s, d) => s + Math.round(d.kcal || 0), 0)
  - exToday.reduce((s, e) => s + Math.round(e.kcal || 0), 0) - base;
let badgeCls = net < -50 ? 'bull' : (net > 50 ? 'bear' : 'flat');
must(mk.data.sectorBadgeCls === badgeCls, 'net 徽章牛/熊/平衡分类正确（net=' + net + '）',
  '实测 ' + mk.data.sectorBadgeCls + ' / 期望 ' + badgeCls);
must(mk.data.sectorDate === calc.todayStr().slice(5).replace('-', '/'), '板块日期 = 今日(月/日)', mk.data.sectorDate);

/* short 列：基础代谢(pin) + 今日运动 */
must(mk.data.sectorsShort.length === exToday.length + 1,
  'short 列 = 基础代谢 + 今日运动笔数', '实测 ' + mk.data.sectorsShort.length);
must(mk.data.sectorsShort[0].type === 'bmr' && mk.data.sectorsShort[0].editable === false,
  'short 列首块恒为基础代谢(pin，不可编辑)', mk.data.sectorsShort[0].name);
/* long 列：今日饮食 */
must(mk.data.sectorsLong.length === dietToday.length, 'long 列 = 今日饮食笔数', '实测 ' + mk.data.sectorsLong.length);
/* flex 公式 = max(1, round(sqrt(kcal)*10)) */
const flexOf = (k) => Math.max(1, Math.round(Math.sqrt(k) * 10));
const allSec = mk.data.sectorsShort.concat(mk.data.sectorsLong);
const flexBad = allSec.filter((s) => s.flex !== flexOf(s.kcal));
must(flexBad.length === 0, '每块 flex = max(1, round(sqrt(kcal)*10))', flexBad.length + ' 块不符');

/* ---------------- E. 今日成交 ---------------- */
sec('E. 今日成交（computeEntries）');
must(mk.data.count === evCount, '成交笔数 = 饮食+运动总笔数', '实测 ' + mk.data.count);
must(mk.data.entries.length === evCount, 'entries 数组长度一致', '实测 ' + mk.data.entries.length);
/* 按时间升序 */
let timeOk = true;
for (let i = 1; i < mk.data.entries.length; i++) {
  const a = calc.recordMinute(dietToday.concat(exToday).find(x => x.id === mk.data.entries[i - 1].id));
  const b = calc.recordMinute(dietToday.concat(exToday).find(x => x.id === mk.data.entries[i].id));
  if (a != null && b != null && a > b) { timeOk = false; break; }
}
must(timeOk, '成交列表按时间升序（与 PWA entryHTML 同口径）');
/* 字段：sign/kcal/color 与类型匹配 */
const fBad = mk.data.entries.filter((e) => {
  if (e.type === 'food') return e.sign !== '+' || e.color !== '#ff3b47';
  return e.sign !== '-' || e.color !== '#00c896';
});
must(fBad.length === 0, '每条 sign(+/-) 与 color(红/绿) 与类型匹配', fBad.length + ' 条不符');

/* ---------------- F. 刷新聚合扁平 / 防回归 ---------------- */
sec('F. 刷新聚合：扁平补丁 + 防回归');
const nested = Object.keys(mk.data).filter((k) => k === 'data' && typeof mk.data[k] === 'object' && 'data' in mk.data[k]);
must(nested.length === 0, 'mk.data 不能出现嵌套 data 键（抓「某块多包一层」静默缺陷）');
/* 各块关键字段都落到页面（没有因 Object.assign 静默丢块） */
must(mk.data.intradayH > 0 && mk.data.badgeText && mk.data.sectorBadgeCls && mk.data.count >= 0,
  '四块关键字段全部落页（无静默丢块）');

/* ---------------- G. 画布绘制（全 no-op mock 会让「一行没画」也显示通过） ---------------- */
sec('G. 分时图画布绘制');
ctxStats.total = 0; ctxStats.fillText = 0;
mk.refresh();
must(ctxStats.total > 50, '分时图 canvas 真画了（绘制调用远超空转）', ctxStats.total + ' 次');
must(ctxStats.fillText > 0, '画布上写下了文字（刻度/标签/封死涨停）', String(ctxStats.fillText));

/* ---------------- H. 空存档（全新用户） ---------------- */
sec('H. 空存档（全新用户）');
const emptySeed = calc.defaultState();
const mk2 = boot(emptySeed);
mk2.refresh();   // onShow 才触发 refresh，mock 不跑生命周期，需手动拉一次
must(mk2.data.count === 0 && mk2.data.entries.length === 0, '无记录 ⇒ 今日成交为空');
must(mk2.data.sectorsLong.length === 0, '无饮食 ⇒ long 列空');
must(mk2.data.sectorsShort.length === 1 && mk2.data.sectorsShort[0].type === 'bmr',
  'short 列只剩基础代谢一块（基础代谢常驻）');
must(/待第一笔/.test(mk2.data.badgeText), '空存档徽章走「待第一笔」', mk2.data.badgeText);

/* ---------------- I. 负控：改净热量口径，徽章必须跟着变 ---------------- */
sec('I. 负控 · 净热量口径');
const netNow = calc.totals().net;
const clsNow = mk.data.sectorBadgeCls;
/* 负控：注入一笔超大饮食，使净热量由负翻正 → 徽章应从 bull 变 bear，
   证明 computeSectors 读的是活口径（calc.totals()），不是常量缓存。
   ⚠️ todayDiet() 返回 filter 副本，push 不进真 state；须直接 push 进 seed.diet
      （mock 下 storage['jianpan_v2'] 与 calc.state 是同一引用）。 */
seed.diet.push({ id: 'rx', type: 'food', name: '大餐', kcal: 5000, date: calc.todayStr(), time: '22:00', ts: null });
mk.refresh();
const clsAfter = mk.data.sectorBadgeCls;
must(clsAfter !== clsNow || (netNow < -50 && calc.totals().net > -50 && clsAfter !== 'bull'),
  '负控 · 注入超大饮食后净热量翻正、板块徽章分类改变（证明读的是活口径）',
  '前 ' + clsNow + ' / 后 ' + clsAfter);

/* ---------------- 汇总 ---------------- */
out('');
out('='.repeat(78));
out('通过 ' + pass + ' 项 / 失败 ' + fails.length + ' 项');
if (fails.length) {
  out('');
  fails.forEach((f) => out('  ✗ ' + f));
}
const summary = (fails.length ? 'RESULT=FAIL (' + fails.length + ')' : 'RESULT=OK');
out(summary);
out('='.repeat(78));
fs.writeFileSync(OUT, lines.join('\n') + '\n', 'utf-8');
/* ⚠️ 明细必须**同时**打到 stdout：out() 只攒进 lines（落文件），
   而 _run_all_asserts.py 的「独立数 ✗ 行」读的是 stdout ⇒ 不补这一行，
   那道「假 OK 守卫」对本题就是**空转**的（数到 0 看着像通过，实际压根没读到）。
   收尾写法与 mp_me_test.js 保持一致。 */
console.log(lines.join('\n'));
process.exit(fails.length ? 1 : 0);
