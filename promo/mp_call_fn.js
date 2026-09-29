/**
 * mp_call_fn.js —— 在模拟器里调云函数（客户端 wx.cloud.callFunction）。
 *
 * 为什么要从模拟器调、而不是云开发控制台的「云端测试」：
 *   控制台走的是 scf/Invoke 通道，本环境反复返回
 *   `[UPSTREAM] Upstream error (ret=-3) system error`（请求进不到函数体）；
 *   而 wx.cloud.callFunction 走 TCB 客户端调用通道 —— 两条独立通路。
 *
 * 用法：node mp_call_fn.js <fnName> <start> <count>
 * 输出：FN_RESULT={...}
 */
const automator = require('miniprogram-automator');

const FN = process.argv[2] || 'uploadRankAssets';
const START = Number(process.argv[3] || 0);
const COUNT = Number(process.argv[4] || 0);
const WS = process.env.MP_WS || 'ws://127.0.0.1:9420';

(async () => {
  const mp = await automator.connect({ wsEndpoint: WS, timeout: 300000 });
  await new Promise((r) => setTimeout(r, 1200));

  const t0 = Date.now();
  const res = await mp.evaluate(function (name, start, count) {
    var data = {};
    if (start > 0 || count > 0) { data.start = start; data.count = count || 10; }
    return new Promise(function (done) {
      wx.cloud.callFunction({
        name: name,
        data: data,
        success: function (r) { done({ ok: true, result: r.result }); },
        fail: function (e) {
          done({ ok: false, errMsg: (e && e.errMsg) || String(e), raw: JSON.stringify(e) });
        },
      });
    });
  }, FN, START, COUNT);

  console.log('ELAPSED_MS=' + (Date.now() - t0));
  console.log('FN_RESULT=' + JSON.stringify(res));
  await mp.disconnect();
  process.exit(res && res.ok ? 0 : 4);
})().catch((e) => {
  console.error('FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
