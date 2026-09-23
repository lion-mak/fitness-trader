/* mp_smoke.js —— 小程序「启动链路 + 首屏绘制」冒烟测试
 *
 * 为什么需要：
 *   WXSS 编译错误会造成白屏（2026-09-22 已修）；但**编译通过 ≠ 不白屏** ——
 *   onLaunch/onLoad/首次绘制里任何一句抛错，页面同样是空的，而且开发者工具只给一行红字。
 *   这个脚本用 mock 的 wx / App / Page / canvas 2d 把「启动 → 各页 onLoad → 首屏绘制」
 *   整条链真跑一遍，抛错在这里带堆栈冒出来，不用等真机。
 *
 * 跑两遍（PWA 侧的真实存档在 promo/mock.json 里）：
 *   ① 空存档  —— 全新用户第一次打开（defaultState 分支）
 *   ② 真实存档 —— 96 天 / 48 条体重 / 388 条饮食 / 88 条运动（有数据分支）
 *   两遍都要过，因为「空态能跑」不代表「有数据能跑」。
 *
 * ⚠️ 写 mock 的注意事项（踩过的坑）：
 *   1. **Page 实例必须带 setData** —— 直接 `opt.onLoad.call(opt)` 会报
 *      `this.setData is not a function`，那是 mock 缺功能，**不是产品 bug**，别去"修"页面。
 *   2. canvas node 要给 `getContext('2d')` 返回方法齐全的假 context，否则绘制路径跑不到。
 *   3. **假 ctx 要记账**（ctxStats）—— 全是 no-op 时「一行没画」也会显示通过。
 *   4. 异步回调里的抛错要用 uncaughtException 抓，并**延迟**输出报告，
 *      否则 SelectorQuery 回调里的错会漏掉。
 *
 * 用法：node promo/mp_smoke.js    退出码 0=全过，非 0=有抛错
 * 报告落盘：promo/_smoke_out.txt
 */
'use strict';
const path = require('path');
const fs = require('fs');

const MINI = 'E:\\WeChatProjects\\jianpan\\miniprogram';
const OUT = path.join(__dirname, '_smoke_out.txt');
const LAST_LABEL = { v: '' };

/* 第 2 遍要逐个跑生命周期的页面。子页也放进来：「新页面上线即白屏」这类事故
   只有这一遍能挡住（漏写 class="page active" / require 路径错 / onLoad 读空对象…）。
   2026-09-23 补上一直缺席的 coins/level，并加上新复刻的 achievements/gacha。 */
const PAGE_LIST = ['market', 'holdings', 'trade', 'board', 'me',
                   'coins', 'level', 'achievements', 'gacha'];

const lines = [];
const errors = [];
const calls = [];
const log = (s) => lines.push(s === undefined ? '' : s);

process.on('uncaughtException', (e) => {
  errors.push({ name: LAST_LABEL.v + ' 异步抛错', err: e });
  log('[FAIL] 异步抛错：' + (e && e.message));
  String((e && e.stack) || '').split('\n').slice(1, 4).forEach((l) => log('        ' + l.trim()));
});

// ---------------- mock ----------------
const storage = {};          // 存档容器（两遍之间会重置）

const noop = () => {};
/** canvas 2d context 的调用统计 —— 用来证明「绘制真的发生了」。
 *  全是 no-op 的假 ctx 会让「一行都没画」也显示通过，所以必须记账。 */
const ctxStats = { total: 0, fillText: 0, fillRect: 0, measureText: 0, stroke: 0, arc: 0 };
function bump(name) {
  ctxStats.total++;
  if (name in ctxStats) ctxStats[name]++;
}
function ctx2d() {
  const wrap = (name) => (...a) => { bump(name); return undefined; };
  return {
    save: wrap('save'), restore: wrap('restore'), beginPath: wrap('beginPath'),
    closePath: wrap('closePath'), moveTo: wrap('moveTo'), lineTo: wrap('lineTo'),
    arc: wrap('arc'), arcTo: wrap('arcTo'), rect: wrap('rect'),
    fill: wrap('fill'), stroke: wrap('stroke'), clip: wrap('clip'),
    fillRect: wrap('fillRect'), strokeRect: wrap('strokeRect'), clearRect: wrap('clearRect'),
    fillText: wrap('fillText'), strokeText: wrap('strokeText'),
    translate: wrap('translate'), rotate: wrap('rotate'), scale: wrap('scale'),
    setTransform: wrap('setTransform'), transform: wrap('transform'),
    drawImage: wrap('drawImage'), setLineDash: wrap('setLineDash'),
    quadraticCurveTo: wrap('quadraticCurveTo'), bezierCurveTo: wrap('bezierCurveTo'),
    createLinearGradient: () => ({ addColorStop: noop }),
    createRadialGradient: () => ({ addColorStop: noop }),
    createPattern: () => ({}),
    measureText: (t) => { bump('measureText'); return { width: String(t).length * 6 }; },
    getImageData: () => ({ data: [] }),
    putImageData: noop,
  };
}
function canvasNode() {
  return {
    width: 1053, height: 450,
    getContext: () => ctx2d(),
    createImage: () => ({ onload: null, onerror: null, src: '', width: 0, height: 0 }),
    requestAnimationFrame: (f) => setTimeout(f, 0),
  };
}
function rectQuery() {
  const box = { width: 351, height: 150, left: 0, top: 0, right: 351, bottom: 150 };
  // ⚠️ exec 的回调必须带 node —— canvas.js 用的是
  //    `.fields({node:true,size:true}).exec(res => res[0].node)`
  //    （真机标准用法）。少了 node 会误报「未找到节点或节点未就绪」，
  //    那是 mock 缺陷冒充产品缺陷，2026-09-22 踩过一次。
  const payload = () => Object.assign({}, box, { node: canvasNode() });
  const q = {
    select: () => q,
    selectAll: () => q,
    in: () => q,
    fields: (opt, cb) => { if (typeof cb === 'function') cb(payload()); return q; },
    boundingClientRect: (cb) => { if (typeof cb === 'function') cb(box); return q; },
    exec: (cb) => { if (typeof cb === 'function') cb([payload()]); return q; },
  };
  return q;
}

global.wx = {
  getStorageSync: (k) => (k in storage ? storage[k] : ''),
  setStorageSync: (k, v) => { storage[k] = v; },
  removeStorageSync: (k) => { delete storage[k]; },
  getStorageInfoSync: () => ({ keys: Object.keys(storage), currentSize: 0, limitSize: 10240 }),
  getWindowInfo: () => ({ statusBarHeight: 44, windowWidth: 375, windowHeight: 724, screenWidth: 375, screenHeight: 812, pixelRatio: 3, safeArea: { top: 44, bottom: 778, left: 0, right: 375 } }),
  getDeviceInfo: () => ({ platform: 'devtools', system: 'iOS 17.0', brand: 'devtools', model: 'iPhone' }),
  getSystemInfoSync: () => global.wx.getWindowInfo(),
  getMenuButtonBoundingClientRect: () => ({ top: 48, bottom: 80, left: 278, right: 365, width: 87, height: 32 }),
  createSelectorQuery: () => rectQuery(),
  nextTick: (fn) => setTimeout(fn, 0),
  showToast: (o) => calls.push(['showToast', o && o.title]),
  showModal: (o) => { calls.push(['showModal', o && o.title]); o && o.success && o.success({ confirm: true }); },
  showActionSheet: (o) => { calls.push(['showActionSheet']); o && o.success && o.success({ tapIndex: 0 }); },
  setClipboardData: (o) => { calls.push(['setClipboardData']); o && o.success && o.success({}); },
  getClipboardData: (o) => { o && o.success && o.success({ data: '' }); },
  setNavigationBarTitle: noop,
  stopPullDownRefresh: noop,
  createCanvasContext: () => ({}),
  // ⚠️ 故意不提供 wx.cloud —— 模拟云环境未开通
};

const captured = { app: null, pages: [] };
global.App = (o) => { captured.app = o; };
global.Page = (o) => { captured.pages.push(o); };
global.Component = (o) => { captured.pages.push(o); };
global.Behavior = (o) => o;
global.getApp = () => captured.app;
global.getCurrentPages = () => [];

/** Page 实例：必须有 setData（真机由框架注入），否则 onLoad 一调就假报错 */
function makeInstance(opt) {
  const inst = Object.create(opt);
  inst.data = Object.assign({}, opt.data || {});
  inst.setData = function (o, cb) {
    Object.assign(inst.data, o || {});
    if (typeof cb === 'function') cb();
  };
  inst.selectComponent = () => null;
  inst.triggerEvent = noop;
  return inst;
}

// ---------------- 跑 ----------------
function step(name, fn) {
  try {
    fn();
    log('[ OK ] ' + name);
    return true;
  } catch (e) {
    errors.push({ name: LAST_LABEL.v + ' ' + name, err: e });
    log('[FAIL] ' + name);
    log('        ' + (e && e.message));
    String((e && e.stack) || '').split('\n').slice(1, 5).forEach((l) => log('        ' + l.trim()));
    return false;
  }
}

function freshRequire() {
  Object.keys(require.cache).forEach((k) => { if (k.indexOf(MINI) === 0) delete require.cache[k]; });
}

function runPass(idx, label, seed) {
  LAST_LABEL.v = '第' + idx + '遍';
  ctxStats.total = 0; ctxStats.fillText = 0; ctxStats.fillRect = 0;
  ctxStats.measureText = 0; ctxStats.stroke = 0; ctxStats.arc = 0;
  Object.keys(storage).forEach((k) => { delete storage[k]; });
  if (seed) storage['jianpan_v2'] = JSON.parse(JSON.stringify(seed));
  captured.app = null; captured.pages.length = 0; calls.length = 0;
  freshRequire();

  log('════════ 第 ' + idx + ' 遍：' + label + ' ════════');
  log();

  step('require app.js', () => {
    require(path.join(MINI, 'app.js'));
    if (!captured.app) throw new Error('app.js 没有调用 App()');
  });
  step('app.onLaunch()（系统信息 + 加载存档 + 初始化云 + 跨天检查）', () => {
    captured.app.onLaunch.call(captured.app);
  });
  step('app.onShow()', () => { captured.app.onShow.call(captured.app); });

  const st = captured.app.globalData.state;
  log();
  log('存档：' + (st ? Object.keys(st).length + ' 个字段' : '❌ 空'));
  if (st) {
    log('  weightLog ' + ((st.weightLog && st.weightLog.length) || 0) + ' 条 / ' +
        'foodLog ' + ((st.foodLog && st.foodLog.length) || 0) + ' 条 / ' +
        'exLog ' + ((st.exLog && st.exLog.length) || 0) + ' 条 / coins ' + st.coins);
  }
  log('云：' + (captured.app.globalData.cloudReady ? '已初始化' : '未初始化（预期：mock 无 wx.cloud）'));
  log();

  /* ⚠️ 子页也要进来：「新页面上线即白屏」这类事故只有这一遍能挡住
     （漏写 class="page active" / require 路径错 / onLoad 里读空对象...）。 */
  const PAGES = PAGE_LIST;
  for (const name of PAGES) {
    captured.pages.length = 0;
    const p = path.join(MINI, 'pages', name, name + '.js');
    const ok = step('require pages/' + name + '.js', () => {
      require(p);
      if (!captured.pages.length) throw new Error('页面 js 没有调用 Page()');
    });
    if (!ok) continue;
    const inst = makeInstance(captured.pages[0]);
    if (typeof inst.onLoad === 'function') step('  ' + name + '.onLoad()', () => { inst.onLoad.call(inst, {}); });
    if (typeof inst.onShow === 'function') step('  ' + name + '.onShow()', () => { inst.onShow.call(inst); });
    if (typeof inst.onReady === 'function') step('  ' + name + '.onReady()', () => { inst.onReady.call(inst); });
  }

  log();
  log('canvas 调用记账：共 ' + ctxStats.total + ' 次' +
      '（fillText ' + ctxStats.fillText + ' / measureText ' + ctxStats.measureText +
      ' / fillRect ' + ctxStats.fillRect + ' / stroke ' + ctxStats.stroke + ' / arc ' + ctxStats.arc + '）');
  if (ctxStats.total === 0) {
    log('  ⚠️ 一次都没画 —— 要么该页还没有图表（骨架页正常），要么绘制路径没被触发（**要查**）');
  }
  log();
}

/* ============================================================
 * 第 3 遍：导入验收 —— 检验「先把数据导进来」这个决定到底成不成立
 *
 * 前两遍只证明「不抛错」。这一遍证明**导入的数据真的被页面用上了**：
 * 走真实的 lib/migrate.js 导入链路，然后重跑页面，断言页面 data 里的
 * 是真实数字（用户第 1 眼看到的那个），而不是内部变量。
 * 少了这一遍，「先把数据导进来，后面迁移就有数据可用」只是口头承诺。
 * ============================================================ */
function runImportPass() {
  LAST_LABEL.v = '第3遍';
  ctxStats.total = 0; ctxStats.fillText = 0; ctxStats.fillRect = 0;
  ctxStats.measureText = 0; ctxStats.stroke = 0; ctxStats.arc = 0;
  Object.keys(storage).forEach((k) => { delete storage[k]; });
  captured.app = null; captured.pages.length = 0; calls.length = 0;
  freshRequire();

  log('════════ 第 3 遍：导入验收（走真实导入链路，再看页面是否用上）════════');
  log();

  step('require app.js（空机启动，模拟全新安装）', () => {
    require(path.join(MINI, 'app.js'));
    if (!captured.app) throw new Error('app.js 没有调用 App()');
  });
  step('app.onLaunch()', () => { captured.app.onLaunch.call(captured.app); });

  const migrate = require(path.join(MINI, 'lib/migrate.js'));
  const TEXT = JSON.stringify({ __app: 'fitness-trader', __schema: 1, state: realState });

  let got = null;
  step('用户点「从剪贴板导入」→ migrate.parse + applyImport（真实存档）', () => {
    got = migrate.applyImport(migrate.parse(TEXT));
  });
  log('        导入结果：' + migrate.summary(got));
  log('        体积 ' + got.kb + ' KB / 健康币 ' + got.coins + ' / ' + got.rank + ' Lv' + got.level);
  log();

  step('断言 · 导入条数与存档源一致（饮食/运动/体重）', () => {
    if (got.diet !== realState.diet.length) throw new Error('饮食 ' + got.diet + ' ≠ ' + realState.diet.length);
    if (got.exercise !== realState.exercise.length) throw new Error('运动 ' + got.exercise + ' ≠ ' + realState.exercise.length);
    if (got.weight !== realState.weightLog.length) throw new Error('体重 ' + got.weight + ' ≠ ' + realState.weightLog.length);
  });

  // 行情页：首屏该显示真实体重，且 K 线不能是空态
  captured.pages.length = 0;
  require(path.join(MINI, 'pages/market/market.js'));
  const mk = makeInstance(captured.pages[0]);
  step('market.onLoad() + onReady()', () => {
    if (typeof mk.onLoad === 'function') mk.onLoad.call(mk, {});
    if (typeof mk.onReady === 'function') mk.onReady.call(mk);
  });
  const wantWeight = (realState.user && realState.user.weight) + ' kg';
  step('断言 · 行情页顶部显示真实体重（' + wantWeight + '）', () => {
    if (mk.data.weightText !== wantWeight) {
      throw new Error('weightText = ' + JSON.stringify(mk.data.weightText) + '，期望 ' + JSON.stringify(wantWeight));
    }
  });
  step('断言 · 行情页 K 线不是空态（48 条体重已进来）', () => {
    if (mk.data.empty) throw new Error('走了空态：' + mk.data.emptyMsg);
  });
  log('        ' + String(mk.data.period).toUpperCase() + 'K · ' + mk.data.ma7Lab + ' / ' + mk.data.ma30Lab);
  log('        canvas 调用记账：共 ' + ctxStats.total + ' 次（用导入的数据重画）');
  if (ctxStats.total === 0) log('  ⚠️ 导入数据后 K 线一次都没画 —— 数据没走到绘制路径，要查');
  log();

  // 我的页：体检卡必须显示导入进来的数字（这是用户确认「导入成功」的依据）
  captured.pages.length = 0;
  require(path.join(MINI, 'pages/me/me.js'));
  const me = makeInstance(captured.pages[0]);
  /* ⚠️ onShow 不能省：本项目约定「onLoad 只设状态栏留白，refresh() 挂 onShow」
     （board / coins / level / me 一致），只调 onLoad 会读到一个还没渲染的空 data ——
     那是真机不可达的状态，断在这种地方是测试写漏了一步，不是页面缺陷。
     （2026-09-23：「饮食格 = undefined」就是这么来的） */
  step('me.onLoad() + onShow()', () => {
    if (typeof me.onLoad === 'function') me.onLoad.call(me, {});
    if (typeof me.onShow === 'function') me.onShow.call(me);
    if (typeof me.onReady === 'function') me.onReady.call(me);
  });
  step('断言 · 我的页体检卡显示真实数字（饮食/运动/体重/健康币）', () => {
    const m = {};
    (me.data.cells || []).forEach((c) => { m[c.lab] = c.v; });
    if (m['饮食'] !== realState.diet.length) throw new Error('饮食格 = ' + m['饮食'] + '，期望 ' + realState.diet.length);
    if (m['运动'] !== realState.exercise.length) throw new Error('运动格 = ' + m['运动'] + '，期望 ' + realState.exercise.length);
    if (m['体重'] !== realState.weightLog.length) throw new Error('体重格 = ' + m['体重'] + '，期望 ' + realState.weightLog.length);
    /* ⚠️ 健康币**不等于**存档里的 8640：导入会补判成就 + 发奖
       （导入的是别处的历史，本机从没为它判过）⇒ 18 项 × 合计 2210 币 ⇒ 10850。
       这个数不是拍出来的，是把**同一份 mock.json 灌进 PWA** 实测得到的：
         promo/_probe_pwa_state.py：写入 8640 → reload 后 localStorage = 10850、ach 真值 26
       复刻移植里 PWA 就是参考实现 ⇒ 两端同值才算复刻成功（此前这里恒为 8640，
       差的正是那 2210 币 —— 2026-09-23 补上 lib/progress.js 才对齐）。
       断三层防呆：与导入链路自报的 got.coins 一致、与字面 10850 一致、与落盘原值一致。 */
    if (m['健康币'] !== got.coins) throw new Error('健康币格 = ' + m['健康币'] + '，与导入链路自报的 ' + got.coins + ' 不一致');
    if (m['健康币'] !== 10850) throw new Error('健康币格 = ' + m['健康币'] + '，期望 10850（= 8640 + 18 项成就补发 2210，PWA 同值）');
    if (storage['jianpan_v2'].coins !== 10850) throw new Error('落盘健康币 = ' + storage['jianpan_v2'].coins + '，期望 10850');
    if (storage['jianpan_v2'].ach.untie !== true) throw new Error('落盘 ach 里没有补发出来的 untie');
  });
  log('        体检卡：' + (me.data.cells || []).map((c) => c.lab + ' ' + c.v).join(' · '));
  log('        跨度：' + me.data.spanText);
  log();

  /* ------------------------------------------------------------
   * 持仓页：账户总览 / 净热量趋势 / 缺口评级 / 套牢 / 持仓评级
   *
   * 这里的期望值**全部用独立实现现算**（不复用 calc），否则就变成
   * 「拿被测代码证明被测代码」—— 那种断言永远为真，等于没测。
   * 站位：账户总览那一行数字是用户判断「我到底在赢还是输」的唯一依据，
   * 口径错一位小数都会被当成账算错了。
   * ------------------------------------------------------------ */
  captured.pages.length = 0;
  require(path.join(MINI, 'pages/holdings/holdings.js'));
  const hold = makeInstance(captured.pages[0]);
  const calc = require(path.join(MINI, 'lib/calc.js'));

  ctxStats.total = 0;   // 单独记账：这一段的绘制必须来自持仓页
  step('holdings.onLoad() + onShow() + onReady()', () => {
    if (typeof hold.onLoad === 'function') hold.onLoad.call(hold, {});
    if (typeof hold.onShow === 'function') hold.onShow.call(hold);
    if (typeof hold.onReady === 'function') hold.onReady.call(hold);
  });

  /* —— 独立实现：建仓价 / 止盈价 / 止盈进度 ——
     与 PWA 同口径但另写一遍：
       持仓成本 = 最早一条真实体重日志（无则退回 startWeight）
       止盈目标 = user.targetWeight（40~300 内）否则 startWeight − 7.5
       止盈进度 = (成本 − 现价) ÷ (成本 − 止盈目标) × 100，clamp 0~100 */
  const wl = (realState.weightLog || []).filter((x) => x && x.weight > 0)
    .slice().sort((a, b) => ((a.date || '') < (b.date || '') ? -1 : 1));
  const costW = wl.length ? +wl[0].weight
    : +(realState.user.startWeight || realState.user.weight || 0);
  const nowW = +realState.user.weight;
  const u = realState.user;
  const targetW = (u.targetWeight != null && u.targetWeight >= 40 && u.targetWeight <= 300)
    ? u.targetWeight
    : Math.max(40, Math.round((u.startWeight - 7.5) * 10) / 10);
  const profitW = +(costW - nowW).toFixed(1);
  const spaceW = +(costW - targetW).toFixed(1);
  const wantProg = spaceW > 0.05
    ? Math.max(0, Math.min(100, profitW / spaceW * 100)).toFixed(1) : null;

  step('断言 · 账户总览账本三行 = 独立算出的成本/市值/止盈价', () => {
    if (hold.data.cost !== costW.toFixed(1) + ' kg') {
      throw new Error('持仓成本 = ' + hold.data.cost + '，独立算 = ' + costW.toFixed(1) + ' kg');
    }
    if (hold.data.now !== nowW.toFixed(1) + ' kg') {
      throw new Error('当前市值 = ' + hold.data.now + '，独立算 = ' + nowW.toFixed(1) + ' kg');
    }
    if (hold.data.target !== targetW.toFixed(1) + ' kg') {
      throw new Error('止盈目标 = ' + hold.data.target + '，独立算 = ' + targetW.toFixed(1) + ' kg');
    }
  });

  step('断言 · 主数字（止盈进度）与独立算出的百分比逐位相同', () => {
    if (wantProg === null) {
      // 没有减重空间 → 退回累计浮盈千克（PWA 的另一条分支），此时不该带 %
      if (hold.data.acctPc !== ' kg') {
        throw new Error('无减重空间时应显示浮盈 kg，实测单位 = ' + JSON.stringify(hold.data.acctPc));
      }
      if ((hold.data.acctIv + hold.data.acctDec) !== ((profitW >= 0 ? '+' : '') + profitW.toFixed(1))) {
        throw new Error('浮盈数字 = ' + hold.data.acctIv + hold.data.acctDec
          + '，独立算 = ' + profitW.toFixed(1));
      }
      return;
    }
    if (hold.data.acctPc !== '%') throw new Error('有减重空间时单位应为 %，实测 ' + hold.data.acctPc);
    const shown = hold.data.acctIv + hold.data.acctDec;
    if (shown !== wantProg) throw new Error('止盈进度 = ' + shown + '%，独立算 = ' + wantProg + '%');
    if (!(Number(wantProg) >= 0 && Number(wantProg) <= 100)) {
      throw new Error('止盈进度必须被 clamp 在 0~100：' + wantProg);
    }
    // 上限是内部量，⛔ 绝不允许上屏（PWA v2.7.50 专门删掉过）
    if (String(showAll(hold.data)).indexOf('上限') >= 0) {
      throw new Error('页面上出现了「上限」字样 —— 止盈空间是内部计算量，不该上屏');
    }
  });

  step('断言 · 账户状态是「浮盈中/浮亏中/持仓中/已止盈」四者之一（不是占位 --）', () => {
    const s = String(hold.data.acctState || '');
    const legal = s.indexOf('已止盈') === 0 || ['浮盈中', '浮亏中', '持仓中'].indexOf(s) >= 0;
    if (!legal) throw new Error('acctState = ' + JSON.stringify(s) + '，看起来还没渲染');
  });

  /* —— 独立实现：九宫格分型（照 BODY_TYPES 的区间规则另写一遍）—— */
  function wantType(bmi, fat) {
    const f = Math.max(0, Math.min(40, +fat || 0));
    const b = +bmi || 0;
    if (b < 18.5) return f < 10 ? '消瘦型' : f < 21 ? '偏瘦型' : '隐性肥胖型';
    if (b < 21) return f < 15 ? '苗条型' : f < 21 ? '健康型' : '隐性肥胖型';
    if (b < 24) return f < 15 ? '模特型' : f < 21 ? '健康型' : f < 26 ? '偏胖型' : '肥胖型';
    if (b < 28) return f < 15 ? '运动型' : f < 26 ? '偏胖型' : '肥胖型';
    return f < 15 ? '运动型' : '肥胖型';
  }

  const fatRaw = +(realState.body && realState.body.bodyFat) || 0;
  const bmiRaw = +(realState.body && realState.body.bmi) || 0;
  step('断言 · 持仓评级大字 = 独立按 BMI/体脂区间推出的分型名', () => {
    const want = wantType(bmiRaw, fatRaw);
    if (hold.data.grade !== want) {
      throw new Error('评级 = ' + JSON.stringify(hold.data.grade) + '，独立审 = ' + want
        + '（体脂 ' + fatRaw + '% / BMI ' + bmiRaw + '）');
    }
    if (!/^#[0-9a-fA-F]{6}$/.test(String(hold.data.gradeColor || ''))) {
      throw new Error('评级名没拿到颜色：' + hold.data.gradeColor);
    }
  });

  step('断言 · 右上角体脂/BMI 就是主页面上写的那两个原始值', () => {
    if (hold.data.hrFat !== fatRaw.toFixed(1) + '%') {
      throw new Error('体脂 = ' + hold.data.hrFat + '，期望 ' + fatRaw.toFixed(1) + '%');
    }
    if (hold.data.hrBmi !== bmiRaw.toFixed(1)) {
      throw new Error('BMI = ' + hold.data.hrBmi + '，期望 ' + bmiRaw.toFixed(1));
    }
    if (!hold.data.hrRange || !hold.data.hrDesc) throw new Error('分型区间/建议为空，说明没渲染');
  });

  step('断言 · 缺口档位刻度条 7 档且最多一档高亮', () => {
    const t = hold.data.gapTiers || [];
    if (t.length !== 7) throw new Error('档位数 = ' + t.length + '，期望 7');
    const on = t.filter((x) => x.on);
    if (on.length > 1) throw new Error('高亮了 ' + on.length + ' 档，只该有 0 或 1 档');
    if (t.some((x) => !x.short)) throw new Error('有档位缺 short 文案');
    if (on.length === 1 && !on[0].st) throw new Error('高亮档没带上色样式，点了也看不出来');
    if (hold.data.hasRecord && on.length !== 1) throw new Error('今天有记录却没高亮任何档位');
    // 单位必须跟数字符号一致（正数=缺口 / 负数=盈余），符号处理最容易写反
    const n = parseDeficit(hold.data.gapDeficit);
    if (hold.data.hasRecord) {
      if (!isFinite(n)) throw new Error('缺口数字不可解析：' + hold.data.gapDeficit);
      const wantUnit = n >= 0 ? 'kcal 缺口' : 'kcal 盈余';
      if (hold.data.gapUnit !== wantUnit) {
        throw new Error('缺口 ' + n + ' 却写「' + hold.data.gapUnit + '」，应为 ' + wantUnit);
      }
    }
  });

  step('断言 · 排名句要么整句消失、要么真有百分比（⛔ 不许写死）', () => {
    if (hold.data.gapRankShow) {
      const m = /跑赢 (\d+)% 的交易日/.exec(String(hold.data.gapRank));
      if (!m) throw new Error('排名文案不对：' + hold.data.gapRank);
      if (!/近 \d+ 个交易日/.test(String(hold.data.gapRankTip))) {
        throw new Error('排名缺样本量说明：' + hold.data.gapRankTip);
      }
    } else if (hold.data.gapRank) {
      throw new Error('隐藏了排名却还留着文案：' + hold.data.gapRank);
    }
  });

  step('断言 · 净热量趋势不是空态，且画布宽 ≥ 视窗宽', () => {
    if (hold.data.ntEmpty) throw new Error('96 天记录却走了空态');
    if (!(hold.data.trendCssW >= hold.data.trendW)) {
      throw new Error('画布宽 ' + hold.data.trendCssW + ' < 视窗宽 ' + hold.data.trendW);
    }
    if (hold.data.trendCssW > hold.data.trendW && !hold.data.ntHint) {
      throw new Error('内容超宽却没提示「左右滑动查看」');
    }
  });

  /* ① 切档必须真的改到内核 —— 这条盯的是 mp_build.py 的 LIVE_VARS：
     顶层 `let trendRange` 若按值导出（trendRange: trendRange），模块外读到的
     永远是初始 'all'，表现是「点了没反应」。② 下面直接查导出描述符，
     是 getter 才算过关 —— 比只看页面 data 更早一层拦住回归。 */
  step('断言 · trendRange 在导出上是 getter（不是值快照）', () => {
    const d = Object.getOwnPropertyDescriptor(calc, 'trendRange');
    if (!d) throw new Error('calc 没导出 trendRange');
    if (typeof d.get !== 'function') {
      throw new Error('trendRange 是值导出（' + JSON.stringify(calc.trendRange)
        + '）—— 内核改了它，模块外读不到，切档会表现为「点了没反应」');
    }
  });

  step('断言 · 点「月度」后内核与页面同步切档（取日均口径）', () => {
    hold.onNtRange({ currentTarget: { dataset: { nt: '30d' } } });
    if (calc.trendRange !== '30d') throw new Error('内核 trendRange = ' + calc.trendRange + '，期望 30d');
    if (hold.data.ntRange !== '30d') throw new Error('页面 ntRange = ' + hold.data.ntRange + '，期望 30d');
    if (String(hold.data.ntSub).indexOf('取日均') < 0) {
      throw new Error('月度口径该追加「取日均」，实测副标题：' + hold.data.ntSub);
    }
  });

  log('        账户：' + hold.data.cost + ' → ' + hold.data.now + ' / 止盈 ' + hold.data.target
    + ' · ' + hold.data.acctState + ' · 进度 ' + hold.data.acctIv + hold.data.acctDec + hold.data.acctPc);
  log('        评级：' + hold.data.grade + '（体脂 ' + hold.data.hrFat + ' / BMI ' + hold.data.hrBmi + '）');
  log('        缺口：' + hold.data.gapDeficit + ' ' + hold.data.gapUnit + ' · ' + hold.data.gapRateName
    + ' · ' + hold.data.gapJin + '/' + hold.data.gapWeek + '/' + hold.data.gapMonth + ' 斤');
  log('        持仓页 canvas 调用记账：共 ' + ctxStats.total + ' 次（趋势图 + 九宫格）');
  if (ctxStats.total === 0) log('  ⚠️ 持仓页一次都没画 —— 两个 canvas 的绘制路径没被触发，要查');
  log();

  /* ------------------------------------------------------------
   * 持仓页第二态：今天真有记录时
   *
   * 上面那一跑，存档最后一天是 2026-09-11，而"今天"不是那天 ——
   * 所以缺口卡走的是「待开盘」分支，**符号与绿色/红色那条路一次都没跑到**。
   * 「缺口为正却写成 kcal 盈余」这类错正是藏在那条分支里，必须真跑一次。
   *
   * 做法：凭空造两笔今天的记录（先运动 → 缺口由正到更大；再猛吃 → 转成盈余），
   * 于是同一页面天然产出两组相反的期望值 —— 这本身就是负控：
   * 断言若不是真读状态，两态不可能都过（写死 true/false 必挂一边）。
   * ------------------------------------------------------------ */
  const store = require(path.join(MINI, 'lib/store.js'));
  // 独立实现的今天（YYYY-MM-DD，本地时区），不使用 calc.todayStr
  const d0 = new Date();
  const todayStrLocal = d0.getFullYear() + '-'
    + String(d0.getMonth() + 1).padStart(2, '0') + '-'
    + String(d0.getDate()).padStart(2, '0');

  const stLive = store.get();
  step('注入前 · 套牢卡必须是关着的（今天没吃超）', () => {
    stLive.diet = (stLive.diet || []).filter((x) => x.date !== todayStrLocal);
    stLive.exercise = (stLive.exercise || []).filter((x) => x.date !== todayStrLocal);
    store.save();
    hold.refreshFromState();
    if (hold.data.hasRecord) throw new Error('今天没有任何记录，不该进「已开盘」分支');
    if (hold.data.stuck) throw new Error('今天没记录却报套牢');
    if (hold.data.gapRateName !== '待开盘') throw new Error('评级名 = ' + hold.data.gapRateName);
  });

  step('注入一笔今日运动 600 kcal → 缺口为正，该高亮到减脂档', () => {
    stLive.exercise.push({ id: 'smoke-ex', date: todayStrLocal, name: '冒烟测试·跑步', kcal: 600, min: 60 });
    store.save();
    hold.refreshFromState();
    if (!hold.data.hasRecord) throw new Error('有记录了却没进「已开盘」分支');
    const n = parseDeficit(hold.data.gapDeficit);
    if (!(n > 0)) throw new Error('运动 600 kcal 后缺口应为正，实测 ' + hold.data.gapDeficit);
    if (hold.data.gapUnit !== 'kcal 缺口') throw new Error('单位 = ' + hold.data.gapUnit);
    const on = (hold.data.gapTiers || []).filter((x) => x.on);
    if (on.length !== 1) throw new Error('高亮档位数 = ' + on.length + '，应恰好 1');
    if (['跌停', '大阴线', '中阴线', '小阴线'].indexOf(on[0].short) < 0) {
      throw new Error('缺口 ' + n + ' 应落在减脂侧档位，实测高亮「' + on[0].short + '」');
    }
    if (hold.data.stuck) throw new Error('缺口为正却报套牢（套牢的判据是净热量 > 0）');
    if (!/^[\d.]+$/.test(String(hold.data.gapJin))) {
      throw new Error('减脂斤数不是数字：' + hold.data.gapJin);
    }
    if (String(hold.data.netSubJin) !== String(hold.data.gapJin)) {
      throw new Error('折算说明里的斤数（' + hold.data.netSubJin + '）与三宫格（' + hold.data.gapJin + '）不一致');
    }
  });

  step('再猛吃 6000 kcal → 缺口转负，单位变「盈余」且套牢卡亮起', () => {
    stLive.diet.push({ id: 'smoke-diet', date: todayStrLocal, name: '冒烟测试·自助餐', kcal: 6000, qty: 1 });
    store.save();
    hold.refreshFromState();
    const n = parseDeficit(hold.data.gapDeficit);
    if (!(n < 0)) throw new Error('吃超后缺口应为负，实测 ' + hold.data.gapDeficit);
    if (hold.data.gapUnit !== 'kcal 盈余') throw new Error('单位 = ' + hold.data.gapUnit + '，应为 kcal 盈余');
    if (!hold.data.stuck) throw new Error('净热量为正却没亮套牢卡');
    const on = (hold.data.gapTiers || []).filter((x) => x.on);
    if (on.length !== 1 || on[0].short !== '涨停') {
      throw new Error('显著盈余应高亮「涨停」，实测 '
        + (on.map((x) => x.short).join(',') || '无'));
    }
  });

  // 复位：把冒烟造的两笔清掉，别污染后面可能的复用
  stLive.diet = stLive.diet.filter((x) => x.id !== 'smoke-diet');
  stLive.exercise = stLive.exercise.filter((x) => x.id !== 'smoke-ex');
  store.save();

  /* ============================================================
   * 行情页剩余 4 块：②运动网格 / ③大盘云图 / ④身体成分 / ⑤历史成交
   *
   * 放在持仓页之后跑，是因为这几条要用到上面已经定义好的 calc / store / todayStrLocal。
   * 期望值全部**独立现算**（不复用 calc）：日历自己按 Date 推、treemap 自己查
   * 重叠/越界/面积比、BMI 与脂肪重量按公式另算、历史成交按日期区间自己求和。
   *
   * 这四块的共同风险不是「报不报错」，而是**数字看着合理但口径错了**：
   *   ② 色阶基准用错样本（分位数 vs 峰值）⇒ 相近消耗跨档跳变、深浅失去意义
   *   ③ 面积不按热量比例 / 块互相重叠 ⇒ 「一眼看出大头」这个功能直接失效
   *   ④ 参考值与等级标签对不上 ⇒ 看着正常、判断反了
   *   ⑤ 平均除以总槽数而不是「有数据的槽」⇒ 日均被空日稀释
   * 以上都不会抛错，只会安静地显示错数字 —— 所以必须比数，不能只看「没报错」。
   * ============================================================ */
  const storeMk = require(path.join(MINI, 'lib/store.js'));

  /* —— 独立实现的本地日历（周一 = 行首），不使用 calc.todayStr —— */
  const p2 = (n) => String(n).padStart(2, '0');
  const ymd = (d) => d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate());
  const spanD = (a, b) => Math.round((new Date(b + 'T00:00:00') - new Date(a + 'T00:00:00')) / 86400000) + 1;
  const addStr = (s, n) => { const d = new Date(s + 'T00:00:00'); d.setDate(d.getDate() + n); return ymd(d); };
  const tNow = new Date(); tNow.setHours(0, 0, 0, 0);
  const dowMon = (tNow.getDay() + 6) % 7;                        // 0 = 周一
  const monThis = new Date(tNow); monThis.setDate(tNow.getDate() - dowMon);
  const monStart = new Date(monThis); monStart.setDate(monThis.getDate() - 52 * 7);
  const dayOff = (k) => Math.round((new Date(k + 'T00:00:00') - monStart) / 86400000);  // 距窗口首日天数 = 格子序号
  const LAST = 52 * 7 + dowMon;                                  // 今天的格子序号
  const burnDay = {};                                            // 独立按日聚合的运动消耗
  (realState.exercise || []).forEach((e) => {
    const k = e.date || todayStrLocal; const v = Math.round(e.kcal || 0);
    if (v > 0) burnDay[k] = (burnDay[k] || 0) + v;
  });

  ctxStats.total = 0; ctxStats.fillText = 0;   // 单独记账：这一段的绘制必须来自行情页

  /* 这条盯的是一整类静默缺陷：refresh() 里的 Object.assign(patch, 某块())，
     只要某块返回值被多包了一层 data，字段就全落不到 page.data 上，
     而 `Object.assign(x, undefined)` 是合法空操作 ⇒ 不抛错、页面照常渲染、只是那块空白。
     2026-09-23 就是靠这条 + 「格子数 / 指标卡数」抓出了运动网格与身体成分两块同时失效。 */
  step('断言 · 行情页 4 块的数据都直接落在 page.data 上（⛔ 不许出现嵌套的 data 键）', () => {
    if (mk.data.data && typeof mk.data.data === 'object') {
      throw new Error('page.data 里出现了嵌套的 data 键（' + Object.keys(mk.data.data).join(',')
        + '）—— 说明某块的返回值被包了一层，字段全没落地');
    }
  });

  /* ---------- ② 运动网格 ---------- */
  step('断言 · 运动网格 = 53 周 × 7 天，今天恰好落在最后一列第 ' + (dowMon + 1) + ' 行', () => {
    const cs = mk.data.exCells || [];
    if (cs.length !== 53 * 7) throw new Error('格子数 = ' + cs.length + '，期望 371（53×7）');
    const on = cs.map((c, i) => (c.t ? i : -1)).filter((i) => i >= 0);
    if (on.length !== 1) throw new Error('「今天」高亮了 ' + on.length + ' 格，应恰好 1 格');
    if (on[0] !== LAST) throw new Error('今天在第 ' + on[0] + ' 格，独立推 = ' + LAST + '（最后一列第 ' + dowMon + ' 行）');
  });

  step('断言 · 未来格 = 最后一列今天之后的 ' + (6 - dowMon) + ' 格（不是整列也不是整周）', () => {
    const cs = mk.data.exCells || [];
    const f = cs.map((c, i) => (c.f ? i : -1)).filter((i) => i >= 0);
    if (f.length !== 6 - dowMon) throw new Error('未来格 = ' + f.length + '，独立推 = ' + (6 - dowMon));
    if (f.some((i) => i < 52 * 7)) throw new Error('未来格跑到最后一列之外：' + f.join(','));
    if (cs[LAST].f) throw new Error('今天自己被标成了未来格');
  });

  step('断言 · 横滑行程 = 53 列宽 + 52 个间隙（格子尺寸由 viewWeeks=22 反推并 clamp 7~18）', () => {
    const gs = String(mk.data.exGridStyle);
    const mc = /grid-auto-columns:([\d.]+)px/.exec(gs);
    if (!mc) throw new Error('网格样式缺 grid-auto-columns：' + gs);
    const cell = +mc[1];
    if (!(cell >= 7 && cell <= 18)) throw new Error('格子尺寸 ' + cell + 'px 越界（应 clamp 在 7~18）');
    const mg = /gap:([\d.]+)px/.exec(gs);
    if (!mg || +mg[1] !== 3) throw new Error('列间隙 = ' + (mg ? mg[1] : '(无)') + '，EX_HEAT.gap 应为 3');
    if (mk.data.exTrackW !== 53 * cell + 52 * 3) {
      throw new Error('横滑内容宽 = ' + mk.data.exTrackW + '，独立算 = ' + (53 * cell + 52 * 3));
    }
    if (!(mk.data.exScrollH >= 7 * cell + 38)) {
      throw new Error('滚动视窗高 ' + mk.data.exScrollH + ' 装不下 7 行 + 月份行（独立算 ' + (7 * cell + 38) + '）');
    }
  });

  /* ⚠️ 色值有两种形态，断言必须都认，否则会把「设计如此」判成缺陷：
       · `rgb(...)` —— 段内线性插值（P50/P75/P90 三段之内）
       · `#hex`    —— 两端锚点：v > P90 时 exHeatColor 直接返回 L[4]，不插值
     （实测踩过：721 kcal 得到 `#05704f` 被判「拿不到插值色」，
       而它正是 EX_HEAT.lv 的第 4 档深绿，行为完全正确。） */
  function lumOf(css) {
    const s = String(css);
    let m = /rgb\((\d+),\s*(\d+),\s*(\d+)\)/.exec(s);
    if (m) return +m[1] + +m[2] + +m[3];
    m = /#([0-9a-f]{6})/i.exec(s);
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return ((n >> 16) & 255) + ((n >> 8) & 255) + (n & 255);
  }

  step('断言 · 有运动的日子不是空色、没运动的日子是空色，且消耗越多越深', () => {
    const cs = mk.data.exCells || [];
    const pts = [];
    Object.keys(burnDay).forEach((k) => {
      const n = dayOff(k);
      if (n < 0 || n > LAST) return;
      const s = String(cs[n].s);
      if (s.indexOf('#1a2030') >= 0) {
        throw new Error('有运动（' + k + ' / ' + burnDay[k] + ' kcal）的格子却是空色：' + s);
      }
      const lum = lumOf(s);
      if (lum == null) throw new Error('有运动（' + k + '）的格子拿不到色值：' + s);
      pts.push({ kcal: burnDay[k], lum: lum });
    });
    if (!pts.length) return;                       // 记录全在 53 周窗口外 ⇒ 这条无从验起
    pts.sort((a, b) => a.kcal - b.kcal);
    for (let i = 1; i < pts.length; i++) {
      if (pts[i].kcal === pts[i - 1].kcal) continue;
      if (pts[i].lum > pts[i - 1].lum) {
        throw new Error('色阶非单调：' + pts[i - 1].kcal + ' kcal（亮度 ' + pts[i - 1].lum
          + '）比 ' + pts[i].kcal + ' kcal（亮度 ' + pts[i].lum + '）还深');
      }
    }
    // 反例：窗口内第一个「没运动」的过去日必须是空色（写死颜色必挂一边）
    let blank = -1;
    for (let n = 0; n <= LAST; n++) if (!burnDay[ymd(new Date(monStart.getTime() + n * 86400000))]) { blank = n; break; }
    if (blank >= 0 && String(cs[blank].s).indexOf('#1a2030') < 0) {
      throw new Error('没运动的那天（格子 ' + blank + '）不是空色：' + cs[blank].s);
    }
  });

  step('断言 · 星期轴是 一/三/五/日，月份轴从 0 起算且同月只标一次', () => {
    if (JSON.stringify(mk.data.exDays) !== JSON.stringify(['一', '', '三', '', '五', '', '日'])) {
      throw new Error('星期行标 = ' + JSON.stringify(mk.data.exDays));
    }
    const ms = mk.data.exMonths || [];
    if (!ms.length) throw new Error('月份标签为空');
    if (ms[0].left !== 0) throw new Error('首个月份标签 left = ' + ms[0].left + '，应为 0（星期轴已移出滚动容器）');
    if (ms[0].text !== (monStart.getMonth() + 1) + '月') {
      throw new Error('首个月份 = ' + ms[0].text + '，独立推 = ' + ((monStart.getMonth() + 1) + '月'));
    }
    for (let i = 1; i < ms.length; i++) {
      if (ms[i].left <= ms[i - 1].left) throw new Error('月份标签 left 没有严格递增');
    }
  });

  step('断言 · 运动网格副标题的峰值 = 独立按日聚合的最大值（⛔ 不许写死）', () => {
    const maxDay = Object.keys(burnDay).reduce((m, k) => Math.max(m, burnDay[k]), 0);
    if (maxDay === 0) {
      if (mk.data.exSub !== '暂无运动记录') throw new Error('无运动记录时副标题 = ' + mk.data.exSub);
      return;
    }
    if (String(mk.data.exSub).indexOf('峰值 ' + maxDay) < 0) {
      throw new Error('副标题 = ' + mk.data.exSub + '，独立算峰值 = ' + maxDay);
    }
  });

  /* ---------- ③ 大盘云图 ---------- */
  /* 只查「内核结果被搬到 DOM 时有没有搬错」：块数、pin 顺序、越界、重叠、面积比。
     内核算得对不对是 mp_calc_test 的事，这里不重复。 */
  function parseRects() {
    return (mk.data.mmBlocks || []).map((b) => {
      const g = (re) => { const m = re.exec(String(b.box)); return m ? +m[1] : NaN; };
      return {
        id: b.id, type: b.type, isBmr: b.isBmr, box: b.box,
        kcal: Number(String(b.vText).replace(/[+\u2212]/g, '')),
        x: g(/left:([\d.]+)px/), y: g(/top:([\d.]+)px/),
        w: g(/width:([\d.]+)px/), h: g(/height:([\d.]+)px/),
      };
    });
  }
  const wantToday = (list) => (list || []).filter((x) => (x.date || todayStrLocal) === todayStrLocal).length;

  step('断言 · 云图无条件常驻基础代谢块，且它永远排最前（pin = 视觉锚点）', () => {
    const rs = parseRects();
    if (!rs.length) throw new Error('一块都没有 —— 基代应当无条件常驻');
    if (rs[0].id !== 'bmr' || rs[0].isBmr !== 1) {
      throw new Error('首块 = ' + rs[0].id + '（isBmr ' + rs[0].isBmr + '），基代必须恒排最前');
    }
    if (mk.data.mmEmpty) throw new Error('有基代块却报了空态');
    if (rs[0].kcal <= 0) throw new Error('基代块热量 = ' + rs[0].kcal);
  });

  step('断言 · 云图块数 = 基代 1 + 今日真实成交笔数（独立按日期数）', () => {
    const wantRec = wantToday(realState.diet) + wantToday(realState.exercise);
    const rs = parseRects();
    if (rs.length !== 1 + wantRec) {
      throw new Error('块数 = ' + rs.length + '，独立数 = ' + (1 + wantRec)
        + '（基代 1 + 今日成交 ' + wantRec + ' 笔）');
    }
  });

  step('断言 · 云图块两两不重叠、且全部落在容器内（treemap 的硬约束）', () => {
    const rs = parseRects();
    const H = mk.data.mmH;
    const W = mk._mmW || Math.max.apply(null, rs.map((r) => r.x + r.w));
    rs.forEach((r) => {
      if (![r.x, r.y, r.w, r.h].every(isFinite)) throw new Error('块 ' + r.id + ' 的 box 解析不出几何：' + r.box);
      if (r.w <= 0 || r.h <= 0) throw new Error('块 ' + r.id + ' 尺寸非正：' + r.w + '×' + r.h);
      if (r.x < -0.6 || r.y < -0.6 || r.x + r.w > W + 0.6 || r.y + r.h > H + 0.6) {
        throw new Error('块 ' + r.id + ' 越界：x' + r.x + ' y' + r.y + ' w' + r.w + ' h' + r.h
          + '（容器 ' + W + '×' + H + '）');
      }
    });
    for (let i = 0; i < rs.length; i++) {
      for (let j = i + 1; j < rs.length; j++) {
        const a = rs[i], b = rs[j];
        const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
        const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
        if (ox > 0.6 && oy > 0.6) {
          throw new Error('块 ' + a.id + ' 与 ' + b.id + ' 重叠 ' + ox.toFixed(1) + '×' + oy.toFixed(1) + 'px');
        }
      }
    }
  });

  step('断言 · 云图配色语义：做多红 / 做空绿 / 基代固定浅绿，且色深随单笔数值', () => {
    const rs = parseRects();
    rs.forEach((r) => {
      if (r.type === 'food' && String(r.box).indexOf('rgba(255,59,71,') < 0) {
        throw new Error('食物块不是红色：' + r.box);
      }
      if (r.type !== 'food' && String(r.box).indexOf('rgba(0,200,150,') < 0) {
        throw new Error(r.type + ' 块不是绿色：' + r.box);
      }
    });
    const bmr = rs.filter((r) => r.type === 'bmr')[0];
    if (bmr && String(bmr.box).indexOf('0.42') < 0) {
      throw new Error('基代块透明度应固定 0.42（不参与色深分档）：' + bmr.box);
    }
    const rec = rs.filter((r) => r.type !== 'bmr');
    if (rec.length > 1) {
      const maxK = Math.max.apply(null, rec.map((r) => r.kcal));
      rec.forEach((r) => {
        const al = +(/rgba\([^)]*?,\s*([\d.]+)\)/.exec(r.box) || [])[1];
        const want = +(0.35 + 0.65 * Math.min(1, r.kcal / maxK)).toFixed(3);
        if (Math.abs(al - want) > 0.002) {
          throw new Error('块 ' + r.id + '（' + r.kcal + ' kcal / 当日最大 ' + maxK
            + '）色深 = ' + al + '，独立算 = ' + want);
        }
      });
    }
  });

  /* ---------- ③ 第二态：今天真有成交时，云图必须长成多块 ---------- */
  const stMk = storeMk.get();
  const bakDiet = (stMk.diet || []).slice();
  const bakEx = (stMk.exercise || []).slice();
  stMk.exercise = bakEx.concat([{ id: 'mk-smoke-ex', date: todayStrLocal, name: '冒烟·椭圆机', kcal: 500 }]);
  stMk.diet = bakDiet.concat([{ id: 'mk-smoke-d1', date: todayStrLocal, name: '冒烟·米饭', kcal: 300, qty: 1 }]);
  storeMk.save();
  mk.refresh();

  step('断言 · 今日记两笔后云图 = 基代 + 2 块，基代仍排最前', () => {
    const rs = parseRects();
    if (rs.length !== 3) throw new Error('块数 = ' + rs.length + '，期望 3');
    if (rs[0].id !== 'bmr') throw new Error('基代不再排最前：' + rs.map((r) => r.id).join(','));
    if (mk.data.mmEmpty) throw new Error('有 3 块却报空态');
  });

  step('断言 · 食物带 +、运动带 −，且面积与热量成正比（容差 15%）', () => {
    const rs = parseRects();
    const food = rs.filter((r) => r.type === 'food');
    const ex = rs.filter((r) => r.type === 'ex');
    if (food.length !== 1 || ex.length !== 1) {
      throw new Error('今日两笔没变成两块：' + rs.map((r) => r.type).join(','));
    }
    if (food[0].kcal !== 300) throw new Error('食物块热量 = ' + food[0].kcal + '，期望 300');
    if (ex[0].kcal !== 500) throw new Error('运动块热量 = ' + ex[0].kcal + '，期望 500');
    const st = mk.data.mmBlocks;
    const fv = String(st.filter((b) => b.type === 'food')[0].vText);
    const ev = String(st.filter((b) => b.type === 'ex')[0].vText);
    if (fv.charAt(0) !== '+') throw new Error('食物块的值应带 +：' + fv);
    if (ev.charAt(0) !== '\u2212') throw new Error('运动块的值应带 −：' + ev);
    const totA = rs.reduce((s, r) => s + r.w * r.h, 0);
    const totK = rs.reduce((s, r) => s + r.kcal, 0);
    rs.forEach((r) => {
      const aShare = r.w * r.h / totA, kShare = r.kcal / totK;
      if (Math.abs(aShare - kShare) / kShare > 0.15) {
        throw new Error('块 ' + r.id + '：面积占比 ' + (aShare * 100).toFixed(1)
          + '% 与热量占比 ' + (kShare * 100).toFixed(1) + '% 相差超过 15%');
      }
    });
  });

  step('断言 · 云图副标题报出真实笔数与合计（做多 / 做空 / 基代）', () => {
    const sub = String(mk.data.mmSub);
    if (sub.indexOf('做多 1 笔 +300') < 0) throw new Error('副标题没报做多笔数/合计：' + sub);
    if (sub.indexOf('做空 1 笔 \u2212500') < 0) throw new Error('副标题没报做空笔数/合计：' + sub);
    if (!/基代 \u2212\d+/.test(sub)) throw new Error('副标题没报基代：' + sub);
  });

  // 复位：云图的注入必须还回去，否则后面的历史成交会多算一笔今天
  stMk.diet = bakDiet;
  stMk.exercise = bakEx;
  storeMk.save();
  mk.refresh();

  /* ---------- ④ 身体成分 ---------- */
  step('断言 · 身体成分 8 张卡、每张都有等级名/参考值/分段色轴/定位点', () => {
    const ms = mk.data.bodyMetrics || [];
    if (ms.length !== 8) throw new Error('指标卡数 = ' + ms.length + '，BODY_RANGES 应为 8 项');
    const by = {};
    ms.forEach((m) => { by[m.label] = m; });
    ms.forEach((m) => {
      if (!m.label) throw new Error('有卡没有名字');
      if (!m.levelName) throw new Error(m.label + ' 没有等级名');
      if (String(m.ref).indexOf('参考 ') !== 0) throw new Error(m.label + ' 的参考值文案不对：' + m.ref);
      if (String(m.levelStyle).indexOf('background:') < 0) throw new Error(m.label + ' 等级标签没上色');
      const segs = m.segs || [];
      if (!segs.length) throw new Error(m.label + ' 没有分段色轴');
      segs.forEach((s) => {
        if (!/^#[0-9a-f]{6}$/i.test(String(s.c))) throw new Error(m.label + ' 分段色不是 hex：' + s.c);
        if (!(s.w > 0)) throw new Error(m.label + ' 有分段宽度为 0');
      });
      const sum = segs.reduce((s, x) => s + x.w, 0);
      if (sum > 100.01) throw new Error(m.label + ' 分段总宽 = ' + sum.toFixed(1) + '% > 100%，色轴会溢出轨道');
      const dm = /left:([\d.]+)%/.exec(String(m.dotStyle));
      if (!dm) throw new Error(m.label + ' 定位点缺 left：' + m.dotStyle);
      const pct = +dm[1];
      if (!(pct >= 3 && pct <= 97)) throw new Error(m.label + ' 定位点 ' + pct + '% 越界（应 clamp 3~97）');
      const bc = String(m.dotStyle).replace(/.*border-color:/, '').replace(/;.*/, '');
      if (!/^#[0-9a-f]{6}$/i.test(bc)) throw new Error(m.label + ' 定位点边框没拿到等级色：' + m.dotStyle);
    });
    /* ⭐ 两项「极简指标」是设计如此：levels 里只有 1 个占位等级 ⇒ 色轴 1 段，
       等级名必须来自 statusWord（'年轻'/'已达标'…），⛔ 不能回落到 levels 的字面名
       —— 回落了卡上会写成「身体年龄 · 身体年龄」这种同义重复。
       （我第一版断言「分段 ≥2 段」，把这条正确行为判成了缺陷 —— 先怀疑测试再怀疑代码。） */
    [['身体年龄', /^(偏高|年轻|正常)$/], ['基础代谢率', /(达标)/]].forEach(([lab, re]) => {
      const m = by[lab];
      if (!m) throw new Error('缺少 ' + lab + ' 卡');
      const segs = m.segs || [];
      if (segs.length !== 1) throw new Error(lab + ' 应有且只有 1 段色轴（极简项），实测 ' + segs.length);
      if (!re.test(String(m.levelName))) {
        throw new Error(lab + ' 的等级名 = ' + m.levelName + '，看起来是回落到了 levels 的字面名');
      }
    });
  });

  step('断言 · BMI / 脂肪重量 = 独立按公式另算一遍（不是读同一份数据自证）', () => {
    const by = {};
    (mk.data.bodyMetrics || []).forEach((m) => { by[m.label] = m; });
    const usr = realState.user;
    const wantBmi = +(usr.weight / Math.pow(usr.height / 100, 2)).toFixed(1);
    if (!by['BMI']) throw new Error('没有 BMI 卡');
    if (Math.abs(+by['BMI'].v - wantBmi) > 0.06) {
      throw new Error('BMI 卡 = ' + by['BMI'].v + '，独立按 体重/身高² 算 = ' + wantBmi
        + '（' + usr.weight + 'kg / ' + usr.height + 'cm）');
    }
    // 脂肪重量（斤）：floor(体重 × 体脂% × 2 × 10) / 10
    const wantFat = Math.floor(usr.weight * (realState.body.bodyFat / 100) * 2 * 10) / 10;
    if (!by['脂肪重量']) throw new Error('没有脂肪重量卡（该值由体重×体脂现算，最容易被写成 NaN）');
    if (Math.abs(+by['脂肪重量'].v - wantFat) > 0.001) {
      throw new Error('脂肪重量 = ' + by['脂肪重量'].v + '，独立算 = ' + wantFat + ' 斤');
    }
  });

  step('断言 · 身体成分来源标签与实际 source 对应（示例/手动/识别三态不许错认）', () => {
    const src = String(mk.data.bodySrcText);
    const s = realState.body.source;
    const want = s === 'manual' ? '手动录入' : s === 'sync' ? '图片识别' : '示例数据';
    if (src.indexOf(want) < 0) throw new Error('source=' + s + ' 时来源文案 = ' + src + '，应含「' + want + '」');
  });

  /* ---------- ⑤ 历史成交 ---------- */
  step('断言 · 历史成交默认「全部」档、且有记录时不走空态', () => {
    if (mk.data.histRange !== 'all') throw new Error('默认档位 = ' + mk.data.histRange + '，应为 all');
    if (mk.data.histEmpty) throw new Error('有 96 天记录却走了空态');
    /* 2026-09-22 起「画布高度」不是 data 字段了 —— 由 wxss 决定：
         ① K 线 .kchart 写死 height:150px（对齐 PWA 的 height:150px + meet 居中）
         ⑤ 历史成交 .hchart-box 的 padding-bottom:60.1266%（= 190/316，对齐 PWA 的 height:auto）
       所以这里守的是「别把高度又算回 JS」；真实高度由 ⑥c rect 对拍 + mp_market_test 的
       CSS 常量断言（读 wxss）两处盯着。 */
    if (mk.data.kchartH !== undefined) throw new Error('kchartH 又回到 data 了（高度应交由 .kchart 的 CSS）');
    if (mk.data.histH !== undefined) throw new Error('histH 又回到 data 了（高度应交由 .hchart-box 的宽高比）');
  });

  step('断言 · 图例合计/平均 = 独立按同一日期区间求和（区间端点差一天就会挂）', () => {
    // 独立实现 PWA 的区间口径：all 档从首条记录起，跨度 >62 天则截为近 61 天
    const alld = (realState.diet || []).map((x) => x.date || todayStrLocal)
      .concat((realState.exercise || []).map((x) => x.date || todayStrLocal)).filter(Boolean).sort();
    const first = alld[0];
    let from = first;
    if (spanD(from, todayStrLocal) > 62) from = addStr(todayStrLocal, -61);
    const inWin = (x) => { const k = x.date || todayStrLocal; return k >= from && k <= todayStrLocal; };
    const sumIn = (realState.diet || []).filter(inWin).reduce((s, x) => s + (x.kcal || 0), 0);
    const sumEx = (realState.exercise || []).filter(inWin).reduce((s, x) => s + (x.kcal || 0), 0);
    if (mk.data.histLegend.in !== sumIn) {
      throw new Error('摄入合计 = ' + mk.data.histLegend.in + '，独立算 = ' + sumIn);
    }
    if (mk.data.histLegend.ex !== sumEx) {
      throw new Error('运动合计 = ' + mk.data.histLegend.ex + '，独立算 = ' + sumEx);
    }
    // 平均只按「有数据的槽」算 —— 除以总槽数是最容易写错的一处（空日会把日均稀释）
    const days = new Set();
    (realState.diet || []).filter(inWin).forEach((x) => { if (x.kcal > 0) days.add(x.date || todayStrLocal); });
    (realState.exercise || []).filter(inWin).forEach((x) => { if (x.kcal > 0) days.add(x.date || todayStrLocal); });
    const act = Math.max(1, days.size);
    if (mk.data.histLegend.avgIn !== Math.round(sumIn / act)) {
      throw new Error('日均摄入 = ' + mk.data.histLegend.avgIn + '，独立算 = '
        + Math.round(sumIn / act) + '（有数据 ' + act + ' 天 / 区间 ' + from + '~' + todayStrLocal + '）');
    }
    if (mk.data.histLegend.avgEx !== Math.round(sumEx / act)) {
      throw new Error('日均运动 = ' + mk.data.histLegend.avgEx + '，独立算 = ' + Math.round(sumEx / act));
    }
  });

  step('断言 · historyRange 在导出上也是 getter（否则切档「点了没反应」）', () => {
    ['trendRange', 'historyRange', 'curTab', 'curBodyIdx', 'lbRange'].forEach((n) => {
      const d = Object.getOwnPropertyDescriptor(calc, n);
      if (!d) throw new Error('calc 没导出 ' + n);
      if (typeof d.get !== 'function') {
        throw new Error(n + ' 是值导出（' + JSON.stringify(calc[n]) + '）—— 内核改了它，模块外读不到');
      }
    });
  });

  step('断言 · 切到「年度」按自然年聚合，槽数 = 记录覆盖的年份数', () => {
    mk.onHistRange({ currentTarget: { dataset: { range: '365d' } } });
    if (calc.historyRange !== '365d') throw new Error('内核 historyRange = ' + calc.historyRange + '，期望 365d');
    if (mk.data.histRange !== '365d') throw new Error('页面 histRange = ' + mk.data.histRange + '，期望 365d');
    const years = new Set();
    (realState.diet || []).forEach((x) => years.add(String(x.date).slice(0, 4)));
    (realState.exercise || []).forEach((x) => years.add(String(x.date).slice(0, 4)));
    if (!mk.hist) throw new Error('切档后没有几何数据');
    if (mk.hist.n !== years.size) throw new Error('年度槽数 = ' + mk.hist.n + '，独立数 = ' + years.size);
    mk.onHistRange({ currentTarget: { dataset: { range: 'all' } } });
    if (calc.historyRange !== 'all' || mk.data.histRange !== 'all') throw new Error('切回「全部」档失败');
  });

  log('        运动网格：371 格 · ' + mk.data.exSub + ' · 横滑内容 ' + mk.data.exTrackW + 'px');
  log('        大盘云图：' + (mk.data.mmBlocks || []).length + ' 块 · ' + mk.data.mmSub);
  log('        身体成分：' + (mk.data.bodyMetrics || []).length + ' 张 · ' + mk.data.bodySrcText);
  log('        历史成交：' + mk.data.histRange + ' 档 · 摄入 ' + mk.data.histLegend.in
    + ' / 运动 ' + mk.data.histLegend.ex + ' · 日均 ' + mk.data.histLegend.avgIn + ' / ' + mk.data.histLegend.avgEx);
  log();

  /* canvas 记账必须放到异步之后读：刷新里的绘制在微任务里跑完 */
  setTimeout(function () {
    step('断言 · 行情页的图表真的画了（canvas 调用 > 0 且画过文字）', () => {
      if (ctxStats.total === 0) throw new Error('一次都没画 —— 图表绘制路径没被触发');
      if (ctxStats.fillText === 0) throw new Error('一个文字都没画 —— 大概率画在空 canvas 上');
    });
    log('        行情页 canvas 调用记账：共 ' + ctxStats.total + ' 次（fillText ' + ctxStats.fillText
      + ' / stroke ' + ctxStats.stroke + '）');
    log();
  }, 120);
}

/** 解析缺口卡上的数字。
 *  ⚠️ 界面口径（PWA 同）：缺口头部**不带符号**，盈余头带 `+`
 *     —— 所以「+3740」是 **−3740**（盈余），不是正 3740。
 *     我第一版就是在这里读反了：直接 Number(replace('+','')) 会把盈余当缺口，
 *     于是「吃超了缺口应该转负」这条断言假失败。 */
function parseDeficit(s) {
  s = String(s);
  const neg = s.charAt(0) === '+';
  const n = Number(s.replace('+', ''));
  return neg ? -n : n;
}

/** 把页面 data 拍平成一段文本，用于「某些字样绝不该出现」这类负向断言 */
function showAll(d) {
  const parts = [];
  Object.keys(d || {}).forEach((k) => {
    const v = d[k];
    if (v === null || v === undefined) return;
    if (typeof v === 'object') { try { parts.push(JSON.stringify(v)); } catch (e) {} }
    else parts.push(k + '=' + v);
  });
  return parts.join(' ');
}

log('# 小程序启动链路 + 首屏绘制 冒烟测试（mock wx，无云环境）');
log();

const MOCK = path.join(__dirname, 'mock.json');
let realState = null;
try {
  realState = JSON.parse(fs.readFileSync(MOCK, 'utf8')).state;
} catch (e) {
  log('（读不到 promo/mock.json，跳过「真实存档」那一遍：' + (e && e.message) + '）');
  log();
}

runPass(1, '空存档（全新用户）', null);
if (realState) runPass(2, '真实存档（96 天记录）', realState);
if (realState) runImportPass();

// 延迟输出：让 SelectorQuery / rAF 之类的异步回调有机会抛错并被 uncaughtException 抓到
setTimeout(function () {
  log('=== storage 最终内容 ===');
  log('  keys: ' + (Object.keys(storage).join(', ') || '(无)'));
  log();
  if (errors.length) {
    log('RESULT=FAIL —— ' + errors.length + ' 处抛错：');
    errors.forEach((e) => log('  · [' + e.name + '] ' + (e.err && e.err.message)));
  } else {
    log('RESULT=OK —— 三遍（空存档 / 真实存档 / 导入验收）+ ' + PAGE_LIST.length + ' 个页面生命周期全部无异常');
  }
  const text = lines.join('\n') + '\n';
  fs.writeFileSync(OUT, text, 'utf8');
  process.stdout.write(text);
  process.exit(errors.length ? 1 : 0);
}, 200);
