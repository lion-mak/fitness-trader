#!/usr/bin/env node
/* 段位卡批量上传到云存储 → 回填 miniprogram/lib/rank_assets.js 真实 fileID
 *
 * A 路线（云存储远程图）：卡面不进主包、用 PWA 836KB 源图保画质。
 * 小程序端 me.js 的 _railCards() 读 rank_assets.js 的 fileID 渲染；本脚本把
 * PWA assets/ranks/*.webp 传到云存储、拿回真实 fileID、写回 manifest。
 * 占位期 manifest 是 cloud://...__PLACEHOLDER__/ranks/xxx.webp，真机加载失败自动回退本地图。
 *
 * ⛔ 正确工具（2026-09-28 修正）：用 @cloudbase/manager-node 的 storage.uploadFile，
 *   它直接操作小程序 `cloud://` 读的 **TCB 云存储**桶。
 *   ⚠️ 之前的 @wxcloud/cli 是「微信云托管 CloudRun」体系，与 TCB 存储是两码事（login 成功但
 *      env:list 返回空、DescribeEnvs 403），传不进小程序能读的地方 —— 已弃用，别再撞。
 *
 * 凭证（环境调用密钥，非交互，走环境变量，绝不写死进脚本/仓库）：
 *   ❌ 不是之前那把没用的「CLI 密钥」（设置→权限设置→CLI 密钥，那是 CloudRun 的）
 *   ✅ 是另一对：云开发控制台(cloud.weixin.qq.com 或 console.cloud.tencent.com/tcb)
 *      → 环境 `cloud1-d1gkkvpez0d48660a` → **设置 → 环境设置 → 环境信息**
 *      → 复制 **Secret ID / Secret Key**（环境调用密钥，只显示一次；看不到就点「重置」生成新的）
 *   设置：
 *      set TCB_SECRET_ID=<环境 Secret ID>
 *      set TCB_SECRET_KEY=<环境 Secret Key>
 *
 * 依赖：@cloudbase/manager-node 装到隔离 node workspace（⚠️ 在 C 盘）：
 *    cd C:\Users\Administrator\.workbuddy\binaries\node\workspace && npm i @cloudbase/manager-node
 *
 * 用法（默认全量传 10 张；顺序从现有 manifest 读取，绝不手抄，避免错位）：
 *    set TCB_SECRET_ID=xxxx & set TCB_SECRET_KEY=yyyy & node promo/mp_upload_assets.js
 *
 * 注：上传必须真连腾讯云，跑时放开沙箱网络（dangerouslyDisableSandbox）。
 */
'use strict';
const M = require('C:/Users/Administrator/.workbuddy/binaries/node/workspace/node_modules/@cloudbase/manager-node');
const fs = require('fs');
const path = require('path');

const ENV = 'cloud1-d1gkkvpez0d48660a';
const SRC = 'E:/WorkBuddy/jianpan-ghpages/assets/ranks';
const MANIFEST = path.resolve(__dirname, '../miniprogram/lib/rank_assets.js');
const HEADER = `/* 段位卡云存储 fileID 清单 —— 顺序与 calc.RANKS / RANK_CARDS 严格一致（index i ⇄ RANKS[i]）。

 * A 路线（云存储远程图）：
 *   · 卡面不再打包进主包（省 ~454KB，且改用 PWA assets/ranks 的 836KB 源图保画质）。
 *   · 本文件由 promo/mp_upload_assets.js 上传 PWA 源图到云存储后自动生成、回填真实 fileID。
 *   · 真机加载 fileID 直渲；云不可达时 me.js onRailImgError 只记日志（2026-09-29 起
 *     ⛔不再回退本地 —— miniprogram/images/ranks/ 的 10 张 webp 已从主包删除）。
 * ⚠️ 顺序绝不能错：错位会让卡面角色与段位名对不上（me.wxml 注释点名过此坑）。
 */`;

function main() {
  const secretId = process.env.TCB_SECRET_ID;
  const secretKey = process.env.TCB_SECRET_KEY;
  if (!secretId || !secretKey) {
    console.error('[upload] 缺 TCB_SECRET_ID / TCB_SECRET_KEY');
    console.error('  去 云开发控制台 → 环境 cloud1-d1gkkvpez0d48660a → 设置 → 环境设置 → 环境信息');
    console.error('  复制 Secret ID / Secret Key（环境调用密钥，只显示一次；没有就点「重置」），再：');
    console.error('  set TCB_SECRET_ID=xxxx & set TCB_SECRET_KEY=yyyy & node promo/mp_upload_assets.js');
    process.exit(2);
  }

  // 顺序从现有 manifest 读取（占位符里含文件名），绝不手抄，避免错位
  const cur = require(MANIFEST);
  if (!Array.isArray(cur) || cur.length === 0) { console.error('[upload] manifest 读不到顺序数组'); process.exit(3); }
  const NAMES = cur.map((s) => String(s).split('/').pop());
  console.log('[read] manifest 顺序:', NAMES.join(','));

  const cloud = new M({ secretId, secretKey, envId: ENV });
  const out = [];

  (async () => {
    for (const name of NAMES) {
      const localPath = path.join(SRC, name);
      const cloudPath = 'ranks/' + name;
      if (!fs.existsSync(localPath)) { console.error('[skip] 本地源图缺失:', localPath); out.push('__MISSING__'); continue; }
      console.log('[upload]', name, '→', cloudPath);
      const res = await cloud.storage.uploadFile({ localPath, cloudPath });
      const fileId = res && (res.fileId || res.fileID) ? (res.fileId || res.fileID) : res;
      console.log('   fileId =', fileId);
      out.push(fileId);
    }
    const body = 'module.exports = [\n' + out.map((f) => "  '" + f + "',").join('\n') + '\n];\n';
    fs.writeFileSync(MANIFEST, HEADER + '\n' + body);
    console.log('[done] 已回填', out.length, '个 fileID 到', path.basename(MANIFEST));
    console.log('  缺失:', out.filter((f) => f === '__MISSING__').length, '张');
    console.log('  下一步：跑 me_test + mp_wxss_check + _run_all_asserts，开发者工具看卡面直渲');
  })().catch((e) => { console.error('[upload] 失败:', e && e.message); process.exit(1); });
}

main();
