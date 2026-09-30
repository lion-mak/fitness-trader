# -*- coding: utf-8 -*-
"""probe_ach_art.py —— 成就像素画落地后的**真渲染**验收（当前 30 张 / 6 赛道口径）。

量四件事，都从真渲染的像素/几何里取，不靠眼看：
  1. 几何：.badge .b = 64×64、.ach-ic = 44×44（两端同值，小程序侧另有 rect 闸对拍）
  2. 锁态剪影：锁着的 img 必须 filter:brightness(0)（→ 纯黑剪影），已解锁的必须**没有** filter
  3. 对比度：把 .b 截图，取「方块底色」与「最暗像素」算对比 —— 这条是「剪影看不看得见」的量化判据，
     老口径（深底 + 深图标 + 整卡 0.35）实测只有 1.13:1，等于空方块
  4. 出图：每个赛道一张「混态」+ 一张「全解锁」+ 一张赛道头（给 Mak 判可读性）

用法：<venv>/python.exe promo/probe_ach_art.py
输出：promo/_ach_pwa_<cat>.png / _ach_pwa_all_<cat>.png / _ach_cat_<cat>.png / _ach_art_report.txt
⚠️ 脚本名**不带**下划线是刻意的：`.gitignore` 的 `promo/_*.py` 只挡一次性脚本，
   而这是**每次换成就图必跑的常规闸**，必须入库（2026-09-30 从 `_probe_ach_art.py` 改名）。
   产物仍带 `_` 前缀 ⇒ 报告与截图不入库（那是生成物）。
"""
import io
import os
import sys
from collections import Counter

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
INDEX = os.path.join(ROOT, 'index.html')
OUT = []


def p(s=''):
    OUT.append(s)
    print(s)


def lum(rgb):
    def lin(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# 解锁 leek/untie/tryorder，其余留锁 —— 这样同一个赛道卡里既有彩图也有剪影，一眼能对比
# ⚠️ 这里填的是**成就 id**（state.ach 的键），不是 icon 名：试单的 id 是 tryorder、icon 是 pen。
UNLOCK = ['leek', 'untie', 'tryorder']

# 「已有像素画」的成就 id —— ⭐ 从 index.html **自动派生**，⛔ 不再手抄：
#   判定 = 该成就的 icon 出现在 ACH_ART 里。加图只需改 index.html 的 ACH_ART，本脚本零改动。
#   手抄的代价（2026-09-30 改）：每批加图都要改这个列表，且 id 与 icon 不同名时极易写错
#   （试单 tryorder/pen、半仓 halfpos/half、高频 hft/lightning、回口小肉 smallmeat/coin、
#    小财主 richboy/bag、分红大户 dividend/vault、首抽 firstgacha/dice、图鉴庄家 gachaking/cards、
#    开光 open/spark、欧气 rarefind/gem、天选 chosen/chosen、集邮 fulln/stamps、满星 maxstar/crown、
#    首板 firstboard/board、二板 secondboard/second、打板 protrader/pro、封神 godmode/god、
#    割肉 cutmeat/cut、爆仓 blowup/bomb、价值投资 valueinvest/diamond）。
import re
_SRC = io.open(INDEX, encoding='utf-8', errors='replace').read()
ACH_ART = re.findall(r"'([a-z]+)'", re.search(r'const ACH_ART = \[(.*?)\];', _SRC, re.S).group(1))
_A = _SRC[_SRC.find('const ACHIEVEMENTS'):]
_A = _A[:_A.find('\n];')]
ALL_UNLOCK = [i for i, ic in re.findall(r"id:'([a-z]+)'.*?icon:'([a-z]+)'", _A) if ic in ACH_ART]
assert len(ALL_UNLOCK) == len(ACH_ART), \
    '有像素画的成就数与 ACH_ART 不等：%d vs %d' % (len(ALL_UNLOCK), len(ACH_ART))

from playwright.sync_api import sync_playwright   # noqa: E402

LAUNCH = [{"channel": "msedge"},
          {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"}]


def launch(pw):
    last = None
    for kw in LAUNCH:
        try:
            return pw.chromium.launch(**kw)
        except Exception as e:            # noqa: BLE001
            last = e
    raise SystemExit('无可用浏览器内核：%s' % last)


GEO_JS = """(unlock) => {
  const badges = [...document.querySelectorAll('#page-achievements .badge')];
  const rows = badges.map((el) => {
    const b = el.querySelector('.b');
    const im = el.querySelector('img.ach-ic');
    const svg = el.querySelector('svg');
    const br = b.getBoundingClientRect();
    const ir = im ? im.getBoundingClientRect() : null;
    const cs = im ? getComputedStyle(im) : null;
    return {
      locked: el.classList.contains('locked'),
      name: el.querySelector('.lbl').textContent,
      b: [+br.width.toFixed(1), +br.height.toFixed(1)],
      box: getComputedStyle(b).backgroundColor,
      art: !!im,
      iw: ir ? +ir.width.toFixed(1) : (svg ? +svg.getBoundingClientRect().width.toFixed(1) : null),
      filt: cs ? cs.filter : null,
      src: im ? im.getAttribute('src') : null,
    };
  });
  return rows;
}"""


def main():
    p('=' * 90)
    p('成就像素画落地验收（真渲染）')
    p('=' * 90)

    with sync_playwright() as pw:
        br = launch(pw)
        pg = br.new_page(viewport={"width": 430, "height": 930}, device_scale_factor=3)
        pg.goto('file:///' + INDEX.replace('\\', '/'))
        pg.wait_for_timeout(800)
        st = pg.evaluate('() => JSON.parse(JSON.stringify(defaultState()))')
        st['user']['weight'] = 72.8
        st['ach'] = {k: True for k in UNLOCK}
        pg.evaluate("(s) => { localStorage.setItem('jianpan_v2', JSON.stringify(s)); }", st)
        pg.reload()
        pg.wait_for_timeout(1400)
        pg.evaluate('() => { showAchievements(); }')
        pg.wait_for_timeout(900)

        rows = pg.evaluate(GEO_JS, UNLOCK)

        # ① 几何
        p()
        p('【几何】')
        bad = 0
        for r in rows:
            if r['b'] != [64.0, 64.0]:
                bad += 1
                p('  ✗ %s 方块 %s ≠ 64×64' % (r['name'], r['b']))
        if not bad:
            p('  ✅ %d 个 .badge .b 全部 64×64' % len(rows))
        art = [r for r in rows if r['art']]
        p('  有像素画的格子 = %d 个（应 %d）；其中 44×44 = %d 个'
          % (len(art), len(ACH_ART), sum(1 for r in art if r['iw'] == 44.0)))
        assert len(art) == len(ACH_ART), \
            '有图的格子数不对：%d（ACH_ART 有 %d 项）' % (len(art), len(ACH_ART))
        assert all(r['iw'] == 44.0 for r in art), '像素画图标尺寸不是 44'
        noart = [r for r in rows if not r['art']]
        assert all(r['iw'] == 34.0 for r in noart), '线稿兜底图标尺寸不是 34'
        p('  没图的格子 = %d 个%s' % (len(noart),
            '（30 项已全有像素画 ⇒ 线稿只作云图加载失败的兜底）' if not noart
            else '，线稿全部 34×34'))

        # ② 剪影口径
        p()
        p('【剪影口径】')
        lock_art = [r for r in art if r['locked']]
        open_art = [r for r in art if not r['locked']]
        p('  锁着的有图格子 = %d / 已解锁 = %d（种了 %d 个 id 的存档）'
          % (len(lock_art), len(open_art), len(UNLOCK)))
        assert len(open_art) == len(UNLOCK), '已解锁数不对：%d（应 %d）' % (len(open_art), len(UNLOCK))
        assert len(lock_art) == len(ACH_ART) - len(UNLOCK), '锁着的图数不对：%d' % len(lock_art)
        assert all(r['filt'] == 'brightness(0)' for r in lock_art), \
            '锁态不是 brightness(0)：%s' % [r['filt'] for r in lock_art]
        assert all(r['filt'] == 'none' for r in open_art), \
            '已解锁不该有 filter：%s' % [r['filt'] for r in open_art]
        p('  ✅ 锁态 %d 个全部 filter:brightness(0)（纯黑剪影）；已解锁 %d 个 filter:none（彩图）'
          % (len(lock_art), len(open_art)))
        p('  ✅ 锁态方块底色 = 赛道色（不再退回 #2a3142）：%s'
          % ', '.join(sorted({r['box'] for r in lock_art})))

        # ③ 对比度（截 .b 元素本身，按 deviceScaleFactor 的真实像素算）
        p()
        p('【剪影 vs 方块底色的对比度】')
        els = pg.query_selector_all('#page-achievements .badge')
        seen = set()
        for i, el in enumerate(els):
            r = rows[i]
            if not r['art'] or r['name'] in seen:
                continue
            seen.add(r['name'])
            raw = el.query_selector('.b').screenshot()
            im = Image.open(io.BytesIO(raw)).convert('RGB')
            px = list(im.getdata())
            # 方块底色 = 众数色（圆角外的角像素是卡片的 --panel，取 (4,4) 会量错 —— 踩过）。
            # 主体只占方块面积约 1/3（44px 图里还有 10% 内边距），故众数必是底色。
            box = Counter(px).most_common(1)[0][0]
            # 剪影 = 方块里最暗的那撮像素（取 0.5% 分位，避开描边抗锯齿的孤点）
            px.sort(key=lum)
            dark = px[max(0, len(px) // 200)]
            cr = contrast(box, dark)
            tag = '锁·剪影' if r['locked'] else '已解锁'
            flag = '' if (not r['locked'] or cr >= 3.0) else '   <<< 剪影太糊'
            p('  %-10s %-8s 底 #%02x%02x%02x  暗部 #%02x%02x%02x  对比 %.2f:1%s'
              % (r['name'], tag, box[0], box[1], box[2], dark[0], dark[1], dark[2], cr, flag))
            if r['locked']:
                assert cr >= 3.0, '锁态剪影与底色对比 %.2f:1 < 3.0，看不见' % cr

        # ④ 出图（六个赛道整卡 —— 混态：已出图的板块有解锁有锁）
        p()
        p('【出图 · 混态】')
        # ⚠️ 成就页有 **6** 个赛道（30 项 / 每赛道 5 项），不是 4 —— 后两个赛道仍是线稿兜底，
        #    一起截出来才能看「像素画与线稿混排」协不协调。
        CATS = [('持仓与套牢', 'hold'), ('盘中操作', 'trade'), ('资本游戏', 'capital'),
                ('交易员图鉴', 'codex'), ('涨停板敢死队', 'limitup'), ('散户的自我修养', 'retail')]
        cats = pg.query_selector_all('#page-achievements .ach-cat')
        assert len(cats) == 6, '赛道卡数不对：%d' % len(cats)
        for i, (cat, key) in enumerate(CATS):
            path = os.path.join(HERE, '_ach_pwa_%s.png' % key)
            cats[i].screenshot(path=path)
            p('  %-12s → %s  %s  %.0f KB'
              % (cat, os.path.basename(path), Image.open(path).size,
                 os.path.getsize(path) / 1024))

        # ④b 全解锁出图：判「彩图贴在赛道色上糊不糊」只能看这个
        #     （混态里后两板块全是剪影，看不出彩图与底色的关系）
        p()
        p('【出图 · %d 张全解锁（判彩色主体 vs 赛道底色的可读性）】' % len(ACH_ART))
        st2 = pg.evaluate('() => JSON.parse(JSON.stringify(defaultState()))')
        st2['user']['weight'] = 72.8
        st2['ach'] = {k: True for k in ALL_UNLOCK}
        pg.evaluate("(s) => { localStorage.setItem('jianpan_v2', JSON.stringify(s)); }", st2)
        pg.reload()
        pg.wait_for_timeout(1400)
        pg.evaluate('() => { showAchievements(); }')
        pg.wait_for_timeout(900)
        unlocked = pg.evaluate(
            """() => [...document.querySelectorAll('#page-achievements .badge')]
                     .filter((e) => e.querySelector('img.ach-ic'))
                     .filter((e) => e.querySelector('img.ach-ic').style.filter !== 'brightness(0)')
                     .length""")
        p('  渲成彩图的有图格子 = %d（应 %d）' % (unlocked, len(ACH_ART)))
        assert unlocked == len(ACH_ART), '全解锁后仍有剪影：%d（应 %d）' % (unlocked, len(ACH_ART))
        cats2 = pg.query_selector_all('#page-achievements .ach-cat')
        for i, (cat, key) in enumerate(CATS):
            path = os.path.join(HERE, '_ach_pwa_all_%s.png' % key)
            cats2[i].screenshot(path=path)
            p('  %-12s → %s  %s  %.0f KB'
              % (cat, os.path.basename(path), Image.open(path).size,
                 os.path.getsize(path) / 1024))
        br.close()

    p()
    p('RESULT=OK')
    io.open(os.path.join(HERE, '_ach_art_report.txt'), 'w', encoding='utf-8').write('\n'.join(OUT))


main()
