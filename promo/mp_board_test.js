/* mp_board_test.js —— 龙虎榜（pages/board）运行时断言
 *
 * 与 mp_trade_test.js 同款 mock：凡是能独立算的，都在这里另写一遍现算再比对。
 * 覆盖：① 周/月卡数量与 kind ② topFoods/topEx/topExKcal 精确聚合
 *      ③ 排名连续 + 前三 rankCls ④ 大胃王日/燃脂日（dayAgg）
 *      ⑤ 复盘卡 total/hit/cnt/bigIn/bigOut/col ⑥ 范围过滤（上周/上月记录被排除）
 *      ⑦ 空存档 ⑧ 负控（注入超大饮食让净缺口翻负）
 *      ⑨ 火花图 canvas 真绘制 ⑩ 复制战绩
 *
 * ⚠️ const calc = require(...) 必须写在 boot(seed) 之后（技能铁律）。
 * ⚠️ mock 下 storage['jianpan_v2'] 与 calc.state / store.get() 是同一引用，
 *    负控改真口径直接 seed.diet.push（todayDiet()/todayExercise() 返回 filter 副本不适用此处）。
 *
 * 用法：node promo/mp_board_test.js   退出码 0=全过
 * 报告落盘：promo/_board_out.txt
 */
'use strict';
const path = require('path');
const fs = require('fs');

const MINI = 'E:\\WeChatProjects\\jianpan\\miniprogram';
const OUT = path.join(__dirname, '_board_out.txt');

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
 * 独立参考实现（故意不复用 board.js 的任何聚合函数）
 * ============================================================ */
const pad2 = (n) => String(n).padStart(2, '0');
const ymd = (d) => d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
function D(n) { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n); return ymd(d); }

/* 与 board.js rangeStartFor 逐行同算法（独立复刻，用于构造落在区间内的种子） */
function weekStartStr() {
  const now = new Date();
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day = d.getDay();
  const diff = (day === 0 ? -6 : 1 - day);
  d.setDate(d.getDate() + diff);
  return ymd(d);
}
function monthStartStr() {
  const now = new Date();
  return ymd(new Date(now.getFullYear(), now.getMonth(), 1));
}
function addDays(ymdStr, k) {
  const p = ymdStr.split('-');
  const d = new Date(+p[0], +p[1] - 1, +p[2]);
  d.setDate(d.getDate() + k);
  return ymd(d);
}
const WD = ['日', '一', '二', '三', '四', '五', '六'];
function fmtDayInd(dt) {
  const p = (dt || '').split('-');
  if (p.length < 3) return dt;
  const y = +p[0], m = +p[1], d = +p[2];
  const wd = WD[new Date(y, m - 1, d).getDay()];
  return d + '号（周' + wd + '）';
}

/* 独立聚合 */
function aggFoods(diet, start) {
  const m = {};
  diet.forEach((x) => { if (x.date >= start) m[x.name] = (m[x.name] || 0) + Math.round(x.kcal || 0); });
  return Object.keys(m).map((n) => ({ name: n, k: m[n] })).sort((a, b) => b.k - a.k).slice(0, 5);
}
function aggExCnt(ex, start) {
  const m = {};
  ex.forEach((x) => { if (x.date >= start) m[x.name] = (m[x.name] || 0) + 1; });
  return Object.keys(m).map((n) => ({ name: n, c: m[n] })).sort((a, b) => b.c - a.c).slice(0, 5);
}
function aggExKcal(ex, start) {
  const m = {};
  ex.forEach((x) => { if (x.date >= start) m[x.name] = (m[x.name] || 0) + Math.round(x.kcal || 0); });
  return Object.keys(m).map((n) => ({ name: n, k: m[n] })).sort((a, b) => b.k - a.k).slice(0, 5);
}
function dayAggInd(diet, ex) {
  const din = {}, dout = {}, dates = {};
  diet.forEach((d) => { din[d.date] = (din[d.date] || 0) + Math.round(d.kcal || 0); dates[d.date] = 1; });
  ex.forEach((e) => { dout[e.date] = (dout[e.date] || 0) + Math.round(e.kcal || 0); dates[e.date] = 1; });
  return Object.keys(dates).map((dt) => ({ date: dt, in: din[dt] || 0, out: dout[dt] || 0 }));
}
function reviewInd(diet, ex, start, bmr) {
  const days = dayAggInd(diet, ex).filter((d) => d.date >= start).sort((a, b) => (a.date < b.date ? -1 : 1));
  let total = 0, hit = 0;
  days.forEach((d) => { const def = d.out + bmr - d.in; total += def; if (def >= 150) hit++; });
  return { total, hit, cnt: days.length };
}
function maxKcalRec(arr, start) {
  let best = null;
  arr.forEach((x) => { if ((x.date || '') >= start && (!best || (x.kcal || 0) > (best.kcal || 0))) best = x; });
  return best;
}

/* ============================================================
 * mock（与 mp_trade_test 同款）
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
  '.board-page': 430,
  '#rv-spark': 320,
  'default': 320,
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
        left: 0, top: 0, width: (BOX[s] !== undefined ? BOX[s] : BOX['default']), height: 56,
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
  setClipboardData: (o) => { calls.push(['setClipboardData', o]); o && o.success && o.success(); },
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
 * 构造真实感存档（全部落在本周内，确保周/月区间都覆盖；外加一条上月陈旧记录验证范围过滤）
 * ============================================================ */
let SEQ = 0;
function mrec(name, kcal, dateStr, hour) {
  return { id: 'r' + (++SEQ), name: name, kcal: kcal, date: dateStr,
           time: pad2(hour) + ':00', ts: null, qty: 1, unit: 'g', gram: 100 };
}
function buildSeed() {
  const calc = require(path.join(MINI, 'lib/calc.js'));
  const st = calc.defaultState();
  st.user = Object.assign({}, st.user, {
    userId: 'FT_TEST', weight: 80, height: 175, gender: 'male', age: 30, startWeight: 86,
  });
  const ws = weekStartStr();
  st.diet = [
    mrec('米饭', 300, addDays(ws, 0), 12),
    mrec('红烧肉', 700, addDays(ws, 0), 19),
    mrec('米饭', 200, addDays(ws, 1), 13),
    mrec('沙拉', 150, addDays(ws, 2), 13),
    mrec('上月大餐', 9999, addDays(monthStartStr(), -10), 19), // 陈旧记录：周/月都应被排除
  ];
  st.exercise = [
    mrec('跑步', 420, addDays(ws, 0), 20),
    mrec('跑步', 380, addDays(ws, 1), 21),
    mrec('举铁', 300, addDays(ws, 2), 21),
  ];
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
  require(path.join(MINI, 'pages/board/board.js'));
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

out('=== 龙虎榜 pages/board 运行时验证 ===');
out('工程：' + MINI);
out('本周一=' + weekStartStr() + '  本月1号=' + monthStartStr());

/* ---------------- A. 周视图结构与状态栏 ---------------- */
sec('A. 周视图结构（默认 lbRange=week）');
must(mk.data.lbRange === 'week', '默认 lbRange = week');
must(mk.data.statusBarHeight === 54, '状态栏留白取三级兜底（wx.getWindowInfo → 54）', String(mk.data.statusBarHeight));
mk.refresh();   // onShow 才触发，mock 不跑生命周期，手动拉一次
must(mk.data.cards.length === 3, '周视图 = 3 张榜单卡（热菜/劳模/暴汗）', '实测 ' + mk.data.cards.length);
must(mk.data.cards.map((c) => c.kind).join(',') === 'food,ex,ex', '周卡 kind 顺序 = food,ex,ex',
  mk.data.cards.map((c) => c.kind).join(','));
must(mk.data.cards[0].title === '热菜榜 · 吃最多的食物', '卡1标题 热菜榜');
must(mk.data.cards[1].title === '劳模榜 · 最常做的运动', '卡2标题 劳模榜');
must(mk.data.cards[2].title === '暴汗榜 · 消耗热量最高运动', '卡3标题 暴汗榜');

/* ---------------- B. 热菜榜（topFoods）精确聚合 ---------------- */
sec('B. 热菜榜 topFoods（按 kcal 聚合，独立现算比对）');
const ws = weekStartStr();
const expFoods = aggFoods(seed.diet, ws);
const cf = mk.data.cards[0].rows;
must(cf.length === expFoods.length, '热菜榜条数 = 独立聚合条数', cf.length + ' / ' + expFoods.length);
let foodOk = true;
expFoods.forEach((e, i) => { if (cf[i].name !== e.name || cf[i].val !== (e.k + ' kcal')) foodOk = false; });
must(foodOk, '热菜榜 排名/名称/热量 与独立聚合一致', JSON.stringify(cf.map((r) => r.name + ':' + r.val)));
must(cf[0].name === '红烧肉' && cf[0].val === '700 kcal', '红烧肉(700) 居首', cf[0].name + ' ' + cf[0].val);
must(cf[1].name === '米饭' && cf[1].val === '500 kcal', '米饭(300+200=500) 第二', cf[1].name + ' ' + cf[1].val);

/* ---------------- B2. 范围过滤 ---------------- */
sec('B2. 范围过滤（上周/上月记录必须被排除）');
must(seed.diet.some((d) => d.name === '上月大餐'), '种子含一条上月陈旧记录（用于验证过滤）');
must(!cf.some((r) => r.name === '上月大餐'), '周热菜榜不含上月记录（rangeStartFor 生效）');

/* ---------------- C. 劳模榜（topEx）精确聚合 ---------------- */
sec('C. 劳模榜 topEx（按次数聚合）');
const expEx = aggExCnt(seed.exercise, ws);
const ce = mk.data.cards[1].rows;
must(ce.length === expEx.length, '劳模榜条数 = 独立聚合条数', ce.length + ' / ' + expEx.length);
let exOk = true;
expEx.forEach((e, i) => { if (ce[i].name !== e.name || ce[i].val !== (e.c + ' 次')) exOk = false; });
must(exOk, '劳模榜 名称/次数 与独立聚合一致', JSON.stringify(ce.map((r) => r.name + ':' + r.val)));
must(ce[0].name === '跑步' && ce[0].val === '2 次', '跑步(2次) 居首', ce[0].name + ' ' + ce[0].val);

/* ---------------- D. 暴汗榜（topExKcal）精确聚合 ---------------- */
sec('D. 暴汗榜 topExKcal（按 kcal 聚合）');
const expEK = aggExKcal(seed.exercise, ws);
const cek = mk.data.cards[2].rows;
must(cek.length === expEK.length, '暴汗榜条数 = 独立聚合条数', cek.length + ' / ' + expEK.length);
let ekOk = true;
expEK.forEach((e, i) => { if (cek[i].name !== e.name || cek[i].val !== (e.k + ' kcal')) ekOk = false; });
must(ekOk, '暴汗榜 名称/热量 与独立聚合一致', JSON.stringify(cek.map((r) => r.name + ':' + r.val)));
must(cek[0].name === '跑步' && cek[0].val === '800 kcal', '跑步(420+380=800) 居首', cek[0].name + ' ' + cek[0].val);

/* ---------------- E. 排名连续 + 前三 rankCls ---------------- */
sec('E. 排名连续 + 前三 rankCls = r1/r2/r3');
let rankOk = true;
mk.data.cards.forEach((card) => {
  card.rows.forEach((r, i) => {
    if (r.rank !== i + 1) rankOk = false;
    const expectCls = (i + 1) <= 3 ? 'r' + (i + 1) : '';
    if (r.rankCls !== expectCls) rankOk = false;
  });
});
must(rankOk, '每张卡 rank 连续 1..n，且前三 rankCls=r1/r2/r3、之后为空');

/* ---------------- G. 复盘卡（周，口径与每日缺口评级一致） ---------------- */
sec('G. 复盘卡 reviewData（净缺口 = 运动+基础代谢−饮食）');
const bmr = calc.calcBMR();
const revExp = reviewInd(seed.diet, seed.exercise, ws, bmr);
must(mk.data.review.cnt === revExp.cnt, '周复盘 cnt = 独立天数', mk.data.review.cnt + ' / ' + revExp.cnt);
must(mk.data.review.hit === revExp.hit, '周复盘 hit = 独立达标天数(>=150)', mk.data.review.hit + ' / ' + revExp.hit);
const expTotal = revExp.total > 0 ? calc.fmtNum(revExp.total)
  : (revExp.total < 0 ? '+' + calc.fmtNum(Math.abs(revExp.total)) : '0');
must(mk.data.review.total === expTotal, '周复盘 total 文本 = 独立算 fmtGap', mk.data.review.total + ' / ' + expTotal);
const expCol = revExp.total >= 0 ? '#ff3b47' : '#00c896';
must(mk.data.review.col === expCol, '周复盘 col 涨红(#ff3b47)跌绿(#00c896)', mk.data.review.col);
const bigInExp = maxKcalRec(seed.diet, ws);
const bigOutExp = maxKcalRec(seed.exercise, ws);
must(mk.data.review.bigIn === bigInExp.name, '做多最狠 = 周期内最大 kcal 食物', mk.data.review.bigIn);
must(mk.data.review.bigOut === bigOutExp.name, '做空之王 = 周期内最大 kcal 运动', mk.data.review.bigOut);
must(mk.data.review.bigInK === '+' + calc.fmtNum(Math.round(bigInExp.kcal || 0)), '做多最狠 kcal 文案',
  mk.data.review.bigInK);
must(/约合减脂/.test(mk.data.review.sub), '减脂文案含「约合减脂 X.XX kg」', mk.data.review.sub);

/* ---------------- J. 火花图绘制（同步驱动 _paintSpark） ---------------- */
sec('J. 火花图 canvas 绘制（复盘卡 #rv-spark）');
ctxStats.total = 0; ctxStats.stroke = 0; ctxStats.arc = 0;
mk._paintSpark({ ctx: ctx2d() });   // 直接驱动内部绘制（同步、确定）
must(ctxStats.stroke > 0, '火花图真画了折线（stroke 调用 > 0）', String(ctxStats.stroke));
must(ctxStats.arc > 0, '火花图末点画了圆点（arc 调用 > 0）', String(ctxStats.arc));

/* ---------------- F. 月视图（5 张卡 + 大胃王日/燃脂日） ---------------- */
sec('F. 月视图结构（5 张卡 + 大胃王日/燃脂日）');
mk.setLbRange({ currentTarget: { dataset: { range: 'month' } } });
must(mk.data.lbRange === 'month', 'setLbRange 切到 month');
must(mk.data.cards.length === 5, '月视图 = 5 张榜单卡', '实测 ' + mk.data.cards.length);
must(mk.data.cards.map((c) => c.kind).join(',') === 'food,ex,ex,food,ex', '月卡 kind = food,ex,ex,food,ex',
  mk.data.cards.map((c) => c.kind).join(','));
must(mk.data.cards[3].title === '大胃王日 · 吃热量最高 5 天', '卡4 大胃王日');
must(mk.data.cards[4].title === '燃脂日 · 消耗最高 5 天', '卡5 燃脂日');
const ms = monthStartStr();
const days = dayAggInd(seed.diet, seed.exercise);
const topIn = days.filter((d) => d.date >= ms).sort((a, b) => b.in - a.in).slice(0, 5);
const topOut = days.filter((d) => d.date >= ms).sort((a, b) => b.out - a.out).slice(0, 5);
const cdi = mk.data.cards[3].rows;
must(cdi.length === topIn.length, '大胃王日条数 = 独立 dayAgg 条数', cdi.length + ' / ' + topIn.length);
let diOk = true;
topIn.forEach((d, i) => { if (cdi[i].name !== fmtDayInd(d.date) || cdi[i].val !== (d.in + ' kcal')) diOk = false; });
must(diOk, '大胃王日 名称(日期)/热量 与独立 dayAgg 一致', JSON.stringify(cdi.map((r) => r.name + ':' + r.val)));
const cdo = mk.data.cards[4].rows;
must(cdo.length === topOut.length, '燃脂日条数 = 独立 dayAgg 条数', cdo.length + ' / ' + topOut.length);
let doOk = true;
topOut.forEach((d, i) => { if (cdo[i].name !== fmtDayInd(d.date) || cdo[i].val !== (d.out + ' kcal')) doOk = false; });
must(doOk, '燃脂日 名称(日期)/热量 与独立 dayAgg 一致', JSON.stringify(cdo.map((r) => r.name + ':' + r.val)));
must(!cdi.some((r) => r.name === fmtDayInd(addDays(ms, -10))), '大胃王日不含上月陈旧记录（月范围过滤生效）');
must(mk.data.review.cnt === 3, '月复盘 cnt = 3（记录均在本月内）', String(mk.data.review.cnt));

/* ---------------- I. 负控：注入超大饮食 → 净缺口翻负 ---------------- */
sec('I. 负控 · 净缺口口径（证明读的是活口径，不是常量缓存）');
mk.setLbRange({ currentTarget: { dataset: { range: 'week' } } });
const beforeCol = mk.data.review.col;
/* 注入一笔 50000 kcal 大餐（date=today，落在周/月区间内） */
seed.diet.push({ id: 'rx', name: '大餐', kcal: 50000, date: D(0), time: '22:00', ts: null });
mk.refresh();
const afterCol = mk.data.review.col;
must(beforeCol === '#ff3b47', '负控前：正常数据净缺口为正 → 红', beforeCol);
must(afterCol === '#00c896' && afterCol !== beforeCol,
  '负控：注入 50000 kcal 后净缺口翻负 → 绿（读活口径）', beforeCol + ' / ' + afterCol);

/* ---------------- H. 空存档（全新用户） ---------------- */
sec('H. 空存档（全新用户）');
const emptySeed = calc.defaultState();
const mk2 = boot(emptySeed);
mk2.refresh();
must(mk2.data.cards.length === 3, '空存档周视图仍渲染 3 张空卡（结构不塌）');
must(mk2.data.cards.every((c) => c.rows.length === 0), '空存档：每张榜单卡 rows 为空');
must(mk2.data.review && mk2.data.review.cnt === 0, '空存档复盘 cnt = 0');
must(mk2.data.review.total === '0', '空存档复盘 total = 0', mk2.data.review.total);
must(/还没有成交记录/.test(mk2.data.review.tip), '空存档复盘 tip 走「先下第一单」', mk2.data.review.tip);

/* ---------------- K. 复制战绩 ---------------- */
sec('K. 复制战绩 copyReview');
calls.length = 0;
mk.copyReview();
const clip = calls.find((c) => c[0] === 'setClipboardData');
must(!!clip, 'copyReview 调用 wx.setClipboardData');
if (clip) {
  must(/复盘周报/.test(clip[1] && clip[1].data), '复制文本含周报标题', clip[1] && clip[1].data ? clip[1].data.slice(0, 30) : '');
  must(/净缺口/.test(clip[1] && clip[1].data), '复制文本含净缺口行');
}

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
process.exit(fails.length ? 1 : 0);
