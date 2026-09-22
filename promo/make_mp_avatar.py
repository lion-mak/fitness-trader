# -*- coding: utf-8 -*-
"""
生成微信小程序专用头像（箭头完整版）。

为什么需要：assets/icon-*.png 是 PWA 图标。微信小程序头像按圆形展示，
而 icon 的图案铺满整个方形画布，裁圆会削掉最外圈。实测溢出量：
    红箭头 max_r = 1.056 R   绿箭头 1.055 R   哑铃 1.168 R
    （R = 内切圆半径）
红/绿箭头是「涨/跌」的语义核心，尖端被削掉会损失方向感；哑铃是装饰主体，
四角被轻切看不出来。所以策略是：缩放到「箭头 100% 进圆内」为止，不为了
哑铃那 0.8% 的边角把整个图标缩得很小（那样小尺寸下反而更弱）。

实测缩放 0.91：箭头 max_r 0.96 R（完全进圆），哑铃 1.063 R（四角轻切，
不可察觉），图标仍保持饱满。

做法：
  1. 抠图案层。判据 = 原图不透明(a>200) 且亮度 V=max(r,g,b)/255 > 0.20。
     ⚠️ 必须同时要求 a>200 —— 四角是「白色 + alpha=0」，只看亮度会误判。
  2. 按箭头半径迭代缩放，居中合成到同色满幅底（裁圆后圆外同色，不露白）。
  3. 不缩放整块原图 —— 原图底色带渐变，整块缩小会露出可见小方框。

用法： python promo/make_mp_avatar.py
输出： assets/wechat-mp-avatar-512.png + promo/_avatar_cmp.png
"""
from PIL import Image, ImageDraw
import math, os

SRC    = "assets/icon-master-1024.png"
OUT    = "assets/wechat-mp-avatar-512.png"
OUT144 = "assets/wechat-mp-avatar-144.png"   # 微信后台建议尺寸
PREV   = "promo/_avatar_cmp.png"
SIZE   = 512
OUT144_SIZE = 144
SEM_SAFE = 0.96     # 箭头最大半径的上限（× 内切圆半径）
V_LO   = 0.20       # 亮度下界，低于此视为背景
V_HI   = 0.30       # 亮度上界，>= 此为实心图案，其间做软边
MARGIN = 6          # 源图最外圈丢弃像素数（去除生成图的边缘残留）

def edge_bg(im):
    W,H = im.size; px = im.load(); s=[]
    for x in range(W//4, W*3//4, 2):
        for y in (4,5,H-5,H-4):
            r,g,b,a = px[x,y]
            if a>200: s.append((r,g,b))
    for y in range(H//4, H*3//4, 2):
        for x in (4,5,W-5,W-4):
            r,g,b,a = px[x,y]
            if a>200: s.append((r,g,b))
    return tuple(sum(c[i] for c in s)//len(s) for i in range(3))

def is_arrow(r,g,b):
    if r>140 and g<110 and b<110: return "red"
    if g>110 and r<110 and g>b:   return "green"
    return None

def build_art(im):
    """抠图案层，同时返回箭头像素坐标（用于算缩放）

    MARGIN：源图最外 6px 一律丢弃。ImageGen 出图时最外一列/一行会留
    1px 的浅色边缘残留（实测 x=0 有一条竖线 + 一个红点），它会在缩放后
    变成新头像里一条可见的淡竖线。哑铃主体离边缘 >100px，丢 6px 无影响。
    """
    W,H = im.size; px = im.load()
    art = Image.new("RGBA",(W,H),(0,0,0,0)); ap = art.load()
    arrows = []
    for y in range(H):
        if y < MARGIN or y >= H-MARGIN: continue
        for x in range(MARGIN, W-MARGIN):
            r,g,b,a = px[x,y]
            if a <= 200: continue
            v = max(r,g,b)/255.0
            if v < V_LO: continue
            al = 255 if v >= V_HI else int((v-V_LO)*255.0/(V_HI-V_LO))
            ap[x,y] = (r,g,b, min(a, al))
            if is_arrow(r,g,b): arrows.append((x,y))
    return art, arrows

def max_r_of(pts, W, scale=1.0):
    if not pts: return 0.0
    cx=cy=(W-1)/2.0
    return max(math.hypot(x-cx,y-cy) for x,y in pts)*scale

src = Image.open(SRC).convert("RGBA")
bg  = edge_bg(src)
art, arrows = build_art(src)
W,H = art.size; R = W/2.0
print("底色 =", bg)
print("箭头像素 %d 个；箭头原始 max_r / R = %.4f" % (len(arrows), max_r_of(arrows,W)/R))

# 迭代求缩放：箭头 max_r × s <= SEM_SAFE × R
s = 1.0
for _ in range(80):
    if max_r_of(arrows,W,s)/R <= SEM_SAFE: break
    s *= 0.99
print("缩放 s = %.4f" % s)

def max_r_all(im):
    """所有不透明图案像素的最大半径（判断哑铃溢出）"""
    w,h = im.size; px = im.load(); cx=cy=(w-1)/2.0; m=0
    for y in range(0,h,2):
        for x in range(0,w,2):
            if px[x,y][3] > 60:
                m = max(m, math.hypot(x-cx,y-cy))
    return m

# ⚠️ s 的语义 = 「图案宽度 / 画布宽度」，所以贴到画布上的尺寸是 SIZE*s。
# 不要写成源尺寸 W*s —— 那会让图案超出画布被裁掉。
nw = max(1,int(round(SIZE*s))); nh = max(1,int(round(SIZE*s)))
t = art.resize((nw,nh), Image.LANCZOS)
print("箭头 max_r = %.3f R (上限 %.2f)  图案整体 max_r = %.3f R"
      % (max_r_of(arrows,W,s)/R, SEM_SAFE, max_r_all(t)/(SIZE/2.0)))
print("   画布内切圆半径 = %d px；图案贴入尺寸 = %dx%d (占画布 %.1f%%)"
      % (SIZE//2, nw, nh, 100.0*nw/SIZE))

canvas = Image.new("RGBA",(SIZE,SIZE), bg+(255,))
canvas.alpha_composite(t, ((SIZE-nw)//2, (SIZE-nh)//2))
canvas.convert("RGB").save(OUT, "PNG", optimize=True)
print("已写出", OUT, os.path.getsize(OUT), "bytes")

# 微信后台建议 144x144、png、<=2M。从同一张 512 直接降采样（不要从源图另走一遍，
# 免得两版视觉不一致）。
small = canvas.convert("RGB").resize((OUT144_SIZE,OUT144_SIZE), Image.LANCZOS)
small.save(OUT144, "PNG", optimize=True)
print("已写出", OUT144, "%dx%d" % small.size, os.path.getsize(OUT144), "bytes")

# ---- 自检：边缘必须全是底色（MARGIN 修复的回归守卫）；箭头必须落在圆内 ----
sm_px = small.load()
edge_bad = 0
for x in range(OUT144_SIZE):
    for y in range(0, 7):
        if max(abs(sm_px[x,y][i]-bg[i]) for i in range(3)) > 18: edge_bad += 1
    for y in range(OUT144_SIZE-7, OUT144_SIZE):
        if max(abs(sm_px[x,y][i]-bg[i]) for i in range(3)) > 18: edge_bad += 1
print("[自检] 144 版上下边缘 7px 内的异色像素 = %d (应为 0，非 0 说明源图边缘残留又回来了)" % edge_bad)
# 箭头在 512 画布上的半径 = 源尺度半径 × (贴入尺寸/源尺寸)。
# 不要再乘 s —— s 是「图案宽度/画布宽度」，乘进去会得到错误的大值。
r512 = max_r_of(arrows, W) * (nw / float(W))
print("[自检] 箭头在 512 画布上 max_r = %.1f px = %.3f R（应 < 1.00）"
      % (r512, r512/(SIZE/2.0)))
print("[自检] 降采样到 144 后归一化半径不变 = %.3f R" % (r512/(SIZE/2.0)))

def circle(im, size, bgc=(128,128,128)):
    s2 = im.convert("RGBA").resize((size,size), Image.LANCZOS)
    out = Image.new("RGBA",(size,size), bgc+(255,))
    m = Image.new("L",(size*4,size*4),0)
    ImageDraw.Draw(m).ellipse((0,0,size*4-1,size*4-1), fill=255)
    out.paste(s2,(0,0),m.resize((size,size), Image.LANCZOS))
    return out.convert("RGB")

CELL=150; PAD=13
sheet = Image.new("RGB",(4*CELL+5*PAD, 3*CELL+4*PAD),(236,238,242))
rows = [("PWA icon-192", Image.open("assets/icon-192.png")),
        ("mp 512",        Image.open(OUT)),
        ("mp 144",        Image.open(OUT144))]
for i,(name,im) in enumerate(rows):
    y = PAD + i*(CELL+PAD)
    sheet.paste(im.convert("RGB").resize((CELL,CELL), Image.LANCZOS), (PAD, y))
    sheet.paste(circle(im,CELL),                     (PAD*2+CELL, y))
    sheet.paste(circle(im,64).resize((CELL,CELL), Image.NEAREST), (PAD*3+CELL*2, y))
    sheet.paste(circle(im,40).resize((CELL,CELL), Image.NEAREST), (PAD*4+CELL*3, y))
sheet.save(PREV)
print("已写出", PREV, "（行=旧PWA图标/mp512/mp144；列=原图/裁圆150/裁圆64/裁圆40）")
