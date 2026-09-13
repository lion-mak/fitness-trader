from PIL import Image
import os

src = r'E:\WorkBuddy\jianpan-ghpages\promo\pixel\16_bit_pixel_art__wide_establi_2026-09-13T13-36-05.png'
im = Image.open(src).convert('RGB')
W, H = im.size
print('size:', W, H)
px = im.load()

bp = []
for y in range(H-140, H):
    for x in range(W-260, W):
        r,g,b = px[x,y]
        if max(r,g,b) > 60:
            bp.append((x,y,r,g,b))

if bp:
    xs=[p[0] for p in bp]; ys=[p[1] for p in bp]
    bb=(min(xs),min(ys),max(xs),max(ys))
    print('wm bbox:', bb, 'count:', len(bp))

    for name,(xa,xb,ya,yb) in [
        ('top-left',(0,260,0,80)),
        ('top-right',(W-260,W,0,80)),
        ('bot-left',(0,260,H-80,H)),
    ]:
        cnt=0
        for y in range(ya,yb):
            for x in range(xa,xb):
                r,g,b=px[x,y]
                if max(r,g,b)>60: cnt+=1
        print('  other-corner', name, 'bright pixels:', cnt)

    x0=max(0,bb[0]-12); y0=max(0,bb[1]-10)
    x1=min(W,bb[2]+14); y1=min(H,bb[3]+10)
    samples=[]
    for sy in range(0,25):
        for sx in range(W-40, W):
            samples.append(px[sx,sy])
    n=len(samples)
    avg=tuple(int(sum(c[i] for c in samples)/n) for i in range(3))
    print('cover rect:',(x0,y0,x1,y1),'fill avg:',avg)
    feather=18
    for y in range(y0,y1):
        for x in range(x0,x1):
            d=min(x-x0,x1-1-x,y-y0,y1-1-y)
            if d>=feather:
                px[x,y]=avg
            else:
                a=(d+1)/(feather+1); o=im.getpixel((x,y))
                px[x,y]=tuple(int(avg[i]*a+o[i]*(1-a)) for i in range(3))
    dst=os.path.join(os.path.dirname(src),'jhyx_full_clean.png')
    im.save(dst)
    print('saved ->', dst, os.path.getsize(dst),'bytes')
else:
    print('no watermark detected')