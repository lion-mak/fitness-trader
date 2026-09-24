/* mp_celeb_test.js —— 全屏涨停仪式（#celeb）运行时断言
 *
 * 覆盖本轮新迁的 #105：
 *   components/celeb       组件本体（visible / net / streak / coin / exp / 关闭事件）
 *   lib/celeb-host.js      两条送达通路（deliver 即时 / pickShow 兜底）
 *   app.js                 celebrate 钩子（留事件 + 置标志 + 尽力路由，⛔ 不发币不弹 toast）
 *   5 个 tab 页            接线（json 注册 + wxml 挂载 + onCelebrate/onCelebClose/onShow 兜底）
 *
 * 为什么必须两条通路都测（本套件的存在理由）：
 *   PWA 的 #celeb 挂在 .app 里，任何页面都盖得到；小程序没有全局浮层 ⇒ 每个 tab 页各挂一份组件。
 *   而「冷启动即涨停」（settleDay 在 App.onLaunch 里跑完）那一刻**页面栈是空的**，
 *   即时通路必然送不到 —— 这正是 globalData.celebPending 兜底通路存在的唯一理由。
 *   所以下面 D 段刻意走「真数据触发涨停」的完整链路，而不是手工塞一个标志。
 *
 * 断言纪律（本工程铁律）：
 *   ⭐ 期望值一律**独立现算**，⛔ 不复用被测算法的同名函数（下面 ref* 系列）。
 *   ⭐ 数字用真数：摄入 1500 / 消耗 600 / BMR 走 Katch-McArdle ⇒ 净缺口 -767，阈值 -500。
 *   ⭐ 币类断言一律看**增量**（limitUpCount / coinsEarnedTotal 的差），
 *      因为 store.init 的冷启动补发会往 coins 里塞成就币 —— 绝对币数是浮动的。
 *
 * ⚠️ const calc = require(...) 必须写在 boot 之后（技能铁律：boot 会清 require cache）。
 * ⚠️ 测试环境 getCurrentPages() 返回 []（与真机不同）⇒ 即时通路必然 false，
 *    这不是缺陷，是**必须**被兜底通路覆盖的场景。
 *
 * 用法：node promo/mp_celeb_test.js   退出码 0=全过
 * 报告落盘：promo/_celeb_out.txt
 */
'use strict';
const path = require('path');
const fs = require('fs');

const MINI = 'E:\\WeChatProjects\\jianpan\\miniprogram';
const OUT = path.join(__dirname, '_celeb_out.txt');

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
 * 独立参考实现（从 PWA / 界面口径重写，不复用被测代码）
 * ============================================================ */
/* 净热量缺口：当日摄入 − 当日消耗 − BMR（PWA dailyNet 的口径，本文件独立复算 */
function refNet(diet, exercise, date, bmr) {
  const intake = diet.filter((d) => d.date === date).reduce((s, d) => s + Math.round(d.kcal || 0), 0);
  const burn = exercise.filter((e) => e.date === date).reduce((s, e) => s + Math.round(e.kcal || 0), 0);
  return intake - burn - bmr;
}
/* BMR 两条公式（独立复算）。
   主值选择规则：档案里有体脂率 ⇒ Katch-McArdle（更准），否则 Mifflin-St Jeor。
   ⚠️🔴 判据取的是 **user.bodyFat（用户档案字段）**，**不是** state.body.bodyFat（体脂秤最近一次录入）。
      两者不一致时（典型场景：秤上量出 18.2%、档案里没填）BMR 按「无体脂」走 Mifflin，差 11 kcal。
      这一条在 B 段末尾有专属断言钉住 —— 我第一次就是按 state.body 写的参考实现，
      期望值偏了 11 kcal（1656 vs 1667），四条断言一起红。 */
function refBmrMifflin(weight, height, age, gender) {
  return Math.round(10 * weight + 6.25 * height - 5 * age + (gender === 'male' ? 5 : -161));
}
function refBmrKatch(weight, bodyFat) {
  return Math.round(370 + 21.6 * (weight * (1 - bodyFat / 100)));
}
function refBmr(u) {
  return (u.bodyFat === null || u.bodyFat === undefined || !(u.bodyFat > 0))
    ? refBmrMifflin(u.weight, u.height, u.age, u.gender)
    : refBmrKatch(u.weight, u.bodyFat);
}

/* ============================================================
 * mock
 * ============================================================ */
const storage = {};
const noop = () => {};
const calls = [];
const compEvents = [];
const ctxStats = { total: 0, fillText: 0 };
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
const BOX = { '.trade-page': 430, '.holdings-page': 430, default: 420 };
function rectQuery() {
  const q = [];
  const r = {
    select: (s) => { q.push(s); return r; },
    selectAll: (s) => { q.push(s); return r; },
    in: () => r, fields: () => r, boundingClientRect: () => r,
    exec: (cb) => {
      const res = q.map(() => ({
        left: 0, top: 0, width: 430, height: 300, node: canvasNode(),
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
  nextTick: (fn) => fn(),
  showToast: (o) => calls.push(['showToast', o && o.title]),
  showModal: (o) => { calls.push(['showModal', o && o.title]); o && o.success && o.success({ confirm: false }); },
  showLoading: noop, hideLoading: noop,
  navigateTo: (o) => calls.push(['navigateTo', o && o.url]),
  navigateBack: () => calls.push(['navigateBack']),
  switchTab: noop, pageScrollTo: noop, stopPullDownRefresh: noop, setNavigationBarTitle: noop,
  setClipboardData: (o) => { calls.push(['setClipboardData', o]); o && o.success && o.success(); },
  chooseMedia: (o) => { calls.push(['chooseMedia', o]); o && o.fail && o.fail({ errMsg: 'cancel' }); },
  cloud: undefined,
};

const captured = { app: null, pages: [], components: [] };
global.App = (o) => { captured.app = o; };
global.Page = (o) => { captured.pages.push(o); };
global.Component = (o) => { captured.components.push(o); };
global.getApp = () => captured.app;
/* ⚠️ 真机上这里有当前页；测试环境恒为空 —— 这正是「即时通路不可依赖」的证据 */
global.getCurrentPages = () => [];

/* 组件实例 / 「组件是否已就绪」开关 */
const COMP = { ready: true, inst: null, page: null };

function mkSetData(inst) {
  return function (o, cb) {
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
}
function makeInstance(opt) {
  const inst = Object.create(opt);
  inst.data = JSON.parse(JSON.stringify(opt.data || {}));
  inst.setData = mkSetData(inst);
  inst.createSelectorQuery = rectQuery;
  /* 页面实例的 selectComponent —— 由 COMP.ready 控制「组件是否已就绪」，
     用来验「取不到组件时不能把待看标志吞掉」。 */
  inst.selectComponent = (sel) => {
    if (sel !== '#celeb') return null;
    return COMP.ready ? COMP.inst : null;
  };
  return inst;
}
/* 造一份 <celeb> 组件实例（模拟框架按 usingComponents 创建节点） */
function makeComp(opt) {
  const inst = Object.create(opt.methods || {});
  inst.data = JSON.parse(JSON.stringify(opt.data || {}));
  inst.setData = mkSetData(inst);
  /* triggerEvent 走**真实分发**：直接回调宿主页面的同名 handler，
     这样 comp.onClose() 就等于用户真的点了那个按钮，能顺带验宿主接线。 */
  inst.triggerEvent = (name, detail) => {
    compEvents.push([name, detail]);
    const p = COMP.page;
    if (name === 'close' && p && typeof p.onCelebClose === 'function') p.onCelebClose(detail);
  };
  if (opt.lifetimes && typeof opt.lifetimes.attached === 'function') opt.lifetimes.attached.call(inst);
  return inst;
}

function fresh() {
  Object.keys(storage).forEach((k) => { delete storage[k]; });
  captured.pages.length = 0;
  captured.components.length = 0;
  captured.app = null;
  calls.length = 0;
  compEvents.length = 0;
  ctxStats.total = 0; ctxStats.fillText = 0;
  COMP.ready = true; COMP.inst = null; COMP.page = null;
  Object.keys(require.cache).forEach((k) => { if (k.indexOf(MINI) === 0) delete require.cache[k]; });
}

function bootPage(relPath, state, query, afterLaunch) {
  fresh();
  storage['jianpan_v2'] = state;
  require(path.join(MINI, 'app.js'));
  captured.app.onLaunch.call(captured.app);
  if (typeof afterLaunch === 'function') afterLaunch(captured.app);
  captured.pages.length = 0;
  /* 框架会按 json 的 usingComponents 加载组件 —— 测试里手动 require 触发 Component() 注册 */
  require(path.join(MINI, 'components/celeb/celeb.js'));
  COMP.inst = makeComp(captured.components[captured.components.length - 1]);
  require(path.join(MINI, relPath));
  const mk = makeInstance(captured.pages[captured.pages.length - 1]);
  COMP.page = mk;
  if (typeof mk.onLoad === 'function') mk.onLoad.call(mk, query || {});
  if (typeof mk.onShow === 'function') mk.onShow.call(mk);
  if (typeof mk.onReady === 'function') mk.onReady.call(mk);
  return mk;
}
/* 🔴 活状态：boot 之后 store 里那一份才是生产里真被改的对象 */
function L() { return require(path.join(MINI, 'lib/store.js')).get(); }

const pad2 = (n) => String(n).padStart(2, '0');
const ymd = (d) => d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
function todayStr() { return ymd(new Date()); }
function daysAgo(n) { const d = new Date(); d.setDate(d.getDate() - n); return ymd(d); }

/* ============================================================
 * 种子：构造一个「昨天刚好封涨停」的存档
 *   昨天摄入 1500（两笔）/ 消耗 600（一笔）/ BMR 1667（Mifflin，档案无体脂）
 *   ⇒ 净缺口 = -767 ≤ 目标 -500，且昨天有记录 ⇒ 满足 settleDay 的三个涨停条件
 * ============================================================ */
const W = 72.8, FAT = 18.2, H = 175, AGE = 32;
const D1 = 900, D2 = 600, BURN = 600;
/* 种子档案里 user.bodyFat 刻意留空 ⇒ BMR 主值走 Mifflin-St Jeor（1667）。
   Katch 那一支在 B 段末尾单独验（把 user.bodyFat 填上，值必须变成 1656）。 */
const BMR_REF = refBmrMifflin(W, H, AGE, 'male');
function limitSeed(calc, opts) {
  opts = opts || {};
  const st = calc.defaultState();
  const Y = daysAgo(1);
  st.user = Object.assign({}, st.user, {
    userId: 'FT_CELEB', weight: W, startWeight: 75.5, height: 175,
    gender: 'male', age: 32, target: -500, activity: 'sedentary',
    bodyFat: null,          // ← 显式留空：BMR 走 Mifflin（见 BMR_REF 处注释）
  });
  st.body = Object.assign({}, st.body, {
    bmi: 22.4, bodyFat: FAT, muscleRate: 42.5, waterRate: 55.8, bodyAge: 28, visceralFat: 8,
  });
  st.diet = [
    { name: '午餐', kcal: D1, time: '12:00', date: Y },
    { name: '晚餐', kcal: D2, time: '19:00', date: Y },
  ];
  st.exercise = [{ name: '跑步', kcal: opts.burn === undefined ? BURN : opts.burn, time: '20:00', date: Y }];
  /* 跨天三件套：lastDate = 昨天 ⇒ checkDayRollover 会结算昨天 */
  st.lastDate = Y;
  st.settledDate = null;
  st.lastLimitUpDate = null;
  st.celebFired = false;
  st.limitUpStreak = 0;
  st.limitUpCount = 0;
  st.coins = 0; st.exp = 0; st.coinsEarnedTotal = 0;
  st.ach = {};
  st.bodyLog = [];
  st.weightLog = [{ date: daysAgo(4), weight: 73.6 }, { date: Y, weight: 73.1 }];
  return st;
}
/* 期望值：独立现算，不是抄内核 */
const EXP_NET = refNet(
  [{ date: daysAgo(1), kcal: D1 }, { date: daysAgo(1), kcal: D2 }],
  [{ date: daysAgo(1), kcal: BURN }],
  daysAgo(1), BMR_REF
);

/* ============================================================
 * 跑
 * ============================================================ */
out('mp_celeb_test —— 全屏涨停仪式运行时断言');
out('时间：' + new Date().toISOString());

/* ---------- A 组件本体 ---------- */
sec('A 组件本体（components/celeb）');
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  const page = bootPage('pages/market/market.js', limitSeed(c0));
  const calc = require(path.join(MINI, 'lib/calc.js'));
  const comp = COMP.inst;

  must(!!comp, '组件实例可取到（selectComponent 命中 #celeb）', String(!!comp));
  must(comp.data.coin === calc.COIN_LIMITUP, 'attached 从内核常量取健康币奖励',
    comp.data.coin + ' vs ' + calc.COIN_LIMITUP);
  must(comp.data.exp === calc.EXP_LIMITUP, 'attached 从内核常量取经验奖励',
    comp.data.exp + ' vs ' + calc.EXP_LIMITUP);

  /* ⚠️ 上面两条只证明「此刻读到的值等于常量」；真正的「没写死」守卫在 G 段
     （把常量改掉再重建组件，值必须跟着变）—— 两条一起才算数。 */

  /* 同样走的是「冷启动即涨停」链路 ⇒ 此刻组件已是显示态；先关掉再逐项验 show() */
  comp.hide();
  must(comp.data.visible === false, 'hide() 之后 visible = false', String(comp.data.visible));

  comp.show({ date: '2026-09-22', net: 812, streak: 3 });
  must(comp.data.visible === true, 'show() 之后 visible = true', String(comp.data.visible));
  must(comp.data.net === 812, 'net 照实写入 812', String(comp.data.net));
  must(comp.data.streak === 3, 'streak 照实写入 3', String(comp.data.streak));
  must(comp.data.date === '2026-09-22', 'date 照实写入', comp.data.date);

  /* 0 是合法值：不能被 `info.net || 0` 之外的写法吃掉，也不能反过来被兜成别的数 */
  comp.show({ date: 'x', net: 0, streak: 0 });
  must(comp.data.net === 0, 'net = 0 照实保留（不是被 || 兜成 0 以外的值）', String(comp.data.net));
  must(comp.data.streak === 1, 'streak = 0 ⇒ 回落 1（连板数最小为 1）', String(comp.data.streak));

  /* 空载荷不能崩（兜底通路在极端情况下可能带着 null 过来） */
  let e1 = null;
  try { comp.show(undefined); } catch (e) { e1 = e; }
  must(!e1, 'show(undefined) 不抛错', e1 && e1.message);
  must(comp.data.visible === true && comp.data.net === 0, '空载荷 ⇒ net 回落 0 且仍然显示', '');
  must(comp.data.date === '', '空载荷 ⇒ date 回落空串', JSON.stringify(comp.data.date));

  /* 关闭事件 */
  compEvents.length = 0;
  comp.onClose();
  must(comp.data.visible === false, 'onClose() 收起浮层', String(comp.data.visible));
  must(compEvents.length === 1 && compEvents[0][0] === 'close', 'onClose() 往外抛 close 事件',
    JSON.stringify(compEvents.map((x) => x[0])));
  must(compEvents[0][1] && compEvents[0][1].net === 0, 'close 载荷带回 net', JSON.stringify(compEvents[0][1]));
}

/* ---------- B 送达通路 ---------- */
sec('B 送达通路（lib/celeb-host.js）');
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  const page = bootPage('pages/market/market.js', limitSeed(c0));
  const HOST = require(path.join(MINI, 'lib/celeb-host.js'));
  const app = captured.app;
  const comp = COMP.inst;

  /* B1 没有待看 ⇒ 不弹、不改状态 */
  app.globalData.celebPending = false;
  comp.hide();
  must(HOST.pickShow(page) === false, '无待看标志 ⇒ pickShow 返回 false', '');
  must(comp.data.visible === false, '无待看标志 ⇒ 组件保持收起', String(comp.data.visible));

  /* B2 有待看 + 组件就绪 ⇒ 弹出并消费标志 */
  app.globalData.lastCelebrate = { date: '2026-09-20', net: 640, streak: 2 };
  app.globalData.celebPending = true;
  must(HOST.pickShow(page) === true, '有待看 ⇒ pickShow 返回 true', '');
  must(comp.data.visible === true, '有待看 ⇒ 组件显示', String(comp.data.visible));
  must(comp.data.net === 640 && comp.data.streak === 2, '载荷原样送达组件',
    comp.data.net + ' / ' + comp.data.streak);
  must(app.globalData.celebPending === false, '消费后标志清零（它是「还没给人看过」，不是「今天涨停过」）',
    String(app.globalData.celebPending));

  /* B3 幂等：同一份标志只消费一次 */
  must(HOST.pickShow(page) === false, '同一标志再消费 ⇒ false（消费一次就清）', '');

  /* B4 ⭐ 组件还没就绪 ⇒ 必须**留着标志**，不能吞（否则冷启动那次仪式永远看不到） */
  comp.hide();
  app.globalData.celebPending = true;
  COMP.ready = false;
  must(HOST.pickShow(page) === false, '组件未就绪 ⇒ pickShow 返回 false', '');
  must(app.globalData.celebPending === true,
    '⭐ 组件未就绪 ⇒ 标志**保持为真**（留给下一次生命周期，不能被吞掉）',
    String(app.globalData.celebPending));
  must(comp.data.visible === false, '组件未就绪 ⇒ 组件当然没显示', String(comp.data.visible));
  COMP.ready = true;
  must(HOST.pickShow(page) === true && comp.data.visible === true,
    '组件就绪后再来一次 ⇒ 补弹成功（兜底通路能自愈）', '');

  /* B5 deliver：即时通路 */
  comp.hide();
  must(HOST.deliver(page, { date: '2026-09-21', net: 700, streak: 1 }) === true,
    '组件就绪 ⇒ deliver 返回 true', '');
  must(comp.data.visible === true && comp.data.net === 700, 'deliver 载荷送达组件', String(comp.data.net));
  must(app.globalData.lastCelebrate && app.globalData.lastCelebrate.net === 700,
    'deliver 顺手更新 lastCelebrate（供兜底通路复用）', JSON.stringify(app.globalData.lastCelebrate));
  must(app.globalData.celebPending === false, 'deliver 也把待看标志清掉（已经给人看过了）', '');

  /* B6 送不到时不能误清标志 */
  app.globalData.celebPending = true;
  COMP.ready = false;
  must(HOST.deliver(page, { net: 1 }) === false, '组件未就绪 ⇒ deliver 返回 false', '');
  must(app.globalData.celebPending === true,
    '⭐ 送不到 ⇒ 标志不能被误清（否则即时通路失败就等于把仪式丢了）', '');
  COMP.ready = true;
  app.globalData.celebPending = false;

  /* B7 交叉验证我的参考 BMR 与内核同口径（不一致 ⇒ 我对「主值用哪个公式、读哪个字段」的理解错了） */
  const calc = require(path.join(MINI, 'lib/calc.js'));
  const u0 = L().user;
  must(calc.calcBMR() === BMR_REF,
    '档案无体脂 ⇒ calcBMR() = Mifflin ' + BMR_REF, 'got ' + calc.calcBMR());
  must(refBmr(u0) === calc.calcBMR(), 'calcBMR() === 独立复算（同一取字段口径）',
    refBmr(u0) + ' vs ' + calc.calcBMR());
  /* Katch 那一支：档案填上体脂 ⇒ 必须换公式（差 11 kcal，两支都验才算钉住口径） */
  u0.bodyFat = FAT;
  must(calc.calcBMR() === refBmrKatch(W, FAT),
    '档案填上体脂 ' + FAT + '% ⇒ calcBMR() 换成 Katch-McArdle ' + refBmrKatch(W, FAT),
    'got ' + calc.calcBMR());
  must(refBmr(u0) === calc.calcBMR(), 'Katch 支也与独立复算一致', '');
  u0.bodyFat = null;                                    // 还原，别影响后面的段
  must(calc.calcBMR() === BMR_REF, '还原档案体脂 ⇒ BMR 回到 ' + BMR_REF, 'got ' + calc.calcBMR());
}

/* ---------- C app.js 的 celebrate 钩子 ---------- */
sec('C app.js · celebrate 钩子');
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  bootPage('pages/me/me.js', limitSeed(c0));
  const app = captured.app;

  must(typeof app.onCelebrate === 'function', 'app 暴露 onCelebrate', typeof app.onCelebrate);

  /* 即时通路在测试环境必然送不到（getCurrentPages 为空）——这不是缺陷，是兜底通路的存在理由 */
  must(app.deliverToPage('onCelebrate', { net: 1 }) === false,
    '⚠️ 页面栈为空 ⇒ 尽力路由返回 false（真机上有页面，这条通路才成立）', '');

  /* 钩子只通知、不发币：币与涨停计数必须一动不动 */
  const st = L();
  const beforeCoins = st.coins, beforeCount = st.limitUpCount, beforeExp = st.exp;
  calls.length = 0;
  app.onCelebrate({ date: '2026-09-19', net: 520, streak: 4 });
  must(st.coins === beforeCoins && st.exp === beforeExp && st.limitUpCount === beforeCount,
    '⭐ 钩子不发币不改计数（币在 settleDay 里早就算好并落盘了，写第二份判定就是两个真相）',
    st.coins + '/' + st.exp + '/' + st.limitUpCount);
  must(app.globalData.celebPending === true, '钩子置「待看」标志', String(app.globalData.celebPending));
  must(app.globalData.lastCelebrate && app.globalData.lastCelebrate.net === 520,
    '钩子留住事件载荷', JSON.stringify(app.globalData.lastCelebrate));
  /* 也**不再弹 toast 兜底**：仪式本身才是那个提示，再叠一条就是两个真相 */
  must(calls.filter((x) => x[0] === 'showToast').length === 0,
    '⭐ 钩子不弹 toast（本轮有意删掉兜底；若哪天加回来，这条会红）',
    JSON.stringify(calls.filter((x) => x[0] === 'showToast')));

  /* 待看标志是「还没给人看过」，与「今天涨停过」是两件事 —— 后者另有幂等锚 */
  app.globalData.celebPending = false;
  app.onCelebrate(null);
  must(app.globalData.lastCelebrate === null, 'null 载荷 ⇒ lastCelebrate 记 null（不崩）', '');
  must(app.globalData.celebPending === true, 'null 载荷也照样置标志', '');
}

/* ---------- D 端到端：真数据触发涨停 → 首页浮出 ---------- */
sec('D 端到端（昨日净缺口 -767 ≤ -500 ⇒ 结算发币 ⇒ 首页补弹仪式）');
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  const snap = {};
  const snap2 = {};                    // ⚠️ 必须声明在 D 段块**内**且在使用之前：
                                       // 写成块外的 `var snap2` 会因为「声明提升但赋值不提升」
                                       // 而在 afterLaunch 回调里炸成 undefined 属性赋值。
  const page = bootPage('pages/market/market.js', limitSeed(c0), {}, (app) => {
    /* 这一刀切在 onLaunch 之后、页面加载之前：此时页面栈还是空的 */
    snap.pending = app.globalData.celebPending;
    snap.info = app.globalData.lastCelebrate;
    snap.count = L().limitUpCount;
    snap.settled = L().settledDate;
    snap.lastLimit = L().lastLimitUpDate;
    snap.streak = L().limitUpStreak;
    snap.coins = L().coins;
    snap.earned = L().coinsEarnedTotal;
    /* 诊断开关（默认不打印）：涨停没触发时一眼看出是哪个前提没满足。
       用法：MP_CELEB_DBG=1 node promo/mp_celeb_test.js
       ⚠️ 走 stderr，不污染 _celeb_out.txt 报告，也不干扰闸驱动器的尾部输出。 */
    if (process.env.MP_CELEB_DBG) {
      const cc = require(path.join(MINI, 'lib/calc.js'));
      console.error('[dbg] lastDate=' + L().lastDate + ' today=' + todayStr()
        + ' settled=' + L().settledDate + ' lastLimit=' + L().lastLimitUpDate
        + ' dietN=' + (L().diet || []).length + ' exN=' + (L().exercise || []).length
        + ' bmr=' + cc.calcBMR() + ' net=' + cc.dailyNet(daysAgo(1))
        + ' target=' + (L().user && L().user.target) + ' count=' + L().limitUpCount);
    }
  });
  const st = L();
  const comp = COMP.inst;
  const calc = require(path.join(MINI, 'lib/calc.js'));

  /* 前提自检：种子确实满足涨停三条件（否则下面全是在验一个没发生的事） */
  must(EXP_NET === -767, '独立现算的净缺口是 -767（前提自检）', String(EXP_NET));
  must(EXP_NET <= st.user.target, '净缺口 ≤ 目标（前提自检）', EXP_NET + ' ≤ ' + st.user.target);

  must(snap.count === 1, '结算把涨停计数从 0 加到 1', 'got ' + snap.count);
  must(snap.coins > 0 && snap.earned > 0, '结算真发了币（不是只加计数）',
    'coins=' + snap.coins + ' earned=' + snap.earned);
  must(snap.settled === daysAgo(1), '幂等锚 settledDate = 昨天', String(snap.settled));
  must(snap.lastLimit === daysAgo(1), 'lastLimitUpDate = 昨天', String(snap.lastLimit));
  must(snap.streak === 1, '首板 ⇒ limitUpStreak = 1', String(snap.streak));

  must(snap.pending === true, '⭐ onLaunch 里结算触发涨停 ⇒ 待看标志置真（此时页面栈为空，即时通路送不到）',
    String(snap.pending));
  must(snap.info && snap.info.net === EXP_NET, '载荷 net = 独立现算的 -767', JSON.stringify(snap.info));
  must(snap.info && snap.info.date === daysAgo(1), '载荷 date = 昨天', JSON.stringify(snap.info));
  must(snap.info && snap.info.streak === 1, '载荷 streak = 1', JSON.stringify(snap.info));

  /* 页面起来之后：兜底通路把仪式补出来 */
  must(comp.data.visible === true, '⭐ 首页 onShow/onReady 的兜底通路把仪式补弹出来',
    'visible=' + comp.data.visible);
  must(comp.data.net === EXP_NET, '浮层上那个大数 = 独立现算的缺口', String(comp.data.net));
  must(comp.data.coin === calc.COIN_LIMITUP && comp.data.exp === calc.EXP_LIMITUP,
    '浮层三格奖励 = 内核常量', comp.data.coin + ' / ' + comp.data.exp);
  must(captured.app.globalData.celebPending === false, '页面消费之后标志清零', '');
  must(comp.data.visible === true, '消费之后浮层仍开着（不是消费即关闭）', '');

  /* 页面再 onShow（例如从子页返回）不能重复弹、也不该把它关掉 */
  page.onShow();
  must(comp.data.visible === true && captured.app.globalData.celebPending === false,
    '页面再次 onShow ⇒ 不重复弹、也不误关', 'visible=' + comp.data.visible);

  /* 幂等：手动再结算同一天，什么都不该发生 */
  const n1 = st.limitUpCount, coins1 = st.coins;
  calc.settleDay(daysAgo(1));
  must(st.limitUpCount === n1 && st.coins === coins1, '同一日期再结算 ⇒ 幂等（计数与币都不动）',
    st.limitUpCount + ' / ' + st.coins);

  /* ⭐ 上线即涨停这一条最重要的守卫：净缺口不达标时**绝不能**弹 */
  const p2 = bootPage('pages/market/market.js', limitSeed(c0, { burn: 0 }), {}, (app) => {
    snap2.pending = app.globalData.celebPending;
    snap2.count = L().limitUpCount;
  });
  must(snap2.count === 0, '消耗改 0 ⇒ 净缺口不达标 ⇒ 不涨停（负控：断言有区分度）', 'got ' + snap2.count);
  must(snap2.pending === false, '不涨停 ⇒ 待看标志保持 false', '');
  must(COMP.inst.data.visible === false, '不涨停 ⇒ 组件不显示',
    'visible=' + COMP.inst.data.visible);
  must(p2, '不涨停时页面照常加载', '');
}

/* ---------- E 5 个 tab 页接线 ---------- */
sec('E 接线 · 5 个 tab 页都能弹');
{
  const PAGES = [
    ['market', 'refresh'],
    ['holdings', 'refreshFromState'],
    ['trade', 'refresh'],
    ['board', 'refresh'],
    ['me', 'refresh'],
  ];
  PAGES.forEach(([name, entry]) => {
    const c0 = require(path.join(MINI, 'lib/calc.js'));
    const page = bootPage('pages/' + name + '/' + name + '.js', limitSeed(c0));
    const comp = COMP.inst;
    must(typeof page.onCelebrate === 'function', name + ' · 有 onCelebrate 入口', typeof page.onCelebrate);
    must(typeof page.onCelebClose === 'function', name + ' · 有 onCelebClose 入口', typeof page.onCelebClose);
    must(comp.data.visible === true, name + ' · 冷启动涨停 ⇒ 首页补弹', 'visible=' + comp.data.visible);

    /* 点「收下奖励，继续盯盘」⇒ 组件关闭 + 宿主页面重算（币/经验/段位都变了） */
    let n = 0;
    const r0 = page[entry];
    page[entry] = function () { n++; return r0.apply(this, arguments); };
    comp.onClose();
    must(comp.data.visible === false, name + ' · 点关闭 ⇒ 浮层收起', String(comp.data.visible));
    must(n >= 1, name + ' · 点关闭 ⇒ 页面走 ' + entry + '() 重算', 'called=' + n);

    /* 即时通路：清掉待看标志后，deliver 直接送达 */
    captured.app.globalData.celebPending = false;
    const HOST = require(path.join(MINI, 'lib/celeb-host.js'));
    must(HOST.deliver(page, { date: '2026-09-18', net: 901, streak: 1 }) === true,
      name + ' · 即时通路送达成功', '');
    must(comp.data.visible === true && comp.data.net === 901, name + ' · 即时通路载荷到位',
      String(comp.data.net));
  });
}

/* ---------- F 静态接线完整性（防漏一页） ---------- */
sec('F 静态接线（wxml/json/wxss 关键行）');
{
  const TABS = ['market', 'holdings', 'trade', 'board', 'me'];
  TABS.forEach((n) => {
    const wxml = fs.readFileSync(path.join(MINI, 'pages', n, n + '.wxml'), 'utf8');
    const json = fs.readFileSync(path.join(MINI, 'pages', n, n + '.json'), 'utf8');
    must(wxml.indexOf('<celeb id="celeb" bind:close="onCelebClose" />') >= 0,
      n + '.wxml 挂了 <celeb id="celeb"> 组件', '');
    must(json.indexOf('"/components/celeb/celeb"') >= 0, n + '.json 注册了 celeb 组件', '');
    must(wxml.indexOf('<celeb') > wxml.lastIndexOf('</view>'),
      n + '.wxml 把组件挂在 .page 之外（浮层不受页面 padding/display 影响）', '');
    const js = fs.readFileSync(path.join(MINI, 'pages', n, n + '.js'), 'utf8');
    must(js.indexOf("require('../../lib/celeb-host.js')") >= 0, n + '.js 引入 celeb-host', '');
    must(js.indexOf('CELEB.pickShow(this)') >= 0, n + '.js 生命周期里接了 pickShow 兜底', '');
  });

  const compJson = fs.readFileSync(path.join(MINI, 'components', 'celeb', 'celeb.json'), 'utf8');
  const compCfg = JSON.parse(compJson);
  must(compCfg.component === true, '组件 json 声明 component:true', '');
  /* 🔴 styleIsolation 必须写在 json 的**顶层**：写成 `"options": {"styleIsolation": ...}`
     是无效位置（options 是 js 里的写法）⇒ 配置被静默忽略 ⇒ 组件退回 isolated
     ⇒ app.wxss 的 .celeb* 一条都进不来（⑥c 实测：浮层宽 144、大数高 41.6、跑到文档流底部）。 */
  must(compCfg.styleIsolation === 'apply-shared',
    '⭐ 组件 json **顶层** 声明 styleIsolation:apply-shared（否则 app.wxss 进不来，整个浮层是白板）',
    JSON.stringify({ styleIsolation: compCfg.styleIsolation, options: compCfg.options }));
  must(compCfg.options === undefined,
    '⛔ 组件 json 里没有 options 字段（那是个无效位置，会让 styleIsolation 静默失效）',
    JSON.stringify(compCfg.options));

  const compWxss = fs.readFileSync(path.join(MINI, 'components', 'celeb', 'celeb.wxss'), 'utf8');
  /* ⚠️ 剥注释再查：本文件第 41 行注释为讲解「为什么不能写 view.celeb」会**字面出现**该串，
     裸 indexOf('view.celeb') 会把注释文字算进去 ⇒ 断言误报失败。真实选择器只认 .fab-fixed。 */
  const compWxssClean = compWxss.replace(/\/\*[\s\S]*?\*\//g, '');
  const compWxml = fs.readFileSync(path.join(MINI, 'components', 'celeb', 'celeb.wxml'), 'utf8');
  /* ⚠️ 这里原先断言的是 `view.celeb{position:fixed}` —— 那个写法在 WXSS 里**静默失效**
     （只支持 .class / #id / element / element,element / ::after / ::before；
      element.class 组合不在列表里）⇒ ⑥c 实测浮层变成文档流里的普通块。
     现在的形态：wxml 根节点带专属类 .fab-fixed + wxss 用纯单类选择器 + !important。 */
  must(/\.fab-fixed\s*\{[^}]*position\s*:\s*fixed/.test(compWxss),
    '⭐ 组件 wxss 用专属类 .fab-fixed 把浮层钉成 fixed（小程序整页滚动，absolute 会画到屏幕外）', '');
  must(/\.fab-fixed\s*\{[^}]*!important/.test(compWxss),
    '⭐ 那条 fixed 带 !important（不依赖 wxss 加载顺序，也不碰 WXSS 的选择器支持边界）', '');
  must(/\.fab-fixed\s*\{[^}]*top\s*:\s*0/.test(compWxss) && /\.fab-fixed\s*\{[^}]*left\s*:\s*0/.test(compWxss),
    '那条 fixed 还显式写了 top/left/right/bottom:0（不把定位押在 inset 简写上）', '');
  const compJs = fs.readFileSync(path.join(MINI, 'components', 'celeb', 'celeb.js'), 'utf8');
  must(/styleIsolation\s*:\s*'apply-shared'/.test(compJs),
    '组件 js 里也写了 options.styleIsolation（与 json 顶层字段双保险）', '');
  must(/class="celeb show fab-fixed"/.test(compWxml),
    '组件根节点 class 同时带 celeb / show / fab-fixed 三个类', '');
  must(compWxml.indexOf('fab-fixed') >= 0 && /\.fab-fixed/.test(compWxss),
    'fab-fixed 在 wxml 与 wxss 两侧成对出现（否则规则没有落点）', '');
  must(compWxssClean.indexOf('view.celeb') < 0,
    '⛔ 组件 wxss 不再出现 element.class 组合（WXSS 不支持，会静默失效）', '');
  must(/\.celeb\s+\.btn\s*\{\s*line-height\s*:\s*1\.333/.test(compWxss),
    '组件内 .btn 行盒按 UA 4/3 校正（1.333）', '');
  must(/\.celeb\s+\.heading\s+\.em\s*\{\s*color\s*:\s*#ffb800/.test(compWxss),
    '「封涨停」放弃 background-clip:text，降级纯琥珀色（否则字会直接消失）', '');
  must(compWxss.indexOf('.celeb .big .small') >= 0,
    'PWA 的 .big small（标签选择器）已换成 .small 类', '');
  /* ⚠️ 只找**通配选择器**（行首的 `*`）：注释里为了强调写了 markdown 的 **粗体**，
     用 indexOf('*') 判断会被误伤（我第一次就是这么写的）。 */
  must(!/^\s*\*\s*\{/m.test(compWxss), '组件 wxss 没有 * 通配选择器（会让 wcsc 报错、整包白屏）', '');

  const host = fs.readFileSync(path.join(MINI, 'lib', 'celeb-host.js'), 'utf8');
  must(host.indexOf('if (!comp) return false') >= 0,
    'celeb-host 在取不到组件时提前返回（不清标志）', '');
  const appJs = fs.readFileSync(path.join(MINI, 'app.js'), 'utf8');
  must(appJs.indexOf('celebPending') >= 0 && appJs.indexOf('lastCelebrate') >= 0,
    'app.js 同时维护 lastCelebrate 与 celebPending 两条真相线索', '');
}

/* ---------- G 专属负控 ---------- */
sec('G 专属负控（证明上面的断言不是恒真的）');
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  const page = bootPage('pages/market/market.js', limitSeed(c0));
  const app = captured.app;
  const comp = COMP.inst;

  /* 负控 1：把标志手动清掉 ⇒ 组件不该弹（证明 D 段的 visible=true 真来自那个标志） */
  comp.hide();
  app.globalData.celebPending = false;
  page.onShow();
  must(comp.data.visible === false,
    '负控 · 没有待看标志 ⇒ onShow 不会凭空弹出仪式', String(comp.data.visible));

  /* 负控 2：把「已结算」锚改回未结算 ⇒ 撤掉涨停（证明 D 段读的是真结算结果） */
  const st = L();
  const n1 = st.limitUpCount;
  st.settledDate = null;
  st.lastLimitUpDate = null;
  const c1 = st.coins;
  require(path.join(MINI, 'lib/calc.js')).settleDay(daysAgo(1));
  must(st.limitUpCount === n1 + 1 && st.coins > c1,
    '负控 · 撤掉幂等锚再结算一次 ⇒ 真的会再发一次（说明锚确实在起作用）',
    st.limitUpCount + ' / ' + st.coins);

  /* 负控 3：组件未就绪时，待看标志必须存活 —— 反向验一遍（若这里返回 true 就说明标志被吞） */
  const HOST = require(path.join(MINI, 'lib/celeb-host.js'));
  app.globalData.celebPending = true;
  COMP.ready = false;
  const r1 = HOST.pickShow(page);
  must(r1 === false && app.globalData.celebPending === true,
    '负控 · 组件未就绪 ⇒ 标志必须活着（false 且 pending 仍为真）',
    'ret=' + r1 + ' pending=' + app.globalData.celebPending);
  COMP.ready = true;
  app.globalData.celebPending = false;

  /* 负控 4：载荷真正参与渲染 —— 换一份载荷，浮层上的数字必须跟着换 */
  comp.show({ date: 'z', net: 123, streak: 1 });
  const v1 = comp.data.net;
  comp.show({ date: 'z', net: 456, streak: 1 });
  must(v1 === 123 && comp.data.net === 456,
    '负控 · 换载荷 ⇒ 浮层数字跟着换（不是渲染固定常量）', v1 + ' → ' + comp.data.net);

  /* 负控 5：证明奖励三格**真读内核常量**而不是写死 200 / 30。
     PWA 的 HTML 里那两格是硬编码的「+200 / +30」，小程序若照抄就会在常量调整后静默显示旧值。
     做法：临时改导出对象上的常量 → 重建组件（attached 重新跑）→ 值必须跟着变。
     ⚠️ 一定要还原：calc 模块对象在同一进程里被后续段复用，改完不还原就是污染。 */
  const calcMod = require(path.join(MINI, 'lib/calc.js'));
  const oCoin = calcMod.COIN_LIMITUP, oExp = calcMod.EXP_LIMITUP;
  calcMod.COIN_LIMITUP = 777; calcMod.EXP_LIMITUP = 88;
  COMP.inst = makeComp(captured.components[captured.components.length - 1]);
  must(COMP.inst.data.coin === 777 && COMP.inst.data.exp === 88,
    '负控 · 改掉内核常量 ⇒ 组件奖励格跟着变（证明没写死 200/30，也没抄 PWA 的硬编码）',
    COMP.inst.data.coin + ' / ' + COMP.inst.data.exp);
  calcMod.COIN_LIMITUP = oCoin; calcMod.EXP_LIMITUP = oExp;
  must(calcMod.COIN_LIMITUP === 200 && calcMod.EXP_LIMITUP === 30,
    '负控 · 常量已还原 200 / 30（不留污染给后续段）',
    calcMod.COIN_LIMITUP + ' / ' + calcMod.EXP_LIMITUP);
}

out('');
out('========================================');
out('通过 ' + pass + ' 项，失败 ' + fails.length + ' 项');
if (fails.length) fails.forEach((f) => out('  ✗ ' + f));
out('RESULT=' + (fails.length ? 'FAIL' : 'OK'));
fs.writeFileSync(OUT, lines.join('\n') + '\n', 'utf8');
console.log(lines.join('\n'));
process.exit(fails.length ? 1 : 0);
