# -*- coding: utf-8 -*-
"""
成就徽章 · 样张处理与「真尺寸预览板」生成
入口：python promo/ach_probe.py            （全量 30 张 · 六板块）
      python promo/ach_probe.py --all      （同上；--all 只是显式声明要跑齐 30 张）

四件事，每件都有硬判据，不靠眼看：
  1. 去水印：右下角平台水印区（位置已实测为固定框，见 WATERMARK）。⛔不是矩形硬铺 ——
     先用连通性判定「水印是否与主体相连」，不相连才允许整块铺回背景色
     （靠 bbox 相交判断会误报：炸弹的 bbox 角点落在水印区里，但真实像素并不相交）。
  2. 抠洋红底 → RGBA 硬边二值化 + MinFilter(3) 缩 1px 去抗锯齿混色边（⛔像素画不许羽化）。
     全流程用 PIL 通道运算向量化（本机无 numpy；逐像素 Python 循环 1024² 会跑成分钟级）。
  3. 两个版本：原色 sprite / 深色剪影 sprite（**只在内存里**，用于预览板）。
     ⚠️ 剪影**不单独出文件**：运行期用 `filter:brightness(0)`（alpha 保留 ⇒ 纯黑剪影）从同一张彩图派生，
        两套资产必然漂移（改图漏改剪影），而 brightness(0) 与 INK #0a0e1a 在 44px 下肉眼无差。
  4. 产出**运行图** `assets/ach/ach-<code>.png` = 132×132（44px 显示 × DPR3，NEAREST 硬边，⛔不羽化）。
     ⛔不再留 512 中间件：PWA 只按 44px 用，132 已够，主包/首访体积优先；重跑本脚本随时可再生成。
  5. 预览板：原始 QC 板 / 每个板块一张「原色·剪影·未解锁 + 1:1 真尺寸」对比板。

⭐ 结论性判据（缺一个都不算验过）：
   · 混色边残余 < 0.5%（洋红倾向像素）
   · 主体不透明占比 30%~80%（太小=画太空，太大=贴边）
   · 每个成就的**主色 vs 所属赛道底色**的对比度（(L+.05)/(L2+.05)）——
     这条是量出来的「韭菜绿配绿底糊不糊」，不靠肉眼直觉。
"""
import os
import sys
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

PROMO = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(PROMO)
SRC = os.path.join(PROMO, 'ach_src')
OUT = os.path.join(REPO, 'assets', 'ach')                        # 运行图 132×132（PWA 部署用）
# 小程序侧的素材源（上传云存储时读这里）：两仓各自的素材是同一份产物的镜像，
# 由本脚本一次写出两边，⛔不要手工 cp（漏一次就漂）。
MP_ACH_SRC = os.environ.get('JP_MP_ACH_SRC') or r'E:\WeChatProjects\jianpan\assets_src\ach'
MINI_ACH = r'E:\WeChatProjects\jianpan\miniprogram\images\ach'   # 主包内的线稿图标（对照用）

# 六个板块（持仓与套牢 / 盘中操作 / 资本游戏 / 交易员图鉴 / 涨停板敢死队 / 散户的自我修养）
# 顺序 = index.html ACHIEVEMENTS 原序（也是 ACH_ART / 云函数 NAMES 的顺序）
ITEMS = [
    ('hold',  'leek',      'Goofy_low_res_pixel_art_game_b_2026-09-29T12-40-19.png', '韭菜入场',   '记下人生第一笔',        '达到 1 次'),
    ('hold',  'untie',     'Goofy_low_res_pixel_art_game_b_2026-09-29T12-40-33.png', '解套成功',   '好不容易减掉 1kg',      '达到 1kg'),
    ('hold',  'wave',      'Goofy_low_res_pixel_art_game_b_2026-09-29T12-46-17.png', '主升浪',     '连涨三天没反弹',        '达到 3kg'),
    ('hold',  'bull',      'Goofy_low_res_pixel_art_game_b_2026-09-29T12-41-07.png', '牛市主升',   '账户飘红五斤',          '达到 5kg'),
    ('hold',  'exit',      'Goofy_low_res_pixel_art_game_b_2026-09-29T12-41-22.png', '止盈封板',   '落袋为安，达成目标',    '达到 7.5kg'),
    ('trade', 'pen',       'Goofy_low_res_pixel_art_game_b_2026-09-29T12-41-36.png', '试单',       '小仓试探，先记一笔',    '达到 1 次'),
    ('trade', 'half',      'Goofy_low_res_pixel_art_game_b_2026-09-29T12-41-54.png', '半仓干',     '一天五顿都在记',        '达到 5 次'),
    ('trade', 'allin',     'Goofy_low_res_pixel_art_game_b_2026-09-29T12-45-23.png', '梭哈选手',   '三次运动，满仓出击',    '达到 3 次'),
    ('trade', 'lightning', 'Goofy_low_res_pixel_art_game_b_2026-09-29T12-42-23.png', '高频交易员', '30笔成交，手速惊人',    '达到 30 次'),
    ('trade', 'whale',     'Goofy_low_res_pixel_art_game_b_2026-09-29T12-42-37.png', '量化巨鲸',   '100笔，机构级交易量',   '达到 100 次'),
    # ── 资本游戏（#5ac8fa）──
    ('capital', 'coin',    'Goofy_low_res_pixel_art_game_b_2026-09-29T13-55-46.png', '回口小肉',   '累计赚到 500 币',       '达到 500'),
    ('capital', 'bag',     'Goofy_low_res_pixel_art_game_b_2026-09-29T13-52-29.png', '小财主',     '累计赚到 2000 币',      '达到 2000'),
    ('capital', 'vault',   'Goofy_low_res_pixel_art_game_b_2026-09-29T13-49-32.png', '分红大户',   '持币过千，利息（没有）香', '达到 1000'),
    ('capital', 'dice',    'Goofy_low_res_pixel_art_game_b_2026-09-29T13-49-10.png', '首抽欧皇',   '第一次打开交易员图鉴',  '达到 1 次'),
    ('capital', 'cards',   'Goofy_low_res_pixel_art_game_b_2026-09-29T13-54-16.png', '图鉴庄家',   '抽了 20 次，包场了',    '达到 20 次'),
    # ── 交易员图鉴（#ffb800）──
    ('codex', 'spark',     'Goofy_low_res_pixel_art_game_b_2026-09-29T13-50-07.png', '开光',       '首张卡入库',            '达到 1 次'),
    ('codex', 'gem',       'Goofy_low_res_pixel_art_game_b_2026-09-29T13-55-29.png', '欧气初显',   '抽到第一张稀有(R)',     '达到 1 次'),
    ('codex', 'chosen',    'Goofy_low_res_pixel_art_game_b_2026-09-29T13-55-06.png', '天选之子',   '抽到第一张传说(SR)',    '达到 1 次'),
    ('codex', 'stamps',    'Goofy_low_res_pixel_art_game_b_2026-09-29T13-51-00.png', '集邮狂魔',   '集齐所有普通(N)卡 6 张', '达到 6 次'),
    ('codex', 'crown',     'Goofy_low_res_pixel_art_game_b_2026-09-29T13-51-16.png', '满星收藏家', '45 星全部点亮',         '达到 45 次'),
    # ── 涨停板敢死队（#ffb800）· 2026-09-30 第三批 ──
    ('limitup', 'board',   'Goofy_low_res_pixel_art_game_b_2026-09-30T02-08-20.png', '首板',       '第一次涨停，开盘即巅峰', '达到 1 次'),
    ('limitup', 'second',  'Goofy_low_res_pixel_art_game_b_2026-09-30T02-08-35.png', '二板换手',   '连续两天涨停，龙头气质', '达到 2 次'),
    ('limitup', 'pro',     'Goofy_low_res_pixel_art_game_b_2026-09-30T02-08-49.png', '打板专业户', '涨停 5 次，手法渐熟',    '达到 5 次'),
    ('limitup', 'demon',   'Goofy_low_res_pixel_art_game_b_2026-09-30T02-09-05.png', '连板妖股',   '涨停 10 次，市场总龙头', '达到 10 次'),
    ('limitup', 'god',     'Goofy_low_res_pixel_art_game_b_2026-09-30T02-09-19.png', '封神榜',     '涨停 20 次，入庙受香火', '达到 20 次'),
    # ── 散户的自我修养（#ff9f43）· 2026-09-30 第三批 ──
    ('retail', 'threeday', 'Goofy_low_res_pixel_art_game_b_2026-09-30T02-13-11.png', '三日游',     '连打卡 3 天，短线思维',  '达到 3 次'),
    ('retail', 'weekline', 'Goofy_low_res_pixel_art_game_b_2026-09-30T02-10-02.png', '周线级别',   '连打卡 7 天，拿成周线',  '达到 7 次'),
    ('retail', 'cut',      'Goofy_low_res_pixel_art_game_b_2026-09-30T02-12-55.png', '割肉离场',   '连续打卡断过，含泪止损', '达到 1 次'),
    ('retail', 'bomb',     'Goofy_low_res_pixel_art_game_b_2026-09-30T02-10-56.png', '爆仓体验',   '单日净热量超标 800 kcal', '达到 800 次'),
    ('retail', 'diamond',  'Goofy_low_res_pixel_art_game_b_2026-09-30T02-11-11.png', '价值投资',   '连打卡 100 天，时间的朋友', '达到 100 次'),
]

CATS = {'hold': ('持仓与套牢', '#00c896'), 'trade': ('盘中操作', '#ff3b47'),
        'capital': ('资本游戏', '#5ac8fa'), 'codex': ('交易员图鉴', '#ffb800'),
        'limitup': ('涨停板敢死队', '#ffb800'), 'retail': ('散户的自我修养', '#ff9f43')}
LOCKED_BG = '#2a3142'          # .badge.locked 的底（index.html / achievements.wxss 同值）
INK = (0x0a, 0x0e, 0x1a)       # 剪影色（现存 24×24 图标语言）
PAPER = (0x0d, 0x12, 0x1f)
PANEL = (0x16, 0x1b, 0x28)
BORDER = (0x25, 0x2c, 0x3e)
SIZE_SRC = 512
DISPLAY = 44                   # 建议放大后的图标渲染尺寸（现在 26）
DPR = 3
BLOCK = 64                     # 建议的 .b 方块边长（现在 48）


def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def load_font(size, bold=False):
    for p in (r'C:\Windows\Fonts\msyhbd.ttc' if bold else r'C:\Windows\Fonts\msyh.ttc',
              r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf',
              r'C:\Windows\Fonts\simsun.ttc'):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _thr(ch, lo=None, hi=None):
    """单通道阈值 → L 掩膜（'min' 表 v>lo 置 255；'max' 表 v<hi 置 255）"""
    if lo is not None:
        return ch.point(lambda v: 255 if v > lo else 0)
    return ch.point(lambda v: 255 if v < hi else 0)


def magenta_mask(im):
    """洋红底掩膜：R>140 & G<125 & (R−G)>70 & (B−G)>15，全用 PIL 通道运算（C 速度）"""
    R, G, B = im.split()
    return ImageChops.multiply(
        ImageChops.multiply(_thr(R, lo=140), _thr(G, hi=125)),
        ImageChops.multiply(_thr(ImageChops.subtract(R, G), lo=70),
                            _thr(ImageChops.subtract(B, G), lo=15)))


def fringe_mask(im):
    """混色边（洋红倾向残留）：(R−G)>40 & (B−G)>20 & G<150。
    金币暗金色 R 高 G 低但 B 也低，不会误判（上一版就是这么误报的）。"""
    R, G, B = im.split()
    return ImageChops.multiply(
        ImageChops.multiply(_thr(ImageChops.subtract(R, G), lo=40),
                            _thr(ImageChops.subtract(B, G), lo=20)),
        _thr(G, hi=150))


def luminance(rgb):
    def lin(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


FILL = (0x80, 0x80, 0x80)      # 量化前给透明区填的中性色（量化后按桶跳过，不当成主体色）


def color_stats(sprite, block_rgb):
    """把主体量化成 ≤32 色再统计（像素画本来就只有 8 色，量化近乎无损，且只跑 32 个桶）：
       · dom     —— 主体主色（出现最多的非空洞色）
       · nearbg  —— 占比「与所属赛道底色对比度 < 1.5:1」的不透明像素 ——
                    这才是「会不会糊进底色」的量化判据（韭菜绿配绿底就靠它现形）
    """
    flat = Image.new('RGB', sprite.size, FILL)
    flat.paste(sprite, (0, 0), sprite)
    q = flat.quantize(colors=32, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    hist = q.histogram()
    buckets = []
    for i, n in enumerate(hist):
        if not n:
            continue
        c = tuple(pal[i * 3:i * 3 + 3])
        if max(abs(c[k] - FILL[k]) for k in range(3)) <= 8:
            continue                      # 中性填色桶 = 透明空洞，不算主体
        buckets.append((n, c))
    total = sum(n for n, _ in buckets)
    if not total:
        return (0, 0, 0), 0.0, 1.0
    buckets.sort(reverse=True)
    dom, dom_n = buckets[0][1], buckets[0][0]
    near = sum(n for n, c in buckets if contrast(c, block_rgb) < 1.5)
    return dom, dom_n / float(total), near / float(total)


def watermark_connected(im, rect, pad=4):
    """水印是否与主体连通？在 rect 内取非背景像素做 4 连通洪泛，冲出 rect+pad 外圈即判定相连。
    只在 170×105 的小窗里跑 Python 循环，不吃性能。返回 (是否相连, rect 内非背景像素数)"""
    W, H = im.size
    x0, y0, x1, y1 = rect
    ex0, ey0 = max(0, x0 - pad), max(0, y0 - pad)
    ex1, ey1 = min(W, x1 + pad), min(H, y1 + pad)
    px = im.load()
    seeds = [(x, y) for y in range(y0, y1) for x in range(x0, x1)
             if not _is_magenta(px[x, y])]
    if not seeds:
        return False, 0
    seen = set()
    stack = list(seeds)
    while stack:
        x, y = stack.pop()
        if (x, y) in seen:
            continue
        seen.add((x, y))
        if x <= ex0 or y <= ey0 or x >= ex1 - 1 or y >= ey1 - 1:
            return True, len(seeds)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if ex0 <= nx < ex1 and ey0 <= ny < ey1 and (nx, ny) not in seen:
                if not _is_magenta(px[nx, ny]):
                    stack.append((nx, ny))
    return False, len(seeds)


def _is_magenta(p):
    r, g, b = p[:3]
    return r > 140 and g < 125 and (r - g) > 70 and (b - g) > 15


# 平台水印实测框（1024×1024 原图坐标系）：x 903..1013 / y 963..1013 = 111×51。
# ⭐ 这是量出来的，不是估的：跨 14 张原图逐张求「非洋红像素包围盒」，14 张完全一致 ⇒ 水印位置固定。
# ⚠️ 旧代码用 (W−170, H−105, W, H) = 170×105 的宽松框，会把「画得宽而低的」题材（如柱状图）
#    自身像素框进来 ⇒ 连通性判定误报「水印与主体相连」，整个流程卡死。
WATERMARK = (903, 963, 1014, 1014)
WM_MIN, WM_MAX = 500, 4000      # 水印像素数合理区间（越界=框到主体了）


def process(code, fname):
    p = os.path.join(SRC, fname)
    im = Image.open(p).convert('RGB')
    W, H = im.size
    print('  [%-9s] %dx%d' % (code, W, H))

    # --- 1. 水印 ---
    assert W == 1024 and H == 1024, '水印框只对 1024×1024 有效，换尺寸要重新量'
    conn, n = watermark_connected(im, WATERMARK)
    print('      水印区非背景像素 = %d，与主体连通 = %s' % (n, conn))
    assert not conn, '水印与主体像素相连 —— 禁止整块覆盖'
    assert WM_MIN <= n <= WM_MAX, '水印区像素数 %d 越界（框到主体了？）' % n
    bg = im.getpixel((W - 12, 12))
    assert _is_magenta(bg), '角落取样不是洋红底：%s' % (bg,)
    ImageDraw.Draw(im).rectangle(WATERMARK, fill=bg)
    conn2, n2 = watermark_connected(im, WATERMARK)
    print('      铺后残留 = %d（期望 0）' % n2)
    assert n2 == 0, '水印未清干净'

    # --- 2. 抠底：硬边二值 + 缩 1px 去混色边（⛔不羽化） ---
    a = ImageChops.invert(magenta_mask(im))          # 255 = 主体
    a = a.filter(ImageFilter.MinFilter(3))           # 缩 1px，吃掉抗锯齿混色边
    rgba = im.convert('RGBA')
    rgba.putalpha(a)

    fr = ImageChops.multiply(fringe_mask(im), a)     # 混色边只在主体内算
    fringe = fr.histogram()[255]
    pct = fringe * 100.0 / (W * H)
    print('      混色边残余 = %d px (%.3f%%)' % (fringe, pct))
    assert pct < 0.5, '混色边过多，抠图有问题'

    # --- 3. 收边 + 居中留白 + 导出 ---
    sprite = rgba.crop(a.getbbox())
    sw, sh = sprite.size
    side = int(max(sw, sh) * 1.10)
    canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    canvas.paste(sprite, ((side - sw) // 2, (side - sh) // 2))
    big = canvas.resize((SIZE_SRC, SIZE_SRC), Image.NEAREST)

    opaque = a.histogram()[255]
    print('      主体 %dx%d，画布占比 %.1f%% → 缩放后留白 10%% 即 %.1f%%'
          % (sw, sh, opaque * 100.0 / (W * H), sw * sh * 100.0 / (side * side)))
    assert opaque * 100.0 / (W * H) > 0.15, '主体占比过小（画太空），抠图/构图有问题'

    d132 = big.resize((DISPLAY * DPR, DISPLAY * DPR), Image.NEAREST)
    sil = Image.new('RGBA', big.size, INK + (0,))
    sil.putalpha(big.getchannel('A'))
    s132 = sil.resize((DISPLAY * DPR, DISPLAY * DPR), Image.NEAREST)

    os.makedirs(OUT, exist_ok=True)
    col_p = os.path.join(OUT, 'ach-%s.png' % code)
    d132.save(col_p, optimize=True)
    kb = os.path.getsize(col_p) / 1024.0
    print('      产出 assets/ach/%s  %dx%d  %.1f KB' % (os.path.basename(col_p), *d132.size, kb))
    assert kb < 40, '单张运行图 %.1f KB 过大（%dpx 纯色块不该这么肥，检查来源）' % (kb, d132.size[0])

    # 镜像到小程序仓库的素材源（上传云存储读的就是这份；一次写两边，杜绝手工 cp 漏拷）
    if os.path.isdir(os.path.dirname(MP_ACH_SRC)):
        os.makedirs(MP_ACH_SRC, exist_ok=True)
        mp_p = os.path.join(MP_ACH_SRC, 'ach-%s.png' % code)
        d132.save(mp_p, optimize=True)
        assert os.path.getsize(mp_p) == os.path.getsize(col_p), '镜像字节不一致：' + mp_p
        print('      镜像 assets_src/ach/%s' % os.path.basename(mp_p))
    else:
        print('      ⚠️ 小程序仓库不在（%s）⇒ 跳过镜像，上线前必须补跑' % os.path.dirname(MP_ACH_SRC))

    return {'code': code, 'big': big, 'sil': sil, 'd132': d132, 's132': s132,
            'sprite': sprite, 'sw': sw, 'sh': sh, 'kb': kb}


def tile(img132, bghex, alpha=1.0):
    """把 132 图贴到 132 方块上，alpha<1 时模拟 .badge.locked{opacity:.35}"""
    bg = hex2rgb(bghex)
    sq = Image.new('RGBA', (132, 132), bg + (255,))
    sq.alpha_composite(img132)
    flat = sq.convert('RGB')
    if alpha < 1.0:
        flat = Image.blend(Image.new('RGB', flat.size, bg), flat, alpha)
    return flat


def sheet_raw(items):
    """原始图 QC 板：直接看模型画了什么（抠图前的原貌）"""
    f1, f2 = load_font(16, True), load_font(12)
    CW, PAD, TOP = 372, 16, 46
    cols = 5
    rows = (len(items) + cols - 1) // cols
    w = PAD + cols * (CW + PAD)
    h = TOP + rows * (CW + 30 + PAD) + PAD
    S = Image.new('RGB', (w, h), PAPER)
    d = ImageDraw.Draw(S)
    d.text((PAD, 14), '原始图 QC —— 抠图前先人眼逐张过（只看有没有画错东西）',
           fill=(205, 218, 238), font=f1)
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x = PAD + c * (CW + PAD)
        y = TOP + r * (CW + 30 + PAD)
        raw = Image.open(it['raw']).convert('RGB').resize((CW, CW), Image.LANCZOS)
        S.paste(raw, (x, y))
        d.text((x, y + CW + 6), '%s  %s · %s' % (it['code'], it['title'], CATS[it['cat']][0]),
               fill=(235, 242, 252), font=f2)
    p = os.path.join(PROMO, '_ach_raw.png')
    S.save(p)
    return p


def sheet_cat(cat, items):
    """板块样图：每行一个成就，列 = 原色3× / 剪影3× / 未解锁3× / 1:1原色 / 1:1剪影"""
    name, color = CATS[cat]
    f_h, f1, f2, f3 = load_font(17, True), load_font(16, True), load_font(12), load_font(11)
    LBL, GAP, PAD, CW, SM = 168, 22, 20, 132, DISPLAY
    col = [PAD + LBL]
    for _ in range(2):
        col.append(col[-1] + CW + GAP)
    col.append(col[-1] + CW + GAP + 8)
    col.append(col[-1] + SM + GAP)
    W = col[-1] + SM + PAD
    ROWH = CW + 8 + SM
    H = 84 + len(items) * (ROWH + 20) + PAD
    B = Image.new('RGB', (W, H), PAPER)
    d = ImageDraw.Draw(B)
    d.text((PAD, 14), '板块样图 · %s（%s）' % (name, color), fill=(235, 242, 252), font=f_h)
    d.text((PAD, 38), '图标现尺寸 26px → 建议 44px；方块 48 → 64。下面是 1:1 真尺寸，请按这个判',
           fill=(130, 148, 174), font=f3)
    heads = ['原色 · 3×', '剪影 · 3×', '未解锁 · 3×']
    for i, t in enumerate(heads):
        d.text((col[i], 58), t, fill=(190, 206, 230), font=f2)
    d.text((col[3], 58), '1:1 原色', fill=(190, 206, 230), font=f2)
    d.text((col[4], 58), '1:1 剪影', fill=(190, 206, 230), font=f2)
    for i, it in enumerate(items):
        y = 84 + i * (ROWH + 20)
        d.text((PAD, y + 6), it['code'], fill=(235, 242, 252), font=f1)
        d.text((PAD, y + 30), it['title'], fill=(190, 206, 230), font=f2)
        d.text((PAD, y + 48), it['desc'], fill=(120, 138, 164), font=f3)
        d.text((PAD, y + 64), it['cond'], fill=(120, 138, 164), font=f3)
        cr = contrast(it['dom'], hex2rgb(color))
        nb = it['nearbg'] * 100
        d.text((PAD, y + 80), '主色 #%02x%02x%02x · 对比 %.2f:1' % (it['dom'] + (cr,)),
               fill=(0x9c, 0xaa, 0xc0) if cr >= 2.0 else (0xff, 0xd0, 0x80), font=f3)
        d.text((PAD, y + 96), '近底占比 %.0f%%' % nb,
               fill=(0xff, 0x8a, 0x8a) if nb >= 25 else (0x9c, 0xaa, 0xc0), font=f3)
        tiles = [tile(it['d132'], color), tile(it['s132'], color), tile(it['d132'], LOCKED_BG, 0.35)]
        for ci, t in enumerate(tiles):
            B.paste(t, (col[ci], y))
        for ci, t in enumerate((it['d132'], it['s132'])):
            small = t.resize((SM, SM), Image.LANCZOS).convert('RGB')
            B.paste(small, (col[3 + ci], y + CW + 8))
        d.rectangle([col[3], y, col[4] + SM, y + CW + 8 + SM], outline=BORDER)
    p = os.path.join(PROMO, '_ach_cat_%s.png' % cat)
    B.save(p)
    return p


def main():
    src = open(os.path.join(REPO, 'index.html'), encoding='utf-8', errors='replace').read()
    for _, color in CATS.values():
        assert color in src, '赛道色 %s 已不在 index.html' % color
    assert LOCKED_BG in src
    print('== 配色真源核对 OK ==')

    items = []
    print('== 逐张处理 + 贴底色可读性体检 ==')
    for cat, code, fname, title, desc, cond in ITEMS:
        print('-- %s/%s' % (cat, code))
        d = process(code, fname)
        dom, dompct, nearbg = color_stats(d.pop('sprite'), hex2rgb(CATS[cat][1]))
        print('      主色 #%02x%02x%02x(%.0f%%)  与底色 %s 对比 %.2f:1  近底像素占比 %.1f%%'
              % (dom + (dompct * 100, CATS[cat][1], contrast(dom, hex2rgb(CATS[cat][1])),
                        nearbg * 100)))
        d.update({'cat': cat, 'title': title, 'desc': desc, 'cond': cond,
                  'dom': dom, 'nearbg': nearbg,
                  'raw': os.path.join(SRC, fname)})
        items.append(d)

    print('== 生成预览板 ==')
    for f in (sheet_raw,):
        p = f(items)
        print('   %-26s %5d KB  %s' % (os.path.basename(p), os.path.getsize(p) // 1024,
                                       Image.open(p).size))
    for cat in CATS:
        sub = [it for it in items if it['cat'] == cat]
        if not sub:
            continue
        p = sheet_cat(cat, sub)
        print('   %-26s %5d KB  %s' % (os.path.basename(p), os.path.getsize(p) // 1024,
                                       Image.open(p).size))
    tot = sum(it['kb'] for it in items)
    print('== 运行图体积 ==')
    print('   %d 张合计 %.1f KB（均价 %.1f KB/张）；满 30 项外推 ≈ %.0f KB'
          % (len(items), tot, tot / len(items), tot / len(items) * 30))
    print('DONE')


if __name__ == '__main__':
    main()
