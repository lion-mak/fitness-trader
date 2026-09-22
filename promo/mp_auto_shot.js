/**
 * 连上微信开发者工具的自动化接口，逐页截图 + 打印页面数据。
 * 前提：先用 `cli auto --project <path> --auto-port 9420` 打开项目。
 *
 * 用法：
 *   NODE_PATH=<workspace>/node_modules node mp_auto_shot.js [输出目录]
 */
const path = require('path');
const fs = require('fs');

const automator = require('miniprogram-automator');

const WS = process.env.MP_WS || 'ws://127.0.0.1:9420';
const OUTDIR = process.argv[2] || 'E:/WorkBuddy/jianpan-ghpages/promo/_shots';

const TABS = [
  ['market', '/pages/market/market'],
  ['holdings', '/pages/holdings/holdings'],
  ['trade', '/pages/trade/trade'],
  ['board', '/pages/board/board'],
  ['me', '/pages/me/me'],
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  if (!fs.existsSync(OUTDIR)) fs.mkdirSync(OUTDIR, { recursive: true });

  console.log('连接自动化接口 ' + WS + ' …');
  const mp = await automator.connect({ wsEndpoint: WS });
  console.log('已连接 ✅');

  try {
    const info = await mp.systemInfo();
    console.log('机型: %s %s / 窗口 %sx%s',
      info.brand, info.model, info.windowWidth, info.windowHeight);
  } catch (e) {
    console.log('systemInfo 失败: ' + e.message);
  }

  const results = [];

  for (const [name, url] of TABS) {
    let line = { name, url };
    try {
      await mp.switchTab(url);
      await sleep(1600);
      const page = await mp.currentPage();
      line.path = page && page.path;

      let data = {};
      try {
        data = await page.data();
      } catch (e) {
        line.dataErr = e.message;
      }
      line.dataKeys = Object.keys(data || {});
      // 抓几个关键字段看有没有真实数据
      const probe = {};
      for (const k of ['state', 'coins', 'todayIntake', 'todayBurn', 'items', 'cards',
        'rows', 'list', 'summary', 'account', 'rating', 'gap', 'trend', 'recent']) {
        if (data && data[k] !== undefined) {
          const v = data[k];
          probe[k] = (v && typeof v === 'object')
            ? (Array.isArray(v) ? ('Array(' + v.length + ')') : ('Object{' + Object.keys(v).slice(0, 8).join(',') + '}'))
            : v;
        }
      }
      line.probe = probe;

      const out = path.join(OUTDIR, name + '.png').replace(/\\/g, '/');
      try {
        const r = await mp.screenshot({ path: out });
        line.shot = fs.existsSync(out) ? (fs.statSync(out).size + ' 字节') : ('未落盘 r=' + r);
      } catch (e) {
        line.shotErr = e.message;
      }
    } catch (e) {
      line.err = e.message;
    }
    results.push(line);
    console.log('---- ' + name + ' ----');
    console.log(JSON.stringify(line, null, 2));
  }

  // 截图文字（OCR 前先看有没有内容）—— 顺便看看首页 DOM 结构
  try {
    await mp.switchTab('/pages/market/market');
    await sleep(1200);
    const page = await mp.currentPage();
    const html = await mp.evaluate(function () {
      return document.body.innerText.slice(0, 1200);
    });
    console.log('==== 首屏 innerText（前 1200 字） ====');
    console.log(html);
  } catch (e) {
    console.log('取 innerText 失败: ' + e.message);
  }

  await mp.disconnect();
  console.log('\nDONE 截图目录: ' + OUTDIR);
  console.log('RESULT=' + (results.every((r) => r.shot) ? 'OK 五页均截图成功' : 'PARTIAL 有页面未截图'));
  process.exit(0);
})().catch((e) => {
  console.error('FAILED: ' + e.message);
  if (e.stack) console.error(e.stack.split('\n').slice(0, 6).join('\n'));
  process.exit(1);
});
