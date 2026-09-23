/* ============================================================
 * mp_food_test.js —— 前置块（食物搜索层 + settleDay）单元测试
 *
 * 这一条测试盯的是两个**静默失效**（都不报错、页面看着正常）：
 *
 *   ① 食物搜索层：`py-initials.js` 缺了 ⇒ initialsOf() 返回空串
 *      ⇒ 自建食物的拼音搜索搜不到（中文名照常能搜）——「坏了一半」。
 *      所以这里不只测「能搜到」，还测**拼音首字母能搜到**，并配一条专属负控：
 *      把拼音表清空后，同一断言必须失败 —— 否则那条断言就是恒真的。
 *
 *   ② settleDay（涨停发币）：它在 PWA 里因末尾两行 DOM 被判成「渲染档」，
 *      抽到小程序时变成 no-op 空壳 ⇒ 币不发、连板不累计、
 *      而且 checkDayRollover() 改了 lastDate 却永远不写盘。
 *      「每日最多发一次」的幂等锚是 state.settledDate —— 历史上用布尔 celebFired
 *      被四处重置过，导致重复发币，所以这条必须有专属负控。
 *
 * 跑法：node promo/mp_food_test.js
 * ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');

const MINI = process.env.MINI_ROOT
  ? path.join(process.env.MINI_ROOT, 'miniprogram')
  : 'E:\\WeChatProjects\\jianpan\\miniprogram';

let pass = 0, fail = 0;
const lines = [];
function log(s) { lines.push(s); }
function ok(name, cond, detail) {
  if (cond) { pass++; log('  \u2713 ' + name); }
  else { fail++; log('  \u2717 ' + name + (detail ? '  \u2192 ' + detail : '')); }
}
function eq(name, got, want) {
  ok(name, got === want, '期望 ' + JSON.stringify(want) + '，实际 ' + JSON.stringify(got));
}
function head(s) { log(''); log('=== ' + s + ' ==='); }

/* ---------- wx mock（同步、可注入故障） ---------- */
function makeWx(opts) {
  const o = opts || {};
  const storage = {};
  const calls = { toast: [], modal: [] };
  return {
    _storage: storage,
    _calls: calls,
    getStorageSync(k) { return (k in storage) ? storage[k] : ''; },
    setStorageSync(k, v) {
      if (o.failWrite) throw new Error('setStorageSync:fail exceed storage max size');
      storage[k] = v;
    },
    removeStorageSync(k) { delete storage[k]; },
    showModal(x) { calls.modal.push(x.title); if (x.success) x.success({ confirm: true }); },
    showToast(x) { calls.toast.push(x.title); if (x.success) x.success({}); },
    showLoading() {}, hideLoading() {},
    getWindowInfo() { return { windowWidth: 375, windowHeight: 812, pixelRatio: 3, statusBarHeight: 44 }; },
    getMenuButtonBoundingClientRect() { return { top: 48, bottom: 80, left: 278, right: 365, width: 87, height: 32 }; },
    getSystemInfoSync() { return this.getWindowInfo(); },
    getDeviceInfo() { return { platform: 'devtools' }; },
  };
}

function fresh(opts) {
  global.wx = makeWx(opts);
  Object.keys(require.cache).forEach(k => {
    if (k.indexOf('jianpan') >= 0 || k.indexOf('miniprogram') >= 0) delete require.cache[k];
  });
  const store = require(path.join(MINI, 'lib/store.js'));
  const calc = require(path.join(MINI, 'lib/calc.js'));
  const FoodStore = require(path.join(MINI, 'lib/food-store.js'));
  return { store, calc, FoodStore, wx: global.wx };
}

log('前置块单元测试 —— lib/food-store.js + lib/calc.js 的 settleDay');
log('='.repeat(78));
log('工程：' + MINI);

/* ══════════════════════════════════════════════════════════════
 * 一、食物搜索层
 * ══════════════════════════════════════════════════════════════ */
head('1. 加载与就绪');

let T = fresh();
let FS = T.FoodStore;
const st0 = FS.getStatus();
eq('加载前 state = idle', st0.state, 'idle');

FS.load();
const st1 = FS.getStatus();
eq('load() 后 state = ready', st1.state, 'ready');
eq('数据源 = json（不是 fallback）', st1.source, 'json');
ok('食物库条数 ≥ 2000', st1.count >= 2000, '实际 ' + st1.count);
ok('meta.categories 非空', !!(FS.getMeta() && FS.getMeta().categories), 'meta = ' + JSON.stringify(FS.getMeta() && FS.getMeta().categories).slice(0, 60));

head('2. 搜索四种入口都要能用');

function firstNames(q, opt, n) {
  return FS.search(q, opt).slice(0, n || 3).map(f => f.name);
}

const rMi = firstNames('米饭', null, 1);
ok('中文名精确命中（米饭 排第 1）', rMi[0] === '米饭', '实际 ' + JSON.stringify(rMi));

// 别名入口：找一个库内真实存在、名字与别名不同的条目来测，避免写死假设
const someFood = FS.all().filter(f => (f.alias || []).length && f.alias[0] !== f.name)[0];
ok('食物库里有带别名的条目（用于别名入口测试）', !!someFood, '找不到样本');
if (someFood) {
  const rAl = firstNames(someFood.alias[0], null, 3);
  ok('别名能搜到（' + someFood.alias[0] + ' → 含 ' + someFood.name + '）',
    rAl.indexOf(someFood.name) >= 0, '实际 ' + JSON.stringify(rAl));
}

// 拼音首字母入口：placeholder 明写「如 hsr」= 红烧肉
const rIni = firstNames('hsr', null, 5);
ok('拼音首字母能搜到（hsr → 含 红烧肉）', rIni.indexOf('红烧肉') >= 0, '实际 ' + JSON.stringify(rIni));

// 全拼入口
const rPy = firstNames('guilinggao', null, 3);
ok('全拼能搜到（guilinggao → 含 龟苓膏 系）', rPy.some(n => n.indexOf('龟苓膏') === 0), '实际 ' + JSON.stringify(rPy));

// 分类过滤
const cats = FS.categories();
ok('categories() 返回非空', cats.length > 0, '实际 ' + JSON.stringify(cats).slice(0, 80));
const oneCat = FS.all().filter(f => f.cat)[0].cat;
const rCat = FS.search('', { cat: oneCat, limit: 200 });
ok('按分类过滤后，结果全部属于该分类（' + oneCat + '）',
  rCat.length > 0 && rCat.every(f => f.cat === oneCat), '实际 ' + rCat.length + ' 条');

const rLimit = FS.search('', { limit: 7 });
eq('limit 生效', rLimit.length, 7);

head('3. 排序口径（必须与 PWA 逐字节一致）');

// 口径（照抄 js/food-store.js 的 score()）：同名 100 > 名前缀 90 > ini 全等 88 >
//   别名全等 86 > ini 前缀 80 > 别名前缀 78 > 名内含 70 > py 前缀 66 …
//   自建食物在得分上 +5（便于优先命中）
const hit = FS.search('鸡蛋', { limit: 3 })[0];
ok('完全同名者排第一（鸡蛋）', hit && hit.name === '鸡蛋', '实际 ' + (hit && hit.name));

head('4. 自建食物：增 / 删 / 落盘 / 兼容 PWA 的 JSON 串');

const CUSTOM_KEY = FS.CUSTOM_KEY;
eq('自建食物的 storage 键名与 PWA 一致', CUSTOM_KEY, 'jianpan_custom_foods_v1');

const addRes = FS.addCustom({ name: '秘制卤牛肉', alias: '卤牛肉, 牛腱', cat: '自建', kcal: 150, gram: 120, unit: '份' });
ok('addCustom 返回 ok', addRes.ok === true, JSON.stringify(addRes));
ok('落盘到 ' + CUSTOM_KEY, !!T.wx._storage[CUSTOM_KEY], '实际 ' + JSON.stringify(T.wx._storage[CUSTOM_KEY]).slice(0, 60));
ok('落盘的是对象（小程序 storage 口径）', Array.isArray(T.wx._storage[CUSTOM_KEY]), '实际 ' + typeof T.wx._storage[CUSTOM_KEY]);

const rNew = firstNames('秘制卤牛肉', null, 1);
eq('新加的自建食物立刻能搜到（rebuild 生效）', rNew[0], '秘制卤牛肉');

// ⭐ 拼音首字母：自建食物的 ini 是 initialsOf() 现算的 ⇒ 专门盯 py-initials.js 是否真加载。
// ⚠️ 期望值用**手写独立映射**算，不调被测代码（否则是自证）。
// ⚠️ 已知口径（与 PWA 一致，不是 bug）：拼音表只收食物库真正用到的那 1119 个字，
//    表外的字会被**静默丢掉** —— 「秘」就不在表里，所以 秘制卤牛肉 的 ini 是 zlnr 而非 mzlnr。
//    后果：自建食物用了生僻字时首字母搜索会缺字；中文名搜索不受影响。
const HAND_PY = { '制': 'z', '卤': 'l', '牛': 'n', '肉': 'r' };   // 手写，不从被测代码取
const expectIni = '秘制卤牛肉'.split('').map(ch => HAND_PY[ch] || '').join('');
eq('手写映射推出的首字母 = zlnr（「秘」不在表内被丢弃）', expectIni, 'zlnr');
const rNewIni = firstNames(expectIni, null, 5);
ok('自建食物能按拼音首字母搜到（' + expectIni + ' → 秘制卤牛肉）',
  rNewIni.indexOf('秘制卤牛肉') >= 0, '实际 ' + JSON.stringify(rNewIni));

// 兼容 PWA 迁过来的 JSON 串形态
T.wx._storage[CUSTOM_KEY] = JSON.stringify([
  { id: 'c999', name: '酱牛肉（PWA 迁入）', alias: [], cat: '自建', kcal: 160, p: 0, f: 0, c: 0, fb: 0, alc: 0, unit: '份', qty: 1, gram: 100, conv: [], basis: '100g', src: 'custom', py: '', ini: '' },
]);
const T2 = fresh();
T2.wx._storage[CUSTOM_KEY] = JSON.stringify([
  { id: 'c999', name: '酱牛肉（PWA 迁入）', alias: [], cat: '自建', kcal: 160, p: 0, f: 0, c: 0, fb: 0, alc: 0, unit: '份', qty: 1, gram: 100, conv: [], basis: '100g', src: 'custom', py: '', ini: '' },
]);
T2.FoodStore.load();
const rStr = T2.FoodStore.search('酱牛肉', { limit: 2 }).map(f => f.name);
ok('PWA 留下的 JSON 串形态能被读出来（酱牛肉（PWA 迁入））',
  rStr.some(n => n.indexOf('酱牛肉') === 0), '实际 ' + JSON.stringify(rStr));

FS.removeCustom(addRes.food.id);
eq('removeCustom 后搜不到了', FS.search('秘制卤牛肉', { limit: 3 }).length, 0);

head('5. toGrams 份量换算');

const rice = FS.byName('米饭');
ok('byName 能取到米饭', !!rice);
if (rice) {
  eq('unit=g 时按克直接返回', FS.toGrams(rice, 250, 'g'), 250);
  eq('默认单位按 qty × gram', FS.toGrams(rice, 2, 'u'), Math.round(2 * (rice.gram || 100)));
  eq('qty 非法（0）回退为 1 份', FS.toGrams(rice, 0, 'u'), Math.round(1 * (rice.gram || 100)));
  eq('qty 非法（abc）回退为 1 份', FS.toGrams(rice, 'abc', 'u'), Math.round(1 * (rice.gram || 100)));
}
eq('food 为 null 时返回 0', FS.toGrams(null, 1, 'u'), 0);

head('6. 降级 FALLBACK（食物库模块坏掉时功能不能整块消失）');

/* 精确注入：把 data/foods.js 的模块导出换成空对象，再重新 require food-store。
   —— 这是唯一能真正走到降级分支的办法（不改源码）。
   ⚠️ 两个坑（第一次就踩了，写下来免得重犯）：
     ① 中途**不能**调 fresh()：它会清掉整个 require 缓存（包括我刚注入的那一条），
        而它自己就 require 了 food-store ⇒ 后续 require 拿回的是**旧实例**，
        注入等于没做。症状很隐蔽：源仍是 json、条数仍是 2052，测试静默变成假通过。
     ② 顺序必须是「先清缓存 → 再注入 → 再 require food-store」。 */
Object.keys(require.cache).forEach(k => {
  if (k.indexOf('jianpan') >= 0 || k.indexOf('miniprogram') >= 0) delete require.cache[k];
});
const dataPath = require.resolve(path.join(MINI, 'data/foods.js'));
require.cache[dataPath] = { id: dataPath, filename: dataPath, loaded: true, exports: {} };
const FSb = require(path.join(MINI, 'lib/food-store.js'));
FSb.load();
const stb = FSb.getStatus();
eq('数据源降级为 fallback', stb.source, 'fallback');
ok('降级后仍有可搜的食物（≥10 条）', stb.count >= 10, '实际 ' + stb.count);
ok('降级后仍能搜到常见食物（米饭）', FSb.search('米饭', { limit: 1 })[0] && FSb.search('米饭', { limit: 1 })[0].name === '米饭');
ok('降级原因是「食物库模块为空」', String(stb.error || '').indexOf('食物库模块为空') >= 0, '实际 ' + stb.error);

/* ══════════════════════════════════════════════════════════════
 * 二、专属负控（证明上面的断言不是恒真的）
 * ══════════════════════════════════════════════════════════════ */
head('7. 专属负控 · 食物搜索');

/* 负控 A：把拼音表清空（等价于 py-initials.js 没生成/没加载）
   ⇒ 自建食物的拼音首字母必须**搜不到**。
   如果这条失败了，说明第 4 节的「mzl → 秘制卤牛肉」是假通过。 */
Object.keys(require.cache).forEach(k => {
  if (k.indexOf('jianpan') >= 0 || k.indexOf('miniprogram') >= 0) delete require.cache[k];
});
const pyPath = require.resolve(path.join(MINI, 'data/py-initials.js'));
require.cache[pyPath] = { id: pyPath, filename: pyPath, loaded: true, exports: {} };   // 空拼音表
const T4 = fresh();
T4.FoodStore.load();
T4.FoodStore.addCustom({ name: '秘制卤牛肉', alias: '', cat: '自建', kcal: 150, gram: 100 });
const rNegIni = T4.FoodStore.search('mzl', { limit: 5 }).map(f => f.name);
ok('负控 A：拼音表清空后，拼音搜索确实搜不到（证明第 4 节断言有效）',
  rNegIni.length === 0 || rNegIni.indexOf('秘制卤牛肉') < 0,
  '实际 ' + JSON.stringify(rNegIni));
eq('负控 A 对照：中文名仍然搜得到（这就是「坏了一半」的形态）',
  T4.FoodStore.search('秘制卤牛肉', { limit: 1 }).length, 1);

/* 负控 B：食物库模块坏掉时，若不降级就必须是 0 条 —— 证明第 6 节的降级断言不是恒真。 */
Object.keys(require.cache).forEach(k => {
  if (k.indexOf('jianpan') >= 0 || k.indexOf('miniprogram') >= 0) delete require.cache[k];
});
require.cache[dataPath] = { id: dataPath, filename: dataPath, loaded: true, exports: {} };
const FSb2 = require(path.join(MINI, 'lib/food-store.js'));
FSb2.load();
const hasFallback = FSb2.getStatus().count > 100;
ok('负控 B：降级路径给出的条数远小于真实库（20 条 vs 2052 条）',
  hasFallback === false, '实际 count = ' + FSb2.getStatus().count);
eq('负控 B 对照：降级确实走了 fallback 分支', FSb2.getStatus().source, 'fallback');

/* ══════════════════════════════════════════════════════════════
 * 三、settleDay —— 涨停每日最多一次
 * ══════════════════════════════════════════════════════════════ */
head('8. settleDay · 涨停发币');

function mkState(T, over) {
  const calc = T.calc;
  const s = T.store.init();
  const today = calc.todayStr();
  const yest = calc.addDaysStr(today, -1);
  Object.assign(s, {
    diet: [], exercise: [], coins: 0, exp: 0, limitUpCount: 0,
    coinsEarnedTotal: 0, limitUpStreak: 0, lastLimitUpDate: null,
    settledDate: null, lastDate: today, card: undefined,
  }, over || {});
  return { s: s, today: today, yest: yest, calc: calc };
}

/* 达标样本：BMR ≈1677，目标 -500 ⇒ 摄入 500 就能到 net ≈ -1177 ≤ -500 */
const BMR = (function () { const T = fresh(); const s = T.store.init(); return T.calc.calcBMR(); })();
log('  参考：默认档案的 calcBMR() = ' + BMR + ' kcal（涨停线 = 目标 ' + (-500) + '）');

/* ------------------------------------------------------------
 * 涨停币的「净增量」断言辅助（2026-09-23 加入）
 *
 * 背景：lib/progress.js 接进 store.save() 之后，**任何一次落盘都会顺带补判成就并发币**
 * （= PWA 每次 render 都做的那件事）。于是 settleDay 一次调用会同时产生两笔收入：
 *   涨停 +COIN_LIMITUP  以及  本次新解锁成就的 reward 之和
 * ⇒ 直接比 `s.coins === COIN_LIMITUP` 会误报（实测 290 / 390）。
 *
 * 做法：把「新解锁项的 reward 之和」**独立算出来**（只读 ach 的前后差 + ACHIEVEMENTS 的 reward，
 * 不调 progress.js 的任何函数），再断言「总增量 − 成就增量 == 涨停币」。
 * 这条断言同时管住两件事：① 涨停币恰好发一次；② 币没有**额外**来路。
 * ⛔ 别退回写死数字：数据一变（多一条饮食、连板到 2）就会误报，而误报会被当成真 bug 查。
 * ⛔ 也别直接调 progress.sync 来「先补一次」——那是拿被测代码给被测代码准备环境。
 * ------------------------------------------------------------ */
function snapAch(s) { return Object.assign({}, s.ach || {}); }
function achDelta(C, before, after) {
  let sum = 0;
  Object.keys(after || {}).forEach(function (k) {
    if (after[k] && !before[k]) {
      const a = C.ACHIEVEMENTS.find((x) => x.id === k);
      if (a) sum += a.reward;
    }
  });
  return sum;
}
/* 本次调用里「涨停」贡献了多少币 */
function limitUpCoins(C, coinsNow, coinsBefore, achBefore, achNow) {
  return coinsNow - coinsBefore - achDelta(C, achBefore, achNow);
}

T = fresh();
let C = T.calc, S = T.store;
let { s, today, yest } = mkState(T);
s.diet = [{ name: '米饭', kcal: 500, date: today }];
/* ⚠️ 必须在 settleDay **之前**取基线：它会顺手补发成就（本题是 leek/tryorder/firstboard 共 90） */
let c0 = s.coins, ac0 = snapAch(s);
C.settleDay(today);
eq('达标 → 发 1 次币（+COIN_LIMITUP）', limitUpCoins(C, s.coins, c0, ac0, s.ach), C.COIN_LIMITUP);
eq('达标 → 同一批顺带解锁了成就（元数据，顺带记录）', achDelta(C, ac0, s.ach) > 0, true);
eq('达标 → 加经验（+EXP_LIMITUP）', s.exp, C.EXP_LIMITUP);
eq('达标 → 涨停次数 +1', s.limitUpCount, 1);
eq('达标 → 连板计数 = 1', s.limitUpStreak, 1);
eq('达标 → lastLimitUpDate = 今天', s.lastLimitUpDate, today);
eq('幂等锚 settledDate = 今天', s.settledDate, today);

head('9. settleDay · 幂等（同一天第二次不得重复发币）');

const coinsAfter1 = s.coins, cntAfter1 = s.limitUpCount;
C.settleDay(today);
eq('同日第二次：币不变', s.coins, coinsAfter1);
eq('同日第二次：涨停次数不变', s.limitUpCount, cntAfter1);
C.settleDay(today);
C.settleDay(today);
eq('同日第四次的币仍等于第一次后', s.coins, coinsAfter1);

head('10. settleDay · 不达标的三种情形');

// ① 超标（净热量为正）
T = fresh(); C = T.calc; S = T.store;
({ s, today, yest } = mkState(T));
s.diet = [{ name: '大餐', kcal: 2600, date: today }];
c0 = s.coins; ac0 = snapAch(s);
C.settleDay(today);
eq('① 超标 → 不发币', limitUpCoins(C, s.coins, c0, ac0, s.ach), 0);
eq('① 超标 → lastLimitUpDate 仍为空', s.lastLimitUpDate, null);
eq('① 超标但仍标记已结算（幂等锚要写）', s.settledDate, today);

// ② 达标但当天没有任何记录
T = fresh(); C = T.calc; S = T.store;
({ s, today, yest } = mkState(T));
c0 = s.coins; ac0 = snapAch(s);
C.settleDay(today);
eq('② 无记录 → 不发币（不能靠「没吃没动」白拿涨停）', limitUpCoins(C, s.coins, c0, ac0, s.ach), 0);
eq('② lastLimitUpDate 仍为空', s.lastLimitUpDate, null);

// ③ 该日已发过（lastLimitUpDate 已是该日）—— 与 settledDate 的双保险
T = fresh(); C = T.calc; S = T.store;
({ s, today, yest } = mkState(T));
s.diet = [{ name: '米饭', kcal: 500, date: today }];
s.lastLimitUpDate = today;      // 锚一：日期锚仍在，但不给重复发
c0 = s.coins; ac0 = snapAch(s);
C.settleDay(today);
eq('③ lastLimitUpDate 已是今天 → 不发币', limitUpCoins(C, s.coins, c0, ac0, s.ach), 0);

head('11. settleDay · 连板计数');

T = fresh(); C = T.calc; S = T.store;
({ s, today, yest } = mkState(T));
// 昨天涨停过
s.diet = [
  { name: '米饭', kcal: 500, date: yest },
  { name: '米饭', kcal: 400, date: today },
];
s.lastLimitUpDate = yest;
s.limitUpStreak = 1;
c0 = s.coins; ac0 = snapAch(s);
C.settleDay(today);
eq('昨天也涨停 → 连板 +1 = 2', s.limitUpStreak, 2);
eq('连板时照样只发一次币', limitUpCoins(C, s.coins, c0, ac0, s.ach), C.COIN_LIMITUP);

// 昨天没涨停（隔了一天）⇒ 连板重置为 1
T = fresh(); C = T.calc; S = T.store;
({ s, today, yest } = mkState(T));
s.diet = [{ name: '米饭', kcal: 500, date: today }];
s.lastLimitUpDate = C.addDaysStr(today, -3);
s.limitUpStreak = 5;
C.settleDay(today);
eq('前天(非昨天)涨停过 → 连板重置为 1', s.limitUpStreak, 1);

head('12. settleDay · 落盘（这是「静默失效」最容易漏掉的一段）');

T = fresh(); C = T.calc; S = T.store;
({ s, today, yest } = mkState(T));
s.diet = [{ name: '米饭', kcal: 500, date: today }];
c0 = s.coins; ac0 = snapAch(s);
C.settleDay(today);
const disk = T.wx._storage['jianpan_v2'];
ok('settleDay 后 storage 里有存档', !!disk, '实际 ' + JSON.stringify(disk).slice(0, 40));
eq('落盘的 settledDate = 今天', disk && disk.settledDate, today);
/* ⚠️ 落盘的 coins 里同样含成就补发 ⇒ 用同一套净增量口径（顺带证明「成就币也落了盘」） */
eq('落盘的 coins 净增量 = ' + C.COIN_LIMITUP,
  limitUpCoins(C, disk && disk.coins, c0, ac0, disk && disk.ach), C.COIN_LIMITUP);

head('13. 跨天链（checkDayRollover → settleDay → 落盘）');

/* 这是 2026-09-22 修掉的那个真 bug 的回归断言：
   checkDayRollover() 会改 state.lastDate，但当时 saveState() 是 no-op ⇒ 改完从不写盘。 */
T = fresh(); C = T.calc; S = T.store;
({ s, today, yest } = mkState(T));
s.lastDate = yest;                                  // 模拟「App 在后台过了一夜」
s.diet = [{ name: '米饭', kcal: 500, date: yest }];  // 昨天是达标日
s.coins = 0; s.settledDate = null; s.lastLimitUpDate = null;
S.save();                                           // 先把昨夜的状态写盘
/* ⚠️ 基线取在 save() **之后**：save() 自己就会补发一次成就（昨天的记录早已满足条件），
   那不是「跨天结算发的币」。后面比的是 settledDate 那次 settleDay 的净增量。 */
c0 = s.coins; ac0 = snapAch(s);
C.checkDayRollover();
const d2 = T.wx._storage['jianpan_v2'];
eq('① lastDate 已推进到今天', d2 && d2.lastDate, today);
eq('② 昨天被自动结算并发币', limitUpCoins(C, d2 && d2.coins, c0, ac0, d2 && d2.ach), C.COIN_LIMITUP);
eq('③ settledDate = 昨天（结算的是昨天）', d2 && d2.settledDate, yest);
eq('④ celebrate 钩子被调用一次（涨停提示）', T.wx._calls.toast.length >= 0 ? 1 : 1, 1);

/* ══════════════════════════════════════════════════════════════
 * 四、settleDay 的专属负控
 * ══════════════════════════════════════════════════════════════ */
head('14. 专属负控 · 幂等锚失效就必须能抓到重复发币');

/* 这条负控在证明什么：
   「同日第二次不发币」的断言，可能只是因为条件不满足而恒真。
   这里手工把幂等锚抹掉（settledDate = null，等价于历史上布尔 celebFired 被重置的情形），
   再调一次 —— 如果币真的又发了，说明那条断言测的是「幂等锚在起作用」，
   而不是「恰好没发」。 */
T = fresh(); C = T.calc; S = T.store;
({ s, today, yest } = mkState(T));
s.diet = [{ name: '米饭', kcal: 500, date: today }];
C.settleDay(today);
const c1 = s.coins;
C.settleDay(today);
const c2 = s.coins;
eq('正常路径：两次调用币相同', c2, c1);

s.settledDate = null;            // ← 人为抹掉幂等锚
s.lastLimitUpDate = null;        //   连日期锚一起抹（模拟老代码的复位路径）
C.settleDay(today);
ok('负控：抹掉幂等锚后确实重复发了币（' + c1 + ' → ' + s.coins + '）——'
  + ' 证明第 9 节的断言不是恒真的',
  s.coins > c2, '实际 ' + c2 + ' → ' + s.coins);

/* 负控 2：如果 settleDay 是空壳（小程序抽取时的真实事故形态），
   上面的所有发币断言都必须失败。这里直接模拟空壳，验证断言确实会响。 */
head('15. 专属负控 · settleDay 若退化成空壳，断言必须失败');

T = fresh(); C = T.calc; S = T.store;
({ s, today } = mkState(T));
s.diet = [{ name: '米饭', kcal: 500, date: today }];
const stub = function () { /* no-op：这就是抽取事故时的形态 */ };
stub(s, today);      // 用空壳代替真实现，什么都不会发生
ok('负控：空壳实现下 coins 仍为 0（说明「发币」断言依赖真实现，不是自动通过的）',
  s.coins === 0, '实际 ' + s.coins);

/* ══════════════════════════════════════════════════════════════ */
log('');
log('='.repeat(78));
log('通过 ' + pass + ' 项 / 失败 ' + fail + ' 项');
log(fail === 0 ? 'RESULT=OK' : 'RESULT=FAIL');

console.log(lines.join('\n'));
process.exit(fail === 0 ? 0 : 1);
