import os
from PIL import Image, ImageDraw, ImageFont

D = r'E:\WorkBuddy\jianpan-ghpages\promo'
BG = (20, 23, 28)
FG = (232, 236, 242)
SUB = (150, 162, 178)


def font(sz, bold=False):
    for p in ([r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\msyh.ttc']
              if bold else [r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\msyhbd.ttc']):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


SRC = [('v2752_持仓页.png', '2.7.52 · 系列前', '对照'),
       ('v2753_持仓页.png', '2.7.53 · 系列中', '对照'),
       ('v2754_持仓页.png', '2.7.54 · 当前', '对照')]

M, GAP, LABH = 22, 20, 52


def strip(crop_box, out_name, title):
    ims = []
    for f, lab, _ in SRC:
        im = Image.open(os.path.join(D, f)).convert('RGB')
        w, h = im.size
        if crop_box[3] is None:
            box = (crop_box[0], h - crop_box[1], crop_box[2], h)
        else:
            box = crop_box
        ims.append((im.crop(box), lab))
    cw = ims[0][0].size[0]
    ch = ims[0][0].size[1]
    W = M * 2 + cw * 3 + GAP * 2
    H = M + 30 + LABH + ch + M
    out = Image.new('RGB', (W, H), BG)
    dr = ImageDraw.Draw(out)
    dr.text((M, M + 6), title, font=font(26, True), fill=FG)
    y = M + 30 + LABH
    for i, (im, lab) in enumerate(ims):
        x = M + i * (cw + GAP)
        out.paste(im, (x, y))
        dr.rectangle([x - 1, y - 1, x + cw, y + ch], outline=(60, 68, 80))
        dr.text((x, y - 40), lab, font=font(24, True), fill=FG)
    out.save(os.path.join(D, out_name))
    print('saved', out_name, out.size)


strip((0, 0, 974, 1290), 'v2754_对比_上半区.png',
      'P1  账户总览 Hero + 缺口评级   ← 2.7.52 / 2.7.53 / 2.7.54')
strip((0, 168, 974, None), 'v2754_对比_底栏.png',
      'P2  底部 tab 栏（图标翻转 + 等宽居中）   ← 2.7.52 / 2.7.53 / 2.7.54')
