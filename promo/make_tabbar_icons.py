# -*- coding: utf-8 -*-
"""
make_tabbar_icons.py —— 生成微信小程序 tabBar 图标（PNG）。

为什么必须生成而不是复用：
  微信 tabBar 只认本地 PNG，且选中/未选中是两张独立的图 —— 不支持 SVG，
  也不支持 PWA 用的 stroke="currentColor"（那是在浏览器里靠 CSS color 继承的）。
  所以必须把 5 个图标 × 2 态烘焙成 10 张位图。

做法：
  从 index.html 的 .tabbar 块里正则提取 <svg> 定义（不手抄坐标 ——
  PWA 改图标后重跑本脚本即可同步），拼成一张 HTML，用 Chromium 渲染后
  逐元素截图（omit_background=True 保证透明底）。

  PWA 的 5 个 tab 图标：
    · 前 4 个是 stroke="currentColor" 线稿 → 未选中 #5a6478 / 选中 #ff3b47
    · 交易图标是彩色手绘（哑铃+鸡腿），颜色写死、不随选中态变化 → 两态同一张
      （与 PWA 一致：CSS 只改 color，而它不含 currentColor）

规格：81×81 px（微信推荐），图形 54×54 居中，四边留 13px。
用法：python promo/make_tabbar_icons.py
输出：E:\\WeChatProjects\\jianpan\\miniprogram\\images\\tabbar\\*.png
"""
import io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "index.html")
OUTDIR = r"E:\WeChatProjects\jianpan\miniprogram\images\tabbar"

CANVAS = 81      # 输出画布边长
ART = 54         # 图形边长
COL_OFF = "#5a6478"   # 未选中：PWA --muted
COL_ON = "#ff3b47"    # 选中：PWA --red

html_src = io.open(SRC, encoding="utf-8", newline="").read()

# 定位 .tabbar 块
i = html_src.find('<div class="tabbar"')
j = html_src.find("</div>\n\n</div>", i)
if i < 0 or j < 0:
    sys.exit("找不到 .tabbar 块")
block = html_src[i:j]

# 每个 tab：data-tab="xxx" ... <svg ...>...</svg>
tabs = []
for m in re.finditer(r'data-tab="([a-z]+)"', block):
    name = m.group(1)
    sv = block.find("<svg", m.end())
    se = block.find("</svg>", sv)
    if sv < 0 or se < 0:
        continue
    svg = block[sv:se + 6]
    tabs.append((name, svg))

if len(tabs) != 5:
    sys.exit("预期 5 个 tab，实际 %d 个：%s" % (len(tabs), [t[0] for t in tabs]))

# 统一把 svg 的 width/height 换成 ART
def resize(svg):
    svg = re.sub(r'width="\d+"', 'width="%d"' % ART, svg, count=1)
    svg = re.sub(r'height="\d+"', 'height="%d"' % ART, svg, count=1)
    return svg

ART_DEFS = {n: resize(s) for n, s in tabs}

rows = []
for name, _ in tabs:
    rows.append((name + "-off", ART_DEFS[name], COL_OFF))
    rows.append((name + "-on", ART_DEFS[name], COL_ON))

# 交易图标是彩色（不含 currentColor），两态渲染结果完全相同。
# 小程序要求两个文件都存在，所以照常输出两张同内容的图 —— 但明确标注，
# 免得以后有人以为"选中态没生效"是 bug。
TRADE_COLORED = "currentColor" not in ART_DEFS.get("trade", "")

cell = ('<div class="cell" id="%s" style="color:%s">%s</div>')
body = "\n".join(cell % (n, c, s) for n, s, c in rows)

html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html,body { margin:0; padding:0; background:transparent; }
  .cell { width:%(canvas)dpx; height:%(canvas)dpx; display:flex; align-items:center;
          justify-content:center; background:transparent; }
</style></head><body>
%(body)s
</body></html>""" % {"canvas": CANVAS, "body": body}

if not os.path.isdir(OUTDIR):
    os.makedirs(OUTDIR)

from playwright.sync_api import sync_playwright

# 本机没有 playwright 自带的 chromium（未执行 playwright install），
# 但系统装了 Edge（Chromium 内核）—— 直接借用，效果一致且省 150MB 下载。
LAUNCH = [
    {"channel": "msedge"},
    {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"},
]


def launch(pw):
    last = None
    for kw in LAUNCH:
        try:
            return pw.chromium.launch(**kw)
        except Exception as e:
            last = e
    raise SystemExit(
        "找不到可用浏览器内核。请任选其一：\n"
        "  · 运行 python -m playwright install chromium（下载约 150MB）\n"
        "  · 或安装 Edge\n最后错误：%s" % last)


written = []
with sync_playwright() as p:
    b = launch(p)
    page = b.new_page(viewport={"width": CANVAS + 40, "height": CANVAS * len(rows) + 40},
                      device_scale_factor=1)
    page.set_content(html)
    for n, _, _ in rows:
        path = os.path.join(OUTDIR, n + ".png")
        page.locator("#" + n).screenshot(path=path, omit_background=True)
        written.append((n + ".png", os.path.getsize(path)))
    b.close()

print("tabBar 图标已生成 → %s" % OUTDIR)
for n, sz in written:
    print("  %-16s %6d bytes" % (n, sz))
if TRADE_COLORED:
    print()
    print("注：trade-on.png 与 trade-off.png 内容相同 —— 交易图标是彩色手绘")
    print("     （不含 currentColor），PWA 里选中态也不变色，保持一致。")
