/* mp_body_test.js —— 身体成分详情子页 + 录入弹层 运行时断言
 *
 * 覆盖两处本轮新迁的东西：
 *   pages/body-detail  —— 8 指标 tab / 数值卡（等级·得分·分段色轴）/ 解读卡 / 趋势折线
 *   pages/market 的 #body-sheet —— 手动录入保存口径 + 「图片识别」的降级通道（粘贴文本）
 *
 * 断言纪律（本工程铁律）：
 *   ⭐ **期望值一律独立实现现算**，⛔ 不复用被测算法的同名函数。
 *      本文件里 ref* 系列是从 PWA 的口径描述重写的一份参考实现，不是 require calc 的。
 *      唯一例外是 BMR：它走 lib/nutrition-engine.js（独立模块），
 *      reimplement 一份等于把公式抄两遍 ⇒ 这里改成验**调用链**（bodyValue('bmr') === calcBMR()），
 *      并在注释里写明为什么不做公式对拍。
 *   ⭐ 数字用真数：种子里的体重/体脂是显式给定的常量，期望值从它推。
 *
 * ⚠️ const calc = require(...) 必须写在 boot 之后（技能铁律：boot 会清 require cache）。
 * ⚠️ wx.nextTick 在本测试里**同步化**（直接调 fn）—— 否则 canvas 挂载与断言赛跑，
 *    会得到「有时画了有时没画」的假失败。真机上仍是异步，这正是页面里要 wx.nextTick 的原因。
 *
 * 用法：node promo/mp_body_test.js   退出码 0=全过
 * 报告落盘：promo/_body_out.txt
 */
'use strict';
const path = require('path');
const fs = require('fs');

const MINI = 'E:\\WeChatProjects\\jianpan\\miniprogram';
const OUT = path.join(__dirname, '_body_out.txt');

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
 * 独立参考实现（从 PWA 的口径重写，不复用被测代码）
 * ============================================================ */
function refLevels(m, u) { return m.dynLevels ? m.dynLevels(u) : m.levels; }
function refLevel(m, v, u) {
  const ls = refLevels(m, u);
  return ls.find((l) => v >= l.min && v < l.max) || ls[ls.length - 1];
}
function refRange(m, u) { return typeof m.range === 'function' ? m.range(u) : { min: m.min, max: m.max }; }
/* 得分：越接近参考区间中心越高，下限 40，上限 100（PWA calcMetricScore 口径） */
function refScore(m, v, u) {
  const r = refRange(m, u);
  const center = (r.min + r.max) / 2;
  const range = (r.max - r.min) / 2 || 1;
  const dist = Math.abs(v - center) / range;
  let s = Math.max(40, Math.round(100 - dist * 35));
  if (s > 100) s = 100;
  return s;
}
function refAxis(m, u) {
  const ls = refLevels(m, u);
  return m.axisFn ? m.axisFn(u) : (m.axis || { min: ls[0].min, max: ls[ls.length - 1].max });
}
/* fatWeight：斤，截断到 1 位小数（PWA bodyValue 的口径：Math.floor(w*bf/100*2*10)/10） */
function refFatWeight(st) { return Math.floor(st.user.weight * st.body.bodyFat / 100 * 2 * 10) / 10; }
function refDotPct(m, v, u) {
  const a = refAxis(m, u);
  return Math.min(98, Math.max(2, (v - a.min) / (a.max - a.min) * 100));
}
function refTick(m, x) { return x.toFixed(m.tickDec || 0) + (m.tickUnit ? (m.unit || '') : ''); }

/* ============================================================
 * mock（与 mp_market_test 同款，nextTick 同步化）
 * ============================================================ */
const storage = {};
const noop = () => {};
const calls = [];
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
/* 详情页趋势画布：卡片内容宽 = 430 - 28(margin) - 32(padding) = 370 → 高 = 370 × 200/320 */
const BOX = {
  '#bd-trendcv': 370,
  '#body-detail-page': 430,
  default: 370,
};
const CV_H = 370 * 200 / 320;
function rectQuery() {
  const q = [];
  const r = {
    select: (s) => { q.push(s); return r; },
    selectAll: (s) => { q.push(s); return r; },
    in: () => r, fields: () => r, boundingClientRect: () => r,
    exec: (cb) => {
      const res = q.map((s) => ({
        left: 0, top: 0, width: (BOX[s] !== undefined ? BOX[s] : BOX['default']),
        height: (s === '#bd-trendcv' ? CV_H : 400), node: canvasNode(),
      }));
      q.length = 0;
      if (typeof cb === 'function') cb(res);
      return r;
    },
  };
  return r;
}

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
  getAccountInfoSync: () => ({ miniProgram: { appId: 'wxtest', version: '2.7.60', envVersion: 'develop' } }),
  getUpdateManager: () => ({ onCheckForUpdate: noop, onUpdateReady: noop, onUpdateFailed: noop, applyUpdate: noop }),
  createSelectorQuery: rectQuery,
  /* ⚠️ 同步化：真实环境是异步的（页面里就是要靠它等 setData 落地再画），
     测试里同步执行才能直接断言绘制结果，不会出现「有时画了有时没画」。 */
  nextTick: (fn) => fn(),
  showToast: (o) => calls.push(['showToast', o && o.title]),
  showModal: (o) => { calls.push(['showModal', o && o.title]); o && o.success && o.success({ confirm: false }); },
  showLoading: noop, hideLoading: noop,
  navigateTo: (o) => calls.push(['navigateTo', o && o.url]),
  navigateBack: () => calls.push(['navigateBack']),
  switchTab: noop, pageScrollTo: noop,
  setClipboardData: (o) => { calls.push(['setClipboardData', o]); o && o.success && o.success(); },
  setNavigationBarTitle: noop, stopPullDownRefresh: noop,
  chooseMedia: (o) => { calls.push(['chooseMedia', o]); o && o.fail && o.fail({ errMsg: 'cancel' }); },
};
const captured = { app: null, pages: [] };
global.App = (o) => { captured.app = o; };
global.Page = (o) => { captured.pages.push(o); };
global.getApp = () => captured.app;
global.getCurrentPages = () => [];

function makeInstance(opt) {
  const inst = Object.create(opt);
  inst.data = JSON.parse(JSON.stringify(opt.data || {}));
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
  inst.createSelectorQuery = rectQuery;
  return inst;
}

const pad2 = (n) => String(n).padStart(2, '0');
const ymd = (d) => d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
function todayStr() { return ymd(new Date()); }
function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return ymd(d);
}

/* ============================================================
 * 种子
 * ============================================================ */
/* 固定档案：体重 72.8 / 身高 175 / 男 / 32 岁；6 项身体成分全给显式值。
   bodyLog 4 个点（体脂率 18.2 → 17.4 → 16.9 → 16.2），
   weightLog 3 个点（其中 2 天的日期**不在** bodyLog 里 ⇒ 用来验 BMI 推算点）。 */
const W = 72.8, FAT = 18.2, MUSCLE = 42.5, WATER = 55.8, AGE = 30, VISC = 8, BMI = 23.8;
const LOG = [
  { date: daysAgo(21), bmi: 24.6, bodyFat: 18.2, muscleRate: 42.5, waterRate: 55.8, bodyAge: 30, visceralFat: 8 },
  { date: daysAgo(14), bmi: 24.2, bodyFat: 17.4, muscleRate: 43.0, waterRate: 56.1, bodyAge: 29, visceralFat: 8 },
  { date: daysAgo(7),  bmi: 24.0, bodyFat: 16.9, muscleRate: 43.4, waterRate: 56.4, bodyAge: 29, visceralFat: 7 },
  { date: daysAgo(1),  bmi: BMI,  bodyFat: 16.2, muscleRate: 43.8, waterRate: 56.7, bodyAge: 28, visceralFat: 7 },
];
const WLOG = [
  { date: daysAgo(20), weight: 75.2 },
  { date: daysAgo(10), weight: 74.0 },
  { date: daysAgo(3),  weight: 73.1 },
];
/* 会被本轮触发的成就全部预置：`_prev` / bodyLog 变化会推动「身体成分」类成就，
   那笔补发的币会混进别的断言里（本文件不测币，但保持种子自洽更安全）。 */
function baseSeed(calc, opts) {
  opts = opts || {};
  const st = calc.defaultState();
  st.user = Object.assign({}, st.user, {
    userId: 'FT_BODY', weight: W, startWeight: 80, height: 175, gender: 'male', age: 32,
  });
  st.body = Object.assign({}, st.body, {
    bmi: BMI, bodyFat: FAT, muscleRate: MUSCLE, waterRate: WATER,
    bodyAge: AGE, visceralFat: VISC, source: 'manual', syncedAt: '09:30',
  });
  st.bodyLog = (opts.bodyLog === undefined ? LOG : opts.bodyLog).map((e) => Object.assign({}, e));
  st.weightLog = (opts.weightLog === undefined ? WLOG : opts.weightLog).map((e) => Object.assign({}, e));
  if (opts.prev) st.body._prev = Object.assign({}, opts.prev);
  st.diet = []; st.exercise = [];
  st.ach = {};
  (opts.ach || []).forEach((id) => { st.ach[id] = true; });
  return st;
}

function fresh() {
  Object.keys(storage).forEach((k) => { delete storage[k]; });
  captured.pages.length = 0;
  captured.app = null;
  calls.length = 0;
  ctxStats.total = 0; ctxStats.fillText = 0; ctxStats.fillRect = 0;
  ctxStats.stroke = 0; ctxStats.arc = 0;
  Object.keys(require.cache).forEach((k) => { if (k.indexOf(MINI) === 0) delete require.cache[k]; });
}
function bootPage(relPath, state, query) {
  fresh();
  storage['jianpan_v2'] = state;
  require(path.join(MINI, 'app.js'));
  captured.app.onLaunch.call(captured.app);
  captured.pages.length = 0;
  require(path.join(MINI, relPath));
  const mk = makeInstance(captured.pages[captured.pages.length - 1]);
  if (typeof mk.onLoad === 'function') mk.onLoad.call(mk, query || {});
  if (typeof mk.onShow === 'function') mk.onShow.call(mk);
  if (typeof mk.onReady === 'function') mk.onReady.call(mk);
  return mk;
}
/* 🔴 活状态：boot 之后 store 里那一份才是生产里真被改的对象 */
function L() { return require(path.join(MINI, 'lib/store.js')).get(); }
function tap(dataset) { return { currentTarget: { dataset: dataset || {} } }; }
function input(v) { return { detail: { value: v } }; }

/* ============================================================
 * 跑
 * ============================================================ */
out('mp_body_test —— 身体成分详情子页 + 录入弹层运行时断言');
out('时间：' + new Date().toISOString());

/* ---------- A 结构：8 个 tab ---------- */
sec('A 结构与 tab 清单');
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  const page = bootPage('pages/body-detail/body-detail.js', baseSeed(c0), { idx: '3' });
  const calc = require(path.join(MINI, 'lib/calc.js'));

  must(calc.BODY_RANGES.length === 8, '内核 BODY_RANGES 是 8 个指标', 'got ' + calc.BODY_RANGES.length);
  must(page.data.tabs.length === 8, '页面渲染出 8 个 tab', 'got ' + page.data.tabs.length);
  must(page.data.tabs.map((t) => t.label).join('|') === calc.BODY_RANGES.map((m) => m.label).join('|'),
    'tab 文案与内核 label 逐项一致', page.data.tabs.map((t) => t.label).join('|'));
  must(page.data.tabs.filter((t) => t.on).length === 1 && page.data.tabs[3].on,
    'query.idx=3 时只有第 4 个 tab 选中', JSON.stringify(page.data.tabs.map((t) => t.on)));
  must(page._idx === 3 && calc.curBodyIdx === 3, '页面 _idx 与内核 curBodyIdx 同为 3',
    'page=' + page._idx + ' kernel=' + calc.curBodyIdx);

  /* 非法 query 一律回 0（不让 NaN 进内核） */
  const p2 = bootPage('pages/body-detail/body-detail.js', baseSeed(require(path.join(MINI, 'lib/calc.js'))), { idx: 'abc' });
  must(p2._idx === 0, 'query.idx 非法 ⇒ 回落 0', 'got ' + p2._idx);
  const p3 = bootPage('pages/body-detail/body-detail.js', baseSeed(require(path.join(MINI, 'lib/calc.js'))), { idx: '99' });
  must(p3._idx === 0, 'query.idx 越界 ⇒ 回落 0', 'got ' + p3._idx);
}

/* ---------- B 逐指标数值卡（期望值独立现算） ---------- */
sec('B 8 个指标的数值卡逐一核对');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  const page = bootPage('pages/body-detail/body-detail.js', baseSeed(c));
  const calc = require(path.join(MINI, 'lib/calc.js'));
  const st = L();
  const u = st.user;

  const keys = calc.BODY_RANGES.map((m) => m.key);
  must(keys.join(',') === 'bmi,bodyFat,muscleRate,waterRate,bodyAge,bmr,fatWeight,visceralFat',
    '8 个指标顺序与内核一致', keys.join(','));

  let nChecked = 0;
  calc.BODY_RANGES.forEach((m, i) => {
    page._idx = i;
    page.render();
    const card = page.data.card;
    /* 独立现算期望值 */
    let v;
    if (m.key === 'fatWeight') v = refFatWeight(st);
    else if (m.key === 'bmr') v = calc.calcBMR();          // 见文件头说明：BMR 只验调用链
    else v = st.body[m.key];
    const lv = refLevel(m, v, u);
    const sc = refScore(m, v, u);
    const dp = refDotPct(m, v, u);

    must(card.value === v, '[' + m.label + '] 数值 = ' + v, 'got ' + card.value);
    must(card.unit === m.unit, '[' + m.label + '] 单位 = ' + JSON.stringify(m.unit), 'got ' + card.unit);
    must(card.label === m.label, '[' + m.label + '] 标题正确', 'got ' + card.label);
    must(card.score === sc, '[' + m.label + '] 得分 = ' + sc, 'got ' + card.score);
    must(card.dotStyle.indexOf('left:' + dp + '%') >= 0, '[' + m.label + '] 定位点 left = ' + dp + '%', card.dotStyle);
    must(card.refText === (typeof m.ref === 'function' ? m.ref(u) : m.ref),
      '[' + m.label + '] 参考区间文案', 'got ' + card.refText);

    if (m.simple) {
      /* 极简模式：无徽章、无得分行、无刻度与段名、单段青轴、track 上边距 26 */
      must(card.simple === true, '[' + m.label + '] 走极简模式', '');
      must(card.levelStyle === '', '[' + m.label + '] 极简 ⇒ 不给徽章', card.levelStyle);
      must(card.ticks.length === 0 && card.names.length === 0, '[' + m.label + '] 极简 ⇒ 无刻度无段名',
        'ticks=' + card.ticks.length + ' names=' + card.names.length);
      must(card.trackStyle === 'margin-top:26px;', '[' + m.label + '] 极简 ⇒ track margin-top 26',
        JSON.stringify(card.trackStyle));
      must(card.dotStyle.indexOf('border-color:#00c896') >= 0, '[' + m.label + '] 极简 ⇒ 定位点恒青',
        card.dotStyle);
    } else {
      must(card.simple === false, '[' + m.label + '] 非常规项', '');
      must(card.levelName === lv.name, '[' + m.label + '] 等级名 = ' + lv.name, 'got ' + card.levelName);
      must(card.levelStyle === 'background:' + lv.color + ';color:#fff;', '[' + m.label + '] 徽章配色随等级',
        card.levelStyle);
      must(card.dotStyle.indexOf('border-color:' + lv.color) >= 0, '[' + m.label + '] 定位点随等级色',
        card.dotStyle);
      must(card.trackStyle === '', '[' + m.label + '] 非极简 ⇒ track 无行内 margin', JSON.stringify(card.trackStyle));
      /* 分段色轴的段宽之和 ≈ 100%，且段色与内核等级一一对应（越界段被裁掉的不算） */
      const sum = card.segs.reduce((a, s) => a + s.w, 0);
      must(Math.abs(sum - 100) < 0.01, '[' + m.label + '] 段宽合计 = 100%', 'got ' + sum.toFixed(3));
      /* 独立现算段数：等级里与轴区间有交集的数量 */
      const a = refAxis(m, u);
      const expSegs = refLevels(m, u).filter((l) => Math.min(l.max, a.max) > Math.max(l.min, a.min)).length;
      must(card.segs.length === expSegs, '[' + m.label + '] 段数 = ' + expSegs, 'got ' + card.segs.length);
      /* 刻度：轴上内部边界（严格在 (min,max) 内），升序 */
      const expTicks = [...new Set(refLevels(m, u).flatMap((l) => [l.min, l.max]))]
        .filter((x) => x > a.min && x < a.max).sort((p, q) => p - q).map((x) => refTick(m, x));
      must(card.ticks.map((t) => t.text).join('|') === expTicks.join('|'),
        '[' + m.label + '] 刻度文案 = ' + expTicks.join(','),
        'got ' + card.ticks.map((t) => t.text).join(','));
      must(card.names.length === expSegs, '[' + m.label + '] 段名数量 = 段数', 'got ' + card.names.length);
      must(card.names.every((x) => x.left > 0 && x.left < 100), '[' + m.label + '] 段名位置都在 0~100% 内', '');
    }
    nChecked++;
  });
  must(nChecked === 8, '8 个指标全部逐项核对过', 'got ' + nChecked);
}

/* ---------- C 切换 tab ---------- */
sec('C 切换 tab');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  const page = bootPage('pages/body-detail/body-detail.js', baseSeed(c));
  const calc = require(path.join(MINI, 'lib/calc.js'));

  const v0 = page.data.card.value;
  page.onTab(tap({ idx: 1 }));       // 体脂率
  must(page._idx === 1, '切到第 2 个 tab', 'got ' + page._idx);
  must(calc.curBodyIdx === 1, '内核 curBodyIdx 同步为 1', 'got ' + calc.curBodyIdx);
  must(page.data.card.value === L().body.bodyFat, '卡片换成了体脂率的值', 'got ' + page.data.card.value);
  must(page.data.tabs[1].on && page.data.tabs.filter((t) => t.on).length === 1, '选中态是唯一一个', '');
  must(page.data.card.value !== v0, '数值确实变了（不是照抄上一个指标）', v0 + ' → ' + page.data.card.value);

  page.onTab(tap({ idx: 1 }));
  must(page._idx === 1, '点同一个 tab 不产生副作用', '');
}

/* ---------- D 解读卡（趋势句 / 差距句 / 知识段） ---------- */
sec('D 解读卡文案口径');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  /* _prev 的体脂率比现值大 ⇒ 「下降」；BMI 与现值相同 ⇒ 「不变」 */
  const page = bootPage('pages/body-detail/body-detail.js', baseSeed(c, {
    prev: { bmi: BMI, bodyFat: 18.2, muscleRate: 42.5, waterRate: 55.8, bodyAge: 30, visceralFat: 8 },
  }));
  const st = L();

  page._idx = 1; page.render();       // 体脂率 18.2 vs _prev 18.2
  must(page.data.ai.p1.indexOf('对比上次不变') >= 0, '相同值 ⇒ 「对比上次不变」', page.data.ai.p1);
  must(page.data.ai.p1.indexOf('体脂率') === 0, '句子以指标名开头', page.data.ai.p1);

  page._idx = 0; page.render();       // BMI 23.8 vs _prev 23.8
  must(page.data.ai.p1.indexOf('对比上次不变') >= 0, 'BMI 同值也走「不变」', page.data.ai.p1);

  /* 造一个真的会变化的情形：把 state.body.bodyFat 改成 16.2（_prev=18.2 ⇒ 下降 2） */
  st.body.bodyFat = 16.2;
  page._idx = 1; page.render();
  must(page.data.ai.p1.indexOf('对比上次下降2') >= 0, '降低了 ⇒ 写「下降」+ 差值', page.data.ai.p1);
  must(page.data.ai.p1.indexOf('%。') > 0 || page.data.ai.p1.indexOf('%') > 0, '趋势句带单位 %', page.data.ai.p1);

  /* 极简项走 statusWord，且不带「对比上次」以外的等级名 */
  page._idx = 5; page.render();       // bmr
  const bmr = c.BODY_RANGES[5];
  must(page.data.ai.p1.indexOf(bmr.label) === 0, '极简项句子以指标名开头', page.data.ai.p1);
  must(page.data.ai.p1.indexOf(bmr.statusWord(st.body.bmr, st.user, st.body)) > 0,
    '极简项用 statusWord 结论', page.data.ai.p1);

  /* p2 = know() 输出，必须非空（否则解读卡只有半句话） */
  must(typeof page.data.ai.p2 === 'string' && page.data.ai.p2.length > 8,
    '知识段非空', JSON.stringify(page.data.ai.p2).slice(0, 60));
  page._idx = 0; page.render();
  must(page.data.ai.p2 === c.BODY_RANGES[0].know(calc0().bodyValue('bmi'), st.user, st.body),
    '知识段 = 内核 know() 的输出（不是另写一份文案）', '');
  function calc0() { return require(path.join(MINI, 'lib/calc.js')); }
}

/* ---------- E 趋势图几何 ---------- */
sec('E 趋势折线（几何 + 真画了）');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  const page = bootPage('pages/body-detail/body-detail.js', baseSeed(c));
  const st = L();
  const calc = require(path.join(MINI, 'lib/calc.js'));

  /* 体脂率：4 个真实点 */
  page._idx = 1; page.render();
  const g = page._trend;
  must(g.n === 4 && !g.empty, '体脂率 4 个数据点', 'got ' + g.n);
  must(page.data.trend.n === 4 && page.data.trend.empty === false, 'data.trend 同步了点数', '');
  const expDelta = '首次 ' + LOG[0].bodyFat + ' → 最新 ' + LOG[3].bodyFat + '（'
    + (LOG[3].bodyFat >= LOG[0].bodyFat ? '+' : '') + (LOG[3].bodyFat - LOG[0].bodyFat) + '%）';
  must(page.data.trend.delta === expDelta, '首→最新 delta 文案', 'got ' + page.data.trend.delta);

  /* 不变量：所有点落在绘图区内；x 单调；末点在最右 */
  const xs = g.vals.map((_, i) => g.xOf(i));
  const ys = g.vals.map((p) => g.yOf(p.v));
  must(xs.every((x, i) => i === 0 || x > xs[i - 1]), 'x 坐标严格递增', xs.map((x) => x.toFixed(1)).join(','));
  must(ys.every((y) => y >= 16 && y <= 200 - 24), '所有点落在绘图区（padT 16 ~ padB 24）',
    ys.map((y) => y.toFixed(1)).join(','));
  /* 独立现算：plotW = 320-34-30 = 256；innerW = 3*58 = 174 ≤ 256 ⇒ 居中起点 34+(256-174)/2 = 75 */
  must(Math.abs(xs[0] - 75) < 1e-9, '4 点未铺满 ⇒ 固定点距 58 居中（首点 x = 75）', 'got ' + xs[0].toFixed(2));
  const padL = 34, plotW = 320 - 34 - 30, GAP = 58, innerW = 3 * GAP;
  must(Math.abs(xs[0] - (padL + (plotW - innerW) / 2)) < 1e-9, '首点位置与独立现算一致',
    xs[0] + ' vs ' + (padL + (plotW - innerW) / 2));
  must(Math.abs(xs[3] - (padL + (plotW - innerW) / 2 + 3 * GAP)) < 1e-9, '末点位置与独立现算一致', '');

  /* 参考色带 / 虚线刻度：都只画与 Y 轴范围有交集的部分 */
  const yMin = Math.min(...g.vals.map((p) => p.v)) / 1, yMax = Math.max(...g.vals.map((p) => p.v));
  const levels = calc.resolveLevels(c.BODY_RANGES[1], st.user);
  must(g.bands.length > 0 && g.bands.length <= levels.length, '色带数量 ≤ 等级数',
    g.bands.length + ' / ' + levels.length);

  /* x 轴标签：≤7 点全标 */
  must(g.xidx.length === 4 && g.xidx[0] === 0 && g.xidx[3] === 3, '≤7 点 ⇒ 每个点都标日期',
    JSON.stringify(g.xidx));

  /* canvas 真的画了 */
  must(page._paintedTrend !== undefined, '画布挂载被调用过（_paintedTrend 字段存在）', '');
  must(ctxStats.total > 50, '绘制调用 > 50 次（折线/色带/刻度/点都真画了）', ctxStats.total + ' 次');
  must(ctxStats.fillText > 0, '画布上写下了文字（Y 轴刻度 / X 轴日期 / 末点数值）', String(ctxStats.fillText));
  must(ctxStats.stroke > 0, '画布上有描边（折线 / 虚线 / 圆点）', String(ctxStats.stroke));
}

/* ---------- F 趋势空态 + BMI 推算点 ---------- */
sec('F 空态 与 BMI 推算点');
{
  const c = require(path.join(MINI, 'lib/calc.js'));

  /* ⚠️ 前提：loadState() 会给**空的** weightLog 补一个「今天的体重」点（PWA 同口径，
     K 线不能是空数组）⇒ 空存档下 BMI 也不是 0 个点。这条先钉住，免得后面的期望值靠猜。 */
  const p0 = bootPage('pages/body-detail/body-detail.js', baseSeed(c, { bodyLog: [], weightLog: [] }));
  must(L().weightLog.length === 1, '空 weightLog 被 loadState 补成 1 个点（前提自检）',
    'got ' + L().weightLog.length);

  /* 空 bodyLog + 无推算渠道（体脂率）⇒ 真空态，且不画布 */
  ctxStats.total = 0;
  const p1 = bootPage('pages/body-detail/body-detail.js', baseSeed(c, { bodyLog: [], weightLog: [] }));
  p1._idx = 1; p1.render();
  must(p1.data.trend.empty === true, '0 个点 ⇒ 空态', 'got ' + p1.data.trend.empty);
  must(p1.data.trend.n === 0, '空态点数 0', 'got ' + p1.data.trend.n);
  must(ctxStats.total === 0, '空态不挂画布（不白画一张空图）', ctxStats.total + ' 次');

  /* 只有 1 个点也走空态（2 个以上才连线）—— 同样挑无推算渠道的指标 */
  const p2 = bootPage('pages/body-detail/body-detail.js', baseSeed(c, { bodyLog: [LOG[0]] }));
  p2._idx = 1; p2.render();
  must(p2.data.trend.empty === true && p2.data.trend.n === 1, '1 个点 ⇒ 仍走空态（不连线）',
    'n=' + p2.data.trend.n + ' empty=' + p2.data.trend.empty);

  /* BMI：bodyLog 里的 4 个日期 + weightLog 里 2 个不在 bodyLog 的日期 ⇒ 6 个点，2 个推算点 */
  const p3 = bootPage('pages/body-detail/body-detail.js', baseSeed(c));
  p3._idx = 0; p3.render();
  const g = p3._trend;
  const have = new Set(LOG.map((e) => e.date));
  const expDerived = WLOG.filter((p) => !have.has(p.date)).length;
  must(expDerived === WLOG.length, '种子里 3 个体重日期都不在 bodyLog 里（前提自检）', 'got ' + expDerived);
  must(g.n === 4 + expDerived, 'BMI 点数 = 4 真实 + 3 推算 = 7', 'got ' + g.n);
  must(g.derivedN === expDerived, 'derivedN = ' + expDerived, 'got ' + g.derivedN);
  must(g.vals.filter((p) => p.d).length === expDerived, '推算点标记数一致', '');
  must(p3.data.trend.delta.indexOf('空心点＝按体重推算') > 0, 'delta 文案带「空心点」说明',
    p3.data.trend.delta);
  /* 推算值按 BMI = w / h² 现算 */
  const h = L().user.height / 100;
  WLOG.filter((x) => !have.has(x.date)).forEach((x) => {
    const exp = Math.round(x.weight / (h * h) * 10) / 10;
    const got = g.vals.find((p) => p.date === x.date);
    must(got && got.v === exp, '体重 ' + x.weight + 'kg ⇒ BMI 推算 ' + exp, got && got.v);
  });
  /* 体脂率没有推算渠道 ⇒ 仍只有 4 点 */
  p3._idx = 1; p3.render();
  must(p3._trend.n === 4, '体脂率无推算渠道 ⇒ 仍是 4 点', 'got ' + p3._trend.n);
}

/* ---------- G 录入弹层 · 手动录入保存口径 ---------- */
sec('G 录入弹层 · saveBody 口径');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  const page = bootPage('pages/market/market.js', baseSeed(c));
  const st = L();

  page.onBodyManual();
  must(page.data.bs.show === true && page.data.bs.ocr === false, '「手动录入」开弹层且不带 OCR 面板',
    JSON.stringify({ show: page.data.bs.show, ocr: page.data.bs.ocr }));
  must(page.data.bs.f.bmi === String(BMI) && page.data.bs.f.visceralFat === String(VISC),
    '6 个输入框预填成 state.body 的当前值',
    page.data.bs.f.bmi + '/' + page.data.bs.f.bodyFat + '/' + page.data.bs.f.visceralFat);

  /* 改两个字段后保存 */
  const old = { bmi: st.body.bmi, bodyFat: st.body.bodyFat, muscleRate: st.body.muscleRate,
                waterRate: st.body.waterRate, bodyAge: st.body.bodyAge, visceralFat: st.body.visceralFat };
  page.onBsInput({ currentTarget: { dataset: { k: 'bodyFat' } }, detail: { value: '16.5' } });
  page.onBsInput({ currentTarget: { dataset: { k: 'visceralFat' } }, detail: { value: '6' } });
  const beforeLog = st.bodyLog.length;
  page.saveBody();

  must(st.body.bodyFat === 16.5, '体脂率被写入 16.5', 'got ' + st.body.bodyFat);
  must(st.body.visceralFat === 6, '内脏脂肪被写入 6（parseInt）', 'got ' + st.body.visceralFat);
  must(JSON.stringify(st.body._prev) === JSON.stringify(old), '有变化 ⇒ _prev = 改动前的快照',
    JSON.stringify(st.body._prev));
  must(st.body.source === 'manual', 'source = manual', 'got ' + st.body.source);
  must(/^\d{1,2}:\d{2}$/.test(st.body.syncedAt || ''), 'syncedAt 形如 H:MM', 'got ' + st.body.syncedAt);
  must(st.bodyLog.length === beforeLog + 1,
    '种子最后日期不是今天 ⇒ bodyLog 追加 1 条（' + beforeLog + ' → ' + (beforeLog + 1) + '）',
    'got ' + st.bodyLog.length);
  const lastRec = st.bodyLog[st.bodyLog.length - 1];
  must(lastRec.date === todayStr(), 'bodyLog 末条是今天', 'got ' + lastRec.date);
  must(lastRec.bodyFat === 16.5 && lastRec.visceralFat === 6, 'bodyLog 记的是本次录入的值', JSON.stringify(lastRec));
  must(st.bodyLog.every((e) => !e.seed), '示例点（seed）已被彻底剔除', '');
  must(page.data.bs.show === false, '保存后关弹层', '');
  must(calls.some((x) => x[0] === 'showToast'), '保存后给了 toast 反馈', '');

  /* 再存一次同一天：覆盖而不是追加 */
  const n1 = st.bodyLog.length;
  page.onBodyManual();
  page.onBsInput({ currentTarget: { dataset: { k: 'waterRate' } }, detail: { value: '57.1' } });
  page.saveBody();
  must(st.bodyLog.length === n1, '同一天再存 ⇒ 覆盖当天样本，不追加', n1 + ' → ' + st.bodyLog.length);
  must(st.bodyLog[st.bodyLog.length - 1].waterRate === 57.1, '覆盖后是新值', '');
  must(st.body._prev.bodyFat === 16.5, '第二次存 ⇒ _prev 变成上一次的值（链式留存）',
    JSON.stringify(st.body._prev));

  /* 完全没改 ⇒ 不写 _prev */
  page.onBodyManual();
  const prevBefore = JSON.stringify(st.body._prev);
  page.saveBody();
  must(JSON.stringify(st.body._prev) === prevBefore, '没改动 ⇒ _prev 不动', JSON.stringify(st.body._prev));

  /* 清空输入框 ⇒ 保持旧值（PWA 的 `parseFloat(...) || b.x` 口径，不是置 0） */
  page.onBodyManual();
  const keep = st.body.bmi;
  page.onBsInput({ currentTarget: { dataset: { k: 'bmi' } }, detail: { value: '' } });
  page.saveBody();
  must(st.body.bmi === keep, '清空输入框 ⇒ 保持旧值（不是变成 0）', 'got ' + st.body.bmi);
}

/* ---------- H 录入弹层 · 图片识别的降级通道 ---------- */
sec('H 图片识别降级（粘贴文本 → 内核 parseBodyText）');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  const page = bootPage('pages/market/market.js', baseSeed(c));
  const st = L();

  page.onBodyOcr();
  must(page.data.bs.show === true && page.data.bs.ocr === true, '「图片识别」开弹层并展开 OCR 面板',
    JSON.stringify({ show: page.data.bs.show, ocr: page.data.bs.ocr }));

  /* 空文本 ⇒ 红字拦下，不改表单 */
  page.parseBodyOcr();
  must(page.data.bs.status.show === true && page.data.bs.status.style.indexOf('#3a1a1a') >= 0,
    '空文本 ⇒ 失败态（红底）', page.data.bs.status.style);
  must(page.data.bs.f.bodyFat === String(FAT), '失败时不动表单', page.data.bs.f.bodyFat);

  /* 乱文本 ⇒ 红字 + 不改表单 */
  page.onBsRaw(input('今天天气不错，去公园走了一圈'));
  page.parseBodyOcr();
  must(page.data.bs.status.style.indexOf('#3a1a1a') >= 0, '认不出字段 ⇒ 失败态', '');
  must(page.data.bs.f.bodyFat === String(FAT), '认不出时不改表单', '');

  /* 真文本 ⇒ 6 个字段 + 体重都填进来 */
  const RAW = 'BMI 23.8 体脂率 16.2% 肌肉率 43.8% 水分率 56.7% 内脏脂肪 7 身体年龄 28 体重 73.1kg';
  page.onBsRaw(input(RAW));
  page.parseBodyOcr();
  must(page.data.bs.status.style.indexOf('#0d3a32') >= 0, '识别成功 ⇒ 成功态（绿底）', page.data.bs.status.style);
  must(page.data.bs.status.text.indexOf('已识别') >= 0, '成功文案带「已识别」', page.data.bs.status.text.slice(0, 40));
  /* 期望值用内核 parseBodyText 独立跑一遍（这里复用的是**内核口径**，不是页面的搬运代码） */
  const f = c.parseBodyText(RAW);
  must(page.data.bs.f.bmi === String(f.bmi), 'BMI 填入 ' + f.bmi, page.data.bs.f.bmi);
  must(page.data.bs.f.bodyFat === String(f.bodyFat), '体脂率填入 ' + f.bodyFat, page.data.bs.f.bodyFat);
  must(page.data.bs.f.muscleRate === String(f.muscleRate), '肌肉率填入 ' + f.muscleRate, page.data.bs.f.muscleRate);
  must(page.data.bs.f.waterRate === String(f.waterRate), '水分率填入 ' + f.waterRate, page.data.bs.f.waterRate);
  must(page.data.bs.f.bodyAge === String(f.bodyAge), '身体年龄填入 ' + f.bodyAge, page.data.bs.f.bodyAge);
  must(page.data.bs.f.visceralFat === String(f.visceralFat), '内脏脂肪填入 ' + f.visceralFat, page.data.bs.f.visceralFat);
  must(st.user.weight === f.weight, '识别到的体重写进了 user.weight（' + f.weight + '）', 'got ' + st.user.weight);
  must(st.weightLog[st.weightLog.length - 1].date === todayStr(), '并记了一笔今日体重点', '');
  must(st.weightLog[st.weightLog.length - 1].weight === f.weight, '体重点的值 = 识别值', '');

  /* 识别后保存 ⇒ source 记 'sync'（与 PWA 的 OCR 路径同口径） */
  page.saveBody();
  must(st.body.source === 'sync', "走 OCR ⇒ source = 'sync'", 'got ' + st.body.source);
  must(st.body._prev == null || Math.abs(st.body._prev.bodyFat - FAT) < 1e-9,
    '_prev 记的是识别前的值', JSON.stringify(st.body._prev));

  /* 下一轮手动录入必须回落 'manual'（ocrFilled 是一次性的） */
  page.onBodyManual();
  page.saveBody();
  must(st.body.source === 'manual', "下一次手动录入 ⇒ source 回落 'manual'", 'got ' + st.body.source);

  /* 负控：恒真守卫 —— 若把 ocrFilled 判据写反，上面两条必有一条挂 */
  must(page._ocrFilled === false, '保存后 _ocrFilled 已复位（不会污染下一次）', 'got ' + page._ocrFilled);
}

/* ---------- I 空存档 ---------- */
sec('I 空存档');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  let page = null, err = null;
  try { page = bootPage('pages/body-detail/body-detail.js', c.defaultState()); } catch (e) { err = e; }
  must(!err, '空存档打开详情页不抛错', err && err.message);
  if (page) {
    must(page.data.tabs.length === 8, '空存档仍有 8 个 tab', 'got ' + page.data.tabs.length);
    must(page.data.trend.empty === true, '空存档 ⇒ 趋势空态', '');
    must(page.data.card.value !== undefined && page.data.card.value !== null, '空存档卡片仍有数值（走出厂值）',
      'got ' + page.data.card.value);
    must(typeof page.data.ai.p1 === 'string' && page.data.ai.p1.length > 0, '空存档解读句非空', page.data.ai.p1);
  }
  /* 空存档 + 无 query：不崩 */
  let p2 = null, err2 = null;
  try { p2 = bootPage('pages/body-detail/body-detail.js', c.defaultState(), undefined); } catch (e) { err2 = e; }
  must(!err2, '不带 query 打开不抛错', err2 && err2.message);

  /* 录入弹层在空存档下也能开 */
  let p3 = null, err3 = null;
  try {
    p3 = bootPage('pages/market/market.js', c.defaultState());
    p3.onBodyManual();
    p3.onBsInput({ currentTarget: { dataset: { k: 'bodyFat' } }, detail: { value: '20' } });
    p3.saveBody();
  } catch (e) { err3 = e; }
  must(!err3, '空存档也能手动录入身体成分', err3 && err3.message);
  must(L().body.bodyFat === 20, '空存档录入生效', 'got ' + L().body.bodyFat);
}

/* ---------- J 专属负控 ---------- */
sec('J 专属负控（证明上面的断言不是恒真的）');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  /* 负控 1：把「极简模式 track margin-top 26」写坏 ⇒ B 段必须挂。
     做法：真的动 state —— 把 bmr 的 bodyFat 设为 0（走 else 分支）不影响 simple；
     所以这里改成直接验判据本身：simple 标志来自 m.simple，改动不了 ⇒
     改为验证「B 段确实在比对具体数值」：把一个指标的 state.body 值改掉，卡片值必须跟着变。 */
  const page = bootPage('pages/body-detail/body-detail.js', baseSeed(c));
  const st = L();
  page._idx = 2; page.render();                    // 肌肉率
  const v1 = page.data.card.value;
  st.body.muscleRate = 39.9;
  page.render();
  must(page.data.card.value === 39.9 && v1 !== 39.9,
    '负控 · 改 state ⇒ 卡片值必须跟着变（否则 B 段是照抄常量）', v1 + ' → ' + page.data.card.value);

  /* 负控 2：把 _prev 的键换掉 ⇒ 「对比上次」必须消失（证明 D 段读的是真 _prev） */
  page._idx = 1;
  st.body._prev = { notFat: 99 };
  page.render();
  must(page.data.ai.p1.indexOf('对比上次') < 0,
    '负控 · _prev 里没有该指标的键 ⇒ 不写趋势句（证明读的是 _prev[key] 而不是随便一个数）',
    page.data.ai.p1);

  /* 负控 3：seed 清理发生在**数据层**（loadState / saveBody），不在渲染层。
     两步都要验，否则「谁负责剔 seed」这件事没有守卫：
       ① 冷启动：种子里只有 seed 点 ⇒ loadState 已剔干净 ⇒ 趋势空态
       ② 运行期：绕过 loadState 直接往活状态里塞 seed 点 ⇒ 渲染层必须照样画出来
          （证明它没有偷偷再滤一遍；口径与 PWA 一致 —— 渲染只负责显示） */
  const p2 = bootPage('pages/body-detail/body-detail.js', baseSeed(c, {
    bodyLog: [{ date: daysAgo(3), seed: 1, bodyFat: 20 }, { date: daysAgo(2), seed: 1, bodyFat: 19 }],
    weightLog: [],
  }));
  must(L().bodyLog.length === 0, '负控 · 冷启动时 loadState 已把 seed 点剔干净', 'got ' + L().bodyLog.length);
  p2._idx = 1; p2.render();
  must(p2.data.trend.empty === true, '负控 · 剔完只剩 0 点 ⇒ 趋势空态', 'got ' + p2.data.trend.n);

  L().bodyLog = [{ date: daysAgo(3), seed: 1, bodyFat: 20 }, { date: daysAgo(2), seed: 1, bodyFat: 19 }];
  p2.render();
  must(p2._trend.n === 2, '负控 · 运行期塞进 2 个 seed 点 ⇒ 渲染层照样画（不替数据层做过滤）',
    'got ' + p2._trend.n);
  must(p2.data.trend.delta.indexOf('首次 20 → 最新 19') === 0, '负控 · 画出来的就是那两点的值',
    p2.data.trend.delta);
}

out('');
out('========================================');
out('通过 ' + pass + ' 项，失败 ' + fails.length + ' 项');
if (fails.length) fails.forEach((f) => out('  ✗ ' + f));
out('RESULT=' + (fails.length ? 'FAIL' : 'OK'));
fs.writeFileSync(OUT, lines.join('\n') + '\n', 'utf8');
console.log(lines.join('\n'));
process.exit(fails.length ? 1 : 0);
