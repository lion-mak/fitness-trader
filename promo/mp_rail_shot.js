/**
 * mp_rail_shot.js —— 截「我的」页模拟器实图，用眼睛复核卡廊（数字 PASS 之外的第二道）。
 *
 * 为什么单独一个：几何量具能证明「矩形没越界」，但证明不了「名条真的整条可见」
 *   （名条是烘焙在卡面图里的像素，不是独立元素）。用户报的就是视觉问题 ⇒ 必须看图。
 *
 * 用法：python promo/_mp_run.py mp_rail_shot.js [输出路径]
 */
const automator = require('miniprogram-automator');

const WS = process.env.MP_WS || 'ws://127.0.0.1:9420';
const ROUTE = '/pages/me/me';
const OUT = process.argv[2] || 'E:/WorkBuddy/jianpan-ghpages/promo/_rail_shot.png';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const mp = await automator.connect({ wsEndpoint: WS, timeout: 300000 });
  await sleep(1200);

  await mp.callWxMethod('reLaunch', { url: ROUTE });
  await sleep(2800);
  try { await mp.switchTab(ROUTE); } catch (e) { /* 非 tab 页跳过 */ }
  /* 等 transition(.2s) 与云图解码都落定，免得截到缩放的中间帧 */
  await sleep(2400);

  await mp.screenshot({ path: OUT });
  console.log('SHOT=' + OUT);

  await mp.disconnect();
  process.exit(0);
})().catch((e) => {
  console.error('FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
