# -*- coding: utf-8 -*-
"""批量截图 + 合成 1920x1080 宣传海报（一次跑完，不做中间调试）"""
import os, subprocess, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PY = r"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"

PAGES = ['market', 'trade', 'holdings', 'leaderboard', 'achievements']


def shot(page, out):
    import shutil
    prof = os.path.join(HERE, '_edgeprofile')
    shutil.rmtree(prof, ignore_errors=True)          # 每次全新区，杜绝 localStorage 残留污染
    url = "file:///E:/WorkBuddy/jianpan-ghpages/_demo.html?p=" + page
    cmd = [EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-sandbox',
           '--user-data-dir=' + prof.replace('\\', '/'),
           '--force-device-scale-factor=2', '--virtual-time-budget=8000',
           '--window-size=430,2600', '--screenshot=' + out.replace('\\', '/'), url]
    subprocess.run(cmd, capture_output=True, timeout=180)
    return os.path.exists(out)


def process(src, dst, card_h):
    """裁掉底部空白 + 底部渐隐到背景色"""
    from PIL import Image
    im = Image.open(src).convert('RGB')
    w, h = im.size
    px = im.load()
    bg = px[w - 3, h - 3]
    last = 0
    for y in range(h - 1, -1, -1):
        for x in range(0, w, 6):
            p = px[x, y]
            if abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > 26:
                last = y
                break
        if last:
            break
    ch = min(h, card_h)
    im = im.crop((0, 0, w, ch))
    w2, h2 = im.size
    px2 = im.load()
    fade = 150
    for i in range(fade):
        y = h2 - fade + i
        a = i / float(fade)
        for x in range(w2):
            p = px2[x, y]
            px2[x, y] = (int(p[0] * (1 - a) + bg[0] * a),
                         int(p[1] * (1 - a) + bg[1] * a),
                         int(p[2] * (1 - a) + bg[2] * a))
    im.save(dst)
    return (w2, h2)


if __name__ == '__main__':
    CARD_H = 1450                     # 设备像素（dpr=2，约 880 CSS px）
    info = {}
    for p in PAGES:
        raw = os.path.join(HERE, 'raw_%s.png' % p)
        crd = os.path.join(HERE, 'card_%s.png' % p)
        ok = shot(p, raw)
        if not ok:
            print('FAIL', p)
            continue
        sz = process(raw, crd, CARD_H)
        info[p] = sz
        print('%-14s %s -> card %dx%d' % (p, 'ok', sz[0], sz[1]))
    json.dump({k: list(v) for k, v in info.items()},
              open(os.path.join(HERE, 'cards.json'), 'w'), indent=1)
    print('done')
