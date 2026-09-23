/* mp_ach_test.js —— 成就殿堂（pages/achievements）运行时断言
 *
 * 与 mp_me_test / mp_trade_test 同款 mock。凡是能独立算的，都在这里**另写一遍**现算再比对：
 *   解锁计数、成就点、段位（ACH_TIERS 的 min 规则）、勋章进度条判据、进度文案两条口径、
 *   近期目标的筛选与排序。
 *
 * 覆盖：
 *   A 头部进度句（N / 30 · 成就点 X · 段位：Y）
 *   B 6 赛道卡（数量 / 顺序 / 每卡 got-total / 与页面 total 自洽）
 *   C 勋章格子（已解锁 → 已达成 +N；未解锁且 target>1 → 进度条；target=1 → 两者都不给）
 *   D 进度文案两条口径（kg 型 toFixed(1) vs 计数型 floor）
 *   E 近期目标（筛选 0<r<1 / 降序 / 取 3 / 与手算一致）
 *   F 两相反态负控（注入 5 笔饮食 ⇒ halfpos 解锁 ⇒ 句子与格子当场变）
 *   G 空存档（不抛错 / 冷启动补发 untie ⇒ 1/30、段位新兵）
 *
 * ⚠️ const calc = require(...) 必须写在 boot 之后（技能铁律）。
 * ⚠️ 种子的 weight 取 72.8（默认档）：这样 wave 的进度是 2.7/3 kg —— 才能同时压住
 *    「unit 型走 toFixed(1)」与「近期目标按完成度降序」两条判据；weight=80 时它恒为 0.0，
 *    两条断言都会退化成恒真（拿不到区分度）。
 *
 * 用法：node promo/mp_ach_test.js   退出码 0=全过
 * 报告落盘：promo/_ach_out.txt
 */
'use strict';
const path = require('path');
const fs = require('fs');

const MINI = 'E:\\WeChatProjects\\jianpan\\miniprogram';
const OUT = path.join(__dirname, '_ach_out.txt');

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
 * 独立参考实现（不复用页面/内核的判定）
 * ============================================================ */
/* 段位表按 PWA ACH_TIERS 的文字规则重抄：unlocked ≥ min 的最后一段生效 */
const TIER_SPEC = [
  { min: 0, name: '新兵' }, { min: 3, name: '青铜' }, { min: 6, name: '白银' },
  { min: 10, name: '黄金' }, { min: 15, name: '铂金' }, { min: 20, name: '钻石' },
  { min: 25, name: '大师' }, { min: 30, name: '传奇' },
];
function tierOf(unlocked) {
  let t = TIER_SPEC[0];
  TIER_SPEC.forEach((x) => { if (unlocked >= x.min) t = x; });
  return t;
}
/* 勋章百分比：min(100, round(prog/target*100)) */
function pctOfProg(prog, target) { return Math.min(100, Math.round(prog / target * 100)); }
/* 进度文案两条口径（照 PWA：unit 型 toFixed(1)，否则 floor） */
function progTxtOf(prog, target, unit) {
  return unit
    ? (Math.min(prog, target).toFixed(1) + ' / ' + target + ' ' + unit)
    : (Math.floor(prog) + ' / ' + target);
}
/* 几个关键成就的 target/unit 硬编码一份 —— 与 calc 的字段交叉校验，防「表被改过」 */
const KEY_SPEC = {
  leek: { target: 1, unit: undefined }, untie: { target: 1, unit: 'kg' },
  wave: { target: 3, unit: 'kg' }, exit: { target: 7.5, unit: 'kg' },
  halfpos: { target: 5, unit: undefined }, allin: { target: 3, unit: undefined },
  blowup: { target: 800, unit: undefined }, maxstar: { target: 45, unit: undefined },
};

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
  switchTab: (o) => calls.push(['switchTab', o && o.url]),
  pageScrollTo: noop,
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
 * 种子存档（自洽：凡被自身数据满足的成就都预先置 true，理由见 mp_me_test 的长注释）
 * ============================================================ */
const SEED_ACH = ['leek', 'untie', 'tryorder', 'open', 'firstboard'];
function buildSeed(calc) {
  const st = calc.defaultState();
  st.user = Object.assign({}, st.user, {
    userId: 'FT_ACH', gender: 'male', age: 30, height: 175, weight: 72.8,
    bodyFat: 18, restingHr: 58, activity: 'light', target: -500, avatar: null,
  });
  st.coins = 320;
  st.coinToday = 40;
  st.coinDate = todayStr();
  st.exp = 250;
  st.limitUpCount = 2;
  st.diet = [
    { id: 'd1', name: '米饭', kcal: 300, date: todayStr(), time: '12:00', gram: 100, unit: 'g', qty: 1 },
    { id: 'd2', name: '鸡胸肉', kcal: 165, date: todayStr(), time: '19:00', gram: 100, unit: 'g', qty: 1 },
    { id: 'd3', name: '米饭', kcal: 200, date: todayStr(), time: '20:00', gram: 100, unit: 'g', qty: 1 },
  ];
  st.exercise = [{ id: 'e1', name: '跑步', kcal: 420, date: todayStr(), time: '21:00', met: 8, min: 40, gram: 0, unit: '', qty: 1 }];
  st.ach = {};
  SEED_ACH.forEach((id) => {
    if (!calc.ACHIEVEMENTS.some((a) => a.id === id)) throw new Error('成就 id 不存在：' + id);
    st.ach[id] = true;
  });
  st.cards = {};
  st.cards[calc.CARDS[0].id] = 1;
  st.cards[calc.CARDS[1].id] = 9;
  return st;
}

function fresh() {
  Object.keys(storage).forEach((k) => { delete storage[k]; });
  captured.pages.length = 0;
  captured.app = null;
  calls.length = 0;
  Object.keys(require.cache).forEach((k) => { if (k.indexOf(MINI) === 0) delete require.cache[k]; });
}
function bootApp(state) {
  fresh();
  storage['jianpan_v2'] = state;
  require(path.join(MINI, 'app.js'));
  captured.app.onLaunch.call(captured.app);
}
function bootPage(state, rel) {
  bootApp(state);
  captured.pages.length = 0;
  require(path.join(MINI, rel));
  const mk = makeInstance(captured.pages[captured.pages.length - 1]);
  if (typeof mk.onLoad === 'function') mk.onLoad.call(mk, {});
  if (typeof mk.onShow === 'function') mk.onShow.call(mk);
  return mk;
}

/* ============================================================
 * 跑
 * ============================================================ */
out('mp_ach_test —— 成就殿堂运行时断言');
out('时间：' + new Date().toISOString());

let seed = null, page = null, calc = null;
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  seed = buildSeed(c0);
  page = bootPage(seed, 'pages/achievements/achievements.js');
  calc = require(path.join(MINI, 'lib/calc.js'));   // ⚠️ boot 之后
}

/* ---------- A 头部进度句 ---------- */
sec('A 头部进度句');
{
  const d = page.data;
  const unlocked = calc.ACHIEVEMENTS.filter((a) => seed.ach[a.id]).length;
  let points = 0;
  calc.ACHIEVEMENTS.forEach((a) => { if (seed.ach[a.id]) points += a.reward; });
  const tier = tierOf(unlocked);
  const want = unlocked + ' / ' + calc.ACHIEVEMENTS.length + ' · 成就点 ' + points + ' · 段位：' + tier.name;

  must(unlocked === 5, '种子自洽：解锁数独立现算 = 5（未触发启动补发）', 'got ' + unlocked);
  must(points === 160, '成就点独立现算 = 20+50+20+20+50 = 160', 'got ' + points);
  must(tier.name === '青铜', '5 项 ⇒ 段位 青铜（≥3 且 <6）', 'got ' + tier.name);
  must(d.progressText === want, '进度句与独立现算逐字一致', 'got ' + JSON.stringify(d.progressText) + ' want ' + JSON.stringify(want));
  must(d.statusBarHeight === 54, '状态栏留白取到真机值 54', 'got ' + d.statusBarHeight);
}

/* ---------- B 6 赛道卡 ---------- */
sec('B 6 赛道卡');
{
  const cats = page.data.achCats;
  must(cats.length === 6, '6 个赛道卡', 'got ' + cats.length);
  must(cats.map((c) => c.id).join(',') === 'hold,trade,capital,codex,limitup,retail',
    '顺序 = ACH_CATS 原序（不按解锁数重排）', 'got ' + cats.map((c) => c.id).join(','));
  /* 每卡的 got 独立现算（按 cat 分组数 seed.ach） */
  const want = {};
  calc.ACHIEVEMENTS.forEach((a) => {
    want[a.cat] = want[a.cat] || { got: 0, n: 0 };
    want[a.cat].n++;
    if (seed.ach[a.id]) want[a.cat].got++;
  });
  cats.forEach((c) => {
    const w = want[c.id];
    must(c.got === w.got && c.total === w.n,
      '赛道「' + c.name + '」=' + w.got + '/' + w.n + '（独立现算）', 'got ' + c.got + '/' + c.total);
  });
  must(cats.reduce((s, c) => s + c.got, 0) === 5, '各卡 got 之和 = 5（与头部计数自洽）',
    'got ' + cats.reduce((s, c) => s + c.got, 0));
  must(cats.reduce((s, c) => s + c.total, 0) === 30, '各卡 total 之和 = 30', 'got ' + cats.reduce((s, c) => s + c.total, 0));
  must(cats.reduce((s, c) => s + c.list.length, 0) === 30, '每卡的 list 行数合计 = 30（每项都渲染出来了）',
    'got ' + cats.reduce((s, c) => s + c.list.length, 0));
  /* 关键成就的 target/unit 与硬编码表交叉校验（防表被改过还不报警） */
  const flat = {};
  cats.forEach((c) => c.list.forEach((b) => { flat[b.id] = b; }));
  Object.keys(KEY_SPEC).forEach((id) => {
    const a = calc.ACHIEVEMENTS.find((x) => x.id === id);
    must(a && a.target === KEY_SPEC[id].target && a.unit === KEY_SPEC[id].unit,
      '内核里 ' + id + ' 的 target/unit 与硬编码表一致', 'got ' + JSON.stringify({ t: a && a.target, u: a && a.unit }));
  });
}

/* ---------- C 勋章格子三态 ---------- */
sec('C 勋章格子（已解锁 / 未解锁带进度条 / 未解锁无进度条）');
{
  const flat = {};
  page.data.achCats.forEach((c) => c.list.forEach((b) => { flat[b.id] = b; }));

  /* ① 已解锁 ⇒ got=true、showBar=false（PWA: showBar = !got && target>1） */
  const leek = flat.leek;
  must(leek.got === true && leek.showBar === false, '已解锁「韭菜入场」⇒ 不给进度条（走「已达成」）',
    'got ' + JSON.stringify({ got: leek.got, showBar: leek.showBar }));
  must(leek.reward === 20, '「韭菜入场」奖励 20 币透传', 'got ' + leek.reward);

  /* ② 未解锁 + target>1 ⇒ 给进度条 */
  const blowup = flat.blowup;
  must(blowup.got === false && blowup.showBar === true, '未解锁「爆仓体验」(target 800) ⇒ 给进度条',
    'got ' + JSON.stringify({ got: blowup.got, showBar: blowup.showBar }));
  must(blowup.pct === 0 && blowup.progTxt === '0 / 800', '进度 0 ⇒ pct 0 / 文案 0 / 800',
    'got ' + blowup.pct + ' / ' + blowup.progTxt);

  /* ③ 未解锁 + target=1（布尔型）⇒ 既无进度条也无「已达成」—— 这是 PWA 的留白，别"补" */
  const cutmeat = flat.cutmeat;
  must(cutmeat.got === false && cutmeat.showBar === false && cutmeat.target === undefined,
    '布尔型未解锁项不给进度条（PWA 同样留白）', 'got ' + JSON.stringify({ got: cutmeat.got, showBar: cutmeat.showBar }));

  /* ④ 每个带条项的 pct 都与独立实现一致 */
  let barN = 0, barBad = 0;
  page.data.achCats.forEach((c) => c.list.forEach((b) => {
    if (!b.showBar) return;
    barN++;
    const a = calc.ACHIEVEMENTS.find((x) => x.id === b.id);
    const prog = a.prog(seed);
    if (b.pct !== pctOfProg(prog, a.target)) barBad++;
  }));
  must(barN === 21, '带进度条的项共 21 个（30 项 − 5 已解锁 − 4 个 target=1）', 'got ' + barN);
  must(barBad === 0, '21 个 pct 全部与独立现算一致', 'bad ' + barBad);
}

/* ---------- D 进度文案两条口径 ---------- */
sec('D 进度文案：unit 型 toFixed(1) vs 计数型 floor');
{
  const flat = {};
  page.data.achCats.forEach((c) => c.list.forEach((b) => { flat[b.id] = b; }));

  /* wave 是 kg 型，prog = 75.5 − 72.8 = 2.7 ⇒ 必须保留一位小数（写 floor 会变 '2 / 3 kg'） */
  must(flat.wave.progTxt === '2.7 / 3 kg', 'kg 型「主升浪」= 2.7 / 3 kg（toFixed(1)）', 'got ' + flat.wave.progTxt);
  must(flat.wave.pct === 90, '「主升浪」pct = round(2.7/3×100) = 90', 'got ' + flat.wave.pct);
  /* 同一项的 prog 独立现算一遍（不走页面） */
  const wave = calc.ACHIEVEMENTS.find((a) => a.id === 'wave');
  const waveProg = Math.max(0, +((seed.user.startWeight - seed.user.weight).toFixed(1)));
  must(waveProg === 2.7 && wave.prog(seed) === 2.7, '内核 prog 与手算 75.5−72.8 = 2.7 一致', 'got ' + waveProg);

  /* halfpos 是计数型（5 笔饮食），prog = 3 ⇒ floor 后 '3 / 5' */
  must(flat.halfpos.progTxt === '3 / 5', '计数型「半仓干」= 3 / 5（floor）', 'got ' + flat.halfpos.progTxt);

  /* 全表扫一遍：文案要么是 '<x.y> / <t> <unit>'，要么是 '<n> / <t>' */
  let bad = 0;
  page.data.achCats.forEach((c) => c.list.forEach((b) => {
    if (!b.showBar) return;
    const a = calc.ACHIEVEMENTS.find((x) => x.id === b.id);
    if (b.progTxt !== progTxtOf(a.prog(seed), a.target, a.unit)) bad++;
  }));
  must(bad === 0, '21 条文案全部与独立现算的 progTxtOf 一致', 'bad ' + bad);
}

/* ---------- E 近期目标 ---------- */
sec('E 近期目标（筛选 + 降序 + 取 3）');
{
  const pend = page.data.pend;
  must(pend.length === 3, '恰好 3 条', 'got ' + pend.length);
  must(pend[0].id === 'wave' && pend[0].pct === 90, '第 1 条 = 主升浪 90%（完成度最高）',
    'got ' + pend[0].id + ' ' + pend[0].pct);
  must(pend[1].id === 'halfpos' && pend[1].pct === 60, '第 2 条 = 半仓干 60%', 'got ' + pend[1].id + ' ' + pend[1].pct);
  /* ⚠️ 第 3 名是 bull（牛市主升，2.7/5 kg = 54%），不是 protrader(40%)——
     我第一版手算时漏了 bull 也用同一个减重 prog。这条正好说明「候选池前 3」那条独立现算断言
     不是多余的：页面始终对，是我的期望错了。 */
  must(pend[2].id === 'bull' && pend[2].pct === 54, '第 3 条 = 牛市主升 54%（2.7/5 kg）',
    'got ' + pend[2].id + ' ' + pend[2].pct);
  must(pend[0].pct >= pend[1].pct && pend[1].pct >= pend[2].pct, 'pct 非递增（确实按完成度排）',
    'got ' + pend.map((x) => x.pct).join(','));
  must(pend.every((x) => !seed.ach[x.id]), '3 条都未解锁（已解锁项不会混进来）',
    'got ' + pend.filter((x) => seed.ach[x.id]).map((x) => x.id).join(','));
  must(pend[0].txt === '2.7 / 3 kg', '近期目标行文案与格子同口径', 'got ' + pend[0].txt);
  must(pend[0].color === '#00c896', '近期目标取所属赛道的颜色（hold = #00c896）', 'got ' + pend[0].color);

  /* 独立现算整张候选表，确认页面没漏掉「比第 3 名更近」的项 */
  const cand = [];
  calc.ACHIEVEMENTS.forEach((a) => {
    if (seed.ach[a.id] || !(a.target > 1)) return;
    const p = a.prog ? a.prog(seed) : 0;
    const r = p / a.target;
    if (r > 0 && r < 1) cand.push({ id: a.id, r: r });
  });
  cand.sort((x, y) => y.r - x.r);
  must(cand.length >= 3, '独立现算的候选池 ≥ 3 条（否则「取 3」没意义）', 'got ' + cand.length);
  must(cand.slice(0, 3).map((x) => x.id).join(',') === pend.map((x) => x.id).join(','),
    '页面取的就是候选池前 3（独立现算一致）',
    'want ' + cand.slice(0, 3).map((x) => x.id).join(',') + ' got ' + pend.map((x) => x.id).join(','));
}

/* ---------- F 两相反态负控：注入 2 笔饮食 ⇒ 半仓干解锁 ---------- */
sec('F 负控：注入饮食 ⇒ halfpos 解锁（同一次运行里的相反态）');
{
  const store = require(path.join(MINI, 'lib/store.js'));
  const beforeTxt = page.data.progressText;
  const coinsBefore = store.get().coins;
  const flatBefore = {};
  page.data.achCats.forEach((c) => c.list.forEach((b) => { flatBefore[b.id] = b; }));
  must(flatBefore.halfpos.progTxt === '3 / 5' && flatBefore.halfpos.showBar === true,
    '注入前：「半仓干」3 / 5 且带进度条', 'got ' + flatBefore.halfpos.progTxt);

  /* 直接改真口径：mock 下 storage['jianpan_v2'].diet 与内核 state.diet 是**同一数组引用**。
     ⚠️ 不用 calc.todayDiet() —— 它返回 filter 出来的**新数组**，push 进去不落真 state。
     ⚠️ 也不能改 seed.coins 这类**标量**：store 里的活状态是 loadState() 的浅拷贝，
        标量是拷贝、数组/对象才是共享引用。要读/写活状态一律走 store.get()。
        （我第一版就是拿 seed.coins 当活状态断言，于是「发币 50」看起来没发生 —— 是测试错，
          生产路径里 progress.sync 拿到的始终是模块内真 state。） */
  seed.diet.push({ id: 'd4', name: '加餐A', kcal: 100, date: todayStr(), time: '15:00', gram: 100, unit: 'g', qty: 1 });
  seed.diet.push({ id: 'd5', name: '加餐B', kcal: 100, date: todayStr(), time: '16:00', gram: 100, unit: 'g', qty: 1 });
  /* 页面自己重算（等价于用户回到本页 / 内核触发 render 钩子） */
  page.refresh();

  const flatMid = {};
  page.data.achCats.forEach((c) => c.list.forEach((b) => { flatMid[b.id] = b; }));
  must(flatMid.halfpos.progTxt === '5 / 5',
    'refresh 后进度条前进 3/5 → 5/5（证明确实在读状态，不是恒真）', 'got ' + flatMid.halfpos.progTxt);
  must(page.data.progressText === beforeTxt && store.get().ach.halfpos === undefined,
    '页面自己不发奖：进度句仍 5 / 30、ach 里还没有 halfpos（发奖只在内核 progress.sync）',
    'got ' + page.data.progressText + ' / ach=' + store.get().ach.halfpos);

  /* 走真实发奖路径：store.save() 是内核 saveState 钩子的落点，
     内部 progress.sync(模块内真 state) ⇒ 判定 + 发币 + 落盘（顺序：判定先于落盘） */
  store.save();
  must(store.get().ach.halfpos === true, 'store.save() 触发 sync ⇒ ach.halfpos 置位',
    'got ' + store.get().ach.halfpos);
  must(store.get().coins === coinsBefore + 50, '解锁发币 50 落在活状态上',
    'got ' + store.get().coins + ' want ' + (coinsBefore + 50));

  page.refresh();
  const flat2 = {};
  page.data.achCats.forEach((c) => c.list.forEach((b) => { flat2[b.id] = b; }));
  must(flat2.halfpos.got === true && flat2.halfpos.showBar === false,
    '解锁后「半仓干」转为已达成态（进度条收起）',
    'got ' + JSON.stringify({ got: flat2.halfpos.got, showBar: flat2.halfpos.showBar }));
  must(flat2.halfpos.pct === 100, '已解锁项的 pct 仍是 100（文案不显示它，但值要对）', 'got ' + flat2.halfpos.pct);
  must(page.data.achCats[1].got === 2, '「盘中操作」赛道计数 1/5 → 2/5', 'got ' + page.data.achCats[1].got);
  must(page.data.progressText.indexOf('6 / 30') === 0, '进度句变 6 / 30', 'got ' + page.data.progressText);
  must(page.data.progressText.indexOf('成就点 210') > 0, '成就点跟着变 160 → 210', 'got ' + page.data.progressText);
}

/* ---------- G 空存档 ---------- */
sec('G 空存档');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  let empty = null, err = null;
  try { empty = bootPage(c.defaultState(), 'pages/achievements/achievements.js'); } catch (e) { err = e; }
  must(!err, '空存档渲染不抛错', err && err.message);
  if (empty) {
    /* 空存档不是全 0：默认档案 75.5 → 72.8 已满足 untie（target 1）⇒ 冷启动补发 1 项 50 币（PWA 同值） */
    must(empty.data.progressText === '1 / 30 · 成就点 50 · 段位：新兵',
      '空存档 ⇒ 1 / 30 · 成就点 50 · 段位：新兵', 'got ' + JSON.stringify(empty.data.progressText));
    must(empty.data.achCats.length === 6, '空存档仍是 6 个赛道卡', 'got ' + empty.data.achCats.length);
    const got = empty.data.achCats.map((x) => x.got).join(',');
    must(got === '1,0,0,0,0,0', '只有「持仓与套牢」有 1 项（解套成功），其余全 0', 'got ' + got);
    must(empty.data.pend.length === 3, '空存档也有 3 条近期目标（wave/bull/exit 都是 0 进度的不算，靠饮食与运动那几项）',
      'got ' + empty.data.pend.map((x) => x.id + ':' + x.pct).join(','));
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
