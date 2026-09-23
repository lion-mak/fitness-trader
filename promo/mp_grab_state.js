/**
 * 连上开发者工具自动化接口，做两件事：
 *   1. 把小程序 storage 里的真实存档导出到 promo/_mp_state.json
 *      —— 用于喂给 PWA 做「同一份数据、两端渲染」的像素比对。
 *   2. 持仓页补拍：首屏 + 滚到底部（评级九宫格在下方，首屏截不到）。
 *
 * 前提：`cli auto --project E:\WeChatProjects\jianpan --auto-port 9420` 已拉起。
 * 用法：NODE_PATH=<workspace>/node_modules node mp_grab_state.js
 */
const fs = require('fs');
const path = require('path');
const automator = require('miniprogram-automator');

const WS = process.env.MP_WS || 'ws://127.0.0.1:9420';
const ROOT = 'E:/WorkBuddy/jianpan-ghpages/promo';
const SHOTS = path.join(ROOT, '_shots');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  if (!fs.existsSync(SHOTS)) fs.mkdirSync(SHOTS, { recursive: true });
  const mp = await automator.connect({ wsEndpoint: WS });

  // ---- 1. 导出真实存档 ----
  // ⚠️ 先 reLaunch 再 switchTab：tab 页是常驻的，switchTab 回去**不会重跑 onLoad**。
  //    改过 onLoad 里的 setData 之后如果只 switchTab，量到/截到的还是旧 data
  //    （2026-09-22 实测踩过）。
  await mp.callWxMethod('reLaunch', { url: '/pages/holdings/holdings' });
  await sleep(2600);
  await mp.switchTab('/pages/holdings/holdings');
  await sleep(1800);

  const st = await mp.evaluate(function () {
    try { return wx.getStorageSync('jianpan_v2'); } catch (e) { return { __err: String(e) }; }
  });
  const out = path.join(ROOT, '_mp_state.json');
  fs.writeFileSync(out, JSON.stringify(st, null, 1), 'utf8');

  const keys = st && typeof st === 'object' ? Object.keys(st) : [];
  console.log('存档已导出 → ' + out);
  console.log('  字段数 ' + keys.length);
  console.log('  diet ' + ((st.diet || []).length) + ' 条 / exercise ' + ((st.exercise || []).length) +
    ' 条 / weightLog ' + ((st.weightLog || []).length) + ' 条 / bodyLog ' + ((st.bodyLog || []).length) + ' 条');
  console.log('  user=' + JSON.stringify(st.user || null));
  console.log('  body=' + JSON.stringify(st.body || null));
  console.log('  今日 ' + new Date().toISOString().slice(0, 10) +
    '  lastDate=' + st.lastDate + ' settledDate=' + st.settledDate);
  const dates = {};
  (st.diet || []).forEach((d) => { dates[d.date] = (dates[d.date] || 0) + 1; });
  console.log('  diet 日期分布: ' + JSON.stringify(dates));
  const edates = {};
  (st.exercise || []).forEach((d) => { edates[d.date] = (edates[d.date] || 0) + 1; });
  console.log('  exercise 日期分布: ' + JSON.stringify(edates));

  // ---- 2. 持仓页补拍 ----
  const shots = [];

  // 2a 首屏
  await mp.evaluate(function () { wx.pageScrollTo({ scrollTop: 0, duration: 0 }); });
  await sleep(900);
  let p = path.join(SHOTS, 'holdings_top.png').replace(/\\/g, '/');
  await mp.screenshot({ path: p });
  shots.push(['holdings_top', p, fs.existsSync(p) ? fs.statSync(p).size : 0]);

  // 2b 滚到中段（净热量趋势 + 每日缺口评级）
  await mp.evaluate(function () { wx.pageScrollTo({ scrollTop: 420, duration: 0 }); });
  await sleep(900);
  p = path.join(SHOTS, 'holdings_mid.png').replace(/\\/g, '/');
  await mp.screenshot({ path: p });
  shots.push(['holdings_mid', p, fs.existsSync(p) ? fs.statSync(p).size : 0]);

  // 2c 滚到底（持仓评级九宫格）
  await mp.evaluate(function () { wx.pageScrollTo({ scrollTop: 99999, duration: 0 }); });
  await sleep(900);
  p = path.join(SHOTS, 'holdings_end.png').replace(/\\/g, '/');
  await mp.screenshot({ path: p });
  shots.push(['holdings_end', p, fs.existsSync(p) ? fs.statSync(p).size : 0]);

  // 顺带把整页可滚高度量出来，用于判断内容会不会被底栏永久遮挡
  const m = await mp.evaluate(function () {
    return new Promise(function (res) {
      wx.createSelectorQuery()
        .select('.page-wrap').boundingClientRect()
        .selectViewport().scrollOffset()
        .exec(function (r) { res(JSON.stringify(r)); });
    });
  });
  console.log('页面度量: ' + m);

  // ---- 3. 页面 data 快照（真实数字，供比对时对拍） ----
  const page = await mp.currentPage();
  const data = await page.data();
  const keep = {};
  ['acctState', 'acctIv', 'acctDec', 'acctPc', 'capK', 'capV', 'cost', 'now', 'target',
    'remainPre', 'remainKg', 'remainPost', 'remainWk', 'barW',
    'ntRange', 'ntEmpty', 'ntSub', 'trendW',
    'hasRecord', 'gapRateName', 'gapDeficit', 'gapUnit', 'gapRankShow', 'gapRank',
    'gapJin', 'gapWeek', 'gapMonth', 'stuck',
    'grade', 'hrFat', 'hrBmi', 'hrRange', 'hrDesc'].forEach((k) => { keep[k] = data[k]; });
  fs.writeFileSync(path.join(ROOT, '_mp_page_data.json'), JSON.stringify(keep, null, 1), 'utf8');
  console.log('页面 data → promo/_mp_page_data.json');
  console.log(JSON.stringify(keep, null, 1));

  for (const [n, f, sz] of shots) console.log('  shot %-16s %s 字节', n, sz);

  await mp.disconnect();
  console.log('RESULT=OK');
  process.exit(0);
})().catch((e) => {
  console.error('FAILED: ' + e.message);
  if (e.stack) console.error(e.stack.split('\n').slice(0, 6).join('\n'));
  process.exit(1);
});
