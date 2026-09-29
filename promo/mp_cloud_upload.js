/**
 * mp_cloud_upload.js —— 把主包内的段位卡图，经**模拟器里的客户端云 API** 直传云存储。
 *
 * 为什么走这条路（2026-09-28 结论，三条死路都已排除）：
 *   ⛔ @wxcloud/cli          —— 是「微信云托管 CloudRun」体系，env:list 返回 0 个环境、
 *                               storage:upload 内部 DescribeEnvs 直接 403，操作不到 TCB 桶。
 *   ⛔ @cloudbase/node-sdk   —— 要 SecretId/SecretKey，而微信云开发控制台**没有**这对密钥的入口
 *                               （那对属腾讯云 CAM，是另一套账号体系）。
 *   ⛔ 云函数 uploadRankAssets —— 代码没问题，但控制台 scf/Invoke 反复报
 *                               `[UPSTREAM] Upstream error (ret=-3) system error`，请求进不到函数体。
 *   ✅ 客户端 wx.cloud.uploadFile —— 小程序端云 API 用 **AppID + 当前用户身份** 鉴权，
 *                               天然有写权限：**零密钥、零云函数、零人工操作**。
 *                               而图本来就已经在主包里（images/ranks/*.webp），
 *                               直接从包内读出来传即可 —— 不需要任何外部网络。
 *
 * 产物：打印 UPLOAD_JSON=[{name,fileID}...]，供回填 miniprogram/lib/rank_assets.js。
 *
 * 用法（需 IDE 开着、项目为 E:\WeChatProjects\jianpan）：
 *   NODE_PATH=<workspace>/node_modules node promo/mp_cloud_upload.js
 *   （端口 arm 由 mp_ws.ensure_port() 负责，见 mp_cloud_upload.py）
 */
const fs = require('fs');
const path = require('path');
const automator = require('miniprogram-automator');

const WS = process.env.MP_WS || 'ws://127.0.0.1:9420';
const SRC_DIR = path.resolve(__dirname, '..', 'assets', 'ranks');
const NAMES = fs.readdirSync(SRC_DIR).filter((f) => f.endsWith('.webp')).sort();
const CLOUD_DIR = 'ranks';

(async () => {
  console.log('[names] ' + NAMES.length + ' 张：' + NAMES.join(','));

  const mp = await automator.connect({ wsEndpoint: WS });
  await new Promise((r) => setTimeout(r, 1500));

  /* ---------------------------------------------------------------
   * 一、能力探测：只拿第 1 张试，三种「从哪里取文件」的路径依次试。
   *    A. 代码包内路径（带前导斜杠）——最省事，直接传
   *    B. 代码包内路径（不带前导斜杠）
   *    C. readFileSync 读出 ArrayBuffer → 写到 USER_DATA_PATH → 传本地临时文件
   *    （C 是兜底：若 uploadFile 不接受包内路径，就只能先落一份到用户目录）
   * 返回全部信息，让「哪条通」这件事有凭据，不靠猜。
   * --------------------------------------------------------------- */
  const probe = await mp.evaluate(function (probeName, cloudPath) {
    var out = { hasCloud: !!wx.cloud, hasUpload: !!(wx.cloud && wx.cloud.uploadFile), tries: [] };
    if (!out.hasUpload) { return Promise.resolve(out); }

    function up(filePath) {
      return new Promise(function (done) {
        wx.cloud.uploadFile({
          cloudPath: cloudPath,
          filePath: filePath,
          success: function (r) {
            done({ ok: true, fileID: r.fileID || (r.fileIDs && r.fileIDs[0]) || '' });
          },
          fail: function (e) { done({ ok: false, err: (e && e.errMsg) || String(e) }); },
        });
      });
    }

    var cands = ['/images/ranks/' + probeName, 'images/ranks/' + probeName];
    var chain = Promise.resolve();
    cands.forEach(function (p) {
      chain = chain.then(function () {
        return up(p).then(function (r) { out.tries.push({ via: 'uploadFile', path: p, r: r }); });
      });
    });
    // 兜底 C：读包内文件 → 写用户目录 → 传
    chain = chain.then(function () {
      var fs2 = wx.getFileSystemManager();
      var readErr = null, bytes = 0, dest = '';
      for (var i = 0; i < cands.length; i++) {
        try {
          var buf = fs2.readFileSync(cands[i]);
          dest = wx.env.USER_DATA_PATH + '/' + probeName;
          fs2.writeFileSync(dest, buf);
          bytes = buf.byteLength;
          readErr = null;
          break;
        } catch (e) { readErr = (e && e.errMsg) || String(e); }
      }
      if (!dest) { out.tries.push({ via: 'copy', ok: false, err: readErr }); return; }
      return up(dest).then(function (r) { out.tries.push({ via: 'copy', path: dest, bytes: bytes, r: r }); });
    });
    return chain.then(function () { return out; });
  }, NAMES[0], CLOUD_DIR + '/' + NAMES[0]);

  console.log('PROBE=' + JSON.stringify(probe));

  // 选第一条成功的路径
  const ok = (probe.tries || []).find((t) => t.r && t.r.ok && t.r.fileID);
  if (!ok) {
    console.log('RESULT=NO_WORKING_PATH');
    await mp.disconnect();
    process.exit(2);
  }
  console.log('[probe-ok] via=' + ok.via + ' path=' + ok.path);

  /* ---------------------------------------------------------------
   * 二、全量：用探测出来的那条路（同一模式）传完剩下 9 张。
   *    串行 —— 段位卡只有 10 张、每张 ~80KB，串行换来的是「哪张失败」可定位。
   * --------------------------------------------------------------- */
  const rest = NAMES.slice(1);
  const list = await mp.evaluate(function (names, cloudDir, mode) {
    function up(filePath, cloudPath) {
      return new Promise(function (done) {
        wx.cloud.uploadFile({
          cloudPath: cloudPath, filePath: filePath,
          success: function (r) { done({ ok: true, fileID: r.fileID || (r.fileIDs && r.fileIDs[0]) || '' }); },
          fail: function (e) { done({ ok: false, err: (e && e.errMsg) || String(e) }); },
        });
      });
    }
    var res = [];
    var chain = Promise.resolve();
    names.forEach(function (name) {
      chain = chain.then(function () {
        var filePath = mode === 'copy' ? (wx.env.USER_DATA_PATH + '/' + name)
          : (mode === 'pkg-noslash' ? ('images/ranks/' + name) : ('/images/ranks/' + name));
        if (mode === 'copy') {
          try {
            var fsm = wx.getFileSystemManager();
            fsm.writeFileSync(filePath, fsm.readFileSync('images/ranks/' + name));
          } catch (e) {
            res.push({ name: name, ok: false, err: (e && e.errMsg) || String(e) });
            return;
          }
        }
        return up(filePath, cloudDir + '/' + name).then(function (r) {
          res.push(r.ok ? { name: name, ok: true, fileID: r.fileID } : { name: name, ok: false, err: r.err });
        });
      });
    });
    return chain.then(function () { return res; });
  }, rest, CLOUD_DIR, ok.via === 'copy' ? 'copy' : (ok.path.indexOf('/') === 0 ? 'pkg' : 'pkg-noslash'));

  const all = [{ name: NAMES[0], ok: true, fileID: ok.r.fileID }].concat(list);
  const good = all.filter((x) => x.ok);
  console.log('UPLOAD_JSON=' + JSON.stringify(all));
  console.log('SUMMARY ok=' + good.length + '/' + all.length);

  await mp.disconnect();
  process.exit(good.length === all.length ? 0 : 3);
})().catch((e) => {
  console.error('FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
