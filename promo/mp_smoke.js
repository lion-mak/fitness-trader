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

  const PAGES = ['market', 'holdings', 'trade', 'board', 'me'];
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

// 延迟输出：让 SelectorQuery / rAF 之类的异步回调有机会抛错并被 uncaughtException 抓到
setTimeout(function () {
  log('=== storage 最终内容 ===');
  log('  keys: ' + (Object.keys(storage).join(', ') || '(无)'));
  log();
  if (errors.length) {
    log('RESULT=FAIL —— ' + errors.length + ' 处抛错：');
    errors.forEach((e) => log('  · [' + e.name + '] ' + (e.err && e.err.message)));
  } else {
    log('RESULT=OK —— 两遍启动链路 + 5 个页面 onLoad/onReady 全部无异常');
  }
  const text = lines.join('\n') + '\n';
  fs.writeFileSync(OUT, text, 'utf8');
  process.stdout.write(text);
  process.exit(errors.length ? 1 : 0);
}, 200);
