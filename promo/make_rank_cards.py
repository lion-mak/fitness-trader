# -*- coding: utf-8 -*-
r"""⛔ 已停用（2026-09-24）—— 段位卡面已改由 Mak 从外部出图，接入管线是
   **promo/build_rank_assets.py**（桌面源图 → 探边裁白 → 统一 0.70 → 双档 WebP → 双端落位）。

   本脚本的 RANKS 仍是**旧 11 段表（含「小散」）**，跑起来会生成与线上不符的卡面
   ⇒ 除非要复活「代码合成卡面」这条路，否则别跑它。
   要重跑素材：改桌面源图 → `python promo/build_rank_assets.py`。

make_rank_cards.py —— 段位「像素卡」生成器。

分工（与六边形版一致的原则，只是换了皮）：
  · 生图只画**像素角色**（洋红纯底，1024x1024）。
  · 卡框 / 英文代号 / 中文称谓 / 段位刻度 / 经验条全部代码合成 ⇒ 11 张卡逐像素一致，
    中文清晰，改称谓只重跑脚本不烧积分。

生图两条坑及对策（都是实测踩出来的）：
  ① `background=transparent` 参数不生效 ⇒ 改成让模型画**洋红纯底 #FF00FF**，
     纯色判据一次抠净（上一版用棋盘格底 + 灰投影，抠了两轮）。
  ② 右下角必带「AI生成」水印（实测占该区 7~8% 像素）⇒ 把水印区**强制划为背景**，
     既抠掉水印，也避免它把角色 bbox 撑大。

量化档位的结论（promo/_rank_ref/quant_sheet.png 实测）：
  **不要**把图强行降到 48/64/96 网格 —— 生图自带的像素块与原网格不对齐，
  NEAREST 降采样会产生满边毛刺（64px 档最明显）。原图本身就是干净的像素画，
  LANCZOS 等比缩放最干净 ⇒ 只做等比缩放，不做网格量化。

用法（必须 venv，playwright 只装在 venv）：
  …/python/envs/default/Scripts/python.exe promo/make_rank_cards.py
"""
import base64
import io
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SRC_DIR = os.path.join(HERE, "_pixel_icons")
OUT_DIR = os.path.join(ROOT, "assets", "ranks")
REVIEW_DIR = os.path.join(HERE, "_rank_ref")

# ---------- 11 段位表 ----------
# acc = 强调色（框 / 刻度 / 进度条），bg = 卡面底色，gate = 晋升经验门槛
RANKS = [
    dict(no=1,  cn="韭菜", en="LEEK",        acc="#3FBF57", bg="#0E1410", gate="0",      icon="leek"),
    dict(no=2,  cn="散户", en="RETAIL",      acc="#7C8DA6", bg="#111316", gate="500",    icon=None),
    dict(no=3,  cn="小散", en="MINOR",       acc="#33A6B8", bg="#0C1417", gate="2千",     icon=None),
    dict(no=4,  cn="中户", en="MID",         acc="#3D7BE0", bg="#0C1119", gate="6千",     icon=None),
    dict(no=5,  cn="大户", en="BIG",         acc="#5B4BC4", bg="#100D1A", gate="1.5万",   icon=None),
    dict(no=6,  cn="牛散", en="PRO",         acc="#E0A020", bg="#16110A", gate="3.5万",   icon=None),
    dict(no=7,  cn="游资", en="HOT MONEY",   acc="#E8781E", bg="#160F09", gate="7万",     icon="hotmoney"),
    dict(no=8,  cn="主力", en="MAIN FORCE",  acc="#C43A2E", bg="#170C0A", gate="13万",    icon=None),
    dict(no=9,  cn="机构", en="INSTITUTION", acc="#8E44AD", bg="#130C17", gate="23万",    icon=None),
    dict(no=10, cn="庄家", en="DEALER",      acc="#4A4A57", bg="#101014", gate="38万",    icon=None),
    dict(no=11, cn="股神", en="STOCK GOD",   acc="#D4AF37", bg="#16130A", gate="60万",    icon=None),
]

# ---------- 卡片几何（512x656 画布，渲染 DPR=2 出 1024x1312） ----------
CW, CH = 512, 656
P_OUT = "M28 0H484L512 28V628L484 656H28L0 628V28Z"      # 外框（切角像素方框）
P_IN = "M32 12H480L500 32V624L480 644H32L12 624V32Z"     # 内面（inset 12，切角 20）
PAD_X = 44.0                       # 内容左右边距
ART_W, ART_H = 424.0, 324.0        # 角色区
ART_CX, ART_CY = 256.0, 362.0
TICK_X0, TICK_DX = 296.0, 16.0     # 11 格段位刻度
YAHEI = "Microsoft YaHei, PingFang SC, sans-serif"
MONO = "Consolas, ui-monospace, monospace"

# 水印区（1024 原图坐标）：右下角「AI生成 WORKBUDDY」——强制划为背景
WM_Y0, WM_X0 = 880, 840
LONG_SIDE = 700                    # 嵌入 SVG 的角色最长边（导出后角色区 2x=648，够用）


def data_uri(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ---------- 1) 抠洋红底 + 去水印 + 裁到内容框 ----------
def matte(src_path):
    im = Image.open(src_path).convert("RGB")
    w, h = im.size
    a = np.asarray(im).astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]

    # 洋红判据：R 高、G 低、R 明显大于 G、B 也高于 G。
    # 实测两张背景分别为 #b12e78 / #d718b5 ⇒ 这条稳过；角色的绿/金/红/白都远不满足。
    mag = (r > 140) & (g < 120) & ((r - g) > 70) & ((b - g) > 15)
    n_mag = int(mag.sum())

    # 水印：右下角的浅色「AI生成」不是洋红 ⇒ 会被当角色留下来并撑大 bbox。
    # 直接强制划为背景（角色居中，从不进入该区，已核 bbox）。
    wm = mag[WM_Y0:, WM_X0:].copy()
    mag[WM_Y0:, WM_X0:] = True
    print("   · 洋红底 %d px | 水印区强制背景 %d px（原非洋红）"
          % (n_mag, int((~wm).sum())))

    # 硬边 alpha：像素画**不能羽化**（GaussianBlur 会把像素块边缘糊掉）。
    # 先用 MinFilter(3) 收缩 1px 切掉洋红与角色的抗锯齿混色边，再二值化取硬边。
    alpha = Image.fromarray(((~mag) * 255).astype(np.uint8), "L")
    alpha = alpha.filter(ImageFilter.MinFilter(3))
    alpha = alpha.point(lambda v: 255 if v > 127 else 0)

    out = im.convert("RGBA")
    out.putalpha(alpha)
    bbox = out.getbbox()
    if bbox:
        pad = 8
        bbox = (max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                min(w, bbox[2] + pad), min(h, bbox[3] + pad))
        out = out.crop(bbox)
    return out


def fit_long_side(img, side=LONG_SIDE):
    w, h = img.size
    if max(w, h) <= side:
        return img
    k = side / float(max(w, h))
    return img.resize((max(1, int(round(w * k))), max(1, int(round(h * k)))), Image.LANCZOS)


# ---------- 2) 拼一张像素卡 ----------
def card_svg(rank, sprite):
    acc, bg = rank["acc"], rank["bg"]
    art = ""
    if sprite is not None:
        iw, ih = sprite.size
        k = min(ART_W / iw, ART_H / ih)
        tw, th = iw * k, ih * k
        art = ('<image x="%.1f" y="%.1f" width="%.1f" height="%.1f" href="%s"/>'
               % (ART_CX - tw / 2, ART_CY - th / 2, tw, th, data_uri(sprite)))

    ticks = ""
    for i in range(11):
        ticks += ('<rect x="%.0f" y="52" width="12" height="14" fill="%s" opacity="%s"/>'
                  % (TICK_X0 + i * TICK_DX, acc, "1" if i < rank["no"] else "0.16"))

    frac = rank["no"] / 11.0
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{CW}" height="{CH}" viewBox="0 0 {CW} {CH}">
<defs><path id="cOut" d="{P_OUT}"/><path id="cIn" d="{P_IN}"/></defs>
<use href="#cOut" fill="{acc}"/>
<use href="#cIn" fill="{bg}"/>
<use href="#cIn" fill="none" stroke="{acc}" stroke-width="2" opacity="0.5"/>
{art}
<text x="{PAD_X:.0f}" y="76" font-family="{MONO}" font-size="26" fill="{acc}">{rank["en"]}</text>
<text x="{PAD_X:.0f}" y="150" font-family="{YAHEI}" font-weight="bold" font-size="58" fill="#EDF3EE">{rank["cn"]}</text>
{ticks}
<line x1="{PAD_X:.0f}" y1="186" x2="{CW - PAD_X:.0f}" y2="186" stroke="{acc}" stroke-width="2" opacity="0.35"/>
<line x1="{PAD_X:.0f}" y1="540" x2="{CW - PAD_X:.0f}" y2="540" stroke="{acc}" stroke-width="2" opacity="0.35"/>
<text x="{PAD_X:.0f}" y="578" font-family="{MONO}" font-size="26" fill="#8C9A90">EXP {rank["gate"]}</text>
<text x="{CW - PAD_X:.0f}" y="578" text-anchor="end" font-family="{MONO}" font-size="26" fill="{acc}">{rank["no"]} / 11</text>
<rect x="{PAD_X:.0f}" y="594" width="{CW - 2 * PAD_X:.0f}" height="22" fill="#FFFFFF" opacity="0.07"/>
<rect x="{PAD_X:.0f}" y="594" width="{round((CW - 2 * PAD_X) * frac)}" height="22" fill="{acc}"/>
</svg>'''


def launch_browser(pw):
    last = None
    for kw in ({"channel": "msedge"},
               {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"}):
        try:
            return pw.chromium.launch(**kw)
        except Exception as e:      # noqa: BLE001
            last = e
    raise SystemExit("找不到可用浏览器内核：%s" % last)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(REVIEW_DIR, exist_ok=True)

    sprites = {}
    for r in RANKS:
        key = r["icon"]
        if not key:
            continue
        src = os.path.join(SRC_DIR, "src_%s.png" % key)
        if not os.path.exists(src):
            print("!! 缺生图源：%s（该段位先跳过）" % src)
            continue
        print("== %s" % key)
        sp = fit_long_side(matte(src))
        sp.save(os.path.join(SRC_DIR, "cut_%s.png" % key))
        sprites[key] = sp
        print("   sprite -> %s" % (sp.size,))

    # 抠图质检：贴深底看有没有残留粉边
    if sprites:
        chk = Image.new("RGB", (len(sprites) * 350, 360), "#111318")
        for i, (k, sp) in enumerate(sprites.items()):
            im = sp.copy()
            im.thumbnail((330, 330), Image.LANCZOS)
            chk.paste(im, (i * 350 + 10, 15), im)
        chk.save(os.path.join(REVIEW_DIR, "matte_check.png"))
        print("质检图 -> _rank_ref/matte_check.png")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = launch_browser(p)
        page = b.new_page(viewport={"width": CW, "height": CH}, device_scale_factor=2)
        master = os.path.join(OUT_DIR, "master")
        os.makedirs(master, exist_ok=True)
        for r in RANKS:
            name = "%02d_%s" % (r["no"], r["en"].replace(" ", "").lower())
            html = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
                    "<style>html,body{margin:0;padding:0;background:transparent}</style>"
                    "</head><body>%s</body></html>" % card_svg(r, sprites.get(r["icon"])))
            page.set_content(html)
            big = os.path.join(master, "%s.png" % name)
            page.screenshot(path=big, omit_background=True)
            im = Image.open(big)
            im.resize((320, round(320 * CH / CW)), Image.LANCZOS).save(
                os.path.join(OUT_DIR, "%s.webp" % name), "WEBP", quality=88, method=6)
            print("card -> %s  master %s  app webp %.0fKB"
                  % (name, im.size,
                     os.path.getsize(os.path.join(OUT_DIR, "%s.webp" % name)) / 1024))
        # 对照板：11 段全套（缺图的段位 = 空角色位，正好先看配色递进与版式一致性）
        cells = "".join(
            "<div class='cell'><div class='bw'>" + card_svg(r, sprites.get(r["icon"]))
            + "</div><div class='cn'>" + r["cn"] + "</div><div class='en'>" + r["en"] + "</div></div>"
            for r in RANKS)
        sheet = ("<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
                 "html,body{margin:0;padding:0;background:#0B0B0E}"
                 ".grid{display:grid;grid-template-columns:repeat(6,190px);gap:22px 24px;padding:26px 28px}"
                 ".cell{width:190px}.bw{width:190px;height:243px}.bw svg{width:190px;height:243px}"
                 ".cn{color:#EDEDF2;font:700 20px 'Microsoft YaHei';margin-top:8px;text-align:center}"
                 ".en{color:#7B7B88;font:400 13px Consolas;text-align:center;margin-top:2px}"
                 "</style></head><body><div class='grid'>" + cells + "</div></body></html>")
        pg = b.new_page(viewport={"width": 1290, "height": 612}, device_scale_factor=2)
        pg.set_content(sheet)
        pg.screenshot(path=os.path.join(REVIEW_DIR, "rank_cards_sheet.png"))
        print("对照板 -> _rank_ref/rank_cards_sheet.png")

        # 小尺寸可读性：卡片在 App 里会缩到 ~160px 甚至更小，小字还认得出吗
        rows = []
        for px in (200, 160, 128, 96):
            items = ""
            for r in RANKS[:2] + [RANKS[6], RANKS[10]]:
                items += ("<div class='c'><div class='s' style='width:" + str(px) + "px;height:"
                          + str(round(px * CH / CW)) + "px'>" + card_svg(r, sprites.get(r["icon"]))
                          + "</div><div class='l'>" + str(px) + "</div></div>")
            rows.append("<div class='r'><div class='tag'>" + str(px) + "px</div>" + items + "</div>")
        sheet2 = ("<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
                  "html,body{margin:0;padding:0;background:#0B0B0E}"
                  ".r{display:flex;gap:24px;padding:18px 26px;align-items:flex-end}"
                  ".tag{color:#6E6E7A;font:400 16px 'Microsoft YaHei';width:60px;"
                  "padding-bottom:18px;text-align:right}"
                  ".c{text-align:center}.s svg{width:100%;height:100%}"
                  ".l{color:#7B7B86;font:400 14px 'Microsoft YaHei';margin-top:5px}"
                  "</style></head><body>" + "".join(rows) + "</body></html>")
        pg2 = b.new_page(viewport={"width": 1180, "height": 1220}, device_scale_factor=2)
        pg2.set_content(sheet2)
        pg2.screenshot(path=os.path.join(REVIEW_DIR, "rank_cards_small.png"))
        print("小尺寸检查 -> _rank_ref/rank_cards_small.png")

        b.close()


if __name__ == "__main__":
    sys.exit(main())
