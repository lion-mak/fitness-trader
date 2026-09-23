# -*- coding: utf-8 -*-
"""
make_ach_assets.py —— 成就殿堂 / 抽卡图鉴所需的图标位图资产。

为什么必须烘焙成 PNG：**小程序视图层不解析 SVG**（`image` 塞 `data:image/svg+xml`
在 Android 不渲染），而 PWA 的成就图标全部是 `badgeIcon(type)` 现拼的 `<svg>`。

产出 → E:\\WeChatProjects\\jianpan\\miniprogram\\images\\ach\\ach-<type>.png
  26px 图标的 3 倍图 = 78×78（`.badge .b` 里的图标在 PWA 是 26×26）
  ⚠️ `.ach-cat-ic` 的图标 PWA 只给 20×20 —— 同一张 78px 图缩到 20px 相当于 3.9 倍图，
     仍然够清晰，所以**不生成第二套**，避免两份资产日后不同步。

⚠️ 图标 path **从 index.html 的 badgeIcon() 正则提取**（不手抄坐标）——
   PWA 改图标后重跑本脚本即可同步；位置变了也能找到（锚点是函数名 + `const s = {`）。
   提取的是函数里的**全部**键（含当前没被任何成就引用的），
   这样以后新增成就图标不用回来改脚本。

用法（必须用 venv，playwright 只装在 venv 里）：
  …/python/envs/default/Scripts/python.exe promo/make_ach_assets.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "index.html")
OUTDIR = r"E:\WeChatProjects\jianpan\miniprogram\images\ach"
ICON_PX = 26           # 渲染基准尺寸（与 PWA `.badge .b svg` 一致）
DPR = 3                # ⇒ 输出 78×78

html_src = open(SRC, encoding="utf-8", newline="").read()

# ---------- 1) 从 badgeIcon() 里抠出图标表 ----------
m = re.search(r"function badgeIcon\(type\)\s*\{\s*const s = \{(.*?)\n  \};", html_src, re.S)
if not m:
    sys.exit("找不到 badgeIcon() 的 const s = {...}（函数被改名/重构了？）")
block = m.group(1)
icons = re.findall(r"(\w+):'((?:[^'\\]|\\.)*)'", block)
if len(icons) < 20:
    sys.exit("badgeIcon() 里只解析出 %d 个图标，明显不对" % len(icons))
# 保持源码顺序，便于人工核对
print("从 badgeIcon() 提取到 %d 个图标：%s" % (len(icons), ", ".join(k for k, _ in icons)))

# ---------- 2) 逐个渲染 ----------
cell = ('<div class="cell" id="%s" style="width:%dpx;height:%dpx;'
        'display:flex;align-items:center;justify-content:center;">'
        '<svg width="%d" height="%d" viewBox="0 0 24 24" fill="none">%s</svg></div>')
body_html = "\n".join(
    cell % ("ic-" + k, ICON_PX, ICON_PX, ICON_PX, ICON_PX, svg)
    for k, svg in icons
)
html = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  html,body { margin:0; padding:0; background:transparent; }
</style></head><body>
%s
</body></html>""" % body_html

from playwright.sync_api import sync_playwright   # noqa: E402

LAUNCH = [
    {"channel": "msedge"},
    {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"},
]


def launch(pw):
    last = None
    for kw in LAUNCH:
        try:
            return pw.chromium.launch(**kw)
        except Exception as e:      # noqa: BLE001
            last = e
    raise SystemExit("找不到可用浏览器内核（Edge / 360ChromeX 均失败）：%s" % last)


if not os.path.isdir(OUTDIR):
    os.makedirs(OUTDIR)

out = []
with sync_playwright() as p:
    b = launch(p)
    page = b.new_page(viewport={"width": 120, "height": 120 * len(icons) + 20},
                      device_scale_factor=DPR)
    page.set_content(html)
    for k, _ in icons:
        dst = os.path.join(OUTDIR, "ach-%s.png" % k)
        page.locator("#ic-" + k).screenshot(path=dst, omit_background=True)
        out.append((k, os.path.getsize(dst)))
    b.close()

total = sum(s for _, s in out)
print("成就图标已生成 → %s" % OUTDIR)
for k, s in out:
    print("    %-14s %7.2f KB" % ("ach-%s.png" % k, s / 1024.0))
print("  合计 %d 个 / %.1f KB（主包增量）" % (len(out), total / 1024.0))
