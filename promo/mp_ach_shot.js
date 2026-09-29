/**
 * mp_ach_shot.js —— 截「成就殿堂」页模拟器实图，用眼睛复核像素画 + 剪影。
 *
 * 为什么必须看图：几何闸能证明「方块 64 / 图标 44」，但证明不了
 *   ①云 fileID 真的渲出来了（不是回退线稿）②锁态的纯黑剪影与赛道底色是否分得开。
 *   这两件都是像素层面的事实，只能看。
 *
 * 用法：python promo/_mp_run.py mp_ach_shot.js [输出路径]
 */
const automator = require('miniprogram-automator');

const WS = process.env.MP_WS || 'ws://127.0.0.1:9420';
const ROUTE = '/pages/achievements/achievements';
const OUT = process.argv[2] || 'E:/WorkBuddy/jianpan-ghpages/promo/_mp_ach_shot.png';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const mp = await automator.connect({ wsEndpoint: WS, timeout: 300000 });
  await sleep(1200);

  await mp.callWxMethod('reLaunch', { url: ROUTE });
  await sleep(2600);
  /* 等云图解码落定，免得截到半张 */
  await sleep(3000);

  /* 回读一次真相：这 30 格到底有几格走云图、几格是剪影 —— 与截图互相印证 */
  const info = await mp.evaluate(function () {
    var pages = getCurrentPages();
    var pg = pages[pages.length - 1];
    var d = pg && pg.data && pg.data.achCats || [];
    var n = 0, sil = 0, cloud = 0, local = 0;
    d.forEach(function (c) {
      (c.list || []).forEach(function (b) {
        n++;
        if (b.sil) sil++;
        if (String(b.src).indexOf('cloud://') === 0) cloud++;
        else local++;
      });
    });
    return { route: pg && pg.route, cells: n, sil: sil, cloudSrc: cloud, localSrc: local };
  });
  console.log('PAGE_STATE=' + JSON.stringify(info));

  await mp.screenshot({ path: OUT });
  console.log('SHOT=' + OUT);

  /* 第二张：往下滚到「盘中操作」板块（红底赛道），确认另一个赛道色的剪影也可读 */
  await mp.callWxMethod('pageScrollTo', { scrollTop: 760, duration: 0 });
  await sleep(1600);
  const OUT2 = OUT.replace(/\.png$/, '_2.png');
  await mp.screenshot({ path: OUT2 });
  console.log('SHOT2=' + OUT2);

  await mp.disconnect();
  process.exit(0);
})().catch((e) => {
  console.error('FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
