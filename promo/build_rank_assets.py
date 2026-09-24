# -*- coding: utf-8 -*-
"""段位卡片素材构建（v2.7.60 起）

Mak 在外部出图（桌面「健身交易员全套卡牌」10 张 PNG），本脚本把它变成
两端可直接引用的运行时资源。

源 PNG 1773x2364（左右各 ~60px 白底边、上下无）
  → 自动探边裁掉白底
  → 等比缩放
  → WebP
  → 两档落位：

  档位   尺寸      质量  去向                    用途
  ----   --------  ----  ----------------------  ----------------------------------------
  hi     504x720   86    PWA  assets/ranks/       网页卡廊（GitHub Pages 无体积约束）
                                                + 小程序云存储的上传源（同一份文件）
  lo     252x360   78    小程序 images/ranks/     主包兜底：秒开；云存储失败时仍看得到

⚠️ 为什么小程序高清必须走云存储（而不是塞主包）：
   主包上限 2MB，当前已 1.33MB（foods.js 507KB 是紧凑 JSON，无可腾空间）。
   3x 十张 WebP = 860KB ⇒ 1.33+0.86 = 2.19MB **超限**。2x 虽能塞下（+357KB），
   但 dpr3 机器上要把 336 物理像素拉到 504 显示宽度，插画会发虚 —— Mak 明确要求保画质。
   ⇒ 小程序 = 主包 1.5x 兜底（210KB，保底可用）+ 云存储 3x 高清（渐进替换）。

⚠️ 三条不能忘：
 1. 白边必须裁掉 —— 卡廊背景是深色 #0a0e1a，留着白边会是一圈刺眼白框。
 2. 10 张裁后**宽高比必须一致**，否则卡廊里卡片高低不齐（本脚本硬校验）。
 3. 图片顺序必须与 index.html 的 RANKS 严格一致，错位会让卡与段位名对不上（硬校验）。

用法：python promo/build_rank_assets.py
"""
import os
import sys
import io
import json

from PIL import Image

SRC_DIR = r'C:\Users\Administrator\Desktop\健身交易员全套卡牌'

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                   # PWA 仓库根
MP_ROOT = r'E:\WeChatProjects\jianpan\miniprogram'              # 小程序根

PWA_OUT = os.path.join(ROOT, 'assets', 'ranks')
MP_OUT = os.path.join(MP_ROOT, 'images', 'ranks')

DISP_W = 168          # 卡廊里卡片的显示宽（CSS px）—— 改动要同步 index.html / me.wxss
DISP_H = 240          # 显示高 = DISP_W / TARGET_RATIO（0.70 整，和 RANKS 卡面完全对齐）
TARGET_RATIO = 0.70   # 统一裁切比例
HI_MUL, HI_Q = 3, 86  # 高清档（PWA 卡廊；将来给小程序云存储用的是同一份）
# 主包兜底档：2.5x —— 显示 168pt 时，dpr2 机器原生清晰、dpr3 只软 17%（基本无感）。
# 实测 3x 十张 816KB 会把主包顶到 2.19MB **超限**；2.5x 是「画质 / 主包」的平衡点（+460KB）。
# 主包若将来吃紧，把它降到 2.0 即可（改这一个数，重跑本脚本）。
LO_MUL, LO_Q = 2.5, 78

# 源文件名（= Mak 出图的中文名，用于**硬校验段位名顺序**）→ 输出名。
# ⚠️ 输出名顺序 = RANKS 顺序（lv 从低到高）。名字对不上直接 FAIL，别靠人眼。
# ⚠️ 扩展名必须是 .webp —— 内容是 WebP，写成 .png 会让 GitHub Pages / 微信按 image/png
#    发 Content-Type，与字节不符（浏览器靠 magic 能解，但属于隐患，小程序端更容易踩）。
MAP = [
    ('01-韭菜.png', '韭菜', '01_leek.webp'),
    ('02-散户.png', '散户', '02_retail.webp'),
    ('03-中户.png', '中户', '03_mid.webp'),
    ('04-大户.png', '大户', '04_big.webp'),
    ('05-牛散.png', '牛散', '05_pro.webp'),
    ('06-游资.png', '游资', '06_hotmoney.webp'),
    ('07-主力.png', '主力', '07_mainforce.webp'),
    ('08-机构.png', '机构', '08_institution.webp'),
    ('09-庄家.png', '庄家', '09_dealer.webp'),
    ('10-股神.png', '股神', '10_stockgod.webp'),
]


def clean_out(d):
    """清掉本脚本的历史产物（只匹配 `两位数字_英文名.webp|png` 这种命名）。

    ⚠️ 必须清：段位表从 11 段换成 10 段后，旧产物 03_minor.png 还留着，
       目录里就会同时存在两套编号，肉眼核对时极易看错。只删自己命名的文件，不碰别的。
    """
    import re
    n = 0
    if not os.path.isdir(d):
        return 0
    for f in sorted(os.listdir(d)):
        if re.match(r'^\d{2}_[a-z_]+\.(webp|png|jpe?g)$', f):
            os.remove(os.path.join(d, f))
            n += 1
    return n


def is_bg(c):
    """近白判定：卡外白底。阈值放 245 太高会漏（图有轻微灰边）⇒ 用 240。"""
    return c[0] > 240 and c[1] > 240 and c[2] > 240


def trim_white(im, step=17):
    """从四边向内扫，返回第一个非白边列/行。step 采样防孤立噪点误判（all() 要求整条都白）。"""
    W, H = im.size
    px = im.load()

    left = 0
    while left < W and all(is_bg(px[left, y]) for y in range(0, H, step)):
        left += 1
    right = 0
    while right < W and all(is_bg(px[W - 1 - right, y]) for y in range(0, H, step)):
        right += 1
    top = 0
    while top < H and all(is_bg(px[x, top]) for x in range(0, W, step)):
        top += 1
    bot = 0
    while bot < H and all(is_bg(px[x, H - 1 - bot]) for x in range(0, W, step)):
        bot += 1
    return (left, top, W - right, H - bot)


def ranks_from_pwa():
    """从 index.html 的 RANKS 读出段位名顺序 —— 用于硬校验图片与段位不错位。
    不 require 任何 js 运行时，直接正则抓 name:'xxx'（RANKS 表是唯一源头）。"""
    p = os.path.join(ROOT, 'index.html')
    s = open(p, encoding='utf-8').read()
    i = s.find('const RANKS = [')
    if i < 0:
        return None
    j = s.find('];', i)
    blk = s[i:j]
    import re
    return re.findall(r"name:'([^']+)'", blk)


def main():
    if not os.path.isdir(SRC_DIR):
        print('FAIL 源目录不存在：%s' % SRC_DIR)
        return 1

    # ---------- 前置硬校验：图片段位名顺序 == RANKS 顺序 ----------
    ranks = ranks_from_pwa()
    if ranks is None:
        print('FAIL 没能从 index.html 解析出 RANKS')
        return 1
    img_names = [n for _, n, _ in MAP]
    if ranks != img_names:
        print('FAIL 图片顺序与 RANKS 不一致 —— 卡与段位名会错位，先对齐再跑')
        print('  RANKS  : %s' % ranks)
        print('  图片   : %s' % img_names)
        return 1
    print('段位名顺序校验 OK：%d 段 %s' % (len(ranks), '/'.join(ranks)))

    for d in (PWA_OUT, MP_OUT):
        os.makedirs(d, exist_ok=True)
    for d in (PWA_OUT, MP_OUT):
        n = clean_out(d)
        if n:
            print('清理旧产物 %d 个：%s' % (n, d))

    # ---------- pass 1：逐张裁白边，先只看尺寸 ----------
    # 每张卡左右白边都不一样（生图时卡面宽度有 ±0.7% 漂移），直接按各自裁后比例输出，
    # 同排卡片会差 3px 高 —— 肉眼能看出「不齐」。所以统一到一个固定比例再输出。
    staged = []
    for src_name, _, out_name in MAP:
        src = os.path.join(SRC_DIR, src_name)
        if not os.path.isfile(src):
            print('FAIL 缺少源图：%s' % src_name)
            return 1
        im = Image.open(src)
        if im.mode != 'RGB':
            im = im.convert('RGB')
        box = trim_white(im)
        cut = im.crop(box)
        staged.append((src_name, out_name, cut, box))

    # ---------- 统一框：宽取十张最小值，高按 TARGET_RATIO 反推，两张方向都居中裁 ----------
    fix_w = min(c.width for _, _, c, _ in staged)
    fix_h = round(fix_w / TARGET_RATIO)
    if fix_h > min(c.height for _, _, c, _ in staged):
        print('FAIL 统一框比最矮的卡还高 —— 调 TARGET_RATIO 或查源图')
        return 1
    print('统一裁切框 %dx%d（比例 %.4f）—— 原图各张宽 %d~%d，多出的边缘居中裁掉'
          % (fix_w, fix_h, TARGET_RATIO,
             min(c.width for _, _, c, _ in staged), max(c.width for _, _, c, _ in staged)))

    ratios = []
    rows = []
    tot_hi = tot_lo = 0

    for src_name, out_name, cut, box in staged:
        ox = (cut.width - fix_w) // 2
        oy = (cut.height - fix_h) // 2
        fix = cut.crop((ox, oy, ox + fix_w, oy + fix_h))
        ratio = fix.width / fix.height
        ratios.append((src_name, ratio))

        # hi：LANCZOS 等比缩放（生图像素块与网格不对齐，NEAREST 降采样会出毛刺）
        w_hi = round(DISP_W * HI_MUL)
        h_hi = round(w_hi / TARGET_RATIO)
        buf = io.BytesIO()
        fix.resize((w_hi, h_hi), Image.LANCZOS).save(buf, 'WEBP', quality=HI_Q, method=6)
        hi = buf.getvalue()

        w_lo = round(DISP_W * LO_MUL)
        h_lo = round(w_lo / TARGET_RATIO)
        buf = io.BytesIO()
        fix.resize((w_lo, h_lo), Image.LANCZOS).save(buf, 'WEBP', quality=LO_Q, method=6)
        lo = buf.getvalue()

        with open(os.path.join(PWA_OUT, out_name), 'wb') as f:
            f.write(hi)                       # 同时也是小程序云存储的上传源
        with open(os.path.join(MP_OUT, out_name), 'wb') as f:
            f.write(lo)

        tot_hi += len(hi)
        tot_lo += len(lo)
        rows.append((out_name, cut.width, cut.height, ratio, hi, lo, box, (ox, oy)))

    # ---------- 校验 1：比例一致 ----------
    rmin = min(r for _, r in ratios)
    rmax = max(r for _, r in ratios)
    print('')
    print('裁后比例 min %.4f  max %.4f  极差 %.4f' % (rmin, rmax, rmax - rmin))
    ok_ratio = (rmax - rmin) < 0.005
    if not ok_ratio:
        print('FAIL 10 张比例不一致 ⇒ 卡廊里卡片会高低不齐，先查源图')

    print('')
    print('%-18s %-13s %-8s %-9s %-9s %-11s %s'
          % ('输出', '探边后尺寸', '比例', 'hi', 'lo', '居中裁偏移', '白边 LTRB'))
    for out_name, w, hh, ratio, hi, lo, box, off in rows:
        print('%-18s %-13s %-8.4f %-9s %-9s %-11s %s'
              % (out_name, '%dx%d' % (w, hh), ratio,
                 '%.1fKB' % (len(hi) / 1024), '%.1fKB' % (len(lo) / 1024),
                 '%d,%d' % off, box))
    print('')
    print('显示 %dx%d CSS px    hi %dx%d q%d 十张 %.1f KB    lo %dx%d q%d 十张 %.1f KB'
          % (DISP_W, DISP_H,
             round(DISP_W * HI_MUL), round(DISP_W * HI_MUL / TARGET_RATIO), HI_Q, tot_hi / 1024,
             round(DISP_W * LO_MUL), round(DISP_W * LO_MUL / TARGET_RATIO), LO_Q, tot_lo / 1024))

    # ---------- 校验 2：主包预算（只算 lo，hi 走云存储不占包）----------
    def du(p):
        t = 0
        for dp, _, fn in os.walk(p):
            for f in fn:
                t += os.path.getsize(os.path.join(dp, f))
        return t

    mp_size = du(MP_ROOT)
    print('小程序主包 %.2f MB（上限 2.00）  余量 %.2f MB'
          % (mp_size / 1024 / 1024, (2 * 1024 * 1024 - mp_size) / 1024 / 1024))
    ok_budget = mp_size < 2 * 1024 * 1024 * 0.9        # 留 10% 安全垫，别贴顶
    if not ok_budget:
        print('FAIL 主包占超过 90%%，兜底图要再压或改走云存储')

    # ---------- 落清单：两端共用一份顺序，避免各写各的 ----------
    manifest = {
        'dispW': DISP_W,
        'dispH': DISP_H,
        'ratio': TARGET_RATIO,
        'hiMul': HI_MUL,
        'loMul': LO_MUL,
        'names': [n for _, _, n in MAP],
        'labels': [n for _, n, _ in MAP],
    }
    with open(os.path.join(HERE, 'rank_assets.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print('清单 promo/rank_assets.json 已写')

    ok = ok_ratio and ok_budget
    print('RESULT ' + ('OK' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
