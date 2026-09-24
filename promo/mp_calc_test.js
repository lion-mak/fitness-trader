/* ============================================================
 * mp_calc_test.js —— 小程序内核（calc.js）运行时验证
 *
 * 为什么要有这个测试：
 *   "把 PWA 算得准的东西搬到小程序" 不能靠肉眼 review 代码，
 *   必须证明「同一份 state，小程序内核算出来的数 == PWA 口径」。
 *   抽取脚本自动切片，任何一处漏抽都会让某个常量为 undefined，
 *   数字就会悄悄算错 —— 这类错误从界面上看不出来，只会显示错的数。
 *
 * 验证方式：交叉验算。测试里用「原始公式独立实现一遍」（Mifflin 公式、
 *   MET 公式、GAP 档位边界……），与 calc.js 的输出比对。这样两个实现
 *   互相独立，任一方写错都会暴露。
 *
 * 用法：node promo/mp_calc_test.js
 * 退出码：0 = 全部通过；1 = 有失败
 * ============================================================ */
'use strict';

const path = require('path');
const fs = require('fs');
const MINI = process.env.MINI_ROOT || 'E:\\WeChatProjects\\jianpan\\miniprogram';

/* 沙箱的 shell 重定向会写成 UTF-16，故自己落盘一份 UTF-8 报告 */
const OUT = path.join(__dirname, '_calc_test_out.txt');
const LOG = [];
const say = s => { console.log(s); LOG.push(s); };
function flush() { try { fs.writeFileSync(OUT, LOG.join('\n') + '\n', 'utf8'); } catch (e) {} }

/* 任何未捕获异常都要留下证据 —— 否则测试崩了却看不到崩在哪，只能看到"没输出" */
process.on('uncaughtException', e => {
  say('!!! 未捕获异常，测试中断');
  say('    ' + (e && e.stack));
  say('RESULT=FAIL');
  flush();
  process.exit(1);
});

let calc;
try {
  calc = require(path.join(MINI, 'lib', 'calc.js'));
} catch (e) {
  say('!!! 内核加载失败 —— 小程序工程里的 calc.js 无法 require');
  say('    路径：' + path.join(MINI, 'lib', 'calc.js'));
  say('    错误：' + (e && e.message));
  say('    栈：' + (e && e.stack));
  say('RESULT=FAIL');
  flush();
  process.exit(1);
}

let pass = 0, fail = 0;
const failures = [];

function ok(name, cond, detail) {
  if (cond) { pass++; }
  else { fail++; failures.push(name + (detail ? '  → ' + detail : '')); }
}
function eq(name, actual, expect) {
  ok(name, actual === expect, `实际 ${JSON.stringify(actual)} / 期望 ${JSON.stringify(expect)}`);
}
function near(name, actual, expect, tol) {
  const t = tol === undefined ? 1e-9 : tol;
  ok(name, Math.abs(actual - expect) <= t, `实际 ${actual} / 期望 ${expect} (±${t})`);
}

say('=== 小程序内核运行时验证 ===');
say('内核：' + path.join(MINI, 'lib', 'calc.js'));
say('');

/* ---------- 1. 加载与导出完整性 ---------- */
{
  const names = Object.keys(calc);
  ok('模块可 require', true);
  ok('导出规模合理（>150 项）', names.length > 150, `实际 ${names.length}`);

  // 关键常量：缺任一个都意味着抽取漏了，计算会静默出错
  const mustConst = ['FOOD_DB', 'EXERCISE_DB', 'GAP_TIERS', 'RANKS', 'CARDS', 'RARITY',
    'KCAL_PER_KG_FAT', 'KCAL_PER_JIN_FAT', 'COIN_PER_FOOD', 'COIN_PER_EX',
    'COIN_DAILY_CAP', 'COIN_LIMITUP', 'STAR_NEED', 'REFUND',
    'COLLECT_MILESTONES', 'ACHIEVEMENTS', 'ACH_TIERS', 'BODY_RANGES'];
  mustConst.forEach(n => ok('常量存在：' + n, calc[n] !== undefined));

  // 关键函数
  const mustFn = ['defaultState', 'loadState', 'calcBMR', 'calcTDEE', 'totals', 'gapTier',
    'fmtJin', 'fmtJin1', 'exerciseKcal', 'todayStr', 'addDaysStr', 'dayAgg',
    'trendBuckets', 'gapRankPct', 'paceWeeks', 'currentRank', 'rollRarity',
    'cardStar', 'totalStars', 'calcFoodKcal', 'getBodyType', 'usualItems',
    'reviewData', 'acctCost', 'currentTargetW', 'migratePayload'];
  mustFn.forEach(n => ok('函数存在：' + n, typeof calc[n] === 'function'));

  // 钩子空壳：内核调用渲染函数时不至于 ReferenceError
  ['render', 'saveState', 'toast', 'switchTab', 'settleDay'].forEach(n =>
    ok('钩子空壳存在：' + n, typeof calc[n] === 'function'));

  ok('内联精选食物库有料（>100 条）', calc.FOOD_DB.length > 100, `实际 ${calc.FOOD_DB.length}`);
  // 2052 条的大库在 data/foods.js（原 data/foods.json），单独加载校验
  try {
    const foods = require(path.join(MINI, 'data', 'foods.js'));
    const arr = Array.isArray(foods) ? foods : (foods.foods || []);
    ok('data/foods.js 大库（>2000 条）', arr.length > 2000, `实际 ${arr.length}`);
    const f0 = arr[0];
    ok('大库条目字段完整（name + kcal）', !!f0 && f0.name !== undefined && f0.kcal !== undefined,
      JSON.stringify(f0 && Object.keys(f0)));
    const bad = arr.filter(f => !f || f.name === undefined || f.kcal === undefined);
    eq('大库无残缺条目', bad.length, 0);

    // 字段白名单（2026-09-22 加）：mp_build.py 的 STRIP_FIELDS 必须真的生效，
    // 且搜索依赖的字段必须还在 —— 否则「裁字段省体积」会静默做成「裁功能」。
    const present = new Set();
    arr.forEach(f => Object.keys(f).forEach(k => present.add(k)));
    // ⛔ 这三项运行期一行都没读（实测 index.html 出现 0 次），裁掉省 246 KB
    ['recipe', 'yield_g', 'basis'].forEach(k =>
      ok('已裁掉运行期不读的字段：' + k, !present.has(k)));
    // ⚠️ 这些是搜索/排序/份量换算要用的（js/food-store.js 真读），缺一个功能就坏
    ['id', 'name', 'alias', 'cat', 'kcal', 'p', 'f', 'c', 'fb', 'alc',
      'unit', 'qty', 'gram', 'conv', 'src', 'est', 'kind', 'py', 'ini'].forEach(k =>
        ok('搜索必需字段保留：' + k, present.has(k)));
    const noPy = arr.filter(f => !f.py && !f.ini).length;
    ok('拼音字段覆盖率（缺 py 且缺 ini 的条数 = 0）', noPy === 0, `实际 ${noPy} 条缺失`);
    const noGram = arr.filter(f => typeof f.gram !== 'number' || f.gram <= 0).length;
    eq('份量 gram 全部有效', noGram, 0);
  } catch (e) {
    ok('data/foods.js 可 require', false, e.message);
  }
  eq('GAP 档位数', calc.GAP_TIERS.length, 7);
  eq('段位数', calc.RANKS.length, 11);
  eq('卡牌数', calc.CARDS.length, 15);
  eq('热量换算 7700', calc.KCAL_PER_KG_FAT, 7700);
  eq('1 斤折算 3850', calc.KCAL_PER_JIN_FAT, 3850);
}

/* ---------- 2. 注入 state 后跑业务 ---------- */
{
  const state = calc.defaultState();
  state.user = { gender: 'male', age: 30, height: 175, weight: 72.8, target: -500,
    startWeight: 75.5, targetWeight: null, avatar: null, userId: 'FT_8848',
    bodyFat: null, restingHr: null, activity: 'sedentary' };
  // 造 12 个历史交易日 + 今日两笔记录，让所有统计函数都有料
  state.diet = []; state.exercise = []; state.weightLog = [];
  for (let i = 12; i >= 1; i--) {
    const d = calc.addDaysStr(calc.todayStr(), -i);
    state.diet.push({ date: d, name: '米饭', kcal: 1800 + i * 20, p: 0, f: 0, c: 0 });
    state.exercise.push({ date: d, name: '跑步', kcal: 300 + i * 10 });
    state.weightLog.push({ date: d, weight: 75.5 - (12 - i) * 0.15 });
  }
  const today = calc.todayStr();
  state.diet.push({ date: today, name: '米饭', kcal: 1500 });
  state.exercise.push({ date: today, name: '跑步', kcal: 400 });
  state.weightLog.push({ date: today, weight: 73.2 });
  calc.bindState(state);

  /* --- 2.1 BMR：与独立实现的 Mifflin-St Jeor 交叉验算 --- */
  const p = state.user;
  const mifflin = Math.round(10 * p.weight + 6.25 * p.height - 5 * p.age + 5);
  eq('calcBMR（Mifflin，无体脂率）', calc.calcBMR(), mifflin);

  // 填了体脂率后应切到 Katch-McArdle：370 + 21.6 × 去脂体重
  state.user.bodyFat = 20;
  const lbm = p.weight * (1 - 20 / 100);
  eq('calcBMR（Katch-McArdle，有体脂率）', calc.calcBMR(), Math.round(370 + 21.6 * lbm));
  state.user.bodyFat = null;

  /* --- 2.2 TDEE = BMR × PAL(久坐 1.20) --- */
  eq('calcTDEE（久坐 PAL=1.20）', calc.calcTDEE(), Math.round(mifflin * 1.20));

  /* --- 2.3 totals：净热量 = 摄入 − 运动 − BMR --- */
  const t = calc.totals();
  eq('今日摄入', t.intake, 1500);
  eq('今日运动', t.burn, 400);
  eq('今日 BMR', t.bmr, mifflin);
  eq('净热量 net', t.net, 1500 - 400 - mifflin);
  eq('预算线 budget = 运动 + BMR', t.budget, 400 + mifflin);

  /* --- 2.4 缺口档位：逐条验边界（含 ±1 的临界） --- */
  const cases = [
    [1000, '跌停'], [999, '大阴线'], [700, '大阴线'], [699, '中阴线'],
    [400, '中阴线'], [399, '小阴线'], [150, '小阴线'], [149, '十字星'],
    [-150, '十字星'], [-151, '小阳线'], [-500, '小阳线'], [-501, '涨停'],
  ];
  cases.forEach(([d, short]) =>
    eq(`缺口 ${d} kcal → ${short}`, calc.gapTier(d).short, short));

  /* --- 2.5 斤数换算：1 斤 = 3850 kcal --- */
  eq('fmtJin(3850) 应为 1.00', calc.fmtJin(3850), '1.00');
  eq('fmtJin(1925) 应为 0.50', calc.fmtJin(1925), '0.50');
  eq('fmtJin(-3850) 盈余带 + 号', calc.fmtJin(-3850), '+1.00');
  eq('fmtJin1(3850) 一位小数', calc.fmtJin1(3850), '1.0');

  /* --- 2.6 运动消耗：独立实现 MET 公式 --- */
  near('exerciseKcal(8 MET, 30min, 中)', calc.exerciseKcal(8, 30, '中'),
    Math.round(8 * 3.5 * p.weight / 200 * 30 * 1.0));
  near('exerciseKcal 低强度系数 0.8', calc.exerciseKcal(8, 30, '低'),
    Math.round(8 * 3.5 * p.weight / 200 * 30 * 0.8));
  near('exerciseKcal 高强度系数 1.25', calc.exerciseKcal(8, 30, '高'),
    Math.round(8 * 3.5 * p.weight / 200 * 30 * 1.25));

  /* --- 2.7 日期工具 --- */
  eq('todayStr 格式 YYYY-MM-DD', /^\d{4}-\d{2}-\d{2}$/.test(calc.todayStr()), true);
  eq('addDaysStr 往回 1 天', calc.addDaysStr('2026-03-01', -1), '2026-02-28');
  eq('addDaysStr 跨年', calc.addDaysStr('2026-12-31', 1), '2027-01-01');
  eq('dayOffset(-1) = 昨天', calc.dayOffset(-1), calc.addDaysStr(calc.todayStr(), -1));
  eq('dayOffset(1) = 明天', calc.dayOffset(1), calc.addDaysStr(calc.todayStr(), 1));

  /* --- 2.8 聚合与趋势 --- */
  const agg = calc.dayAgg();
  ok('dayAgg 覆盖 13 个交易日', agg.length >= 13, `实际 ${agg.length}`);
  const buckets = calc.trendBuckets('all');
  ok('trendBuckets("all") 有数据', Array.isArray(buckets) && buckets.length > 0);

  /* --- 2.9 两个"能算就算、算不了就删"的口径：样本不足必须返回 null --- */
  const rank = calc.gapRankPct(500);
  ok('gapRankPct 样本 12 天 → 有值', rank !== null && typeof rank.pct === 'number');
  const state2 = calc.defaultState();
  calc.bindState(state2);
  eq('gapRankPct 样本 < 7 天 → null（不许编）', calc.gapRankPct(500), null);
  eq('paceWeeks 无数据 → null（不许编）', calc.paceWeeks(5), null);
  calc.bindState(state);

  /* --- 2.10 账户口径：主数字是"止盈进度"，不是收益率 --- */
  const cost = calc.acctCost();
  eq('持仓成本 = 最早一条体重日志', cost, 75.5);
  const tw = calc.currentTargetW();
  ok('止盈目标有值', typeof tw === 'number' && tw > 0 && tw < 75.5, `实际 ${tw}`);

  /* --- 2.11 等级：经验 → 段位（100 经验一档，11 段位）--- */
  const r0 = calc.currentRank();
  ok('currentRank 结构 {lv, rank}', !!r0 && typeof r0.lv === 'number' && !!r0.rank && !!r0.rank.name,
    JSON.stringify(r0));
  eq('exp=0 → lv1 → 韭菜', r0.rank.name, '韭菜');
  const expBak = state.exp;
  state.exp = 100; eq('exp=100 → lv2', calc.currentRank().lv, 2);
  /* 早期节奏：100 经验（≈首日「3 餐 + 1 次运动 + 一次涨停」）就脱离韭菜 ⇒ 新用户的正反馈 */
  state.exp = 100; eq('exp=100 → lv2 → 散户', calc.currentRank().rank.name, '散户');
  state.exp = 2900; eq('exp=2900 → lv30 → 股神（封顶）', calc.currentRank().rank.name, '股神');
  state.exp = expBak;

  /* --- 2.12 抽卡概率：跑 40000 次统计分布，验证 70/25/5 --- */
  const cnt = { N: 0, R: 0, SR: 0 };
  const N = 40000;
  for (let i = 0; i < N; i++) cnt[calc.rollRarity()]++;
  const pN = cnt.N / N * 100, pR = cnt.R / N * 100, pSR = cnt.SR / N * 100;
  ok('普通卡概率 ≈70%', Math.abs(pN - 70) < 1.5, `实际 ${pN.toFixed(2)}%`);
  ok('稀有卡概率 ≈25%', Math.abs(pR - 25) < 1.5, `实际 ${pR.toFixed(2)}%`);
  ok('传说卡概率 ≈5%', Math.abs(pSR - 5) < 1.0, `实际 ${pSR.toFixed(2)}%`);

  /* --- 2.13 升星：1/3/9 张 → 1/2/3 星 --- */
  eq('1 张 = 1 星', calc.cardStar(1), 1);
  eq('3 张 = 2 星', calc.cardStar(3), 2);
  eq('9 张 = 3 星', calc.cardStar(9), 3);
  eq('0 张 = 0 星', calc.cardStar(0), 0);
  eq('空图鉴 = 0 星', calc.totalStars(), 0);
  {   // 全图鉴满星：15 张 × 3 星 = 45
    const bak = state.cards;
    state.cards = {};
    calc.CARDS.forEach(c => { state.cards[c.id] = 9; });
    eq('全图鉴满星 = 45 星', calc.totalStars(), 45);
    state.cards = bak || {};
  }

  /* --- 2.14 食物热量换算：每 100g 口径 → 实际克重 ---
     ⚠️ calcFoodKcal() 是「读全局 curFood 的 UI 辅助」，不是纯函数，测试直接验引擎。
     同时这条断言也是 NutritionEngine 挂载的哨兵：没挂上时 calcBMR 会静默返回 1500。 */
  const NE = calc.NutritionEngine;
  ok('NutritionEngine 已挂载', !!NE && typeof NE.bmr === 'function');
  const rice = { name: '米饭', kcal: 116, p: 2.6, f: 0.3, c: 25.9, fb: 0.3 };
  eq('米饭 150g', NE.food(rice, 150).kcal, 174);
  eq('米饭 100g', NE.food(rice, 100).kcal, 116);
  eq('米饭 333g 取整', NE.food(rice, 333).kcal, Math.round(116 * 3.33));

  /* --- 2.15 身体类型九宫格 --- */
  ok('getBodyType 返回体脂/BMI 双轴', (() => {
    const bt = calc.getBodyType(22.4, 18.2);
    return bt && typeof bt === 'object';
  })());

  /* --- 2.16 复盘口径：必须与「每日缺口评级」同口径（无参数，读全局 period） --- */
  const rv = calc.reviewData();
  ok('reviewData() 有产出', rv && typeof rv === 'object',
    JSON.stringify(rv && Object.keys(rv)));

  /* --- 2.17 数据迁移链（为小程序预留的那套） --- */
  const payload = calc.buildExportPayload();
  eq('导出载荷带 __schema', payload.__schema, 1);
  eq('导出载荷带 __app', payload.__app, 'fitness-trader');
  const bare = calc.migratePayload({ user: {}, diet: [] });
  ok('裸 state（__schema=0）可迁移', bare && typeof bare === 'object' && bare.user);
  ok('带 tag 的载荷可迁移',
    !!calc.migratePayload({ __app: 'fitness-trader', __schema: 1, state: { user: {} } }));
  // 更高版本必须拒绝（实现是抛错，不是返回 null）—— 静默按旧结构读进来会丢字段
  let rejected = false;
  try { calc.migratePayload({ __app: 'fitness-trader', __schema: 99, state: {} }); }
  catch (e) { rejected = true; }
  ok('更高版本存档被拒绝', rejected);
  let threw = false;
  try { calc.migratePayload('not-an-object'); } catch (e) { threw = true; }
  ok('非法输入抛错', threw);
}

/* ---------- 3. 钩子调用不抛错（内核调渲染函数时的安全网） ---------- */
{
  let called = [];
  calc.bindHooks({ render: () => called.push('render'), toast: m => called.push('toast:' + m) });
  calc.render();
  calc.toast('测试');
  eq('钩子被正确调用', called.join(','), 'render,toast:测试');
  calc.bindHooks({});
}

/* ---------- 汇总 ---------- */
say(`结果：通过 ${pass} 项，失败 ${fail} 项`);
if (fail) {
  say('');
  say('失败明细：');
  failures.forEach(f => say('  ✗ ' + f));
  say('');
  say('RESULT=FAIL');
} else {
  say('');
  say('RESULT=OK');
}
fs.writeFileSync(OUT, LOG.join('\n') + '\n', 'utf8');
process.exit(fail ? 1 : 0);