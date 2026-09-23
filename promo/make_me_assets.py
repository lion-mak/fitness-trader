# -*- coding: utf-8 -*-
"""
make_me_assets.py —— 「我的」簇所需的位图资产（小程序视图层不解析 SVG，图标必须烘焙成 PNG）。

产出 4 张到 E:\\WeChatProjects\\jianpan\\miniprogram\\images\\me\\：
  · menu-ach.png    成就殿堂图标（PWA: #ff3b47 圆+缎带，18×18）
  · menu-gacha.png  涨停抽卡图标（PWA: #ffb800 卡片，18×18）
  · menu-body.png   身体档案图标（PWA: #5ac8fa 时钟，18×18）
  · avatar-ph.png   头像占位（PWA avatarHTML() 的灰色人形，80×80）

⚠️ 三个菜单图标直接**从 index.html 正则提取对应 <svg>**（不手抄坐标）——
   PWA 改图标后重跑本脚本即可同步。提取锚点是各自的 onclick（showAchievements /
   showGacha / scrollToProfile），所以位置变了也能找到。
   渲染用 device_scale_factor=3 ⇒ 18px 图标得到 54px PNG（3 倍图）。

另有身体人形图重采样（不是渲染，是缩放）：
  assets/body_{male,female}.png (400×600, 343.7/111.6 KB) → images/me/body_*.png
  PWA 显示高 228px，故按 2 倍图 = 高 456px 重采样。原图直接进主包会多占 455 KB。

用法（必须用 venv，playwright 只装在 venv 里）：
  …/python/envs/default/Scripts/python.exe promo/make_me_assets.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "index.html")
ASSETS = os.path.join(ROOT, "assets")
OUTDIR = r"E:\WeChatProjects\jianpan\miniprogram\images\me"
BODY_H = 456          # 身体人形输出高度（PWA 显示 228px 的 2 倍图）

html_src = io.open(SRC, encoding="utf-8", newline="").read()


def svg_after_onclick(fn, label):
    """取 onclick="fn(...)" 之后出现的第一个 <svg>…</svg>。"""
    m = re.search(r'onclick="' + re.escape(fn) + r'\(\)"', html_src)
    if not m:
        sys.exit("找不到 onclick=%s()（%s）" % (fn, label))
    i = html_src.find("<svg", m.end())
    j = html_src.find("</svg>", i)
    if i < 0 or j < 0:
        sys.exit("onclick=%s() 之后找不到 <svg>（%s）" % (fn, label))
    return html_src[i:j + 6]


# 头像占位：avatarHTML() 里 width/height=80 的那支（openProfileEdit 里同款）
m = re.search(r"<svg viewBox=\"0 0 24 24\" width=\"80\" height=\"80\".*?</svg>", html_src)
if not m:
    sys.exit("找不到 avatarHTML() 的占位 SVG")
AVATAR_SVG = m.group(0)

ICONS = [
    ("menu-ach", svg_after_onclick("showAchievements", "成就殿堂菜单图标"), 18),
    ("menu-gacha", svg_after_onclick("showGacha", "涨停抽卡菜单图标"), 18),
    ("menu-body", svg_after_onclick("scrollToProfile", "身体档案菜单图标"), 18),
    ("avatar-ph", AVATAR_SVG, 80),
]

if not os.path.isdir(OUTDIR):
    os.makedirs(OUTDIR)

# ---------- 1) 身体人形图：重采样 ----------
try:
    from PIL import Image
except ImportError:
    sys.exit("需要 Pillow（用 venv 的解释器跑）")

body_out = []
for g in ("male", "female"):
    src = os.path.join(ASSETS, "body_%s.png" % g)
    if not os.path.exists(src):
        sys.exit("缺源图：" + src)
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    nw = max(1, round(w * BODY_H / h))
    im2 = im.resize((nw, BODY_H), Image.LANCZOS)
    dst = os.path.join(OUTDIR, "body_%s.png" % g)
    im2.save(dst, "PNG", optimize=True)
    body_out.append(("body_%s.png" % g, os.path.getsize(src), os.path.getsize(dst), "%dx%d→%dx%d" % (w, h, nw, BODY_H)))

# ---------- 2) 图标：SVG → PNG（playwright + Edge） ----------
cell = '<div class="cell" id="%s" style="width:%dpx;height:%dpx;display:flex;align-items:center;justify-content:center;">%s</div>'
body_html = "\n".join(cell % (n, sz, sz, s) for n, s, sz in ICONS)
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


icon_out = []
with sync_playwright() as p:
    b = launch(p)
    page = b.new_page(viewport={"width": 120, "height": 120 * len(ICONS) + 20},
                      device_scale_factor=3)
    page.set_content(html)
    for n, _, _ in ICONS:
        dst = os.path.join(OUTDIR, n + ".png")
        page.locator("#" + n).screenshot(path=dst, omit_background=True)
        icon_out.append((n + ".png", os.path.getsize(dst)))
    b.close()

print("「我的」簇资产已生成 → %s" % OUTDIR)
print("  图标（SVG→PNG，3 倍图）")
for n, sz in icon_out:
    print("    %-16s %7.1f KB" % (n, sz / 1024.0))
print("  身体人形（重采样到 2 倍显示高）")
for n, a, b_, dim in body_out:
    print("    %-16s %7.1f → %6.1f KB   %s" % (n, a / 1024.0, b_ / 1024.0, dim))
print("  合计 %.1f KB（原样搬入需 %.1f KB，省 %.1f KB）" % (
    sum(s for _, s in icon_out) / 1024.0 + sum(b for _, _, b, _ in body_out) / 1024.0,
    sum(a for _, a, _, _ in body_out) / 1024.0,
    (sum(a for _, a, _, _ in body_out) - sum(b for _, _, b, _ in body_out)) / 1024.0))
