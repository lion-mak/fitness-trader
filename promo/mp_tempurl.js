/**
 * mp_tempurl.js —— 在模拟器里用 wx.cloud.getTempFileURL 验证云文件真实可读。
 *
 * 用途：证明「上传上去的 fileID 指向的对象真实存在、且是完整图片」。
 *   getTempFileURL 返回带签名的临时链接（2 小时有效）⇒ 拿回本地 curl 一次，
 *   比对字节数与源图，就能把「传上去了」这句话变成「字节级一致」。
 *
 * 用法：node mp_tempurl.js '<fileID>' '<fileID>' ...
 * 输出：TEMP_URLS=[{fileID,tempFileURL,status,errMsg}]
 */
const automator = require('miniprogram-automator');

const LIST = process.argv.slice(2);
const WS = process.env.MP_WS || 'ws://127.0.0.1:9420';

(async () => {
  const mp = await automator.connect({ wsEndpoint: WS, timeout: 300000 });
  await new Promise((r) => setTimeout(r, 1200));

  const res = await mp.evaluate(function (fileList) {
    return new Promise(function (done) {
      wx.cloud.getTempFileURL({
        fileList: fileList,
        success: function (r) {
          done((r.fileList || []).map(function (x) {
            return { fileID: x.fileID, status: x.status, tempFileURL: x.tempFileURL || '', errMsg: x.errMsg || 'ok' };
          }));
        },
        fail: function (e) { done({ fail: (e && e.errMsg) || String(e) }); },
      });
    });
  }, LIST);

  console.log('TEMP_URLS=' + JSON.stringify(res));
  await mp.disconnect();
  process.exit(0);
})().catch((e) => {
  console.error('FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
