# -*- coding: utf-8 -*-
r"""⛔ 已停用（2026-09-24）—— 段位卡面已改由 Mak 从外部出图，接入管线是
   **promo/build_rank_assets.py**（桌面源图 → 探边裁白 → 统一 0.70 → 双档 WebP → 双端落位）。

   本脚本的 RANKS 仍是**旧 11 段表（含「小散」）**，跑起来会生成与线上不符的卡面
   ⇒ 除非要复活「代码合成卡面」这条路，否则别跑它。

make_rank_card_v3.py —— 「三横排」像素段位卡（122x171）批量生成器。

几何怎么来的（量的，不是猜的）：
  · 卡宽由「手机 430 下一行放 3 个」反推 ⇒ 3 卡 + 2 间距 = 402（=430 − 左右各 14）。
    间距放宽到 18px（Mak：间距大一点没关系）⇒ 单卡宽 (402 − 36) / 3 = **122px**。
  · 卡高 **171px** ⇒ 122:171 ≈ 0.713，与实体交易卡比例（2.5:3.5）一致，比方形更「瘦长」。
  · 卡面只留 **角色区 119px + 名称条 36px**：实测 ≤128px 时英文代号 / EXP / 刻度全糊 ⇒ 全去掉。

文字（Mak：不要像素字体，跟卡不搭 ⇒ 回到黑体）：
  · 名称条底色 = 段位强调色；**字色按底色相对亮度取对比更高的一侧**（实测绿底配白字只有 2.4:1）。
  · 文字加一道**无模糊硬阴影**（+2px 深色）—— 缩到 96px 时比纯色更抓得住。

生图（11 段像素搞怪风）：
  · 源图在 `promo/_pixel3_icons/src/NN_key.png`（洋红底），抠图走 `make_rank_cards.matte`。
  · ⚠️ 生图工具并发会串 output_dir + 同秒文件名互相覆盖 ⇒ **必须串行出图**，归档靠人眼复核
    （见 `_pixel3_icons/_organize.py`）。

用法（必须 venv）：
  …/python/envs/default/Scripts/python.exe promo/make_rank_card_v3.py
"""
import base64
import io
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from make_rank_cards import matte, fit_long_side, launch_browser  # noqa: E402

SRC_DIR = os.path.join(HERE, "rank_src")          # 11 张生图源（512px，**入库**，保证可复现）
CUT_DIR = os.path.join(HERE, "_pixel3_icons", "cut")   # 抠图中间产物（不入库）
OUT_DIR = os.path.join(ROOT, "assets", "ranks")
REVIEW_DIR = os.path.join(HERE, "_rank_ref")

# ---------- 卡面几何（逻辑 px；DPR=3 出 366x513） ----------
CW, CH = 122, 171
GAP = 18
DPR = 3
ART_X, ART_Y, ART_W, ART_H = 8.0, 6.0, 106.0, 117.0
NAME_X, NAME_Y, NAME_W, NAME_H = 8.0, 127.0, 106.0, 36.0
NAME_FS = 25.0
P_OUT = "M7 0H115L122 7V164L115 171H7L0 164V7Z"
P_IN = "M9.2 2.6H112.8L119.4 9.2V161.8L112.8 168.4H9.2L2.6 161.8V9.2Z"
CN_FAMILY = "Microsoft YaHei, PingFang SC, Hiragino Sans GB, sans-serif"

# ---------- 11 段位表（门槛/配色见 promo/rank_prompts.md 第四节） ----------
RANKS = [
    dict(no=1,  key="01_leek",        cn="韭菜", en="LEEK",        acc="#3FBF57", bg="#0E1410"),
    dict(no=2,  key="02_retail",      cn="散户", en="RETAIL",      acc="#7C8DA6", bg="#111316"),
    dict(no=3,  key="03_minor",       cn="小散", en="MINOR",       acc="#33A6B8", bg="#0C1417"),
    dict(no=4,  key="04_mid",         cn="中户", en="MID",         acc="#3D7BE0", bg="#0C1119"),
    dict(no=5,  key="05_big",         cn="大户", en="BIG",         acc="#5B4BC4", bg="#100D1A"),
    dict(no=6,  key="06_pro",         cn="牛散", en="PRO",         acc="#C08A2E", bg="#16110A"),
    dict(no=7,  key="07_hotmoney",    cn="游资", en="HOT MONEY",   acc="#E8781E", bg="#160F09"),
    dict(no=8,  key="08_mainforce",   cn="主力", en="MAIN FORCE",  acc="#C43A2E", bg="#170C0A"),
    dict(no=9,  key="09_institution", cn="机构", en="INSTITUTION", acc="#8E44AD", bg="#130C17"),
    dict(no=10, key="10_dealer",      cn="庄家", en="DEALER",      acc="#4A4A57", bg="#101014"),
    dict(no=11, key="11_stockgod",    cn="股神", en="STOCK GOD",   acc="#D4AF37", bg="#16130A"),
]


def _lum(hx):
    r, g, b = [int(hx[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]

    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ink_on(hx):
    """名称条文字色：按**对比度最大化**取黑白中更高的一侧（不是凭深/浅直觉）。
    ⭐对比度公式 (L1+0.05)/(L2+0.05)：黑字 = (L+0.05)/0.05、白字 = 1.05/(L+0.05)
      ⇒ 分界在 L ≈ 0.179，不是 0.5。实测韭菜绿 #3FBF57 配白字只有 2.4:1（发虚）。"""
    l = _lum(hx)
    c_black = (l + 0.05) / 0.05
    c_white = 1.05 / (l + 0.05)
    return "#0B0F0C" if c_black >= c_white else "#FFFFFF"


def mix_white(hx, k=0.88):
    """把强调色混白 k 得到「画面底色」。
    ⭐为什么必须给角色一块**淡色画面**：11 张里有黑西装（机构）、暗皮衣（牛散）、
      深绿魔鬼（庄家）—— 直接摆在深色卡面上会糊成一坨。淡色画面 + 生图自带的 1px 深描边，
      是唯一能让 11 张**全部**可读的分区方式（也等于集换式卡牌的「深框 + 画面 + 色条」三段式）。"""
    c = [int(hx[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(int(v * (1 - k) + 255 * k) for v in c)


def data_uri(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def card_svg(rank, sprite, dy=0.0):
    acc, bg = rank["acc"], rank["bg"]
    face = mix_white(acc)
    art = ""
    if sprite is not None:
        iw, ih = sprite.size
        k = min((ART_W - 8) / iw, (ART_H - 8) / ih)
        tw, th = iw * k, ih * k
        art = ('<image x="%.1f" y="%.1f" width="%.1f" height="%.1f" href="%s"/>'
               % (ART_X + (ART_W - tw) / 2, ART_Y + (ART_H - th) / 2, tw, th, data_uri(sprite)))
    base = NAME_Y + NAME_H / 2 + NAME_FS * 0.35 + dy
    ink = ink_on(acc)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{CW}" height="{CH}" viewBox="0 0 {CW} {CH}">
<defs><path id="o" d="{P_OUT}"/><path id="i" d="{P_IN}"/>
  <linearGradient id="gf" x1="0" y1="{ART_Y:.0f}" x2="0" y2="{ART_Y + ART_H:.0f}" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="{face}"/>
  </linearGradient></defs>
<use href="#o" fill="{acc}"/>
<use href="#i" fill="{bg}"/>
<rect x="{ART_X}" y="{ART_Y}" width="{ART_W}" height="{ART_H}" rx="4" fill="url(#gf)"/>
{art}
<rect x="{NAME_X}" y="{NAME_Y}" width="{NAME_W}" height="{NAME_H}" rx="3" fill="{acc}"/>
<text x="{CW / 2:.1f}" y="{base + 2:.1f}" text-anchor="middle"
      font-family="{CN_FAMILY}" font-weight="700" font-size="{NAME_FS:.0f}" letter-spacing="2"
      fill="#000000" opacity="0.40">{rank["cn"]}</text>
<text x="{CW / 2:.1f}" y="{base:.1f}" text-anchor="middle"
      font-family="{CN_FAMILY}" font-weight="700" font-size="{NAME_FS:.0f}" letter-spacing="2"
      fill="{ink}">{rank["cn"]}</text>
</svg>'''


def ink_center(png_path, acc_hex):
    """量名称条里墨迹的垂直重心（设备 px → 逻辑 px），用于自动居中。"""
    im = Image.open(png_path).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    y0, y1 = int(NAME_Y * DPR), int((NAME_Y + NAME_H) * DPR)
    sub = a[y0:y1]
    acc = np.array([int(acc_hex[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.int16)
    dist = np.abs(sub - acc).sum(axis=2)
    rows = np.where((dist > 190).any(axis=1))[0]
    if len(rows) == 0:
        return None
    return (y0 + (rows.min() + rows.max()) / 2.0) / DPR


def grid_html(sprites, cols=3, caption=""):
    cells = ""
    for r in RANKS:
        cells += ("<div class='cell'>" + card_svg(r, sprites[r["key"]])
                  + "</div>")
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
            "html,body{margin:0;padding:0;background:#0B0B0E}"
            ".vp{width:430px;padding:14px;box-sizing:border-box}"
            ".grid{display:grid;grid-template-columns:repeat(" + str(cols)
            + ",1fr);gap:" + str(GAP) + "px}"
            ".cell{width:" + str(CW) + "px;height:" + str(CH) + "px}"
            ".cell svg{width:" + str(CW) + "px;height:" + str(CH)
            + "px;display:block}"
            ".lb{color:#6E6E7A;font:400 12px '" + CN_FAMILY
            + "';margin:12px 0 0}</style></head><body><div class='vp'>"
            "<div class='grid'>" + cells + "</div>"
            "<div class='lb'>" + caption + "</div></div></body></html>")


def main():
    for d in (REVIEW_DIR, CUT_DIR, OUT_DIR, os.path.join(OUT_DIR, "webp")):
        os.makedirs(d, exist_ok=True)

    # ---------- ① 抠 11 张（洋红底 + 去水印 + 裁内容框） ----------
    sprites = {}
    for r in RANKS:
        p = os.path.join(SRC_DIR, r["key"] + ".png")
        if not os.path.exists(p):
            raise SystemExit("缺生图源：%s" % p)
        print("== matte %s ==" % r["key"])
        sp = fit_long_side(matte(p), 480)
        sp.save(os.path.join(CUT_DIR, r["key"] + ".png"))
        sprites[r["key"]] = sp
        print("   %s %s  比例 %.2f" % (r["cn"], sp.size, sp.size[0] / sp.size[1]))

    # 抠图质检板（每个角色一张，深底上看有无洋红残边）
    cw2 = 170
    sheet = Image.new("RGB", (cw2 * 6, cw2 * 2 + 40), "#131318")
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(RANKS):
        a = sprites[r["key"]].copy()
        a.thumbnail((cw2 - 16, cw2 - 16), Image.LANCZOS)
        x, y = (i % 6) * cw2, (i // 6) * cw2
        sheet.paste(a, (x + (cw2 - a.size[0]) // 2, y + (cw2 - a.size[1]) // 2), a)
        d.text((x + 6, y + cw2 - 14), r["cn"], fill="#8A8A96")
    dst_chk = os.path.join(REVIEW_DIR, "matte_sheet.png")
    sheet.save(dst_chk)
    print("抠图质检 ->", dst_chk)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = launch_browser(p)
        pg = b.new_page(viewport={"width": CW, "height": CH}, device_scale_factor=DPR)

        # ---------- ② 逐张出卡 @3x + 名称条自动居中 ----------
        for r in RANKS:
            dst = os.path.join(OUT_DIR, "%s.png" % r["key"])
            dy = 0.0
            for it in range(4):
                pg.set_content("<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
                               "html,body{margin:0;padding:0;background:transparent}</style>"
                               "</head><body>" + card_svg(r, sprites[r["key"]], dy)
                               + "</body></html>")
                pg.wait_for_timeout(200)
                pg.screenshot(path=dst, omit_background=True)
                c = ink_center(dst, r["acc"])
                if c is None:
                    print("   !! %s 名称条量不到墨迹" % r["cn"])
                    break
                off = (NAME_Y + NAME_H / 2.0) - c
                if abs(off) < 0.34:
                    break
                dy += off
            # WebP（小程序侧实际用的格式）
            im = Image.open(dst).convert("RGBA")
            wp = os.path.join(OUT_DIR, "webp", "%s.webp" % r["key"])
            im.save(wp, "WEBP", quality=88, method=6)
            print("卡 %-4s -> %s %s | webp %5.1f KB | 基线 %+.2f"
                  % (r["cn"], os.path.basename(dst), im.size,
                     os.path.getsize(wp) / 1024, dy))

        # ---------- ③ 全套对照板（4 列，深底） ----------
        cells = []
        for r in RANKS:
            cells.append("<div class='c'><div class='s'>" + card_svg(r, sprites[r["key"]])
                         + "</div><div class='t'>" + r["cn"] + " · " + r["en"]
                         + "</div></div>")
        scw, sch = 176, 246
        sh = ("<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
              "html,body{margin:0;padding:0;background:#0B0B0E}"
              ".r{display:flex;gap:18px;padding:22px 24px;flex-wrap:wrap;width:"
              + str(scw * 4 + 18 * 3 + 48) + "px}"
              ".c{text-align:center;width:" + str(scw) + "px}"
              ".s{width:" + str(scw) + "px;height:" + str(sch) + "px}"
              ".s svg{width:100%;height:100%;display:block}"
              ".t{color:#9A9AA6;font:400 13px '" + CN_FAMILY + "';margin-top:8px}"
              "</style></head><body><div class='r'>" + "".join(cells)
              + "</div></body></html>")
        pg2 = b.new_page(viewport={"width": scw * 4 + 18 * 3 + 48,
                                   "height": (sch + 42) * 3 + 44}, device_scale_factor=2)
        pg2.set_content(sh)
        pg2.wait_for_timeout(500)
        dst_all = os.path.join(REVIEW_DIR, "rank_cards_all.png")
        pg2.screenshot(path=dst_all)
        print("对照板 -> %s %s" % (dst_all, Image.open(dst_all).size))

        # ---------- ④ 真机比例：430 视口 3 列 ----------
        cap = ("视口 430px ｜ 单卡 " + str(CW) + "x" + str(CH) + "px ｜ 间距 "
               + str(GAP) + "px ｜ 三列 = " + str(CW * 3 + GAP * 2) + "px")
        pg3 = b.new_page(viewport={"width": 430, "height": (CH + 18) * 4 + 60},
                         device_scale_factor=DPR)
        pg3.set_content(grid_html(sprites, 3, cap))
        pg3.wait_for_timeout(500)
        dst_row = os.path.join(REVIEW_DIR, "rank_row_430.png")
        pg3.screenshot(path=dst_row)
        print("真机比例 -> %s %s" % (dst_row, Image.open(dst_row).size))

        # ---------- ⑤ 尺寸阶梯：122 缩小后中文还读不读得出 ----------
        pick = [RANKS[0], RANKS[6], RANKS[10]]
        # ⚠️ 必须是 list：曾误写成字符串 `cells2 = ""` ⇒ `cells2[i:i+3]` 变成「切 3 个字符」，
        #    于是每个字符被包成一行，拼出 23 MB 的 HTML、body 高 2^25、页面全黑（踩过）。
        cells2 = []
        for px in (140, 122, 96, 72):
            for r in pick:
                hh = round(px * CH / CW)
                cells2.append("<div class='c'><div class='s' style='width:" + str(px)
                              + "px;height:" + str(hh) + "px'>" + card_svg(r, sprites[r["key"]])
                              + "</div><div class='l'>" + str(px) + "px</div></div>")
        sh2 = ("<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
               "html,body{margin:0;padding:0;background:#0B0B0E}"
               ".rr{display:flex;gap:24px;padding:20px 26px;align-items:flex-end}"
               ".c{text-align:center;flex:0 0 auto}.s svg{width:100%;height:100%;display:block}"
               ".l{color:#7B7B86;font:400 12px '" + CN_FAMILY + "';margin-top:6px}"
               "</style></head><body>"
               + "".join("<div class='rr'>" + "".join(cells2[i:i + 3]) + "</div>"
                         for i in range(0, len(cells2), 3))
               + "</body></html>")
        pg4 = b.new_page(viewport={"width": 3 * 164 + 52, "height": (200 + 40) * 4 + 44},
                         device_scale_factor=3)
        pg4.set_content(sh2)
        pg4.wait_for_timeout(500)
        diag = pg4.evaluate("""() => {
            const svgs = document.querySelectorAll('svg');
            const r = svgs.length ? svgs[0].getBoundingClientRect() : null;
            const s = document.querySelector('.s');
            const sr = s ? s.getBoundingClientRect() : null;
            return {n: svgs.length,
                    svg0: r ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] : null,
                    s0: sr ? [Math.round(sr.x), Math.round(sr.y), Math.round(sr.width), Math.round(sr.height)] : null,
                    bodyH: document.body.scrollHeight};
        }""")
        print("诊断：svg 数 %s | 首个 svg rect %s | 首个 .s rect %s | body 高 %s"
              % (diag["n"], diag["svg0"], diag["s0"], diag["bodyH"]))
        print("诊断：html 长 %d | '<svg' 出现 %d 次（应为 %d）"
              % (len(sh2), sh2.count("<svg"), len(cells2)))
        dst_sz = os.path.join(REVIEW_DIR, "rank_sizes.png")
        pg4.screenshot(path=dst_sz)
        print("尺寸阶梯 -> %s %s" % (dst_sz, Image.open(dst_sz).size))

        b.close()

    tot = sum(os.path.getsize(os.path.join(OUT_DIR, "webp", f))
              for f in os.listdir(os.path.join(OUT_DIR, "webp")))
    print("11 张 webp 合计 %.0f KB（主包 2MB 的 %.1f%%）" % (tot / 1024, 100 * tot / 1024 / 2048))
    return 0


if __name__ == "__main__":
    sys.exit(main())
