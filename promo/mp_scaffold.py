# -*- coding: utf-8 -*-
"""
mp_scaffold.py —— 生成尚未迁移的页面骨架（占位）。

为什么用脚本而不是手写：5 个 tab 页骨架结构完全同构，手写就是复制粘贴 16 个文件；
且这些文件是**临时**的 —— 每页真正迁完时会被替换掉。脚本生成便于统一改版式、
也便于最后一次性清理。

生成：
  miniprogram/pages/<name>/<name>.{json,wxml,wxss,js}   × 4 页

已迁移的 market 页不在本脚本管辖内。

⚠️ 2026-09-22 改版：**不再生成 styles/scaffold.wxss，各页也不再 @import**。
   原因见 mp_build.py 里 ADAPT 那段注释（开发者工具的文件索引滞后 ⇒ 被 import 的
   文件进不了 WXSS 编译单元 ⇒ 整包编译失败、白屏）。共享样式一律写 app.wxss，
   骨架临时样式内联到各页 wxss（本页迁完时随本页一起删，反而更好清理）。
"""
import io, os

MINI = r"E:\WeChatProjects\jianpan\miniprogram"
HERE = os.path.dirname(os.path.abspath(__file__))

PAGES = [
    {
        "dir": "holdings", "name": "持仓", "sub": "账户总览 · 缺口评级",
        "mods": [
            ("账户总览 Hero", "止盈进度主数字 · 三格账本", True),
            ("净热量趋势", "canvas 2d · 7日/月度/年度/全部", True),
            ("每日缺口评级", "档位刻度条 · 三格折算", True),
            ("身体成分趋势", "体脂/BMI 双轴 · 分区色带", False),
            ("持仓评级九宫格", "hero 化 · 30px 大字", False),
        ],
    },
    {
        "dir": "trade", "name": "交易", "sub": "做多 · 饮食 / 做空 · 运动",
        "mods": [
            ("今日流水", "按时间列当日成交", False),
            ("食物录入", "2052 条库 · 搜索/分类/常吃", False),
            ("运动录入", "MET 法算耗能 · 密度/时长", False),
            ("自定义食物/运动", "用户自建并入库", False),
        ],
    },
    {
        "dir": "board", "name": "龙虎榜", "sub": "热菜榜 · 劳模榜 · 复盘",
        "mods": [
            ("热菜榜", "按食物热量排名 · 三档配色", False),
            ("劳模榜 / 暴汗榜", "运动时长 / 消耗排名", False),
            ("大胃王日 / 燃脂日", "月榜专属", False),
            ("复盘周报 / 月报", "分享卡式 · 口径对齐缺口评级", False),
        ],
    },
    {
        "dir": "me", "name": "我的", "sub": "档案 · 等级 · 图鉴",
        "mods": [
            ("个人档案", "性别/年龄/身高/体重/体脂", False),
            ("等级与健康币", "8 段位 · 记录得币", False),
            ("成就体系", "分类进度 · 解锁记录", False),
            ("交易员图鉴抽卡", "15 卡 · 概率 70/25/5", False),
            ("数据导入导出", "跨端迁移（PWA → 小程序）", False),
            ("云同步", "云开发开通后接", False),
        ],
    },
]

WXSS_TPL = u"""/* %(name)s页（骨架）—— 只写本页增量。
   ⚠️ 不要写 @import：跨文件依赖在本工程是脆弱点（开发者工具的文件索引滞后会让
   被 import 的文件进不了 WXSS 编译单元 ⇒ 整包编译失败 ⇒ 白屏，2026-09-22 事故）。
   全局适配在 app.wxss，本页要用的骨架样式直接内联在下面。 */
.page { padding-bottom: 0; }

/* ---- 搬迁进度卡（临时，本页迁完即删）---- */
.mod-row {
  display:flex; align-items:center; gap:8px; padding:8px 0;
  font-size:12px; border-top:1px solid var(--border);
}
.mod-row:first-child { border-top:none; }
.mod-dot { font-size:10px; color:var(--muted); flex:none; }
.mod-dot.ok { color:var(--green); }
.mod-name { color:var(--muted2); flex:none; }
.mod-name.ok { color:#fff; }
.mod-note { margin-left:auto; color:var(--muted); font-size:11px; text-align:right; }

.scaf-hint {
  margin:10px 14px 0; padding:10px 12px; border-radius:10px;
  background:rgba(90,200,250,.06); border:1px solid rgba(90,200,250,.18);
  color:var(--muted2); font-size:11px; line-height:1.7;
}
.scaf-hint b { color:var(--blue); font-weight:600; }
"""

JSON_TPL = u"""{
  "usingComponents": {},
  "navigationStyle": "custom",
  "enablePullDownRefresh": false,
  "backgroundColor": "#0a0e1a"
}
"""

WXML_TPL = u"""<!-- %(name)s页（骨架）—— 功能模块迁移中，本页会逐块替换成真实现。
     结构参考 PWA index.html 的 #page-%(id)s。 -->
<view class="page active">

  <view class="pheader" style="padding-top:{{headPadTop}}px;">
    <view class="logo">
      <view class="lt">
        <text class="id">%(name)s</text>
        <text class="s">%(sub)s</text>
      </view>
    </view>
  </view>

  <view class="card">
    <view class="card-title">
      <text class="t">%(name)s · 搬迁进度</text>
      <text class="m">0 / {{modules.length}}</text>
    </view>
    <view class="mod-row" wx:for="{{modules}}" wx:key="name">
      <text class="mod-dot {{item.done?'ok':''}}">{{item.done ? '●' : '○'}}</text>
      <text class="mod-name {{item.done?'ok':''}}">{{item.name}}</text>
      <text class="mod-note">{{item.note}}</text>
    </view>
  </view>

  <view class="scaf-hint">
    本页功能正在迁移。当前可用的完整页面：<b>行情</b>（体重 K 线已用 canvas 2d 复刻）。
  </view>

</view>
"""

JS_TPL = u"""/* %(name)s页（骨架）—— 模块迁移中。
   数据层已就绪：store.get() 拿存档，calc.js 提供全部计算（与 PWA 同口径）。 */
'use strict';

const store = require('../../lib/store.js');
const calc = require('../../lib/calc.js');

const MODULES = %(mods)s;

Page({
  data: {
    headPadTop: 30,
    modules: MODULES,
  },

  onLoad() {
    const sbh = (getApp().globalData && getApp().globalData.statusBarHeight) || 20;
    this.setData({ headPadTop: sbh + 10 });
  },
});
"""

def w(path, content):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    io.open(path, "w", encoding="utf-8", newline="").write(content)
    return len(content)


made = []

for p in PAGES:
    base = os.path.join(MINI, "pages", p["dir"])
    mods_js = u"[\n" + u"".join(
        u"  { name: '%s', note: '%s', done: %s },\n" % (n, note, "true" if done else "false")
        for n, note, done in p["mods"]) + u"]"
    ctx = {"name": p["name"], "sub": p["sub"], "id": p["dir"], "mods": mods_js}
    for ext, tpl in (("json", JSON_TPL), ("wxml", WXML_TPL), ("wxss", WXSS_TPL), ("js", JS_TPL)):
        fp = os.path.join(base, p["dir"] + "." + ext)
        made.append((p["dir"] + "/" + p["dir"] + "." + ext, w(fp, tpl % ctx)))

print("页面骨架已生成：")
for name, size in made:
    print("  %-42s %6d bytes" % (name, size))
