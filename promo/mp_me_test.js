/* mp_me_test.js —— 「我的」簇（pages/me 本体 + pages/coins + pages/level）运行时断言
 *
 * 与 mp_trade_test / mp_board_test 同款 mock。凡是能独立算的，都在这里**另写一遍**现算再比对
 * （段位判定、经验百分比、收集度星数、Mifflin BMR、TDEE=BMR×PAL、成就解锁计数）。
 *
 * 覆盖：
 *   A 我的页头部（lv / 段位名 / 健交所持仓 N 天 / 累计三格 / 勋章计数）
 *   B 币卡与菜单（余额 / 成就总数 / 收集度% / 三个菜单数值）
 *   C 身体档案（表单初值 / viz 四格 / 人形图路径 / BMR·TDEE 盒 / 活动水平标签与内核 id 顺序一致）
 *   D 表单交互（改活动水平写回 state / 改体重当场重算 BMR）
 *   E 上传档案（写 state.user + recordWeight 真写一条体重日志）
 *   F 健康币页（余额 / 今日已赚 / 赚花规则条数与文案 / 跨天归零负控 / 余额负控）
 *   G 段位页（段位判定 / lv / 经验条 pct / 距下一段 / 8 行区间文案 / 当前行唯一高亮 / 顶段与零经验负控）
 *   H 空存档（三页都不抛错、走空态）
 *
 * ⚠️ const calc = require(...) 必须写在 boot(seed) 之后（技能铁律）。
 * ⚠️ mock 下 storage['jianpan_v2'] 与 calc.state / store.get() 是同一引用 ⇒ 负控直接改 seed。
 *
 * 用法：node promo/mp_me_test.js   退出码 0=全过
 * 报告落盘：promo/_me_out.txt
 */
'use strict';
const path = require('path');
const fs = require('fs');

const MINI = 'E:\\WeChatProjects\\jianpan\\miniprogram';
const OUT = path.join(__dirname, '_me_out.txt');

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
 * 独立参考实现（不复用页面/内核的任何计算）
 * ============================================================ */
/* 段位表按 PWA RANKS 的「文字规则」重抄一份：lv ≥ minLv 的最后一段生效 */
const RANK_SPEC = [
  { name: '散户', minLv: 1 }, { name: '小散', minLv: 3 }, { name: '中户', minLv: 5 },
  { name: '大户', minLv: 7 }, { name: '游资', minLv: 9 }, { name: '机构', minLv: 11 },
  { name: '庄家', minLv: 14 }, { name: '股神', minLv: 17 },
];
function lvOf(exp) { return Math.floor((exp || 0) / 100) + 1; }
function rankOf(exp) {
  const lv = lvOf(exp);
  let r = RANK_SPEC[0];
  RANK_SPEC.forEach((x) => { if (lv >= x.minLv) r = x; });
  return { lv: lv, rank: r, idx: RANK_SPEC.indexOf(r) };
}
function pctOf(exp) { return Math.min(100, Math.round(((exp || 0) % 100) / 100 * 100)); }
/* 星数规则（STAR_NEED = [0,1,3,9]） */
function starOf(cnt) {
  if (cnt >= 9) return 3;
  if (cnt >= 3) return 2;
  if (cnt >= 1) return 1;
  return 0;
}
function collectPctOf(cards, owned) {
  let sum = 0;
  cards.forEach((c) => { sum += starOf(owned[c.id] || 0); });
  return Math.round(sum / 45 * 100);
}
/* Mifflin-St Jeor（男 +5 / 女 −161）：未填体脂时的主公式 */
function bmrMifflin(u) {
  const base = 10 * u.weight + 6.25 * u.height - 5 * u.age;
  return Math.round(base + (u.gender === 'female' ? -161 : 5));
}
/* Katch-McArdle：填了体脂率时的主公式（去脂体重 LBM 口径） */
function bmrKatch(u) {
  const lbm = u.weight * (1 - u.bodyFat / 100);
  return Math.round(370 + 21.6 * lbm);
}
/* 内核按「有没有体脂率」切主公式 ⇒ 期望值必须跟着切 */
function bmrInd(u) { return u.bodyFat ? bmrKatch(u) : bmrMifflin(u); }
const PAL = { sedentary: 1.2, light: 1.375, moderate: 1.55, active: 1.725, athlete: 1.9 };

/* ⚠️ store.get() 返回的是 loadState() 的**浅拷贝**：标量（coins/exp/coinToday…）改 seed 不会影响活状态，
   数组（diet/weightLog/cards…）则共享引用。⇒ 负控一律改活状态，不猜。 */
function S() { return require(path.join(MINI, 'lib/store.js')); }

/* ============================================================
 * mock（与 mp_board_test 同款 + 我的簇需要的 API）
 * ============================================================ */
const storage = {};
const noop = () => {};
const calls = [];
const BADGE_IDS = [];   // 由 seed 里塞入

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
  createSelectorQuery: () => mkQuery(),
  nextTick: (fn) => setTimeout(fn, 0),
  showToast: (o) => calls.push(['showToast', o && o.title]),
  showModal: (o) => { calls.push(['showModal', o && o.title]); o && o.success && o.success({ confirm: false }); },
  showLoading: (o) => calls.push(['showLoading', o && o.title]),
  hideLoading: noop,
  navigateTo: (o) => calls.push(['navigateTo', o && o.url]),
  navigateBack: () => calls.push(['navigateBack']),
  switchTab: (o) => calls.push(['switchTab', o && o.url]),
  pageScrollTo: (o) => calls.push(['pageScrollTo', o && o.selector]),
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
  inst.createSelectorQuery = () => mkQuery();
  return inst;
}

/* ---------- 选择器查询 mock（补 .fields({node}) —— 头像管道要拿画布节点）----------
   原来只有 boundingClientRect 且 exec 不回调。lib/avatar.js 的 queryCanvas 走的是
   `select(sel).fields({node:true,size:true}).exec(cb)` ⇒ 不给 fields 就会 TypeError，
   症状是「点头像后整个流程静默不动」，而测试因为没走到那里会说通过。 */
function mkQuery() {
  const r = {
    _fields: false,
    select: () => r,
    in: () => r,
    fields: () => { r._fields = true; return r; },
    /* ⚠️ boundingClientRect 保持「exec 不回调」的原行为（既有断言默认它返回 null） */
    boundingClientRect: () => { r._fields = false; return r; },
    selectAll: () => r,
    exec: (cb) => {
      if (typeof cb === 'function') {
        cb(r._fields ? [{ node: avatarCanvasNode(), width: 256, height: 256,
                          left: 0, top: 0 }] : undefined);
      }
      return r;
    },
  };
  return r;
}

/* ---------- 头像管道用的画布节点 + wx API ----------
   记录每一次 drawImage / canvasToTempFilePath 的参数 —— 这些正是「口径是否与 PWA 一致」
   的可观测证据（最长边 256 / JPEG q0.85 / 先设位图尺寸再取 ctx）。 */
const avDraw = [];
let avNode = null;          // 最后一次交出去的画布节点（用来断言「先设位图尺寸再取 ctx」）
function avatarCanvasNode() {
  avNode = {
    width: 0, height: 0,
    getContext: () => ({
      clearRect: (...a) => avDraw.push(['clearRect'].concat(a)),
      drawImage: (...a) => avDraw.push(['drawImage'].concat(a.slice(1))),
    }),
    createImage: () => {
      const img = { onload: null, onerror: null, _src: '', width: 0, height: 0 };
      Object.defineProperty(img, 'src', {
        get() { return img._src; },
        /* 真机是异步加载；这里也异步，避免「同步 onload」把真实时序问题掩盖掉 */
        set(v) { img._src = v; setTimeout(() => { if (typeof img.onload === 'function') img.onload(); }, 0); },
      });
      return img;
    },
  };
  return avNode;
}
let avLastTemp = null;      // 最后一次 canvasToTempFilePath 的参数
let avChoose = 'ok';        // 'ok' | 'cancel' | 'none'
global.wx.getImageInfo = (o) => {
  calls.push(['getImageInfo', o && o.src]);
  o.success({ width: 1024, height: 800, path: o.src, type: 'jpg' });
};
global.wx.chooseMedia = (o) => {
  calls.push(['chooseMedia']);
  if (avChoose === 'cancel') { o.fail({ errMsg: 'chooseMedia:fail cancel' }); return; }
  if (avChoose === 'none') { o.success({ tempFiles: [] }); return; }
  o.success({ tempFiles: [{ tempFilePath: '/tmp/pick.jpg', size: 900000 }] });
};
global.wx.canvasToTempFilePath = (o) => {
  avLastTemp = o;
  o.success({ tempFilePath: '/tmp/av_out.jpg' });
};
global.wx.getFileSystemManager = () => ({
  readFile: (o) => {
    if (o.encoding === 'base64') { o.success({ data: 'QkFTRTY0UEFZTE9BRA==' }); return; }
    o.success({ data: o.__text || '' });
  },
  writeFileSync: noop,
});

const pad2 = (n) => String(n).padStart(2, '0');
const ymd = (d) => d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
function todayStr() { return ymd(new Date()); }

/* ============================================================
 * 种子存档
 * ============================================================ */
function buildSeed(calc) {
  const st = calc.defaultState();
  st.user = Object.assign({}, st.user, {
    userId: 'FT_TEST', gender: 'male', age: 30, height: 175, weight: 80,
    bodyFat: 18, restingHr: 58, activity: 'light', target: -500, avatar: null,
  });
  st.coins = 320;
  st.coinToday = 40;
  st.coinDate = todayStr();
  st.exp = 250;                       // lv 3 ⇒ 小散
  st.limitUpCount = 2;
  st.diet = [{ id: 'd1', name: '米饭', kcal: 300, date: todayStr(), time: '12:00', gram: 100, unit: 'g', qty: 1 },
             { id: 'd2', name: '鸡胸肉', kcal: 165, date: todayStr(), time: '19:00', gram: 100, unit: 'g', qty: 1 },
             { id: 'd3', name: '米饭', kcal: 200, date: todayStr(), time: '20:00', gram: 100, unit: 'g', qty: 1 }];
  st.exercise = [{ id: 'e1', name: '跑步', kcal: 420, date: todayStr(), time: '21:00', met: 8, min: 40, gram: 0, unit: '', qty: 1 }];
  /* 成就：这个种子必须是一份**自洽的存档** —— 也就是说，凡是被它自己的数据满足的成就，
     都要预先置 true。理由：接入 lib/progress.js 之后，`store.init()` 冷启动会做一次补发
     （PWA 每次 render 都做，见 _probe_pwa_coldstart_ach.py），不预置的话启动瞬间就会
     多发 90 币 / 多 3 个勋章，把「页面忠实读取 state」的断言变成「在看补发的副作用」。
     逐条独立对照（不用 prog，只看本种子给了什么 + ACHIEVEMENTS 的 target）：
       diet 3 + exercise 1 = 4 →  leek(1) ✓  tryorder(1) ✓  halfpos(5) ✗  allin(3) ✗  hft(30) ✗
       weight 80 > startWeight 75.5 → untie/wave/bull/exit 的 prog 为 0 ⇒ 全 ✗
       limitUpCount 2 → firstboard(1) ✓  protrader(5) ✗  demon(10) ✗  godmode(20) ✗
       cards 2 张有碎片 → open(1) ✓  fulln(6) ✗  maxstar(45) ✗（1★+3★=4 星）
       两张卡都是 N 稀有度 → rarefind(R) ✗  chosen(SR) ✗
       coinsEarnedTotal 0 → smallmeat/richboy ✗ ｜ coins 320 < 1000 → dividend ✗
       totalDraws 0 / streakDays 0 / everBroke false / maxOverage 0 → 对应项全 ✗
     ⇒ 应预置的正好 5 项（leek / untie / tryorder / open / firstboard）。
     ⚠️ untie 与 leek 是原实现就预置的（模拟「已经玩过一阵」）；补上其余 3 项。 */
  const seedAch = ['leek', 'untie', 'tryorder', 'open', 'firstboard'];
  st.ach = {};
  seedAch.forEach((id) => {
    if (!calc.ACHIEVEMENTS.some((a) => a.id === id)) throw new Error('成就 id 不存在：' + id);
    st.ach[id] = true;
  });
  BADGE_IDS.length = 0;
  BADGE_IDS.push.apply(BADGE_IDS, seedAch);
  /* 图鉴：给 15 张卡里的前 2 张填上碎片数（1 张 1★、1 张 3★ ⇒ 4 星 / 45 = 9%） */
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
out('mp_me_test —— 「我的」簇运行时断言');
out('时间：' + new Date().toISOString());

/* ---------- A~E：我的页本体 ---------- */
sec('A 我的页头部');
let seed = null, me = null, calc = null;
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  seed = buildSeed(c0);
  me = bootPage(seed, 'pages/me/me.js');
  calc = require(path.join(MINI, 'lib/calc.js'));   // ⚠️ boot 之后（铁律）
  const d = me.data;
  const R = rankOf(seed.exp);

  must(d.statusBarHeight === 54, '状态栏留白取到真机值 54（三级兜底）', 'got ' + d.statusBarHeight);
  must(d.lv === R.lv && d.lv === 3, 'lv = floor(exp/100)+1 = 3', 'got ' + d.lv);
  must(d.rankName === R.rank.name && d.rankName === '小散', '段位名按 minLv 判定 = 小散', 'got ' + d.rankName);
  must(d.limitUpCount === 2, '持仓天数 = state.limitUpCount = 2', 'got ' + d.limitUpCount);
  must(d.dietCount === 3, '累计饮食 = diet.length = 3', 'got ' + d.dietCount);
  must(d.exCount === 1, '累计运动 = exercise.length = 1', 'got ' + d.exCount);
  must(d.badges === 5, '勋章 = 种子预置的 5 项且启动补发无新增（自洽存档）', 'got ' + d.badges);
  must(d.userId === 'FT_TEST', 'ID 显示 state.user.userId', 'got ' + d.userId);
  must(d.avatar === '', '未设头像 ⇒ avatar 为空（wxml 走占位图分支）', 'got ' + JSON.stringify(d.avatar));
}

sec('B 币卡与菜单');
{
  const d = me.data;
  must(d.coins === 320, '币卡余额 = state.coins = 320', 'got ' + d.coins);
  must(d.achTotal === 30, '成就总数 = ACHIEVEMENTS.length = 30', 'got ' + d.achTotal);
  const pct = collectPctOf(calc.CARDS, seed.cards);
  must(d.collectPct === pct, '收集度 = 星数/45 独立现算 = ' + pct + '%', 'got ' + d.collectPct);
  must(pct === 9, '独立现算的收集度确实是 9%（4 星 / 45）', 'got ' + pct);
}

sec('C 身体档案');
{
  const d = me.data;
  const u = seed.user;
  must(d.genderIdx === 0 && d.actIdx === 1, '性别/活动水平索引由 state.user 反查（male=0 / light=1）',
    'got ' + d.genderIdx + ',' + d.actIdx);
  must(d.bodyFig === '/images/me/body_male.png', '人形图路径随性别切换', 'got ' + d.bodyFig);
  const vs = d.vizStats;
  must(vs.length === 4, 'viz 四格', 'got ' + vs.length);
  must(vs[0].l === '性别' && vs[0].v === '男', '第 1 格 性别=男', JSON.stringify(vs[0]));
  must(vs[1].v === '30 岁' && vs[2].v === '175 cm' && vs[3].v === '80 kg',
    '年龄/身高/体重三格格式与 PWA 一致', JSON.stringify(vs.slice(1)));
  must(d.form.age === '30' && d.form.weight === '80' && d.form.bodyFat === '18'
    && d.form.restingHr === '58' && d.form.target === '-500',
    '表单初值 = state.user 的字符串形态', JSON.stringify(d.form));
  /* BMR 盒：种子里填了体脂率 18% ⇒ 内核走 Katch-McArdle（不是 Mifflin），独立复刻该公式比对 */
  const katch = bmrKatch(u);
  must(katch === 1787, '独立现算 Katch-McArdle（80kg / 体脂 18%）= 1787', 'got ' + katch);
  must(d.bmr && d.bmr.bmrV === katch, 'BMR 盒数值 = 独立 Katch 现算 = ' + katch, 'got ' + (d.bmr && d.bmr.bmrV));
  const tdeeInd = Math.round(katch * PAL.light);
  must(Math.abs(d.bmr.tdeeV - tdeeInd) <= 1, 'TDEE = BMR×PAL(1.375) 独立现算 ≈ ' + tdeeInd, 'got ' + d.bmr.tdeeV);
  must(d.bmr.tdeeLine.indexOf('× 1.375') > 0 && d.bmr.tdeeLine.indexOf('轻度') > 0,
    'TDEE 行显示系数与活动名', d.bmr.tdeeLine);
  must(/Katch-McArdle/.test(d.bmr.bmrFormula), '填了体脂 ⇒ 盒里露出的公式名是 Katch-McArdle', d.bmr.bmrFormula);
  must(!d.bmr.warn && /已填体脂率/.test(d.bmr.ok), '已填体脂 ⇒ 无降级提示、显示 Katch-McArdle 提示',
    'warn=' + d.bmr.warn + ' ok=' + d.bmr.ok);
  /* 同页两态负控：把体脂清空 ⇒ 主公式必须切回 Mifflin 且出现降级提示 */
  {
    const st = S().get();
    st.user.bodyFat = null;
    me.refresh();
    must(me.data.bmr.bmrV === bmrMifflin(st.user),
      '负控 · 清空体脂 ⇒ 主公式切回 Mifflin（' + bmrMifflin(st.user) + '）', 'got ' + me.data.bmr.bmrV);
    must(/Mifflin/.test(me.data.bmr.bmrFormula), '负控 · 公式名同步为 Mifflin', me.data.bmr.bmrFormula);
    must(/⚠ 降级提示/.test(me.data.bmr.warn), '负控 · 出现「未填体脂率」降级提示', me.data.bmr.warn.slice(0, 40));
    must(!me.data.bmr.ok, '负控 · 不再显示「已填体脂率」确认句', me.data.bmr.ok);
    st.user.bodyFat = 18;            // 还原，后续小节依赖
    me.refresh();
  }
  /* 活动水平界面文案的**顺序**必须与内核 id 顺序一致（否则 picker 选 A 存成 B） */
  const ids = calc.NutritionEngine.ACTIVITY_LEVELS.map((a) => a.id);
  must(ids.join(',') === 'sedentary,light,moderate,active,athlete',
    '内核 ACTIVITY_LEVELS 顺序 = 页面 ACT_LABELS 顺序（picker 索引对齐）', ids.join(','));
  must(d.actLabels.length === 5 && d.actLabels[1] === '轻度（每周 1～3 天）',
    '活动水平文案取自 PWA 的 <option> 原文', JSON.stringify(d.actLabels));
}

sec('D 表单交互');
{
  const st = S().get();
  /* 改活动水平 ⇒ 立刻写回 state 并重算（PWA 的 onchange=renderBodyViz() 等价物）
     ⚠️ 断言读活状态（loadState 给 user 做的是浅拷贝，seed.user 不会变） */
  me.onActChange({ detail: { value: '0' } });          // 切到 sedentary
  must(st.user.activity === 'sedentary', '改活动水平写回 state.user.activity', 'got ' + st.user.activity);
  must(me.data.actIdx === 0 && me.data.bmr.tdeeLine.indexOf('× 1.2') > 0,
    '活动水平切档后 TDEE 系数跟着变 1.2', me.data.bmr.tdeeLine);
  /* 改体重 ⇒ 当场重算 BMR（不等保存） */
  const before = me.data.bmr.bmrV;
  me.onFieldInput({ currentTarget: { dataset: { k: 'weight' } }, detail: { value: '100' } });
  const after = me.data.bmr.bmrV;
  must(after === bmrInd({ weight: 100, height: 175, age: 30, gender: 'male', bodyFat: 18 }),
    '改体重当场重算 BMR（100kg → ' + after + '）', 'got ' + after + ' before ' + before);
  must(after > before, '体重上调 ⇒ BMR 变大（方向正确）', before + ' → ' + after);
  must(me.data.form.weight === '100', '表单值同步到 data.form.weight', me.data.form.weight);
  /* 非 BMR 相关字段不该动 BMR */
  const keep = me.data.bmr.bmrV;
  me.onFieldInput({ currentTarget: { dataset: { k: 'target' } }, detail: { value: '-800' } });
  must(me.data.bmr.bmrV === keep, '改「目标缺口」不影响 BMR 盒', 'got ' + me.data.bmr.bmrV);
}

sec('E 上传档案');
{
  const st = S().get();
  /* ⚠️ 内核 recordWeight 的规则是「同一天覆盖当日点、跨天追加」；
     而 loadState() 在 weightLog 为空时会种入一个「真实锚点」（今天 + 当前体重）
     ⇒ 载入后必定已有 1 条，且它与今天同日期 ⇒ 第一次上传应当是**覆盖**。 */
  const wl0 = st.weightLog.length;
  must(wl0 === 1, '载入时按内核规则种入唯一真实锚点（1 条）', 'got ' + wl0);
  me.onFieldInput({ currentTarget: { dataset: { k: 'weight' } }, detail: { value: '77.7' } });
  calls.length = 0;
  me.uploadProfile();
  must(st.user.weight === 77.7, '上传后活状态 user.weight = 77.7', 'got ' + st.user.weight);
  must(st.weightLog.length === wl0, '同一天上传 ⇒ 覆盖当日点（条数不变）', 'got ' + st.weightLog.length);
  must(Number(st.weightLog[st.weightLog.length - 1].weight) === 77.7, '当日点的值被更新为 77.7',
    JSON.stringify(st.weightLog));
  must(calls.some((c) => c[0] === 'showModal' && /身体档案已上传/.test(c[1] || '')),
    '上传后有确认弹窗（内含新 BMR）', JSON.stringify(calls));
  /* 负控：把当日点改成昨天 ⇒ 再上传应**追加**一条（跨天语义） */
  st.weightLog[st.weightLog.length - 1].date = '2000-01-01';
  const wl1 = st.weightLog.length;
  me.onFieldInput({ currentTarget: { dataset: { k: 'weight' } }, detail: { value: '76.6' } });
  me.uploadProfile();
  must(st.weightLog.length === wl1 + 1, '负控 · 最后一条是旧日期 ⇒ 追加新点（' + wl1 + ' → ' + st.weightLog.length + '）',
    'got ' + st.weightLog.length);
  must(st.weightLog[st.weightLog.length - 1].date === todayStr()
    && st.weightLog[st.weightLog.length - 1].weight === 76.6,
    '负控 · 新点是「今天 + 新体重」', JSON.stringify(st.weightLog[st.weightLog.length - 1]));
  /* 写盘要真的过 storage（不是只改内存） */
  const raw = storage['jianpan_v2'];
  must(raw && raw.user && raw.user.weight === 76.6, 'storage 里的 user.weight 也是 76.6',
    'got ' + (raw && raw.user && raw.user.weight));
  const rawWl = raw && raw.weightLog || [];
  must(rawWl.length === st.weightLog.length, 'storage 里的 weightLog 条数与活状态一致',
    rawWl.length + ' vs ' + st.weightLog.length);
}

/* ---------- F：健康币子页 ---------- */
sec('F 健康币页 coins');
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  const s2 = buildSeed(c0);
  const pg = bootPage(s2, 'pages/coins/coins.js');
  const c = require(path.join(MINI, 'lib/calc.js'));
  const d = pg.data;

  must(d.balance === 320, '余额 = state.coins', 'got ' + d.balance);
  must(d.todayText === '今日已赚 40 / ' + c.COIN_DAILY_CAP,
    '今日已赚 = state.coinToday / COIN_DAILY_CAP', d.todayText);
  must(d.earn.length === 5, '「怎么赚」5 条', 'got ' + d.earn.length);
  must(d.earn[0].v === '+5' && d.earn[1].v === '+10', '记录饮食 +5 / 运动 +10（取自内核常量）',
    d.earn[0].v + ',' + d.earn[1].v);
  must(d.earn[2].v === '+200' && /每天限一次/.test(d.earn[2].d), '触发涨停 +200 且写明每天限一次', JSON.stringify(d.earn[2]));
  must(d.earn[3].v === '100' && /不占此额度/.test(d.earn[3].d), '每日上限 100 且注明涨停不占额度', JSON.stringify(d.earn[3]));
  must(d.earn[4].v === '+20~500' && d.earn[4].d.indexOf('30 项') > 0, '成就奖励 +20~500 / 30 项', JSON.stringify(d.earn[4]));
  must(d.spend.length === 3, '「怎么花」3 条', 'got ' + d.spend.length);
  must(d.spend[0].v === '50币/次' && /已上线/.test(d.spend[0].d), '抽卡 50币/次 · 已上线', JSON.stringify(d.spend[0]));
  must(!d.spend[1].v && !d.spend[2].v && /敬请期待/.test(d.spend[1].d),
    '后两条无价格且明写「敬请期待」（不假装已上线）', JSON.stringify(d.spend.slice(1)));

  /* 负控 1：改余额 ⇒ 跟着变（改**活状态**：loadState 对标量是拷贝，改 seed 无效） */
  const st = S().get();
  st.coins = 7;
  pg.refresh();
  must(pg.data.balance === 7, '负控 · 改 state.coins ⇒ 余额变 7', 'got ' + pg.data.balance);

  /* 负控 2：跨天 ⇒ 今日已赚归零（PWA renderCoins 的显示层重置） */
  st.coinDate = '2000-01-01';
  st.coinToday = 55;
  pg.refresh();
  must(st.coinToday === 0, '负控 · coinDate 是旧日期 ⇒ coinToday 归零', 'got ' + st.coinToday);
  must(pg.data.todayText === '今日已赚 0 / ' + c.COIN_DAILY_CAP, '负控 · 文案同步为 0', pg.data.todayText);
  must(st.coinDate === todayStr(), '负控 · coinDate 被刷成今天（幂等锚）', st.coinDate);
}

/* ---------- G：段位子页 ---------- */
sec('G 段位页 level');
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  const s3 = buildSeed(c0);
  const pg = bootPage(s3, 'pages/level/level.js');
  const d = pg.data;
  const R = rankOf(s3.exp);

  must(d.hero && d.hero.name === R.rank.name, '段位名 = 独立判定 ' + R.rank.name, 'got ' + (d.hero && d.hero.name));
  must(d.hero.lv === R.lv && d.hero.lv === 3, 'lv = 3', 'got ' + d.hero.lv);
  must(d.expText === '250 经验', '经验文案 = 「250 经验」', d.expText);
  must(d.pct === pctOf(s3.exp) && d.pct === 50, '经验条 = 本段进度 50%（250%100）', 'got ' + d.pct);
  must(d.tip === '距「中户」还差 250 经验', '距下一段 = next.minLv*100 − exp = 250', d.tip);
  must(d.ranks.length === 8, '段位列表 8 行', 'got ' + d.ranks.length);
  must(d.ranks[0].range === 'lv 1–2' && d.ranks[1].range === 'lv 3–4', '区间文案 lv a–b（en dash）',
    d.ranks[0].range + ' / ' + d.ranks[1].range);
  must(d.ranks[7].range === 'lv 17+', '末段文案 lv a+', d.ranks[7].range);
  const onRows = d.ranks.filter((r) => r.on);
  must(onRows.length === 1 && onRows[0].name === d.hero.name, '当前段位恰好 1 行高亮且与 hero 同名',
    JSON.stringify(onRows.map((r) => r.name)));

  /* 负控 1：零经验 ⇒ 散户 / 0% / 距小散 300 */
  const st = S().get();
  st.exp = 0;
  pg.refresh();
  must(pg.data.hero.name === '散户' && pg.data.pct === 0 && pg.data.tip === '距「小散」还差 300 经验',
    '负控 · exp=0 ⇒ 散户 / 0% / 距小散 300', pg.data.hero.name + ' ' + pg.data.pct + ' ' + pg.data.tip);

  /* 负控 2：顶段 ⇒ 已登顶、无下一段（这条同时守住「空存档也不能崩」） */
  st.exp = 1700;
  pg.refresh();
  must(pg.data.hero.name === '股神' && pg.data.tip === '已登顶，继续稳如泰山',
    '负控 · exp=1700（lv18）⇒ 股神 + 已登顶', pg.data.hero.name + ' / ' + pg.data.tip);
  must(pg.data.ranks.filter((r) => r.on).length === 1, '负控 · 顶段仍只有 1 行高亮', '');
  /* 负控 3：段位边界（lv 恰好落在 minLv 上，与「差一级」两态） */
  st.exp = 600;                        // lv 7 ⇒ 大户
  pg.refresh();
  must(pg.data.hero.name === '大户', '负控 · exp=600（lv7）⇒ 大户（边界含等号）', pg.data.hero.name);
  st.exp = 599;                        // lv 6 ⇒ 中户
  pg.refresh();
  must(pg.data.hero.name === '中户', '负控 · exp=599（lv6）⇒ 中户（差 1 点就掉级）', pg.data.hero.name);
}

/* ---------- H：空存档 ---------- */
sec('H 空存档（三页都不抛错）');
{
  const c0 = require(path.join(MINI, 'lib/calc.js'));
  const empty = c0.defaultState();
  let err = null, meD = null;
  try {
    const pg = bootPage(empty, 'pages/me/me.js');
    meD = pg.data;
  } catch (e) { err = e; }
  must(!err, '空存档 · 我的页 onLoad/onShow 不抛错', err && err.message);
  /* ⚠️ 内核 loadState() 有一条明确规则：「无历史记录时以当前真实体重作为唯一真实锚点（单点，非模拟数据）」
     ⇒ 真·空存档下体检卡是「天数 1 / 体重 1」，跨度=今天~今天。这不是脏数据，是内核设计。 */
  must(meD && meD.spanText === todayStr() + ' ~ ' + todayStr() + ' · 散户 Lv1',
    '空存档 · 体检跨度 = 今天~今天（唯一真实锚点）', meD && meD.spanText);
  must(meD && meD.cells.length === 6, '空存档 · 体检 6 格', meD && JSON.stringify(meD.cells));
  must(meD && meD.cells[0].v === 1 && meD.cells[3].v === 1 && meD.cells[1].v === 0 && meD.cells[2].v === 0,
    '空存档 · 天数/体重各 1（真实锚点），饮食/运动 0', meD && JSON.stringify(meD.cells));
  /* ⚠️ 空存档不是「全 0」：冷启动补发会立刻解锁 untie「解套成功」+50 币。
     为什么：默认档案 startWeight 75.5 / weight 72.8 ⇒ prog = 2.7 斤 ≥ target 1。
     **这是 PWA 行为，不是小程序偏差** —— 用 playwright 跑 PWA 空存储冷启动实测同值：
       {coins:50, coinsEarnedTotal:50, achTrue:['untie'], 且 localStorage 里已落盘}
     （见 promo/_probe_pwa_coldstart_ach.py；小程序的 store.init 静默补发正是它的等价物） */
  must(meD && meD.cells[4].v === 50, '空存档 · 健康币 50（默认档案已减 2.7 斤 ⇒ 补发「解套成功」）',
    meD && JSON.stringify(meD.cells[4]));
  must(meD && meD.lv === 1 && meD.rankName === '散户', '空存档 · lv1 散户',
    meD && (meD.lv + ' ' + meD.rankName));
  must(meD && meD.badges === 1 && meD.collectPct === 0, '空存档 · 勋章 1（只有 untie）/ 收集度 0%',
    meD && (meD.badges + ' / ' + meD.collectPct));
  must(meD && meD.bmr && meD.bmr.bmrV > 0, '空存档 · BMR 盒仍算得出（默认档案 30/175/72.8）', meD && JSON.stringify(meD.bmr));

  err = null;
  try { bootPage(c0.defaultState(), 'pages/coins/coins.js'); } catch (e) { err = e; }
  must(!err, '空存档 · 健康币页不抛错', err && err.message);

  err = null;
  let lvD = null;
  try { lvD = bootPage(c0.defaultState(), 'pages/level/level.js').data; } catch (e) { err = e; }
  must(!err, '空存档 · 段位页不抛错', err && err.message);
  must(lvD && lvD.hero.name === '散户' && lvD.pct === 0, '空存档 · 段位页散户 0%',
    lvD && (lvD.hero.name + ' ' + lvD.pct));
}

/* ============================================================
 * 成就补发专用夹具（I / J 两节共用 ⇒ 定义在文件层，不放进块里）
 * ============================================================ */
/* 基线态：把**所有成就 prog 的取值来源**显式压到 0。
   期望解锁集合 = ∅ 是**推出来的**，不是跑出来的 —— 逐条对照 ACHIEVEMENTS 的 prog：
     diet/exercise 长度 → leek/tryorder/halfpos/allin/hft/whale
     startWeight − weight → untie/wave/bull/exit
     coins / coinsEarnedTotal → dividend/smallmeat/richboy
     totalDraws → firstgacha/gachaking ｜ cards → open/rarefind/chosen/fulln/maxstar
     limitUpCount / limitUpStreak → firstboard/protrader/demon/godmode/secondboard
     streakDays → threeday/weekline/valueinvest ｜ everBroke → cutmeat
     maxOverage → blowup
   全部为 0 ⇒ 每个条件的 target（最小 1）都不成立。 */
function achBaseline(calc) {
  const st = calc.defaultState();
  st.diet = []; st.exercise = [];
  st.user.startWeight = st.user.weight;
  st.coins = 0; st.coinsEarnedTotal = 0;
  st.totalDraws = 0; st.cards = {};
  st.limitUpCount = 0; st.limitUpStreak = 0;
  st.streakDays = 0; st.everBroke = false; st.maxOverage = 0;
  st.ach = {};
  return st;
}
const recDiet = (kcal) => ({ id: 'r1', name: '测试餐', kcal: kcal, date: todayStr(),
                             time: '12:00', gram: 100, unit: 'g', qty: 1 });
/* 跑一次 sync，回报「新解锁了哪些 / 加了多少币」。⚠️ 必须先 bindState：sync 内部的
   calc.totals() 读的是内核当前绑定的那个 state，不绑就是拿上一节的状态在算。 */
function runSync(calc, progress, st) {
  calc.bindState(st);
  const c0 = st.coins, e0 = st.coinsEarnedTotal;
  const newly = progress.sync(st);
  return { ids: newly.map((a) => a.id).sort().join(','), n: newly.length,
           reward: newly.reduce((s, a) => s + a.reward, 0),
           dCoin: st.coins - c0, dEarn: st.coinsEarnedTotal - e0, state: st };
}

/* ---------- I：成就补发 lib/progress.js ---------- */
sec('I 成就补发（lib/progress.js）');
{
  const c = require(path.join(MINI, 'lib/calc.js'));
  const pr = require(path.join(MINI, 'lib/progress.js'));
  const achBaseline0 = () => achBaseline(c);
  const rec = recDiet;
  const runSync0 = (st) => runSync(c, pr, st);

  /* I-1 基线：零进度 ⇒ 一项都不解锁（负数控制：若哪条 prog 在零态返回 >0，这里立刻炸） */
  let r = runSync0(achBaseline0());
  must(r.n === 0, '零进度基线 ⇒ 新解锁 0 项', 'got ' + r.ids);
  must(r.dCoin === 0 && r.dEarn === 0, '零进度基线 ⇒ 币与累计币都不动',
    r.dCoin + ' / ' + r.dEarn);
  must(r.state.gapToday === true && r.state.maxOverage === 0,
    '零进度基线 ⇒ gapToday=true（净热量为负）且 maxOverage 不被写',
    r.state.gapToday + ' / ' + r.state.maxOverage);

  /* I-2 单变量：每个条件单独拉满到「刚达标」，期望集合与奖励都能从 target 表直接推出来 */
  const CASES = [
    ['limitUpCount = 1', (s) => { s.limitUpCount = 1; }, 'firstboard', 50],
    ['limitUpStreak = 2', (s) => { s.limitUpStreak = 2; }, 'secondboard', 100],
    ['limitUpCount = 20', (s) => { s.limitUpCount = 20; },
      'demon,firstboard,godmode,protrader', 50 + 200 + 500 + 300],
    ['totalDraws = 1', (s) => { s.totalDraws = 1; }, 'firstgacha', 20],
    ['everBroke = true', (s) => { s.everBroke = true; }, 'cutmeat', 50],
    ['streakDays = 7', (s) => { s.streakDays = 7; }, 'threeday,weekline', 30 + 80],
    ['coinsEarnedTotal = 1000', (s) => { s.coinsEarnedTotal = 1000; }, 'smallmeat', 30],
    ['diet 5 条', (s) => { s.diet = [rec(100), rec(100), rec(100), rec(100), rec(100)]; },
      'halfpos,leek,tryorder', 50 + 20 + 20],
    /* ⚠️ 这一格的期望值含**级联**：untie/wave/bull/exit 在 ACHIEVEMENTS 里的位置（index 1~4）
       早于 smallmeat（index 10），所以本次补发的 850 币当场就把 coinsEarnedTotal 顶过 500，
       「回口小肉」在同一次 sync 里跟着解锁 +30 ⇒ 合计 880。
       这不是 bug，是 PWA render() 同一段循环的**顺序决定的**行为（复刻目标就是这个顺序）；
       反之「limitUpCount = 20」那组不会级联 —— 那几项（index 20~24）排在 smallmeat 之后。 */
    ['weight 降 8（对 startWeight）', (s) => { s.user.weight = s.user.startWeight - 8; },
      'bull,exit,smallmeat,untie,wave', 200 + 500 + 30 + 50 + 100],
    ['diet+exercise 合计 100 条',
      (s) => { for (let i = 0; i < 100; i++) s.diet.push(rec(1)); },
      'halfpos,hft,leek,tryorder,whale', 50 + 100 + 20 + 20 + 200],
  ];
  CASES.forEach(([name, mutate, wantIds, wantReward]) => {
    const st = achBaseline0();
    mutate(st);
    const rr = runSync0(st);
    must(rr.ids === wantIds, '单变量 · ' + name + ' ⇒ 恰好解锁 ' + wantIds, 'got ' + rr.ids);
    must(rr.reward === wantReward && rr.dCoin === wantReward && rr.dEarn === wantReward,
      '单变量 · ' + name + ' ⇒ 发币 = 各 reward 之和 = ' + wantReward,
      rr.reward + ' / ' + rr.dCoin + ' / ' + rr.dEarn);
  });

  /* I-3 maxOverage 的**时序**：爆仓成就依赖同一次 sync 里先算出的 maxOverage。
     若把「更新 maxOverage」挪到成就判定之后，当天首次超标就永远不解锁（要等下一次）。
     期望 net 与 bmr 都在本文件里独立现算（bmrInd 是独立实现，见文件头）。 */
  {
    const st = achBaseline0();
    st.diet = [rec(3000)];
    const u = st.user;
    const netIndep = 3000 - (bmrInd(u) + 0);
    must(netIndep > 800, '独立现算 net=' + netIndep + ' 确实越过爆仓线 800', 'got ' + netIndep);
    const rr = runSync0(st);
    must(st.maxOverage === netIndep,
      'sync 顺带把 maxOverage 写成独立现算的 net=' + netIndep, 'got ' + st.maxOverage);
    must(rr.ids === 'blowup,leek,tryorder',
      '单次调用内 ⇒ 爆仓与两条「首次记录」同时解锁（顺序无关性）', 'got ' + rr.ids);
  }

  /* I-4 幂等负控：连调两次，第二次必须一项不发 */
  {
    const st = achBaseline0();
    st.limitUpCount = 1;
    const r1 = runSync0(st);
    const coins1 = st.coins, ach1 = JSON.stringify(st.ach);
    const r2 = runSync0(st);
    must(r1.n === 1 && r2.n === 0, '幂等 · 第一次解锁 1 项、第二次 0 项',
      r1.n + ' / ' + r2.n);
    must(st.coins === coins1 && JSON.stringify(st.ach) === ach1,
      '幂等 · 第二次调用币与 ach 都没动（锚 = state.ach[id]，不是凭 totals 重判）',
      coins1 + '→' + st.coins);
  }

  /* I-5 已解锁不重发（另一态：同样 limitUpCount=1，但 ach 里已经写着 true） */
  {
    const st = achBaseline0();
    st.limitUpCount = 1;
    st.ach = { firstboard: true };
    st.coins = 777;
    const rr = runSync0(st);
    must(rr.n === 0 && rr.dCoin === 0, '已解锁 · 不再重复发币', rr.ids + ' / ' + rr.dCoin);
    must(st.coins === 777, '已解锁 · 余额原封不动 = 777', 'got ' + st.coins);
    must(st.ach.firstboard === true, '已解锁 · 标记仍是 true', 'got ' + st.ach.firstboard);
  }

  /* I-6 gapToday 的**两种相反态**（同一函数跑出 true / false） */
  {
    const st = achBaseline0();
    st.diet = [rec(3000)];                 // 净 = 3000 − bmr > 0 ⇒ 超标
    runSync0(st);
    must(st.gapToday === false, 'gapToday · 净超标 ⇒ false', 'got ' + st.gapToday);
    const st2 = achBaseline0();
    st2.diet = [rec(10)];                  // 净 = 10 − bmr < 0 且 ≤ target(−500) ⇒ 达标
    runSync0(st2);
    must(st2.gapToday === true, 'gapToday · 净缺口达标 ⇒ true', 'got ' + st2.gapToday);
  }

  /* I-7 unlockedCount 的**专属负控**：ach 里的残留键不能被算进勋章数 */
  {
    const st = achBaseline0();
    st.ach = { __stale_deleted_ach__: true, firstboard: true };
    must(pr.unlockedCount(st) === 1,
      'unlockedCount · ach 里 1 个残留键 + 1 个真键 ⇒ 只数 1（⛔不能数 Object.keys）',
      'got ' + pr.unlockedCount(st));
    must(pr.unlockedCount({}) === 0 && pr.unlockedCount(null) === 0,
      'unlockedCount · 无 ach / 传 null ⇒ 0（不抛错）', '');
  }

  /* I-8 页面与 lib 的口径**同源**：我的页 badges 必须 = progress.unlockedCount。
     这是「两处各数一遍」的回归网 —— 谁以后在本页重写计数循环，这里就红。
     用「2 个真键 + 1 个残留键」的存档：真值只有 2，任何走 Object.keys 的实现都会给 3。 */
  {
    const bad = achBaseline0();
    bad.ach = { __stale_deleted_ach__: true, firstboard: true, tryorder: true };
    const meD = bootPage(bad, 'pages/me/me.js').data;
    /* ⚠️ require 必须在 bootPage **之后**：帧内 fresh() 会清掉 require.cache，
       先 require 拿到的是上一轮的旧实例（旧 state），对拍就成了自己跟自己比。 */
    const store0 = require(path.join(MINI, 'lib/store.js'));
    const pr0 = require(path.join(MINI, 'lib/progress.js'));
    const libN = pr0.unlockedCount(store0.get());
    must(meD.badges === libN && meD.badges === 2,
      '我的页 badges = progress.unlockedCount = 2（残留键不计，两处口径一致）',
      meD.badges + ' / lib ' + libN);
  }
}

/* ---------- J：store / app 接线（save / init / importPayload 三处补发） ---------- */
sec('J 成就补发接线（store.save / store.init / importPayload）');
{
  const c = require(path.join(MINI, 'lib/calc.js'));

  /* J-1 save()：判定必须发生在落盘之前 ⇒ 落盘值就是加币后的值 */
  const s1 = achBaseline(c);
  s1.limitUpCount = 0;
  bootApp(s1);                                   // init：此时无达标项 ⇒ 无动静
  const store1 = require(path.join(MINI, 'lib/store.js'));
  const live = store1.get();
  must(live.limitUpCount === 0 && live.coins === 0, 'J-1 前置：干净启动（0 币 / 0 持仓天数）',
    live.coins + ' / ' + live.limitUpCount);
  calls.length = 0;
  live.limitUpCount = 1;                          // 造一个「刚刚达标」
  const saved = store1.save();
  must(saved === true, 'J-1 store.save() 返回 true', 'got ' + saved);
  must(live.ach.firstboard === true, 'J-1 save 顺带解锁 firstboard', 'got ' + live.ach.firstboard);
  must(live.coins === 50 && live.coinsEarnedTotal === 50,
    'J-1 save 顺带发币 +50（币与累计币都加）', live.coins + ' / ' + live.coinsEarnedTotal);
  const disk1 = storage['jianpan_v2'];
  must(disk1.coins === 50 && disk1.ach && disk1.ach.firstboard === true,
    'J-1 落盘的是**加币后**的值（判定先于写盘）',
    JSON.stringify({ coins: disk1.coins, ach: disk1.ach }));
  const t1 = calls.filter((x) => x[0] === 'showToast');
  must(t1.length === 1 && /首板/.test(String(t1[0][1])),
    'J-1 解锁钩子弹了一条 toast（含成就名）', JSON.stringify(t1));

  /* J-2 幂等：再 save 一次不该二次发币 */
  const t2 = calls.length;
  store1.save();
  must(live.coins === 50, 'J-2 重复 save 不二次发币（余额仍 50）', 'got ' + live.coins);
  must(calls.length - t2 === 0, 'J-2 重复 save 不再弹提示', 'got ' + (calls.length - t2));

  /* J-3 init 冷启动补发：存档里「早已达标但从没判过」⇒ 补上并落盘，但**静默** */
  const s3 = achBaseline(c);
  s3.limitUpCount = 3;                            // firstboard(1) 达标；protrader(5) 未达
  bootApp(s3);
  const store3 = require(path.join(MINI, 'lib/store.js'));
  const live3 = store3.get();
  must(live3.ach.firstboard === true && live3.coins === 50,
    'J-3 冷启动补发：ach.firstboard=true / +50 币', live3.coins + ' / ' + JSON.stringify(live3.ach));
  must(storage['jianpan_v2'].ach.firstboard === true && storage['jianpan_v2'].coins === 50,
    'J-3 冷启动补发**落了盘**（不是只在内存里）',
    JSON.stringify({ coins: storage['jianpan_v2'].coins }));
  must(calls.filter((x) => x[0] === 'showToast').length === 0,
    'J-3 冷启动补发静默（不弹 toast —— 导入/迁移可能一次补十几项）',
    JSON.stringify(calls.filter((x) => x[0] === 'showToast')));

  /* J-4 importPayload：导入的是别处的历史 ⇒ 必须补判，且**要弹提示**（用户主动动作） */
  bootApp(achBaseline(c));
  calls.length = 0;
  const store4 = require(path.join(MINI, 'lib/store.js'));
  const payload = { __app: 'fitness-trader', __schema: 1,
                    state: Object.assign(achBaseline(c), { limitUpCount: 2, coins: 7 }) };
  const imported = store4.importPayload(payload);
  must(imported.ach.firstboard === true, 'J-4 导入后补判出 firstboard',
    JSON.stringify(imported.ach));
  must(imported.coins === 57, 'J-4 导入余额 7 + 补发 50 = 57', 'got ' + imported.coins);
  const t4 = calls.filter((x) => x[0] === 'showToast');
  must(t4.length === 1 && /首板/.test(String(t4[0][1])),
    'J-4 导入触发的解锁**有**提示', JSON.stringify(t4));
}

/* ============================================================
 * K 个人资料编辑（头像 / ID）+ 自建食物迁移接线
 *
 * 起因（2026-09-24 Mak 真机反馈）：
 *   · 「我的页面，点击头像无法更换头像和ID昵称」—— me.js 的 openProfileEdit 原本只是
 *      一句 toast 占位（迁移文档写明「本轮不做」）⇒ 这次补齐。
 *   · 「json 导出的存档里为何没有自建的食物」的 UI 侧：页面必须在导入时把
 *      customFoods 一起交给 applyImport，漏了第二个参数就会「导入成功但自建食物没进来」。
 *
 * ⚠️ 头像管道（chooseMedia → getImageInfo → canvas → canvasToTempFilePath → readFile）
 *    全链是异步的 ⇒ 本节放在 pending 里，最后用 Promise.all 统一收尾出报告。
 * ============================================================ */
sec('K 个人资料编辑（头像 / ID）+ 自建食物接线');
const pending = [];
{
  const cK = require(path.join(MINI, 'lib/calc.js'));
  const sK = buildSeed(cK);
  const mK = bootPage(sK, 'pages/me/me.js');

  const meWxml = fs.readFileSync(path.join(MINI, 'pages/me/me.wxml'), 'utf8');
  const meJs = fs.readFileSync(path.join(MINI, 'pages/me/me.js'), 'utf8');

  /* ---- 静态口径 ---- */
  const sheets = meWxml.match(/class="sheet-mask"/g) || [];
  must(sheets.length === 1, 'me.wxml 有 1 个资料编辑弹层（.sheet-mask）', '命中 ' + sheets.length);
  must(/wx:if="\{\{pe\.show\}\}"/.test(meWxml),
    '弹层用 wx:if 而非 display:none（藏起来的元素 rect 照样量得到，会把对拍带偏）');
  must(/catchtap="stopTap"/.test(meWxml),
    '弹层内容区用 catchtap="stopTap"（bindtap 不阻止冒泡 ⇒ 点空白就关掉弹层）');
  must(typeof mK.stopTap === 'function', 'me.js 定义了 stopTap（wxml 引用了它）');
  must(/id="av-canvas"/.test(meWxml) && /type="2d"/.test(meWxml),
    '页面里有 type=2d 的隐藏画布 #av-canvas（头像压缩要用）');
  must(/lib\/avatar\.js/.test(meJs), 'me.js 走 lib/avatar.js 的压缩管道（页面零判定）');

  /* ---- 纯函数：尺寸规划（PWA 口径：只在超出时缩，最长边 256）---- */
  const AV = require(path.join(MINI, 'lib/avatar.js'));
  const p1 = AV.planSize(1024, 800, 256);
  must(p1.w === 256 && p1.h === 200 && p1.scaled === true,
    'planSize(1024×800) ⇒ 256×200 等比缩放', JSON.stringify(p1));
  const p2 = AV.planSize(100, 80, 256);
  must(p2.w === 100 && p2.h === 80 && p2.scaled === false,
    '小图不放大（放大只会更糊、字符串更大）', JSON.stringify(p2));
  const p3 = AV.planSize(256, 256, 256);
  must(p3.w === 256 && p3.h === 256 && p3.scaled === false, '恰好等于上限时不动', JSON.stringify(p3));
  const p4 = AV.planSize(0, 80, 256);
  must(p4.w === 0 && p4.h === 0, '尺寸非法 ⇒ 返回 0（调用方据此报「图片尺寸异常」）', JSON.stringify(p4));
  must(AV.MAX === 256 && AV.QUALITY === 0.85 && AV.PREFIX === 'data:image/jpeg;base64,',
    '常量与 PWA 对齐（256 / q0.85 / jpeg data URL）',
    AV.MAX + ' / ' + AV.QUALITY + ' / ' + AV.PREFIX);

  /* ---- 校验器：把脏串挡回去，别渲染成破图 ---- */
  must(AV.isDataUrl('data:image/jpeg;base64,AAAA') === true, '认 jpeg data URL');
  must(AV.isDataUrl('data:image/png;base64,AAAA') === true, '认 png data URL');
  must(AV.isDataUrl('blob:http://localhost/x') === false, '不认 blob:（换机必成死链）');
  must(AV.isDataUrl('data:image/jpeg;base64,') === false, '不认空载荷');
  must(AV.isDataUrl('data:image/jpeg;base64,AA AA') === false, '不认带空格的伪 base64');

  /* ---- 弹层开关 ---- */
  mK.openProfileEdit();
  must(mK.data.pe.show === true, 'openProfileEdit 打开弹层');
  must(mK.data.pe.id === sK.user.userId,
    '弹层里预填当前 ID（= state.user.userId）', mK.data.pe.id);
  must(mK.data.pe.avatar === (sK.user.avatar || ''), '弹层里预填当前头像');

  /* ---- 自定义 ID：非空才写（留空 = 「这次不改」，不是「清空」）---- */
  mK.onPeIdInput({ detail: { value: '  LION_888  ' } });
  mK.saveProfileEdit();
  const s1 = require(path.join(MINI, 'lib/store.js')).get();
  must(s1.user.userId === 'LION_888', '保存自定义 ID（首尾空格已 trim）', s1.user.userId);
  must(mK.data.pe.show === false, '保存后弹层关闭');
  must(mK.data.userId === 'LION_888', '页头 ID 立刻跟着变');
  must(storage['jianpan_v2'].user.userId === 'LION_888', 'ID 落了盘');

  mK.openProfileEdit();
  mK.onPeIdInput({ detail: { value: '   ' } });
  mK.saveProfileEdit();
  must(require(path.join(MINI, 'lib/store.js')).get().user.userId === 'LION_888',
    '负控 · ID 留空保存 ⇒ 不改（照 PWA 语义：留空是「这次不改」，不是「清空账号」）',
    require(path.join(MINI, 'lib/store.js')).get().user.userId);

  /* ---- 自建食物：页面必须把行李位原样交给 applyImport ---- */
  const FoodK = require(path.join(MINI, 'lib/food-store.js'));
  must(mK._customLine({ present: false, list: [] }) === '自建食物：存档未携带，本机现有的保持不变',
    '「未携带」的措辞（否则用户会以为自己的食物要被删）',
    mK._customLine({ present: false, list: [] }));
  must(mK._customLine({ present: true, list: [1, 2] }) === '自建食物：存档带 2 条，导入后以存档为准',
    '「带了 N 条」的措辞', mK._customLine({ present: true, list: [1, 2] }));

  /* 端到端接线：确认框点「导入」后，自建食物必须真的落到本机。
     ⚠️ 这正是「页面忘了传第二个参数」那类静默缺陷的守门断言 ——
        state 照常导入成功、不报任何错，只有自建食物没进来。 */
  const incoming = JSON.parse(JSON.stringify(buildSeed(cK)));
  const realModal = global.wx.showModal;
  global.wx.showModal = (o) => { calls.push(['showModal', o && o.title]); if (o && o.success) o.success({ confirm: true }); };
  mK.confirmApply({
    data: incoming, sv: { days: 1, diet: 3, exercise: 1 },
    customFoods: { present: true, list: [{ name: '迁移来的自制酱', kcal: 88, py: 'qyldzj', ini: 'QYLDZJ', src: 'custom' }] },
    src: '剪贴板',
  });
  must(FoodK.loadCustom().length === 1 && FoodK.loadCustom()[0].name === '迁移来的自制酱',
    '点「导入」后自建食物真的落盘（页面把 customFoods 传下去了）',
    JSON.stringify(FoodK.loadCustom()));
  must(mK.data.result.ok === true, '导入结果提示为成功', JSON.stringify(mK.data.result));

  /* 负控：存档「没带」行李位时，本机自建食物必须一条不动 */
  const incoming2 = JSON.parse(JSON.stringify(buildSeed(cK)));
  mK.confirmApply({ data: incoming2, sv: { days: 1, diet: 3, exercise: 1 },
                    customFoods: { present: false, list: [] }, src: '剪贴板' });
  must(FoodK.loadCustom().length === 1,
    '负控 · 存档没带行李位（PWA 备份）⇒ 本机自建食物一条不动',
    JSON.stringify(FoodK.loadCustom()));
  global.wx.showModal = realModal;

  /* ---- 头像管道（异步）---- */
  pending.push((async function () {
    avDraw.length = 0; avLastTemp = null; avNode = null;
    avChoose = 'ok';
    const before = calls.length;
    mK.pickAvatar();
    /* 两次微任务让渡：queryCanvas 一级 + compressToDataUrl 内部 getImageInfo/canvasToTempFilePath/readFile 一级 */
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    const live = require(path.join(MINI, 'lib/store.js')).get();
    must(AV.isDataUrl(live.user.avatar) === true,
      '选图后 state.user.avatar 是合法 jpeg data URL',
      String(live.user.avatar).slice(0, 40));
    must(live.user.avatar === 'data:image/jpeg;base64,QkFTRTY0UEFZTE9BRA==',
      '内容就是压缩产物（不是本地路径 —— 存路径换机必成死链）',
      String(live.user.avatar).slice(0, 44));
    must(mK.data.pe.avatar === live.user.avatar, '弹层里的预览环立刻回填新头像');
    must(mK.data.avatar === live.user.avatar, '页头头像立刻跟着变');
    must(storage['jianpan_v2'].user.avatar === live.user.avatar, '头像落了盘（重进页面还在）');

    must(avNode && avNode.width === 256 && avNode.height === 200,
      '画布位图尺寸 = 压缩后尺寸 256×200（先设尺寸再取 ctx，否则位图被重置）',
      avNode ? avNode.width + '×' + avNode.height : '没有拿到节点');
    const di = avDraw.filter((x) => x[0] === 'drawImage')[0];
    must(di && di[3] === 256 && di[4] === 200,
      'drawImage 按目标尺寸铺满（不是按原图 1024×800 铺偏）',
      JSON.stringify(di));
    must(avDraw.filter((x) => x[0] === 'clearRect').length === 1, '重绘前清一次画布');
    must(avLastTemp && avLastTemp.fileType === 'jpg' && avLastTemp.quality === 0.85,
      '导出用 jpeg q0.85（与 PWA 的 toDataURL("image/jpeg", 0.85) 一致）',
      avLastTemp ? (avLastTemp.fileType + ' / ' + avLastTemp.quality) : '没调用');
    must(avLastTemp && avLastTemp.destWidth === 256 && avLastTemp.destHeight === 200,
      '导出尺寸 = 256×200（不重采样，避免二次劣化）',
      avLastTemp ? (avLastTemp.destWidth + '×' + avLastTemp.destHeight) : '没调用');
    const toasts = calls.slice(before).filter((x) => x[0] === 'showToast');
    must(toasts.length === 1 && /头像已更新/.test(String(toasts[0][1])),
      '成功后有且仅有一条提示', JSON.stringify(toasts));

    /* 负控：用户取消 ⇒ 静默（不弹提示、不改数据） */
    const keep = require(path.join(MINI, 'lib/store.js')).get().user.avatar;
    avChoose = 'cancel';
    const b2 = calls.length;
    mK.pickAvatar();
    await new Promise((r) => setTimeout(r, 0));
    must(calls.slice(b2).filter((x) => x[0] === 'showToast').length === 0,
      '负控 · 用户取消选图 ⇒ 不弹任何提示（取消不是错误）',
      JSON.stringify(calls.slice(b2)));
    must(require(path.join(MINI, 'lib/store.js')).get().user.avatar === keep,
      '负控 · 取消后头像一字未改');

    avChoose = 'ok';
  })());
}

/* ---------- 汇总 ---------- */
Promise.all(pending).then(finish).catch((e) => {
  /* ⚠️ 异步段落自身抛错必须计为失败：否则「K 段整段没跑完」会以退出码 0 收场，
     看起来全绿 —— 这正是「假保证」三连里的第 2 条（未测到要算失败）。 */
  fails.push('K 头像管道自身异常 → ' + (e && e.message));
  out('  ✗ K 头像管道自身异常 → ' + (e && e.message));
  finish();
});
function finish() {
out('');
out('============================================================');
out('通过 ' + pass + ' 项，失败 ' + fails.length + ' 项');
fails.forEach((f) => out('  ✗ ' + f));
out('RESULT=' + (fails.length ? 'FAIL' : 'OK'));
fs.writeFileSync(OUT, lines.join('\n'), 'utf8');
console.log('通过 ' + pass + ' 项，失败 ' + fails.length + ' 项');
console.log('RESULT=' + (fails.length ? 'FAIL' : 'OK') + '  → ' + OUT);
process.exit(fails.length ? 1 : 0);
}
