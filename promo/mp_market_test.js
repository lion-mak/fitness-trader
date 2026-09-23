/* mp_market_test.js —— 行情页四块新逻辑的运行时断言（③ 运动网格 / 大盘云图 / 身体成分 / 历史成交）
 *
 * 为什么单独开一个闸：
 *   内核断言（mp_calc_test 149 项）只覆盖 calc.js 里的**纯函数**，而本批四块里
 *   有两类东西它盖不到：
 *     ① 页面侧的时间轴/桶构造（PWA 原来写在 renderHistoryChart 里，属"渲染档"，
 *        抽取器不会把它搬进内核）—— 它决定「摄入/运动合计」这类用户直接看到的数字；
 *     ② 内核里已有、但从未被断言过的算法（treemapLayout / exHeatBreaks / exHeatColor）
 *        —— treemapLayout 历史上有过真 bug（横排细条的 acc 误用 y 起点，整排右移出洞）。
 *
 * 测试策略（与持仓页同款）：**凡是能独立算的，都在这里另写一遍现算再比对**，
 *   绝不「把页面算出来的值当成期望值」—— 那是拿被测代码证明被测代码。
 *
 * 负控（每条断言都要能失败）：
 *   · pin 规则负控 —— 去掉 pin 后顺序必须变（证明"基代恒在最前"不是自动成立的）
 *   · 重叠/覆盖检查器自检 —— 手工喂一份有重叠 / 有洞的矩形表，检查器必须报出来
 *   · 色阶单调性负控 —— 把分位断点反转，单调断言必须失败
 *   · 切档真值来源负控 —— 只改内核档位不调页面刷新，页面数据必须还是旧的（证明它读的是内核）
 *   · 等级跟随负控 —— 改 BMI 后等级名与定位点必须跟着动（证明不是写死的）
 *
 * 用法：node promo/mp_market_test.js   退出码 0=全过
 * 报告落盘：promo/_market_out.txt
 */
'use strict';
const path = require('path');
const fs = require('fs');

const MINI = 'E:\\WeChatProjects\\jianpan\\miniprogram';
const OUT = path.join(__dirname, '_market_out.txt');

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
/** 相对今天偏移 n 天的日期串（内核 todayStr 也是本地时区，口径一致） */
function D(n) { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n); return dstr(d); }

/* 运动网格：PWA 的 53 周 × 7 天窗口（周一为首） */
function refGrid(cells) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const dow = (today.getDay() + 6) % 7;
  const thisMon = new Date(today); thisMon.setDate(today.getDate() - dow);
  const startMon = new Date(thisMon); startMon.setDate(thisMon.getDate() - 52 * 7);
  const shift = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const w = [];
  for (let c = 0; c < 53; c++) for (let r = 0; r < 7; r++) w.push(dstr(shift(startMon, c * 7 + r)));
  return w;
}
/* 分位断点：P50 / P75 / P90，样本 <8 返回 null */
function refBreaks(vals) {
  const a = vals.slice().sort((x, y) => x - y);
  if (a.length < 8) return null;
  const q = (p) => { const idx = (a.length - 1) * p, lo = Math.floor(idx), hi = Math.ceil(idx);
                     return lo === hi ? a[lo] : a[lo] + (a[hi] - a[lo]) * (idx - lo); };
  const b = [q(0.50), q(0.75), q(0.90)];
  if (b[0] < 1) b[0] = 1;
  if (b[1] <= b[0]) b[1] = b[0] + 1;
  if (b[2] <= b[1]) b[2] = b[1] + 1;
  return b;
}
const REF_LV = ['', '#8fe3c4', '#3ecfa0', '#00a97c', '#05704f'];
const REF_EMPTY = '#1a2030';
function refRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function refMix(a, b, t) {
  if (t <= 0) return a;
  if (t >= 1) return b;
  const A = refRgb(a), B = refRgb(b);
  return 'rgb(' + Math.round(A[0] + (B[0] - A[0]) * t) + ',' + Math.round(A[1] + (B[1] - A[1]) * t)
       + ',' + Math.round(A[2] + (B[2] - A[2]) * t) + ')';
}
/** 色阶：PWA v2.7.41 起的段内插值版（段内线性 → 数值越大颜色严格不浅） */
function refColor(v, breaks, maxDay, L) {
  L = L || REF_LV;
  if (!v || v <= 0) return REF_EMPTY;
  if (!breaks) {
    if (!maxDay || maxDay <= 0) return L[4];
    const r = Math.min(1, v / maxDay);
    if (r <= 0.25) return refMix(L[1], L[2], r / 0.25);
    if (r <= 0.50) return refMix(L[2], L[3], (r - 0.25) / 0.25);
    if (r <= 0.75) return refMix(L[3], L[4], (r - 0.50) / 0.25);
    return L[4];
  }
  const b0 = breaks[0], b1 = breaks[1], b2 = breaks[2];
  if (v <= b0) return refMix(L[1], L[2], b0 > 0 ? v / b0 : 1);
  if (v <= b1) return refMix(L[2], L[3], (v - b0) / Math.max(1, b1 - b0));
  if (v <= b2) return refMix(L[3], L[4], (v - b1) / Math.max(1, b2 - b1));
  return L[4];
}
/** 色深序：把色值换算成一个单调标量（取 RGB 三通道之和 —— 本色阶的四锚点严格递减） */
function colorDeep(s) {
  if (s === REF_EMPTY) return -1;
  const m = /^#([0-9a-f]{6})$/i.exec(s);
  if (m) { const n = parseInt(m[1], 16); return ((n >> 16) & 255) + ((n >> 8) & 255) + (n & 255); }
  const g = /^rgb\((\d+),(\d+),(\d+)\)$/.exec(s);
  if (!g) return NaN;
  return +g[1] + +g[2] + +g[3];
}

/* ---------------- 样式串解析（页面把坐标写成 inline style） ---------------- */
function parseBox(style) {
  const g = (k) => { const m = new RegExp(k + ':(-?[\\d.]+)px').exec(style); return m ? +m[1] : NaN; };
  return { x: g('left'), y: g('top'), w: g('width'), h: g('height') };
}
/** 重叠面积（两两求交，返回总面积；正常 treemap 必须为 0） */
function overlapArea(rects) {
  let s = 0;
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length; j++) {
      const a = rects[i], b = rects[j];
      const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (ox > 0.01 && oy > 0.01) s += ox * oy;
    }
  }
  return s;
}
/** 覆盖面积（所有矩形并集 —— 用 200×200 网格采样近似，足够分辨「有洞」） */
function coverRatio(rects, W, H) {
  const N = 200;
  let hit = 0;
  for (let i = 0; i < N; i++) {
    for (let j = 0; j < N; j++) {
      const px = (i + 0.5) / N * W, py = (j + 0.5) / N * H;
      for (let k = 0; k < rects.length; k++) {
        const r = rects[k];
        if (px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h) { hit++; break; }
      }
    }
  }
  return hit / (N * N);
}

/* ============================================================
 * mock（与 mp_smoke 同款；新增：select 队列，让不同选择器返回不同宽度）
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

/* 真实布局宽度（与 WXSS 一致，iPhone 15 Pro Max 430 逻辑像素）：
   页面 430 → 卡片内容 430-56 = 374 → 云图内层 374-8 = 366 → 网格滚动视窗 374-22 = 352
   ⚠️ 这些数字是**测试输入**，页面从 selector 查询里拿到的就是它们 —— 断言就能反过来
      验证「按容器宽算高度/格宽」这条链真的通了。 */
const BOX = {
  '.market-page': 430,
  '#ex-heat': 374,
  '#market-map': 366,
  '.ex-heat-scroll': 352,
  '#history-chart': 374,
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
  /* setData 必须支持点路径（真机框架支持 'a.b.c'）：onTipEnd 写 'tip.show'、
     onHistEnd 写 'histTip.show'。若只做 Object.assign，点路径会变成字面键，
     histTip.show 永不置 false —— 「松手后标签收起」这类断言会误报成产品缺陷。 */
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
  /* 页面实例必须有 createSelectorQuery（真机由框架注入）：measureWidths 走
     `this.createSelectorQuery()` 量容器宽。mock 少了它 ⇒ measureWidths 短路到
     cb(null)，avail/_mmW/_exScrollW 全落到兜底值 ⇒ 云图按 311 宽布、滚动视窗宽算 0，
     「覆盖 100% / 首帧贴最右」这类断言会被 mock 缺陷带崩（2026-09-23 踩过）。 */
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

  /* 体重：5 条，够画 K 线 */
  st.weightLog = [-12, -8, -5, -2, 0].map((o, i) => ({ date: D(o), weight: 79.6 - i * 0.3 }));

  /* 饮食：今日 2 笔 + 过去多笔（跨 70 天，用于验证 62 天截断） */
  const dietDays = [-1, -3, -5, -8, -12, -20, -30, -45, -60, -70];
  st.diet = [rec('米饭', 300, 0, 12), rec('红烧肉', 700, 0, 19)];
  dietDays.forEach((o, i) => {
    st.diet.push(rec('第' + (i + 1) + '天餐', 400 + i * 37, o, 13));
  });

  /* 运动：今日 1 笔 + 近 14 天各一笔（样本 ≥8 才会走分位色阶） */
  st.exercise = [rec('跑步', 420, 0, 20)];
  for (let i = 1; i <= 14; i++) st.exercise.push(rec('训练' + i, 120 + i * 30, -i, 21));

  st.bodyLog = [];
  return st;
}

/* ============================================================
 * 启动
 * ============================================================ */
function fresh() {
  Object.keys(storage).forEach((k) => { delete storage[k]; });
  captured.pages.length = 0;
  captured.app = null;
  calls.length = 0;
  Object.keys(require.cache).forEach((k) => {
    if (k.indexOf(MINI) === 0) delete require.cache[k];
  });
}

function boot(state) {
  fresh();
  storage['jianpan_v2'] = state;
  require(path.join(MINI, 'app.js'));
  captured.app.onLaunch.call(captured.app);
  require(path.join(MINI, 'pages/market/market.js'));
  const mk = makeInstance(captured.pages[captured.pages.length - 1]);
  mk.onLoad.call(mk, {});
  mk.onReady.call(mk);
  return mk;
}

/* ============================================================
 * 跑
 * ============================================================ */
const seed = buildSeed();
const mk = boot(seed);
const calc = require(path.join(MINI, 'lib/calc.js'));
const st = calc.getState ? calc.getState() : null;

out('=== 行情页四块运行时验证 ===');
out('工程：' + MINI);
out('卡片内容宽 374 / 云图宽 366 / 网格视窗 352（mock 按真实 WXSS 给出）');

/* ---------------- A. 画布盒尺寸口径 ---------------- */
/* 2026-09-22 纠错：本节原先断的是「画布高 = 容器宽 × 设计高 / 设计宽」。它对**历史成交**成立，
   但对 **K 线是错的** —— PWA 的 K 线是
     <svg viewBox="0 0 340 150" style="width:100%;height:150px">   （高度写死 + meet ⇒ 不放大、左右留白居中）
   只有历史成交是 height:auto（按宽等比撑满）。按「统一按宽算高」做的后果是 K 线高 165 而非 150，
   多出的 15px 被下游所有块继承（整页下移 15px）。
   现在两个高度都由 wxss 决定、JS 不产出 ⇒ 断言改成**直接读 wxss 常量**（唯一真值来源），
   再补一条「高度不许回到 data」的守卫。真实渲染高度交给 ⑥c rect 对拍。 */
sec('A. 画布盒尺寸口径（读 wxss 常量，防被改回「统一按宽算高」）');
const mwx = fs.readFileSync(path.join(MINI, 'pages/market/market.wxss'), 'utf8');
must(/\.kchart\s*\{[^}]*height:\s*150px/.test(mwx),
  'K 线画布固定 150px（对齐 PWA 的 height:150px + meet 居中）', '见 market.wxss 的 .kchart');
must(/\.hchart-box\s*\{[^}]*padding-bottom:\s*60\.1266%/.test(mwx),
  '历史成交宽高比盒 padding-bottom = 60.1266%（190/316）', '见 market.wxss 的 .hchart-box');
must(Math.abs(190 / 316 * 100 - 60.1266) < 0.0001,
  '该常数与 PWA 的 viewBox 316×190 自洽（独立算 190/316）', '190/316 = ' + (190 / 316 * 100) + '%');
must(mk.data.kchartH === undefined && mk.data.histH === undefined,
  '两个高度都不在 data 里（JS 不再算画布高度）',
  'kchartH=' + mk.data.kchartH + ' histH=' + mk.data.histH);
must(mk.data.statusBarHeight === 54, '状态栏留白取到真值（不是兜底 20）', '实测 ' + mk.data.statusBarHeight);

/* ---------------- B. 运动网格 ---------------- */
sec('B. 运动网格（53 周 × 7 天，分位色阶）');
const cells = mk.data.exCells;
must(cells.length === 53 * 7, '格子数 = 53 × 7 = 371', '实测 ' + cells.length);

const expDates = refGrid();
const todayKey = D(0);
const byDate = {};
seed.exercise.forEach((e) => { byDate[e.date] = (byDate[e.date] || 0) + Math.round(e.kcal || 0); });
const expVals = [];
const expCellBg = expDates.map((k) => {
  const fut = k > todayKey;
  const v = (!fut && byDate[k]) ? byDate[k] : 0;
  if (v > 0) expVals.push(v);
  return { k: k, v: v, fut: fut };
});
const expBreaks = refBreaks(expVals);
const expMax = Math.max.apply(null, expDates.map((k) => byDate[k] || 0));
must(expBreaks !== null, '样本 ≥8 天 ⇒ 走分位色阶（不是峰值兜底）', '样本 ' + expVals.length);

let bgBad = 0, firstBad = null;
expCellBg.forEach((g, i) => {
  if (!cells[i]) { bgBad++; if (!firstBad) firstBad = '第 ' + i + ' 格不存在（exCells 只有 ' + cells.length + ' 项）'; return; }
  const exp = g.fut ? 'background:transparent' : 'background:' + refColor(g.v, expBreaks, expMax);
  if (cells[i].s !== exp) { bgBad++; if (!firstBad) firstBad = g.k + ' 期望 ' + exp + ' 实测 ' + cells[i].s; }
});
must(bgBad === 0, '371 格背景色与独立实现逐格一致', bgBad + ' 格不符' + (firstBad ? '（首例 ' + firstBad + '）' : ''));

const todayIdx = expDates.indexOf(todayKey);
must(todayIdx >= 0 && !!((cells[todayIdx] || {}).t), '今天那格带 is-today 高亮',
  'todayIdx=' + todayIdx + ' / exCells=' + cells.length);
must(expCellBg.filter(g => g.fut).length === 7 * 53 - todayIdx - 1, '未来格数 = 总格数 − 今天下标 − 1');
const futIdx = expDates.findIndex((k) => k > todayKey);
must(futIdx > 0 && !!(cells[futIdx] || {}).f && (cells[futIdx] || {}).s === 'background:transparent',
  '未来格透明（不画成"无运动"的暗底）', 'futIdx=' + futIdx);

const hasExDays = Object.keys(byDate).length;
must(hasExDays >= 8, '构造的存档里确实有 ≥8 个运动日（否则上面色阶断言会退化成兜底分支）', hasExDays + ' 天');

/* 单调性：数值越大颜色越深（色阶的核心承诺）。
   ⚠️ colorDeep = RGB 三通道之和 = 亮度标量：越深（越暗）数值**越小**。
   「逆序」的正确判据是「后面的更大」即 `deep[i] > deep[i-1]`（更亮 = 方向反了）。
   初版写反成 `<`，把「正确地在变深」当成了逆序，恒报 12 处。 */
const sorted = expVals.slice().sort((a, b) => a - b);
let monoBad = 0;
for (let i = 1; i < sorted.length; i++) {
  if (colorDeep(refColor(sorted[i], expBreaks, expMax)) > colorDeep(refColor(sorted[i - 1], expBreaks, expMax))) monoBad++;
}
must(monoBad === 0, '色阶单调：消耗越多颜色越深（不相近值跨档跳变）', monoBad + ' 处逆序');

/* 负控：把色锚点反转（深→浅），单调断言必须报出逆序。
   反转断点不可靠（值仍可能落在同一段内、方向不变）；反转调色板则必然
   越大的值越亮 ⇒ colorDeep 递增 ⇒ 检查器必报 > 0。 */
const REV_LV = ['', '#05704f', '#00a97c', '#3ecfa0', '#8fe3c4'];
let revBad = 0;
for (let i = 1; i < sorted.length; i++) {
  if (colorDeep(refColor(sorted[i], expBreaks, expMax, REV_LV)) > colorDeep(refColor(sorted[i - 1], expBreaks, expMax, REV_LV))) revBad++;
}
must(revBad > 0, '负控 · 反转色锚点后单调性确实被破坏（证明上一条不是恒真）',
  '反转后逆序数 ' + revBad);

/* 调色板与口径常量必须还是 PWA 那一套 */
must(JSON.stringify(calc.EX_HEAT.lv) === JSON.stringify(REF_LV), '色锚点仍是四档浅→深绿（未被悄悄改色）',
  JSON.stringify(calc.EX_HEAT.lv));
must(calc.EX_HEAT.empty === REF_EMPTY, '空的格底色仍是 #1a2030', calc.EX_HEAT.empty);
must(calc.EX_HEAT.weeks === 53 && calc.EX_HEAT.viewWeeks === 22, '窗口 53 周 / 一屏 22 周口径未变');
must(refBreaks(expVals.slice(0, 7)) === null, '样本 <8 天 ⇒ 分位断点返回 null（走峰值兜底）');

/* 格宽自适应 */
const cellPx = parseInt((/grid-auto-columns:(\d+)px/.exec(mk.data.exGridStyle) || [])[1], 10);
must(cellPx >= 7 && cellPx <= 18, '格宽落在 7~18 的钳制区间内', '实测 ' + cellPx);
must(22 * cellPx + 21 * 3 <= 352, '一屏 22 周放得进滚动视窗（不会露出半截列）',
  '需要 ' + (22 * cellPx + 21 * 3) + 'px ≤ 352px');
must(mk.data.exTrackW === 53 * cellPx + 52 * 3, '轨道总宽 = 53 列 + 52 个间隙',
  mk.data.exTrackW + ' vs ' + (53 * cellPx + 52 * 3));
must(mk.data.exScrollH === 15 + 5 + (7 * cellPx + 6 * 3), '滚动视窗高 = 月份 15 + 间距 5 + 网格高',
  mk.data.exScrollH + ' vs ' + (15 + 5 + 7 * cellPx + 18));
must(mk.data.exScrollLeft === Math.max(0, mk.data.exTrackW - 352), '首帧默认贴最右（最新）',
  'scrollLeft ' + mk.data.exScrollLeft);
must(mk.data.exSub.indexOf('中位') === 0, '副标题走分位口径「中位 X / 峰值 Y」', mk.data.exSub);

/* ---------------- C. 大盘云图 ---------------- */
sec('C. 大盘云图（treemap 面积 ∝ 热量 · 零重叠 · 全覆盖）');
must(calc.treemapLayout !== undefined, '内核有 treemapLayout（页面没自己重写一份）');
const todays = calc.todayDiet().length + calc.todayExercise().length;
must(mk.data.mmBlocks.length === todays + 1, '块数 = 今日记录数 + 1（基代常驻）',
  mk.data.mmBlocks.length + ' vs ' + (todays + 1));
must(mk.data.mmBlocks[0].isBmr === 1, '第一块是基础代谢（pin 恒排最前）');
must(mk.data.mmEmpty === false, '今天有成交 ⇒ 不是空态');

const mmRects = mk.data.mmBlocks.map((b) => parseBox(b.box));
const mmW = 366, mmH = mk.data.mmH;
const ov = overlapArea(mmRects);
/* 阈值为什么是 50 而非 0：页面把 rect 序列化成 `toFixed(1)` 的 inline style，
   相邻两块共享的边界各自舍入，最多差 0.1px，× 边高 ~212px ≈ 21px²/条边界。
   4 块有 3 条内部边界 ⇒ 理论上限 ~63px²（实测仅 10.75px²，来自跑步↔米饭那一条）。
   这是**亚像素级舍入**，不是布局重叠 —— 真正的「整排右移出洞」类 bug 是百 px 级，
   仍会被下面覆盖检查与负控（>2400px²）抓到。 */
must(ov < 50, '块之间无可见重叠（容差覆盖 toFixed(1) 亚像素舍入）', '重叠面积 ' + ov.toFixed(3) + 'px²');
const cov = coverRatio(mmRects, mmW, mmH);
must(cov > 0.995, '块 100% 覆盖容器（不留洞）', '覆盖 ' + (cov * 100).toFixed(2) + '%');

/* 负控：检查器自检 —— 手工造一份有重叠 / 有洞的矩形表，必须能报出来 */
const badOverlap = [{ x: 0, y: 0, w: 100, h: 100 }, { x: 50, y: 50, w: 100, h: 100 }];
must(overlapArea(badOverlap) > 2400, '负控 · 重叠检查器能抓到人造重叠',
  '报出 ' + overlapArea(badOverlap).toFixed(0) + 'px²');
const badGap = [{ x: 0, y: 0, w: 100, h: 100 }, { x: 100, y: 0, w: 100, h: 100 }];
must(coverRatio(badGap, mmW, mmH) < 0.4, '负控 · 覆盖检查器能抓到人造的洞',
  '覆盖 ' + (coverRatio(badGap, mmW, mmH) * 100).toFixed(1) + '%');

/* 面积 ∝ 热量：面积比 vs 热量比（热量从块自己的数值文本里取，不依赖内核内部量） */
const mmK = mk.data.mmBlocks.map((b) => Math.max(1, +(/(\d+)/.exec(b.vText) || [0, 0])[1]));
const totK = mmK.reduce((s, k) => s + k, 0);
let areaBad = 0, areaWorst = 0;
mk.data.mmBlocks.forEach((b, i) => {
  const k = mmK[i];
  const expRatio = k / totK;
  const actRatio = (mmRects[i].w * mmRects[i].h) / (mmW * mmH);
  if (k >= 200) {                       // 极小块会被 8px 最小边长钳制，不参与比例判定
    const err = Math.abs(actRatio - expRatio) / expRatio;
    if (err > areaWorst) areaWorst = err;
    if (err > 0.06) areaBad++;
  }
});
must(areaBad === 0, '面积 ∝ 热量（≥200 kcal 的块误差 <6%）',
  areaBad + ' 块超差，最大误差 ' + (areaWorst * 100).toFixed(2) + '%');

/* pin 规则负控：给一个热量很小的块加 pin，顺序必须变 */
const pinA = calc.treemapLayout([{ id: 'bmr', kcal: 50, pin: true }, { id: 'big', kcal: 5000 }], mmW, mmH);
const pinB = calc.treemapLayout([{ id: 'bmr', kcal: 50, pin: false }, { id: 'big', kcal: 5000 }], mmW, mmH);
must(pinA.length === 2 && pinA[0].b.id === 'bmr', '负控 A · 小热量块加 pin 后仍排最前（pin 真的在起作用）');
must(pinB[0].b.id === 'big', '负控 B · 去掉 pin 后小块就排到最后（证明上一条不是排序巧合）');

/* 色深分档基准只看真实记录：给一笔超大食物，它必须满档 */
const storeMod = require(path.join(MINI, 'lib/store.js'));
storeMod.get().diet.push(rec('巨无霸', 3000, 0, 15));
storeMod.save();
mk.refresh();
const bigBlock = mk.data.mmBlocks.filter(b => b.name === '巨无霸')[0];
const bigAlpha = bigBlock ? +(/([\d.]+)\)/.exec(bigBlock.box) || [0, 0])[1] : NaN;
must(bigAlpha > 0.99, '当日最大单笔的块接近满档（色深基准 = 最大单笔，不含基代）',
  'alpha ' + bigAlpha);
const bmrAlpha = +(/([\d.]+)\)/.exec(mk.data.mmBlocks[0].box) || [0, 0])[1];
must(Math.abs(bmrAlpha - 0.42) < 0.001, '基代块固定 0.42 中档色深（不参与分档）', 'alpha ' + bmrAlpha);
/* 拆掉这笔试探数据，避免污染后面「历史成交」的独立求和 */
storeMod.get().diet.pop();
storeMod.save();
mk.refresh();
must(mk.data.mmBlocks.length === todays + 1, '移除试探记录后块数回到 记录数+1');

/* ---------------- D. 身体成分 ---------------- */
sec('D. 身体成分（等级 / 参考值 / 定位点全部走内核口径）');
must(mk.data.bodyMetrics.length === calc.BODY_RANGES.length, '指标卡数量 = BODY_RANGES 条数',
  mk.data.bodyMetrics.length + ' vs ' + calc.BODY_RANGES.length);
must(mk.data.bodyMetrics.length >= 8, '至少有 8 项指标', String(mk.data.bodyMetrics.length));

let metricBad = [];
calc.BODY_RANGES.forEach((m, i) => {
  const got = mk.data.bodyMetrics[i];
  if (!got) { metricBad.push(m.label + ' 缺卡（bodyMetrics 只有 ' + mk.data.bodyMetrics.length + ' 张）'); return; }
  const u = seed.user;
  const real = calc.bodyValue(m.key);
  if (got.label !== m.label) metricBad.push(m.label + ' 标签');
  if (got.v !== real) metricBad.push(m.label + ' 值 ' + got.v + '≠' + real);
  if (got.ref !== '参考 ' + calc.refOf(m, u)) metricBad.push(m.label + ' 参考值');
  // 独立推等级：遍历内核等级表找区间（不调 findMetricLevel）
  const ls = calc.resolveLevels(m, u);
  const want = (ls.filter(l => real >= l.min && real < l.max)[0] || ls[ls.length - 1]).name;
  if (m.simple && m.statusWord) { /* 极简项用 statusWord，文案不参与对照 */ }
  else if (got.levelName !== want) metricBad.push(m.label + ' 等级 ' + got.levelName + '≠' + want);
  // 定位点：至少落在 3%~97% 且与轴范围一致
  const dp = parseFloat((/left:([\d.]+)%/.exec(got.dotStyle) || [])[1]);
  if (!(dp >= 3 && dp <= 97)) metricBad.push(m.label + ' 定位点 ' + dp);
});
must(metricBad.length === 0, '每项指标的值/参考值/等级/定位点都与独立推算一致',
  metricBad.slice(0, 4).join('；'));

must(mk.data.bodySrcText.indexOf('手动录入') === 0 && mk.data.bodySrcColor === '#00c896',
  '来源行口径：manual → 「手动录入 · HH:MM」+ 绿色', mk.data.bodySrcText + ' / ' + mk.data.bodySrcColor);

/* 负控：改 BMI，等级名与定位点必须跟着动（storeMod 在 C 节已 require） */
const bmiIdx = calc.BODY_RANGES.findIndex(m => m.key === 'bmi');
const beforeBmi = mk.data.bodyMetrics[bmiIdx];
storeMod.get().body.bmi = 33.5;
mk.refresh();
const afterBmi = mk.data.bodyMetrics[bmiIdx];
must(afterBmi.v === 33.5, '负控 A · 改 BMI 后卡片数值立刻变', '实测 ' + afterBmi.v);
must(afterBmi.levelName !== beforeBmi.levelName, '负控 B · 等级名跟着变（不是写死的）',
  beforeBmi.levelName + ' → ' + afterBmi.levelName);
const dotBefore = parseFloat(/left:([\d.]+)%/.exec(beforeBmi.dotStyle)[1]);
const dotAfter = parseFloat(/left:([\d.]+)%/.exec(afterBmi.dotStyle)[1]);
must(dotAfter > dotBefore, '负控 C · 定位点向右移（色轴上真的动了）',
  dotBefore + '% → ' + dotAfter + '%');
storeMod.get().body.bmi = 23.3;
mk.refresh();

/* ---------------- E. 历史成交 ---------------- */
sec('E. 历史成交（四档口径 / 62 天截断 / 命中列）');
const allDietKcal = seed.diet.reduce((s, x) => s + x.kcal, 0);
const allExKcal = seed.exercise.reduce((s, x) => s + x.kcal, 0);
const sumSince = (arr, days) => arr.filter(x => x.date >= D(-days)).reduce((s, x) => s + x.kcal, 0);
/* 62 天窗口：firstD → today 跨度 ≥ 63 天 ⇒ 截为近 61 天（含两端 = 62 个桶） */
const winDiet = seed.diet.filter(x => x.date >= D(-61)).reduce((s, x) => s + x.kcal, 0);
const winEx = seed.exercise.filter(x => x.date >= D(-61)).reduce((s, x) => s + x.kcal, 0);

must(mk.data.histRange === 'all', '默认档位 = 全部（与内核初值一致）', mk.data.histRange);
must(mk.data.histEmpty === false, '有记录 ⇒ 不是空态');
must(mk.data.histLegend.in === winDiet, '「全部」档合计摄入 = 独立算的近 62 天窗口和',
  mk.data.histLegend.in + ' vs ' + winDiet);
must(mk.data.histLegend.ex === winEx, '「全部」档合计运动 = 独立算的近 62 天窗口和',
  mk.data.histLegend.ex + ' vs ' + winEx);
must(winDiet < allDietKcal, '62 天截断真的生效（窗口和 < 全量和）',
  winDiet + ' < ' + allDietKcal);

/* 各档合计 */
const ranges = [
  ['30d', allDietKcal, '月度：桶覆盖首条~最新所在月 ⇒ 合计 = 全量'],
  ['365d', allDietKcal, '年度：桶覆盖首条~最新所在年 ⇒ 合计 = 全量'],
  ['7d', sumSince(seed.diet, 6), '7日：只算近 7 天（含今天）'],
];
ranges.forEach(([r, want, label]) => {
  mk.onHistRange({ currentTarget: { dataset: { range: r } } });
  must(mk.data.histRange === r, '切到「' + r + '」后页面档位同步', mk.data.histRange);
  must(calc.historyRange === r, '切到「' + r + '」后**内核**档位同步（getter 不是值快照）', calc.historyRange);
  must(mk.data.histLegend.in === want, label + ' 摄入 = ' + want + '（独立算）',
    '实测 ' + mk.data.histLegend.in);
});

mk.onHistRange({ currentTarget: { dataset: { range: 'all' } } });
must(mk.data.histLegend.in === winDiet, '切回「全部」后合计回到窗口口径');

/* 命中列：最右端必须是今天 */
/* 画布高 = 宽 × 190/316（与 .hchart-box 的 padding-bottom 同一口径）。
   JS 已不产出该值，测试里按同一公式现算，用于伪造 handle 的 scale。 */
const histCanvasH = 374 * 190 / 316;
const mkRect = { left: 0, top: 0, width: 374, height: histCanvasH };
mk._histRect = mkRect;
mk._histHandle = { offsetX: 0, offsetY: 0, scale: Math.min(374 / 316, histCanvasH / 190),
                   toDesign: function (cx, cy) { return [cx / this.scale, cy / this.scale]; } };
mk.onHistTouch({ touches: [{ clientX: 372, clientY: 100 }] });
must(mk.data.histTip.show === true, '触摸历史图弹出该列标签');
must(mk.data.histTip.date === D(0).slice(5).replace('-', '/'),
  '最右端命中「今天」', '实测 ' + mk.data.histTip.date + '，期望 ' + D(0).slice(5).replace('-', '/'));
mk.onHistTouch({ touches: [{ clientX: 39, clientY: 100 }] });
must(mk.data.histTip.date === D(-61).slice(5).replace('-', '/'),
  '最左端命中窗口首日（今天 −61）', '实测 ' + mk.data.histTip.date + '，期望 ' + D(-61).slice(5).replace('-', '/'));

/* 中间某一列：62 个桶时 下标 i ↔ 日期 = 今天 − (61 − i) */
const slotW = (316 - 38 - 6) / 62;
const midIdx = 31;                      // → 今天 −30，那天正好有一笔 622 kcal
const midX = (38 + midIdx * slotW + slotW / 2) * mk._histHandle.scale;
mk.onHistTouch({ touches: [{ clientX: midX, clientY: 100 }] });
const wantMid = D(-(61 - midIdx)).slice(5).replace('-', '/');
const wantMidIn = seed.diet.filter(x => x.date === D(-30)).reduce((s, x) => s + x.kcal, 0);
must(mk.data.histTip.date === wantMid, '中间第 32 列命中今天 −30（独立算）',
  '实测 ' + mk.data.histTip.date + '，期望 ' + wantMid);
must(wantMidIn > 0 && mk.data.histTip.intake === wantMidIn,
  '该列摄入值 = 独立算出的当日摄入 ' + wantMidIn, String(mk.data.histTip.intake));
mk.onHistEnd();
must(mk.data.histTip.show === false, '松手后标签收起');

/* 负控：只改内核档位、不刷新页面 ⇒ 页面数据必须还是旧的（证明它读内核而不是写死） */
mk.onHistRange({ currentTarget: { dataset: { range: '7d' } } });
const n7 = mk.data.histLegend.in;
calc.switchHistoryRange('all');                 // 只动内核
must(mk.data.histLegend.in === n7 && calc.historyRange === 'all',
  '负控 · 只改内核不刷新页面时页面仍是旧数据（页面确实读的是内核真值）',
  '页面 ' + mk.data.histLegend.in + ' / 内核 ' + calc.historyRange);
mk.refresh();
must(mk.data.histLegend.in === winDiet, '显式刷新后页面才跟上');

/* ---------------- F. 首屏绘制清单 ---------------- */
sec('F. 首屏绘制清单（全 no-op 的 mock 会让「一行没画」也显示通过）');
ctxStats.total = 0; ctxStats.fillText = 0;
mk.refresh();
out('        canvas 调用记账：共 ' + ctxStats.total + ' 次');
/* 更硬的判据：两个画笔对象都被挂载（_P = K 线 / _P2 = 历史成交）——
   这比数调用次数更直接地回答「两块 canvas 是否真的走到了绘制回调」。 */
must(mk._P && mk._P2, '两处 canvas 都挂载并绘制（K 线 _P + 历史成交 _P2）',
  'K线' + (mk._P ? '✓' : '✗') + ' / 历史' + (mk._P2 ? '✓' : '✗'));
must(ctxStats.total > 200, '绘制调用次数远超空转（K 线 + 历史成交都真画了）', ctxStats.total + ' 次');
must(ctxStats.fillText > 0, '画布上写下了文字（刻度/标签）', String(ctxStats.fillText));

/* ---------------- G. 空存档（全新用户） ---------------- */
sec('G. 空存档（全新用户）');
const calc2 = require(path.join(MINI, 'lib/calc.js'));
const emptySeed = calc2.defaultState();
const mk2 = boot(emptySeed);
must(mk2.data.histEmpty === true, '没有记录 ⇒ 历史成交走空态');
must(mk2.data.mmEmpty === false && mk2.data.mmBlocks.length === 1 && mk2.data.mmBlocks[0].isBmr === 1,
  '云图只剩基代一块（不是空态，因为基代常驻）');
must(mk2.data.mmSub.indexOf('今日暂无成交') === 0, '云图副标题走「今日暂无成交」口径', mk2.data.mmSub);
must(mk2.data.exSub === '暂无运动记录', '运动网格副标题走「暂无运动记录」', mk2.data.exSub);
must(mk2.data.exCells.every(c => c.s === 'background:transparent' || c.s === 'background:' + REF_EMPTY),
  '无运动时所有格都是暗底或未来透明');
must(mk2.data.empty === true && mk2.data.weightText === ((emptySeed.user && emptySeed.user.weight) || 0) + ' kg',
  'K 线走空态且顶部仍是真实体重');
must(mk2.data.bodyMetrics.length === calc2.BODY_RANGES.length,
  '空存档下身体成分仍按内核等级表渲染（走示例数据的出厂值）');

/* ---------------- 汇总 ---------------- */
out('');
out('='.repeat(78));
out('通过 ' + pass + ' 项 / 失败 ' + fails.length + ' 项');
if (fails.length) {
  out('');
  out('失败明细：');
  fails.forEach((f) => out('  ✗ ' + f));
  out('');
  out('RESULT=FAIL');
} else {
  out('RESULT=OK');
}
fs.writeFileSync(OUT, lines.join('\n') + '\n', 'utf8');
console.log(lines.join('\n'));
/* ⚠️ 必须显式 exit：app.js 的跨天轮询 setInterval 会吊住事件循环，
   否则脚本跑完不退出（表现为「卡住不返回」，很容易被误读成死循环）。 */
process.exit(fails.length ? 1 : 0);
