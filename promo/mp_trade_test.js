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
const ctxStats = { total: 0, fillText: 0, fillRect: 0, stroke: 0, arc: 0, clearRect: 0 };
function bump(n) { ctxStats.total++; if (n in ctxStats) ctxStats[n]++; }
/* arc 半径要**记下来**：末端琥珀点的呼吸动效唯一的可观测表现就是「光晕半径随相位在 5~12 之间走」。
   只数 arc 调用次数是不够的 —— 半径恒定也算「画了圆」。 */
const arcRadii = [];
function ctx2d() {
  const w = (name) => (...a) => { bump(name); return undefined; };
  return {
    save: w('save'), restore: w('restore'), beginPath: w('beginPath'), closePath: w('closePath'),
    moveTo: w('moveTo'), lineTo: w('lineTo'), arc: (...a) => { bump('arc'); arcRadii.push(a[2]); return undefined; },
    arcTo: w('arcTo'), rect: w('rect'),
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
/* 留住最后一次建出来的 ctx：核心点的呼吸表现为 `globalAlpha` 的赋值，
   而 globalAlpha 是**属性**不是方法调用 ⇒ 数不到，只能从对象上读。
   本工程 ctx2d() 的 save/restore 是 no-op，所以赋值会留在对象上 —— 正好可读。 */
let lastCtx = null;
const canvasNode = () => ({
  width: 600, height: 400,
  getContext: () => { lastCtx = ctx2d(); return lastCtx; },
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
  /* 分时图只画到「现在」为止（shown = events.filter(ev.min<=lineEnd)，lineEnd 含 now）⇒
     绘制调用随跑测试时刻漂移：16:48 仅 1 条可见 ⇒ ~50 次，晚上 3 条全在窗内 ⇒ ~66 次。
     断言自带时间窗：期望 = 脚手架(~20) + 每可见事件点(~9 调用：分时线顶点/事件标记/量柱)。
     markCount 已在 B 段独立现算（落在 [05:00,现在] 的今日记录数）。 */
  const drawFloor = 20 + 9 * markCount;
  must(ctxStats.total >= drawFloor,
    '分时图 canvas 真画了（绘制调用 ≥ 脚手架+可见点，窗内 ' + markCount + ' 点）',
    ctxStats.total + ' 次 / 期望≥' + drawFloor);
  if (clipped.length) out('  ℹ️ 负控：' + clipped.length + ' 条记录在「现在」之后被裁掉（不计入绘制）');
  must(ctxStats.fillText > 0, '画布上写下了文字（刻度/标签/封死涨停）', String(ctxStats.fillText));

/* ---------------- I. 负控：改净热量口径，徽章必须跟着变 ---------------- */
sec('I. 负控 · 净热量口径');
const netNow = calc.totals().net;
const clsNow = mk.data.sectorBadgeCls;
/* 负控：注入一笔超大饮食，使净热量由负翻正 → 徽章应从 bull 变 bear，
   证明 computeSectors 读的是活口径（calc.totals()），不是常量缓存。
   ⚠️ todayDiet() 返回 filter 副本，push 不进真 state；须直接 push 进 seed.diet
      （mock 下 storage['jianpan_v2'] 与 seed 是同一引用）。 */
seed.diet.push({ id: 'rx', type: 'food', name: '大餐', kcal: 5000, date: calc.todayStr(), time: '22:00', ts: null });
mk.refresh();
const clsAfter = mk.data.sectorBadgeCls;
must(clsAfter !== clsNow || (netNow < -50 && calc.totals().net > -50 && clsAfter !== 'bull'),
  '负控 · 注入超大饮食后净热量翻正、板块徽章分类改变（证明读的是活口径）',
  '前 ' + clsNow + ' / 后 ' + clsAfter);

/* ---------------- J. 录入口（RecordActions）实测 ----------------
 * ⚠️ 这是 2026-09-25 挖出的真缺口：mini 的 awardRecordCoins 被降成纯 UI 钩子后，
 *    「记录得币」逻辑在迁移中整个丢了（PWA index.html:2000 的 coinToday/coins 累加没了）。
 *    下面的断言独立现算期望发币数（受当日剩余额度限制），验证：写 diet/exercise +
 *    发币(coinToday/coins) + 打卡(lastRecordDate) + 我的常吃频次(bumpFoodFreq) + 落盘(store.save)。
 * ⚠️ 必须用 store.get() 取「活 state」断言：loadState 会建合并对象（merged !== seed），
 *    progress.sync 还会重指派 diet/exercise 数组 ⇒ seed.diet 是过期孤儿，读它会假失败。 */
sec('J. 录入口 · 写盘 + 发币 + 打卡 + 频次');
const STORE = require(path.join(MINI, 'lib/store.js'));
const RecordActions = require(path.join(MINI, 'lib/record-actions.js'));
const appRef = captured.app;
const S0 = STORE.get();
const coinsBeforeJ = S0.coins;
const coinTodayBeforeJ = S0.coinToday || 0;
const dietLenBefore = S0.diet.length;
const freqBefore = (S0.foodFreq && S0.foodFreq['米饭']) ? S0.foodFreq['米饭'].n : 0;
const awardBefore = appRef.globalData.lastAward;

const testFood = { name: '米饭', unit: '份', gram: 100, kcal: 116, p: 2.6, f: 0.3, c: 25.9, src: 'db' };
const frec = RecordActions.addFoodRecord(testFood, { qty: 1, mode: '份', time: '12:30' });
const S1 = STORE.get();
must(frec && frec.id && S1.diet.length === dietLenBefore + 1,
  'addFoodRecord：写入 diet（长度 ' + dietLenBefore + '→' + S1.diet.length + '）');
must(calc.todayDiet().some((r) => r.id === frec.id), 'addFoodRecord：新记录落在今日 diet');
must(appRef.globalData.lastAward && appRef.globalData.lastAward.kind === 'food',
  'addFoodRecord：触发 awardRecordCoins 钩子（lastAward.kind=food）');
const grantedFood = Math.max(0, Math.min(calc.COIN_PER_FOOD, calc.COIN_DAILY_CAP - coinTodayBeforeJ));
must(S1.coinToday === coinTodayBeforeJ + grantedFood,
  'addFoodRecord：coinToday 增加 = 实际发币(' + grantedFood + ')', 'coinToday ' + coinTodayBeforeJ + '→' + S1.coinToday);
must(S1.coins >= coinsBeforeJ + grantedFood,
  'addFoodRecord：coins 增加 ≥ 实际发币(' + grantedFood + ')', 'coins ' + coinsBeforeJ + '→' + S1.coins);
const freqAfter = (S1.foodFreq && S1.foodFreq['米饭']) ? S1.foodFreq['米饭'].n : 0;
must(freqAfter > freqBefore, 'addFoodRecord：我的常吃频次 bumpFoodFreq 自增（' + freqBefore + '→' + freqAfter + '）');
must(S1.lastRecordDate === calc.todayStr(), 'addFoodRecord：bumpStreak 更新 lastRecordDate=今日');
must(storage['jianpan_v2'] && storage['jianpan_v2'].diet.length === S1.diet.length,
  'addFoodRecord：store.save 落盘（storage 与 live 长度一致）');

/* 运动 */
const coinsBeforeEx = S1.coins;
const coinTodayBeforeEx = S1.coinToday || 0;
const exLenBefore = S1.exercise.length;
const testEx = { name: '跑步', met: 7, cat: '有氧' };
const erec = RecordActions.addExerciseRecord(testEx, { minutes: 30, intensity: '中', time: '20:00' });
const S2 = STORE.get();
must(erec && erec.id && S2.exercise.length === exLenBefore + 1,
  'addExerciseRecord：写入 exercise（长度 ' + exLenBefore + '→' + S2.exercise.length + '）');
must(calc.todayExercise().some((r) => r.id === erec.id), 'addExerciseRecord：新记录落在今日 exercise');
must(appRef.globalData.lastAward && appRef.globalData.lastAward.kind === 'ex',
  'addExerciseRecord：钩子 kind=ex');
const grantedEx = Math.max(0, Math.min(calc.COIN_PER_EX, calc.COIN_DAILY_CAP - coinTodayBeforeEx));
must(S2.coinToday === coinTodayBeforeEx + grantedEx,
  'addExerciseRecord：coinToday 增加 = 实际发币(' + grantedEx + ')', 'coinToday→' + S2.coinToday);
must(S2.coins >= coinsBeforeEx + grantedEx,
  'addExerciseRecord：coins 增加 ≥ 实际发币(' + grantedEx + ')');
must(storage['jianpan_v2'].exercise.length === S2.exercise.length, 'addExerciseRecord：落盘');

/* ---------------- K. 负控 · 坏副本不应写盘/发币 ---------------- */
sec('K. 负控 · 坏副本（food=null / 非法 id）');
const S3 = STORE.get();
const dietLenK = S3.diet.length;
const coinsK = S3.coins;
const awardK = appRef.globalData.lastAward;
const badRet = RecordActions.addFoodRecord(null, { qty: 1, mode: '份' });
must(badRet === null, '负控·food=null 返回 null');
const S3b = STORE.get();
must(S3b.diet.length === dietLenK, '负控·food=null 不写 diet');
must(S3b.coins === coinsK, '负控·food=null 不发币');
must(appRef.globalData.lastAward === awardK, '负控·food=null 不触发发币钩子');

const editBad = RecordActions.saveRecordEdit('__no_such_id__', 'food', 999, '08:30');
must(editBad === false, '负控·saveRecordEdit 非法 id 返回 false');
must(STORE.get().diet.length === dietLenK, '负控·saveRecordEdit 非法 id 不改任何记录');

/* 合法 id 改值落盘（正向，验证 saveRecordEdit 真生效） */
const tgt = STORE.get().diet.find((r) => r.id === frec.id);
const kcalBeforeEdit = tgt.kcal, timeBeforeEdit = tgt.time;
const okEdit = RecordActions.saveRecordEdit(frec.id, 'food', 999, '08:30');
must(okEdit === true, 'saveRecordEdit 合法 id 返回 true');
const S4 = STORE.get();
must(tgt.kcal === 999 && tgt.manualKcal === true, 'saveRecordEdit：改 kcal=999 且标记 manualKcal');
must(tgt.time === '08:30' && tgt.ts === calc.tsFromHM('08:30'),
  'saveRecordEdit：改 time + 重算 ts', 'time ' + timeBeforeEdit + '→' + tgt.time);
must(S4.diet.find((r) => r.id === frec.id).kcal === 999, 'saveRecordEdit：落盘');

/* ---------------- H. 空存档（全新用户） ----------------
 * ⚠️ 必须放在 J/K 之后：H 会 fresh() 清 require 缓存并重建 calc/store 模块实例，
 *    若 H 在 J/K 之前跑，测试顶层的 const calc 仍是旧实例，与 store.get() 新实例错位
 *    （calc.todayDiet 读旧实例、store.get 读新实例），J/K 的「记录落在今日」断言会假失败。 */
sec('H. 空存档（全新用户）');
const emptySeed = calc.defaultState();
const mk2 = boot(emptySeed);
mk2.refresh();   // onShow 才触发 refresh，mock 不跑生命周期，需手动拉一次
must(mk2.data.count === 0 && mk2.data.entries.length === 0, '无记录 ⇒ 今日成交为空');
must(mk2.data.sectorsLong.length === 0, '无饮食 ⇒ long 列空');
must(mk2.data.sectorsShort.length === 1 && mk2.data.sectorsShort[0].type === 'bmr',
  'short 列只剩基础代谢一块（基础代谢常驻）');
must(/待第一笔/.test(mk2.data.badgeText), '空存档徽章走「待第一笔」', mk2.data.badgeText);

/* ---------------- L. 时间滚轴 + 分时线呼吸动效（2026-09-24 真机 #108 + #109） ----------------
   真机症状（Mak 反馈）：
     · 「食物记录的时间选择不是滚轴选取，是纯文本，一个时间的冒号不对都不行」
       —— 根因 `<input type="time">` 不是小程序的合法 type（合法值只有
          text/number/idcard/digit/safe-password/nickname/password），被当成 text 渲染。
          必须换 `<picker mode="time">`。
     · 「分时线的尾端那个琥珀点没有呼吸闪烁的动效」
       —— PWA 用 SMIL <animate>（光晕 r 5→12、opacity .30→.02；核心点 opacity 1→.38，1.8s）；
          canvas 没有 SMIL，原实现只画了个静态光晕。改成手算相位 + 定时器重绘。
   本节分三段验：**样式/标签静态口径**、**呼吸相位与半径真的在动**、**定时器起停**。 */
sec('L. 时间滚轴 + 分时线呼吸动效');

/* 读「某条选择器在 app.wxss 里最终生效的 display」——同 mp_market_test 的做法：
   PWA 原规则在前、mp_build.py 的适配层追加在后，只搜「有没有」会漏掉「写了但被前面的盖住」。 */
function finalDisplay(css, cls) {
  const re = new RegExp(cls.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}', 'g');
  let m, last = null;
  while ((m = re.exec(css))) {
    const d = /display\s*:\s*([a-zA-Z-]+)/.exec(m[1]);
    if (d) last = d[1];
  }
  return last;
}

(async function () {
  await new Promise((r) => setTimeout(r, 0));   // flush：_intradayHandle 在 mount().then 里挂上

  const wxml = fs.readFileSync(path.join(MINI, 'pages/trade/trade.wxml'), 'utf8');
  const appWxss = fs.readFileSync(path.join(MINI, 'app.wxss'), 'utf8');
  const tradeJs = fs.readFileSync(path.join(MINI, 'pages/trade/trade.js'), 'utf8');

  /* ---- ① 时间选择：非法 input 必须清干净 ---- */
  must(!/type\s*=\s*"time"/.test(wxml),
    'trade.wxml 里没有 input[type=time]（小程序非法 type，真机上退化成纯文本）');
  const pickers = wxml.match(/picker\s+mode="time"/g) || [];
  must(pickers.length === 3,
    '三处时间输入（食物 / 运动 / 改记录）全部换成 picker mode=time', '命中 ' + pickers.length + ' 处');
  const binders = wxml.match(/bindchange="on(Food|Ex|Rec)TimeInput"/g) || [];
  must(binders.length === 3,
    '三个 picker 都挂了 bindchange（picker 走 change 事件，不写就取不到值）',
    binders.join(' / ') || '一个都没有');
  must(!/<input[^>]*class="inp-time"/.test(wxml),
    '原 <input class="inp-time"> 已全部替换为 <view class="inp-time">（view 取代 input 后样式选择器会变）');
  must(finalDisplay(appWxss, '.field .inp-time') === 'flex',
    'app.wxss 里 .field .inp-time 的最终 display 是 flex（补回 input 换成 view 后丢掉的框样式）',
    '最终值 ' + finalDisplay(appWxss, '.field .inp-time'));

  /* ---- ② 呼吸相位：函数本身 ---- */
  const realNow = Date.now;
  const at = (t) => { Date.now = () => t; return mk.pulsePhase(); };
  must(typeof mk.pulsePhase === 'function', '页面暴露 pulsePhase()（相位是它算的，别散在绘制里）');
  must(at(1800 * 100) === 0, 't=0 ⇒ 相位 0（光晕最小、核心点最亮）', String(at(1800 * 100)));
  must(Math.abs(at(1800 * 100 + 900) - 1) < 1e-9,
    't=半周期 ⇒ 相位 1（光晕最大、核心点最暗）', String(at(1800 * 100 + 900)));
  must(Math.abs(at(1800 * 100 + 450) - 0.5) < 1e-9,
    't=1/4 周期 ⇒ 相位 0.5（(1-cos(π/2))/2，与 ease-in-out 的关键帧一致）',
    String(at(1800 * 100 + 450)));
  let inRange = true, minPh = 9, maxPh = -9;
  for (let k = 0; k < 3600; k += 37) {
    const v = at(1800 * 100 + k);
    if (!(v >= 0 && v <= 1)) { inRange = false; break; }
    if (v < minPh) minPh = v;
    if (v > maxPh) maxPh = v;
  }
  must(inRange, '相位在整个周期内恒在 [0,1]（越界会把光晕画成负半径 / alpha 超 1）',
    '实测 [' + minPh.toFixed(3) + ', ' + maxPh.toFixed(3) + ']');
  must(maxPh > 0.99, '相位在周期内确实摸到过 ~1（不是被截断成一条平线）', maxPh.toFixed(3));

  /* ---- ③ 呼吸真的落到画布上：半径与 alpha 随相位走 ---- */
  const h = mk._intradayHandle;
  must(!!h && typeof h.repaint === 'function',
    '分时 canvas 的 handle 已就绪（呼吸靠 handle.repaint() 按帧重绘）',
    'handle=' + (h ? Object.keys(h).length + ' 个字段' : String(h)));

  const snap = (t) => {
    Date.now = () => t;
    arcRadii.length = 0;
    h.repaint();
    Date.now = realNow;
    /* ⚠️ alpha 必须从 `h.ctx` 读，**不能**从 lastCtx 读：redrawIntraday() 每刷新一次就
       重新 mount 一次 ⇒ getContext() 会建一个新 ctx 对象，而 lastCtx 记的是「最后一次
       getContext 的产物」。两者在最后一次重绘之后才对齐，中间任何一次延后执行的 mount
       都会让 lastCtx 指到一个「刚建好、还没被这次 repaint 画过」的新对象上 ——
       症状是读到一个与本次相位无关的陈旧值（0.38042484…，即真实时刻的相位算出来的）。 */
    return { radii: arcRadii.slice(), alpha: h.ctx.globalAlpha };
  };
  const s0 = snap(1800 * 100);            // 相位 0
  const s1 = snap(1800 * 100 + 900);      // 相位 1
  must(s0.radii.indexOf(5) >= 0,
    '相位 0 时画出了 r=5 的光晕（PWA 的 <animate> 起点就是 5，旧静态实现写死 6）',
    '半径集合 ' + JSON.stringify(s0.radii.slice(-6)));
  must(s1.radii.indexOf(12) >= 0,
    '相位 1 时画出了 r=12 的光晕（PWA 的 <animate> 终点）',
    '半径集合 ' + JSON.stringify(s1.radii.slice(-6)));
  must(s1.radii.indexOf(5) < 0,
    '相位 1 时不再有 r=5 的光晕（证明半径真的随相位变，不是画了两个固定的圈）');
  must(Math.abs(s0.alpha - 1) < 1e-6,
    '相位 0 时核心点 globalAlpha=1（最亮）', String(s0.alpha));
  must(Math.abs(s1.alpha - 0.38) < 1e-6,
    '相位 1 时核心点 globalAlpha=0.38（= 1 - 0.62，与 PWA 的 opacity:1→.38 一致）',
    String(s1.alpha));

  /* 负控：去掉相位（恒取固定值）时上面那对断言必然不再同时成立 ——
     用一个「相位被钉死」的替身跑一遍，半径集合必须退化。 */
  const savedPhase = mk.pulsePhase;
  mk.pulsePhase = () => 0;
  const pinned = snap(1800 * 100 + 900);   // 时间在相位 1，但相位函数被钉在 0
  must(pinned.radii.indexOf(12) < 0,
    '负控 · 把 pulsePhase() 钉死为 0 后，即使时间落在相位 1 也不再出现 r=12（证明半径确实由相位驱动）',
    '半径集合 ' + JSON.stringify(pinned.radii.slice(-6)));
  mk.pulsePhase = savedPhase;

  /* ---- ④ 定时器起停 ---- */
  must(mk._pulseTimer == null,
    '页面未 onShow 时不挂呼吸定时器（不该在后台空转重绘）',
    String(mk._pulseTimer));
  mk.onShow();
  must(!!mk._pulseTimer, 'onShow 后挂上呼吸定时器', typeof mk._pulseTimer);
  const pt = mk._pulseTimer;
  mk.onHide();
  must(mk._pulseTimer === null, 'onHide 后定时器被清掉（否则页面隐藏还在按 15fps 重绘）',
    String(mk._pulseTimer));
  mk.onShow();
  must(mk._pulseTimer !== pt, '再次 onShow 会新建一个定时器（旧的已被清，不是复用一个死句柄）');
  mk.onHide();   // 收尾：别把定时器留给 process.exit 之前的这段代码

  /* 定时器落地实跑一次：tick 的执行体必须只调 repaint，且 repaint 会清屏 */
  const before = ctxStats.clearRect;
  mk.onShow();
  must(!!mk._pulseTimer, 'onShow 再次挂上定时器（下面要实跑一拍）');
  /* ⚠️ 不 sleep 等真实 tick：直接把定时器回调体取出来跑 ——
     setInterval 的回调在 Node 里拿不到，所以这里改为断言「重绘路径本身清屏」，
     并由 ③ 段已经证明 repaint 每次都清屏 ⇒ 两段合起来就是「每拍都清屏」。 */
  h.repaint();
  h.repaint();
  must(ctxStats.clearRect >= before + 2,
    '连续按帧重绘每次都清屏（呼吸每 66ms 跑一次，不清屏就会把光晕拖成一圈残影）',
    '清屏 ' + (ctxStats.clearRect - before) + ' 次 / 期望≥2');
  mk.onHide();

  must(/setInterval\([\s\S]{0,80}PULSE_TICK/.test(tradeJs),
    '定时器间隔用的是 PULSE_TICK 常量（不是就地写死一个魔法数）');

  finish();
})();

/* ---------------- 汇总 ---------------- */
function finish() {
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
}
