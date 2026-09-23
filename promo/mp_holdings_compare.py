# -*- coding: utf-8 -*-
"""
mp_holdings_compare.py —— 持仓页「PWA 线上版」vs「小程序版」端到端像素比对。

为什么必须做：
    前面几道闸（断言 / 冒烟）只保证"代码不抛错、数字算对"，
    但它们**都是在小程序这一侧自证**。真正要交付的是"和 PWA 长得一样"，
    这句话只能用两端各自真实渲染的结果去量。

关键做法：**同一份存档、同一视口、同一滚动位置**
    A 侧：playwright 打开线上 index.html（file://），localStorage 清空
          ⇒ PWA 走 defaultState()，与小程序当前状态对等（IDE 里也是空存档）。
    B 侧：开发者工具自动化截的 holdings_top.png（同一份 defaultState）。

对齐：两端顶部结构不同 —— 小程序有 43px 状态栏（灵动岛），PWA 在浏览器里
    env(safe-area-inset-top)=0。所以**不能**直接相减，否则整体错位会被误读成
    "排版全错"。这里自动搜索最佳垂直偏移 dy（0~90 设备像素），取平均差最小者，
    并把该 dy 一并打印出来 —— dy 应该≈状态栏高度，若明显偏离说明真错位。

用法：python promo/mp_holdings_compare.py
输出：promo/_holdings_cmp.png（左 PWA / 中 小程序 / 右 差分）
"""
import io
import os
import sys

from playwright.sync_api import sync_playwright
from PIL import Image, ImageChops, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
INDEX = os.path.join(ROOT, "index.html")
SHOTS = os.path.join(HERE, "_shots")

VW, VH = 430, 930      # iPhone 15 Pro Max 逻辑像素（IDE 报 430x930，截图 362x783 = ×0.842）
DPR = 2

# 小程序的状态栏高度（--sbh 54）。PWA 在浏览器里 env(safe-area-inset-top)=0、真机才有值，
# 所以给 .app 补上等高 padding-top 让两端顶部同基准；否则整页会错位 54px，
# 差分图和 dy 都会指向一个并不存在的「排版问题」。
SBH = 0
if "--sbh" in sys.argv:
    SBH = int(sys.argv[sys.argv.index("--sbh") + 1])

# 与小程序侧对应的抓拍点：首屏 / 滚到底（九宫格在页面下方，首屏截不到）
POS = [("top", 0), ("end", 99999)]

# 小程序 windowHeight（原生 tabBar 之外的可视区）。PWA 的 .screen 要锁成同高，
# 否则「滚到底」这一屏两端可见范围不同，差分里会出现一大片纯结构性偏差
# （实测：小程序 850 / PWA 803 —— 平台底栏高度不同，不是排版问题）。
SCREEN_H = 850

LAUNCH = [{"channel": "msedge"},
          {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"}]


def launch_browser(p):
    last = None
    for kw in LAUNCH:
        try:
            return p.chromium.launch(**kw)
        except Exception as e:            # noqa: BLE001
            last = e
    raise SystemExit("无可用浏览器内核：%s" % last)


# ────────────────────────────────────────────────
# A 侧：PWA
# ────────────────────────────────────────────────
pwa = {}
info = {}
with sync_playwright() as p:
    b = launch_browser(p)
    page = b.new_page(viewport={"width": VW, "height": VH}, device_scale_factor=DPR)
    page.goto("file:///" + INDEX.replace("\\", "/"))
    page.wait_for_timeout(900)
    # 清掉 localStorage 再重载 —— 保证走 defaultState()，与小程序空存档对等
    page.evaluate("try{localStorage.clear()}catch(e){}")
    page.reload()
    page.wait_for_timeout(1400)
    page.evaluate("switchTab('holdings')")
    page.wait_for_timeout(1000)
    if SBH:
        # ⚠️ 留白必须注入到 #page-holdings（**滚动内容之内**），不能注入 .app：
        #    小程序的留白写在 .page 上、属于滚动内容 ⇒ 若注到 .app（滚动内容之外），
        #    两端 scrollHeight 会差 sbh，滚到底时整屏错开 54px，
        #    差分图上表现为「越往上错得越多」的假偏移（2026-09-22 实测）。
        page.evaluate("(v) => { document.querySelector('#page-holdings').style.paddingTop = v + 'px'; }", SBH)
    # 锁可视高，与小程序 windowHeight 一致（消除平台底栏高度差带来的结构性偏移）
    page.evaluate("(h) => { const s = document.querySelector('#screen');"
                  " s.style.flex = 'none'; s.style.height = h + 'px'; }", SCREEN_H)
    page.wait_for_timeout(300)

    info["scrollHeight"] = page.evaluate(
        "document.querySelector('#screen').scrollHeight")
    info["clientHeight"] = page.evaluate(
        "document.querySelector('#screen').clientHeight")
    info["pageH"] = page.evaluate("document.querySelector('.app').getBoundingClientRect().height")
    info["tabH"] = page.evaluate("document.querySelector('.tabbar').getBoundingClientRect().height")

    for name, st in POS:
        page.evaluate("document.querySelector('#screen').scrollTop = %d" % st)
        page.wait_for_timeout(520)
        png = page.locator(".app").screenshot()
        pwa[name] = png
        io.open(os.path.join(HERE, "_cmp_pwa_%s.png" % name), "wb").write(png)

    # 关键文本对拍：两端 innerText 逐行比，比像素更能定位"哪个数字/文案不一样"
    txt = page.evaluate("document.querySelector('#page-holdings').innerText")
    io.open(os.path.join(HERE, "_cmp_pwa_text.txt"), "w", encoding="utf-8").write(txt)
    b.close()

print("PWA #screen scrollHeight=%s clientHeight=%s  .app 高=%s  底栏高=%s"
      % (info["scrollHeight"], info["clientHeight"], info["pageH"], info["tabH"]))

# ────────────────────────────────────────────────
# B 侧读取 + 比对
# ────────────────────────────────────────────────
TARGET = (362, 783)


def load_mp(name):
    fp = os.path.join(SHOTS, "holdings_%s.png" % name)
    if not os.path.exists(fp):
        raise SystemExit("缺小程序截图：" + fp +
                         "\n先跑：node promo/mp_grab_state.js （需 cli auto 已拉起）")
    return Image.open(fp).convert("RGB")


def best_dy(A, B):
    """在 0~90 设备像素里搜最佳垂直偏移（B 向下平移 dy 后与 A 比）"""
    W, H = A.size
    best = (0, 1e9)
    for dy in range(0, 91, 2):
        h = H - dy
        if h < 200:
            break
        a = A.crop((0, 0, W, h))
        b = B.crop((0, dy, W, dy + h))
        d = ImageChops.difference(a, b).convert("L")
        px = d.getdata()
        m = sum(px) / float(len(px))
        if m < best[1]:
            best = (dy, m)
    # 在最佳附近做 1px 精修
    dy0 = best[0]
    for dy in range(max(0, dy0 - 3), dy0 + 4):
        h = H - dy
        if h < 200:
            continue
        a = A.crop((0, 0, W, h))
        b = B.crop((0, dy, W, dy + h))
        d = ImageChops.difference(a, b).convert("L")
        px = d.getdata()
        m = sum(px) / float(len(px))
        if m < best[1]:
            best = (dy, m)
    return best


rows = []
for name, _st in POS:
    A = Image.open(io.BytesIO(pwa[name])).convert("RGB")
    A = A.resize(TARGET, Image.LANCZOS)          # 与小程序截图同尺寸
    B = load_mp(name)
    if B.size != TARGET:
        B = B.resize(TARGET, Image.LANCZOS)

    dy, mean = best_dy(A, B)
    W, H = TARGET
    h = H - dy
    a = A.crop((0, 0, W, h))
    bb = B.crop((0, dy, W, dy + h))
    diff = ImageChops.difference(a, bb).convert("L")
    px = list(diff.getdata())
    over = sum(1 for v in px if v > 48)
    over_pct = 100.0 * over / len(px)
    rows.append((name, dy, mean, over, over_pct))

    vis = diff.point(lambda v: min(255, v * 4))
    PAD = 10
    sheet = Image.new("RGB", (W * 3 + PAD * 4, h + PAD * 2 + 26), (20, 26, 42))
    d = ImageDraw.Draw(sheet)
    for i, (im, lab) in enumerate([(a, "A: PWA 线上版"), (bb, "B: 小程序版"), (vis, "差分 x4")]):
        x = PAD + i * (W + PAD)
        sheet.paste(im, (x, PAD + 22))
        d.text((x, PAD + 6), lab, fill=(200, 210, 230))
    sheet.save(os.path.join(HERE, "_holdings_cmp_%s.png" % name))
    print("  写出 promo/_holdings_cmp_%s.png" % name)

print()
print("%-6s %-6s %-10s %-10s %s" % ("位置", "对齐dy", "平均差", ">48像素", "占比"))
for name, dy, mean, over, pct in rows:
    print("%-6s %-6d %-10.2f %-10d %.3f%%" % (name, dy, mean, over, pct))

# 顶部对齐自检：dy 是「B 侧相对 A 侧的下移量」，两端顶部同基准时应当为 0
for name, dy, mean, over, pct in rows:
    if name == "top":
        if SBH:
            ok = dy <= 3
            exp = "dy≈0（--sbh %d 已把安全区注入两端 ⇒ 顶部同基准）" % SBH
        else:
            ok = 24 <= dy <= 60
            exp = "dy≈%d（没传 --sbh：差的就是状态栏那一段的缩放值）" % int(54 * 0.842)
        print()
        print("顶部对齐自检：dy=%d ⇒ %s  期望 %s" % (dy, "✅ 合理" if ok else "❌ 异常", exp))
        break

print()
print("RESULT=OK")
