/* mp_gacha_test.js —— 涨停抽卡 · 交易员图鉴（pages/gacha）运行时断言
 *
 * 抽卡是随机的 ⇒ 断言分两层，缺一不可：
 *   ① **确定性层**：monkeypatch Math.random 到定值，把「稀有度映射」「十连保底」「满星返币」
 *      三类随机逻辑压成可复现的确定结果 —— 这是唯一能给出精确期望值的办法
 *   ② **不变量层**：无论抽到什么都必须成立的（扣币额、totalDraws、碎片只增不减、幂等锚…）
 *
 * 覆盖：
 *   A hero 四格（余额 / 星数 / 收集度 / 张数）+ 概率公示与 RARITY 同源
 *   B 图鉴格子（已拥有带碎片进度 / 满星 MAX / 未拥有打码）
 *   C 稀有度映射的 7 个边界点（确定性）
 *   D 十连保底：全 N 也必得 1 张稀有（确定性）+ 扣币 450
 *   E 满星重复卡返币（确定性）+ 弹层 resultRefund 不丢（drawCard 钩子签名修复的回归守卫）
 *   F 币不足拦截（不扣币、不记 totalDraws、不开弹层、发 toast）
 *   G 里程碑（reach 判据 / 领取发币 / 幂等 / 未达标拦下）
 *   H 空存档
 *
 * ⚠️ const calc = require(...) 必须写在 boot 之后（技能铁律）。
 * ⚠️ 每段用**独立 boot**：抽卡会改 state（碎片/币/收集度），共用实例会让期望值互相污染。
 * 🔴 **期望值一律读活状态 `L()`，⛔不要读种子对象 `seed.coins` 这类标量**：
 *    boot 时 store 里的活状态是 loadState() 的**浅拷贝** ⇒ 标量是拷贝、只有数组/对象共享引用。
 *    我第一版就是拿 seed.coins 当活状态断言，「扣币 450」「返币 10」全部看起来没发生 ——
 *    是**测试错**，生产路径里 drawCard 改的一直是模块内真 state。（踩过一次，别重走。）
 *
 * 用法：node promo/mp_gacha_test.js   退出码 0=全过
 * 报告落盘：promo/_gacha_out.txt
 */
'use strict';
const path = require('path');
const fs = require('fs');

const MINI = 'E:\\WeChatProjects\\jianpan\\miniprogram';
const OUT = path.join(__dirname, '_gacha_out.txt');

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
 * 独立参考实现（抄表 + 自己重写判定，不复用 calc 的同名函数）
 * ============================================================ */
const STAR_NEED = [0, 1, 3, 9];          // 1★/2★/3★ 所需碎片
const MAX_FRAG = 9;
const COLLECT_TOTAL = 45;                // 15 张 × 3 星
const REFUND_SPEC = { N: 10, R: 25, SR: 100 };
const RARITY_SPEC = { N: { name: '普通', rate: 70 }, R: { name: '稀有', rate: 25 }, SR: { name: '传说', rate: 5 } };
const MS_SPEC = [
  { pct: 30, coin: 200 }, { pct: 50, coin: 500 }, { pct: 70, coin: 800 },
  { pct: 90, coin: 1200 }, { pct: 100, coin: 2000 },
];
function starOf(cnt) {
  if (cnt >= STAR_NEED[3]) return 3;
  if (cnt >= STAR_NEED[2]) return 2;
  if (cnt >= STAR_NEED[1]) return 1;
  return 0;
}
function starStrOf(s) { let o = ''; for (let i = 1; i <= 3; i++) o += (i <= s) ? '★' : '☆'; return o; }
function totalStarsOf(cardList, owned) {
  let sum = 0;
  cardList.forEach((c) => { sum += starOf(owned[c.id] || 0); });
  return sum;
}
function pctOfStars(s) { return Math.round(s / COLLECT_TOTAL * 100); }
/* 碎片进度（cardCellHTML 的口径：分母是当前档的跨度，不是 need） */
function fragOf(own) {
  const s = starOf(own);
  if (s >= 3) return null;
  const need = STAR_NEED[s + 1];
  const span = need - STAR_NEED[s];
  return { pct: Math.round((own - STAR_NEED[s]) / span * 100), txt: own + ' / ' + need + ' 碎片' };
}

/* ============================================================
 * mock（与 mp_me_test 同款）
 * ============================================================ */
const storage = {};
const noop = () => {};
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
  getAccountInfoSync: () => ({ miniProgram: { appId: 'wxtest', version: '2.7.60', envVersion: 'develop' } }),
  getUpdateManager: () => ({ onCheckForUpdate: noop, onUpdateReady: noop, onUpdateFailed: noop, applyUpdate: noop }),
  createSelectorQuery: () => ({ select: () => ({ boundingClientRect: () => ({ exec: noop }) }), exec: noop }),
  nextTick: (fn) => setTimeout(fn, 0),
  showToast: (o) => calls.push(['showToast', o && o.title]),
  showModal: (o) => { calls.push(['showModal', o && o.title]); o && o.success && o.success({ confirm: false }); },
  showLoading: noop, hideLoading: noop,
  navigateTo: (o) => calls.push(['navigateTo', o && o.url]),
  navigateBack: () => calls.push(['navigateBack']),
  switchTab: noop, pageScrollTo: noop,
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
  inst.createSelectorQuery = () => ({ select: () => ({ boundingClientRect: () => ({ exec: noop }) }), exec: noop });
  return inst;
}

const pad2 = (n) => String(n).padStart(2, '0');
const ymd = (d) => d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
function todayStr() { return ymd(new Date()); }

/* ============================================================
 * 种子
 * ============================================================ */
/* 抽卡会连带动到成就（首抽 / 集齐 / 欧气…）⇒ 种子必须把「会被这次测试触发的成就」全部预置掉，
   否则那笔补发的币会混进「扣币 / 返币 / 余额」的期望里。
   自洽性说明：`state.ach` 是**幂等锚**，一旦 true 永不复位 ⇒
   「数据不满足也预置 true」是允许的（PWA 也不会撤销），只要「数据满足的没漏置」。逐条对照：
     untie(减重 ≥1kg)：种子 75.5→72.8 = 2.7kg ⇒ **数据满足，必须预置**（漏了它冷启动就 +50 币）
     open(codex, ≥1 张卡)：种子里有 4 张 ⇒ **必须预置**（漏了 +20）
     firstgacha(totalDraws≥1)：totalDraws=0 ⇒ 不满足；预置掉可免「第一次抽卡悄悄 +20」
     rarefind(抽到第一张 R)：种子全是 N ⇒ 不满足；但 D 段的十连保底**必定**产出一张 R
       ⇒ **必须预置**，否则「扣币 450」会变成 400（实测踩到）
     chosen(抽到第一张 SR)：本文件的 random 只出 N/R ⇒ 不触发；预置是保险
     fulln(N 卡 6 张)：种子 4 张 ⇒ D 段十连把第 5 张 gerou 抽出来 ⇒ 仍差 1 张 ⇒ 不触发
     maxstar(45 星)：种子 8 星 ⇒ 不满足（G 段的 5 张满星只有 15 星）
     smallmeat(累计 500)：coinsEarnedTotal=0 ⇒ 不满足（只有 E 段的返币 +10）
     dividend(持币 ≥1000)：种子 900 与 700 ⇒ 不满足
     gachaking(totalDraws≥20)：单段最多抽 10 次 ⇒ 不满足
   ⚠️ 也就是说：**每次往种子里加「会让某个成就达标的数据」，都要回来对一遍这张表。** */
const SEED_ACH = ['untie', 'open', 'firstgacha', 'rarefind', 'chosen'];
function baseSeed(calc, opts) {
  opts = opts || {};
  const st = calc.defaultState();
  st.user = Object.assign({}, st.user, { userId: 'FT_GACHA', weight: 72.8, startWeight: 75.5 });
  st.coins = opts.coins === undefined ? 900 : opts.coins;
  st.coinDate = todayStr();
  st.diet = [];
  st.exercise = [];
  st.coinsEarnedTotal = 0;
  st.totalDraws = 0;
  st.collectRewards = {};
  st.ach = {};
  SEED_ACH.forEach((id) => {
    if (!calc.ACHIEVEMENTS.some((a) => a.id === id)) throw new Error('成就 id 不存在：' + id);
    st.ach[id] = true;
  });
  st.cards = Object.assign({}, opts.cards || {});
  Object.keys(st.cards).forEach((id) => {
    if (!calc.CARDS.some((c) => c.id === id)) throw new Error('卡 id 不存在：' + id);
  });
  return st;
}
/* A/B/H 用的基础档：1★(0% 进度) / 3★(MAX) / 2★(0% 进度) / 2★(17% 进度) ⇒ 8 星 = 18% */
function cardsBasic(calc) {
  const id = (i) => calc.CARDS[i].id;
  const o = {};
  o[id(0)] = 1;   // sanhu   1★  1/3 → 0%
  o[id(1)] = 9;   // xiaosan 3★  MAX
  o[id(2)] = 3;   // zhuigao 2★  3/9 → 0%
  o[id(3)] = 4;   // chaodi  2★  4/9 → 17%
  return o;
}
/* G 用的里程碑档：5 张满星 ⇒ 15 星 = 33% ⇒ 跨过 30% 但没到 50% */
function cardsMilestone(calc) {
  const o = {};
  for (let i = 0; i < 5; i++) o[calc.CARDS[i].id] = 9;
  return o;
}
/* 固定 random=0.9 时 rollOne 会抽到的 N 卡（池内第 6 张） */
function gerouId(calc) { return calc.CARDS.filter((x) => x.rarity === 'N')[5].id; }

function fresh() {
  Object.keys(storage).forEach((k) => { delete storage[k]; });
  captured.pages.length = 0;
  captured.app = null;
  calls.length = 0;
  Object.keys(require.cache).forEach((k) => { if (k.indexOf(MINI) === 0) delete require.cache[k]; });
}
function bootPage(state) {
  fresh();
  storage['jianpan_v2'] = state;
  require(path.join(MINI, 'app.js'));
  captured.app.onLaunch.call(captured.app);
  captured.pages.length = 0;
  require(path.join(MINI, 'pages/gacha/gacha.js'));
  const mk = makeInstance(captured.pages[captured.pages.length - 1]);
  if (typeof mk.onLoad === 'function') mk.onLoad.call(mk, {});
  if (typeof mk.onShow === 'function') mk.onShow.call(mk);
  return mk;
}
function withRandom(v, fn) {
  const orig = Math.random;
  Math.random = () => v;
  try { return fn(); } finally { Math.random = orig; }
}
function tap(dataset) { return { currentTarget: { dataset: dataset || {} } }; }
/* 🔴 活状态：boot 之后 store 里那一份就是「生产里真被改的对象」 */
function L() { return require(path.join(MINI, 'lib/store.js')).get(); }

/* ============================================================
 * 跑
 * ============================================================ */
out('mp_gacha_test —— 涨停抽卡运行时断言');
out('时间：' + new Date().toISOString());

let page = null, calc = null;

/* ---------- A hero ---------- */
sec('A hero 四格 + 概率公示');
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  page = bootPage(baseSeed(c0, { cards: cardsBasic(c0) }));
  calc = require(path.join(MINI, 'lib/calc.js'));   // ⚠️ boot 之后
  const d = page.data;

  must(calc.CARDS.length === 15, '内核 15 张卡', 'got ' + calc.CARDS.length);
  must(calc.COLLECT_TOTAL === COLLECT_TOTAL, 'COLLECT_TOTAL 仍等于 15×3 = 45', 'got ' + calc.COLLECT_TOTAL);
  must(d.collectTotal === COLLECT_TOTAL && d.cardTotal === 15, '页面 45 星 / 15 张',
    'got ' + d.collectTotal + '/' + d.cardTotal);

  const stars = totalStarsOf(calc.CARDS, L().cards);
  must(stars === 8, '星数独立现算 = 1+3+2+2 = 8', 'got ' + stars);
  must(d.stars === stars, 'hero 星数与独立现算一致', 'got ' + d.stars);
  must(d.collectPct === pctOfStars(stars) && d.collectPct === 18, '收集度 = round(8/45×100) = 18%', 'got ' + d.collectPct);
  must(d.owned === 4, '张数 = 4', 'got ' + d.owned);
  must(d.coins === 900, '余额 = 活状态 coins = 900', 'got ' + d.coins);
  must(d.cardCost === 50 && d.cardCost10 === 450, '单抽 50 / 十连 450', 'got ' + d.cardCost + '/' + d.cardCost10);

  must(d.rateRow.length === 3, '概率公示 3 行', 'got ' + d.rateRow.length);
  must(d.rateRow[0].text === '普通 70%' && d.rateRow[1].text === '稀有 25%' && d.rateRow[2].text === '传说 5%',
    '文案 = RARITY 现算（不是页面写死的字符串）', 'got ' + d.rateRow.map((r) => r.text).join(' | '));
  must(d.rateRow[2].color === '#ffb800', '传说行取 RARITY.SR.color', 'got ' + d.rateRow[2].color);
  ['N', 'R', 'SR'].forEach((k) => {
    must(calc.RARITY[k].rate === RARITY_SPEC[k].rate && calc.RARITY[k].name === RARITY_SPEC[k].name,
      '内核 RARITY.' + k + ' 与硬编码表一致', 'got ' + JSON.stringify(calc.RARITY[k]));
  });
  must(calc.REFUND.N === REFUND_SPEC.N && calc.REFUND.R === REFUND_SPEC.R && calc.REFUND.SR === REFUND_SPEC.SR,
    'REFUND 表未漂', 'got ' + JSON.stringify(calc.REFUND));
  must(calc.STAR_NEED.join(',') === STAR_NEED.join(',') && calc.MAX_FRAG === MAX_FRAG,
    'STAR_NEED / MAX_FRAG 未漂', 'got ' + calc.STAR_NEED.join(',') + ' / ' + calc.MAX_FRAG);
}

/* ---------- B 图鉴格子 ---------- */
sec('B 图鉴格子（已拥有 / 满星 / 未拥有）');
{
  const byId = {};
  page.data.cards.forEach((c) => { byId[c.id] = c; });
  must(page.data.cards.length === 15, '15 个格子（含未拥有）', 'got ' + page.data.cards.length);
  const idOf = (i) => calc.CARDS[i].id;

  const c0 = byId[idOf(0)];
  must(c0.owned === true && c0.star === starStrOf(1) && c0.max === false, '第 1 张 1★ ⇒ ★☆☆',
    'got ' + c0.star);
  must(c0.prog && c0.prog.pct === fragOf(1).pct && c0.prog.pct === 0, '1★ 进度 0%（分母 3−0=2）',
    'got ' + (c0.prog && c0.prog.pct));
  must(c0.prog.frag === '1 / 3 碎片', '1★ 碎片文案 1 / 3 碎片', 'got ' + c0.prog.frag);

  const c1 = byId[idOf(1)];
  must(c1.star === starStrOf(3) && c1.max === true && c1.prog === null,
    '第 2 张 3★ ⇒ MAX · 满星（无进度条）',
    'got ' + JSON.stringify({ star: c1.star, max: c1.max, prog: c1.prog }));

  const c3 = byId[idOf(3)];
  must(c3.star === starStrOf(2) && c3.prog.pct === fragOf(4).pct && c3.prog.pct === 17,
    '2★ 且 4 片 ⇒ 进度 17%（分母 9−3=6；照 own/need 会算成 44%）', 'got ' + c3.prog.pct);
  must(c3.prog.frag === '4 / 9 碎片', '2★ 碎片文案 4 / 9 碎片', 'got ' + c3.prog.frag);

  const locked = page.data.cards.filter((c) => !c.owned);
  must(locked.length === 11, '未拥有 11 张', 'got ' + locked.length);
  must(locked[0].name === '???' && locked[0].emoji === '?' && locked[0].star === '☆☆☆' && locked[0].prog === null,
    '未拥有一律打码（??? / ? / ☆☆☆，且无进度条）',
    'got ' + JSON.stringify({ n: locked[0].name, e: locked[0].emoji, s: locked[0].star }));
  const lockedCard = calc.CARDS.find((c) => c.id === locked[0].id);
  must(locked[0].rname === RARITY_SPEC[lockedCard.rarity].name,
    '未拥有仍露出稀有度名（PWA 同样露着，别"修"）', 'got ' + locked[0].rname);
}

/* ---------- C 稀有度映射（确定性） ---------- */
sec('C 稀有度映射 7 个边界点（monkeypatch Math.random）');
{
  /* rollRarity: r = random×100；r<5 ⇒ SR；r<30 ⇒ R；否则 N */
  const pts = [
    [0.010, 'SR', 'r=1.0 → SR'],
    [0.049, 'SR', 'r=4.9 → SR（SR 上边界）'],
    [0.050, 'R', 'r=5.0 → R（SR/R 分界）'],
    [0.100, 'R', 'r=10 → R'],
    [0.299, 'R', 'r=29.9 → R（R 上边界）'],
    [0.300, 'N', 'r=30.0 → N（R/N 分界）'],
    [0.900, 'N', 'r=90 → N'],
  ];
  const bad = [];
  pts.forEach(([v, want, label]) => {
    const got = withRandom(v, () => calc.rollRarity());
    if (got !== want) bad.push(label + ' got ' + got);
  });
  must(bad.length === 0, '7 个边界点全部落对段位', bad.join(' | '));

  const rp = withRandom(0.9, () => calc.rollOne());
  must(rp.rarity === 'N' && rp.id === gerouId(calc), 'rollOne(0.9) ⇒ N 池第 6 张（gerou）',
    'got ' + rp.id + '/' + rp.rarity);
  const srp = withRandom(0.0, () => calc.rollOne());
  must(srp.rarity === 'SR' && srp.id === calc.CARDS.filter((c) => c.rarity === 'SR')[0].id,
    'rollOne(0.0) ⇒ SR 池第 1 张（jigou）', 'got ' + srp.id + '/' + srp.rarity);
  must(withRandom(0.9, () => calc.rollOneUpgraded()).rarity === 'R', 'rollOneUpgraded(0.9) ⇒ R', '');
  must(withRandom(0.1, () => calc.rollOneUpgraded()).rarity === 'SR', 'rollOneUpgraded(0.1) ⇒ SR', '');
}

/* ---------- D 十连保底 ---------- */
sec('D 十连保底（全 N 也必得 1 张稀有）+ 扣币 450');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  const pg = bootPage(baseSeed(c, { cards: cardsBasic(c) }));
  const gId = gerouId(c);
  const coins0 = L().coins, stars0 = totalStarsOf(c.CARDS, L().cards), owned0 = Object.keys(L().cards).length;

  /* random 恒 0.9 ⇒ rollOne 每次都给 N(gerou) ⇒ 必然触发保底分支 */
  withRandom(0.9, () => pg.onDraw(tap({ n: 10 })));

  must(pg.data.resultShow === true, '十连后弹层打开', 'got ' + pg.data.resultShow);
  must(pg.data.resultCards.length === 10, '弹层 10 张卡', 'got ' + pg.data.resultCards.length);
  must(pg.data.resultSingle === false && pg.data.resultCount === 10, '十连 ⇒ 非 single、标题张数 10',
    'got ' + pg.data.resultSingle + '/' + pg.data.resultCount);
  const rare = pg.data.resultCards.filter((x) => x.rname !== '普通');
  must(rare.length >= 1, '十连至少 1 张稀有或以上（保底生效）',
    'got ' + pg.data.resultCards.map((x) => x.rname).join(','));
  must(rare.length === 1 && rare[0].rname === '稀有', '本例恰好 1 张稀有（保底把第 10 张换成 R）',
    'got ' + rare.map((x) => x.name).join(','));
  must(pg.data.resultRefund === 0, '本次无返币（gerou 从 0 累到 9，没到「have ≥ 9」）', 'got ' + pg.data.resultRefund);

  const order = { 传说: 0, 稀有: 1, 普通: 2 };
  let sortedOk = true;
  for (let i = 1; i < pg.data.resultCards.length; i++) {
    if (order[pg.data.resultCards[i - 1].rname] > order[pg.data.resultCards[i].rname]) sortedOk = false;
  }
  must(sortedOk, '弹层按 传说→稀有→普通 排序', 'got ' + pg.data.resultCards.map((x) => x.rname).join(','));

  const live = L();
  must(live.coins === coins0 - 450, '扣币 450（十连价）', 'got ' + live.coins + ' want ' + (coins0 - 450));
  must(live.totalDraws === 10, 'totalDraws +10', 'got ' + live.totalDraws);
  must(live.cards[gId] === 9, 'gerou 碎片 0 → 9（1★→3★）', 'got ' + live.cards[gId]);
  must(Object.keys(live.cards).length === owned0 + 2, '卡键 +2（gerou 与保底那张 R）',
    'got ' + Object.keys(live.cards).length + ' want ' + (owned0 + 2));
  const stars1 = totalStarsOf(c.CARDS, live.cards);
  must(stars1 === stars0 + 4, '星数 +4（gerou 0→3★、R 卡 0→1★）',
    'got ' + stars1 + ' want ' + (stars0 + 4));
  must(pg.data.owned === Object.keys(live.cards).length, '页面张数同步', 'got ' + pg.data.owned);
  must(pg.data.collectPct === pctOfStars(stars1), '页面收集度同步（独立现算）',
    'got ' + pg.data.collectPct + ' want ' + pctOfStars(stars1));
}

/* ---------- E 满星返币 + 弹层 refund 不丢 ---------- */
sec('E 满星重复卡返币（确定性）—— 同时守住 drawCard 钩子签名不再丢 refundTotal');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  const gId = gerouId(c);
  const cards = cardsBasic(c);
  cards[gId] = MAX_FRAG;                      // 先满星
  const pg = bootPage(baseSeed(c, { cards: cards }));
  const coins0 = L().coins;

  withRandom(0.9, () => pg.onDraw(tap({ n: 1 })));   // 抽到 gerou ⇒ 满星重复 ⇒ 返 N=10

  const live = L();
  must(live.cards[gId] === MAX_FRAG, '满星卡的碎片不再增长（停在 9）', 'got ' + live.cards[gId]);
  must(live.coins === coins0 - 50 + REFUND_SPEC.N, '净扣 50 − 返 10 = 40',
    'got ' + live.coins + ' want ' + (coins0 - 40));
  must(live.coinsEarnedTotal === REFUND_SPEC.N, '返币计入 coinsEarnedTotal（+10）', 'got ' + live.coinsEarnedTotal);
  must(pg.data.resultRefund === REFUND_SPEC.N, '弹层 resultRefund = 10（refundTotal 没被钩子吞掉）',
    'got ' + pg.data.resultRefund);
  must(pg.data.resultCards.length === 1 && pg.data.resultCards[0].refund === REFUND_SPEC.N,
    '结果卡自报「已满星 · 转化 +10 币」', 'got ' + JSON.stringify(pg.data.resultCards.map((x) => x.refund)));
  must(pg.data.resultSingle === true, '单抽 ⇒ 走 single 布局', 'got ' + pg.data.resultSingle);
  must(pg.data.resultName === c.CARDS.find((x) => x.id === gId).name, '标题里的卡名 = 抽到的那张',
    'got ' + pg.data.resultName);
  must(pg.data.resultColor === c.RARITY.N.color, '标题里卡名颜色取 RARITY', 'got ' + pg.data.resultColor);

  pg.closeResult();
  must(pg.data.resultShow === false, 'closeResult 关掉弹层', 'got ' + pg.data.resultShow);

  /* 不变量负控：同一张满星卡再抽一次 ⇒ 仍然 −50+10，碎片不叠 */
  withRandom(0.9, () => pg.onDraw(tap({ n: 1 })));
  must(L().cards[gId] === MAX_FRAG && L().coins === coins0 - 80,
    '再抽一次仍 −40 且碎片不叠', 'got ' + L().coins + ' / frag ' + L().cards[gId]);
}

/* ---------- F 币不足拦截 ---------- */
sec('F 币不足：不扣币 / 不记次数 / 不开弹层 / 发提示');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  const pg = bootPage(baseSeed(c, { cards: cardsBasic(c), coins: 10 }));
  calls.length = 0;

  withRandom(0.9, () => pg.onDraw(tap({ n: 1 })));

  must(L().coins === 10, '扣币前就拦下（仍是 10）', 'got ' + L().coins);
  must(L().totalDraws === 0, 'totalDraws 不变', 'got ' + L().totalDraws);
  must(pg.data.resultShow === false, '不开弹层', 'got ' + pg.data.resultShow);
  const toast = calls.filter((x) => x[0] === 'showToast');
  must(toast.length >= 1 && String(toast[0][1]).indexOf('健康币不足') === 0,
    '内核 toast 钩子接到「健康币不足…」', 'got ' + JSON.stringify(toast));

  calls.length = 0;
  withRandom(0.9, () => pg.onDraw(tap({ n: 10 })));
  must(L().coins === 10 && pg.data.resultShow === false, '十连同样拦下（10 < 450）', 'got ' + L().coins);
  must(calls.some((x) => x[0] === 'showToast' && String(x[1]).indexOf('健康币不足') === 0),
    '十连也发了同一条提示', 'got ' + JSON.stringify(calls));
}

/* ---------- G 里程碑 ---------- */
sec('G 收集度里程碑（reach / 领取 / 幂等 / 未达标拦下）');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  const pg = bootPage(baseSeed(c, { cards: cardsMilestone(c), coins: 700 }));
  const pct = pctOfStars(totalStarsOf(c.CARDS, L().cards));
  must(pct === 33, '里程碑档星数 = 15/45 = 33%（独立现算）', 'got ' + pct);
  must(pg.data.collectPct === 33, '页面 collectPct = 33%', 'got ' + pg.data.collectPct);
  must(pg.data.owned === 5, '张数 = 5', 'got ' + pg.data.owned);

  const ms = pg.data.milestones;
  must(ms.length === 5, '5 档里程碑', 'got ' + ms.length);
  ms.forEach((m, i) => {
    must(m.pct === MS_SPEC[i].pct && m.coin === MS_SPEC[i].coin,
      '第 ' + (i + 1) + ' 档 = ' + MS_SPEC[i].pct + '% · +' + MS_SPEC[i].coin + ' 币',
      'got ' + m.pct + '/' + m.coin);
  });
  must(ms[0].reach === true && ms[0].got === false, '30% 档 reach=true 且尚未领取', JSON.stringify(ms[0]));
  must(ms[1].reach === false && ms[1].got === false, '50% 档 reach=false（33% 没到）', JSON.stringify(ms[1]));

  /* 领未达标的：拦下 */
  const coins0 = L().coins;
  calls.length = 0;
  pg.onClaim(tap({ pct: 50 }));
  must(L().collectRewards[50] === undefined && L().coins === coins0, '未达标领取 ⇒ 不发币、不置位',
    'got ' + L().coins + ' / ' + L().collectRewards[50]);
  must(calls.some((x) => x[0] === 'showToast' && String(x[1]).indexOf('收集度还没到') === 0),
    '未达标提示「收集度还没到，继续抽卡吧」', 'got ' + JSON.stringify(calls));

  /* 领达标的：发币 + 置位 */
  calls.length = 0;
  pg.onClaim(tap({ pct: 30 }));
  must(L().collectRewards[30] === true, '达标领取 ⇒ collectRewards[30] 置位', 'got ' + L().collectRewards[30]);
  must(L().coins === coins0 + MS_SPEC[0].coin, '+200 币落账', 'got ' + L().coins + ' want ' + (coins0 + 200));
  must(L().coinsEarnedTotal === MS_SPEC[0].coin, '计入 coinsEarnedTotal', 'got ' + L().coinsEarnedTotal);
  must(calls.some((x) => x[0] === 'showToast' && String(x[1]).indexOf('领取') === 0),
    '成功提示「领取「新锐收藏家」 +200 健康币」', 'got ' + JSON.stringify(calls));
  const idx30 = pg.data.milestones.findIndex((m) => m.pct === 30);
  must(pg.data.milestones[idx30].got === true && pg.data.milestones[idx30].reach === true,
    '页面刷新后该档显示「已领取」', 'got ' + JSON.stringify(pg.data.milestones[idx30]));

  /* 幂等：再点一次不重复发 */
  const coins1 = L().coins;
  pg.onClaim(tap({ pct: 30 }));
  must(L().coins === coins1, '重复领取不再发币（幂等锚 collectRewards）', 'got ' + L().coins);
}

/* ---------- H 空存档 ---------- */
sec('H 空存档');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  let empty = null, err = null;
  try { empty = bootPage(c.defaultState()); } catch (e) { err = e; }
  must(!err, '空存档渲染不抛错', err && err.message);
  if (empty) {
    must(empty.data.owned === 0 && empty.data.stars === 0 && empty.data.collectPct === 0,
      '0 张 / 0 星 / 0%', 'got ' + empty.data.owned + '/' + empty.data.stars + '/' + empty.data.collectPct);
    must(empty.data.cards.length === 15 && empty.data.cards.every((x) => !x.owned), '15 格全锁定', '');
    must(empty.data.cards[0].name === '???' && empty.data.cards[0].prog === null, '锁定格无进度条', '');
    must(empty.data.milestones.every((m) => !m.reach && !m.got), '5 档里程碑全未达成', '');
    /* 空存档不是 0 币：默认档案 75.5→72.8 满足 untie ⇒ 冷启动补发 +50（PWA 同值） */
    must(empty.data.coins === 50, '空存档余额 = 冷启动补发的 50', 'got ' + empty.data.coins);
    must(empty.data.resultShow === false, '初始不开弹层', 'got ' + empty.data.resultShow);
  }
}

out('');
out('========================================');
out('通过 ' + pass + ' 项，失败 ' + fails.length + ' 项');
if (fails.length) fails.forEach((f) => out('  ✗ ' + f));
out('RESULT=' + (fails.length ? 'FAIL' : 'OK'));
fs.writeFileSync(OUT, lines.join('\n') + '\n', 'utf8');
console.log(lines.join('\n'));
process.exit(fails.length ? 1 : 0);
