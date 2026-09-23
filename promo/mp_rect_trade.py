# -*- coding: utf-8 -*-
"""
mp_rect_trade.py —— 交易页元素级对拍：同一组选择器在两端量 rect，逐项比位置与尺寸。

与 mp_rect_compare.py（持仓页）同机制，仅换交易页的选择器与页面路由。
两端视口都是 430 CSS px 逻辑宽，所以 rect 可以直接相减，不用换算。
（需先 cli auto 拉起 9420；arm 后 sleep 6 再跑，详见 jianpan-mp-port 技能）

输出：promo/_rect_trade_cmp.txt
"""
import io
import json
import os
import subprocess
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
INDEX = os.path.join(ROOT, "index.html")
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NM = r"C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules"

VW, VH = 430, 930
ROUTE = "/pages/trade/trade"

# 两端同源选择器（wxml 照搬了 PWA 的 class / id）
SEL = [
    ".pagetitle", ".pagetitle .k", ".pagetitle .t",
    "#intraday-chart", ".intraday-legend", ".jp-state-pill",
    ".addbtns", ".addbtn",
    ".sector-card", ".sector-header", ".sector-net-badge", ".sector-grid",
    ".sector-col.sector-short", ".sector-col.sector-long", ".sector-item",
    "#t-list", ".entry",
]

OUT = []


def p(s=""):
    OUT.append(s)
    print(s)


def node_side():
    env = dict(os.environ)
    env["NODE_PATH"] = NM
    env["PATH"] = os.path.dirname(NODE) + ";" + env.get("PATH", "")
    pr = subprocess.run(
        [NODE, os.path.join(HERE, "_rect_mp.js"), json.dumps(SEL), ROUTE],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env, timeout=300)
    lines = (pr.stdout or "").splitlines()
    line = [l for l in lines if l.startswith("RECT_JSON=")]
    vp = [l for l in lines if l.startswith("VIEWPORT=")]
    sy = [l for l in lines if l.startswith("SYS=")]
    if not line:
        raise SystemExit("小程序侧测量失败：\n" + (pr.stdout or "")[-1500:] + "\n" + (pr.stderr or "")[-1500:])
    return (json.loads(line[0][len("RECT_JSON="):]),
            (vp[0][len("VIEWPORT="):] if vp else "{}"),
            json.loads(sy[0][len("SYS="):]) if sy else {})


def pwa_side(sbh, vw):
    """sbh: 小程序的状态栏高度。PWA 在浏览器里 env(safe-area-inset-top)=0，
       真机才有值 ⇒ 这里给 .app 补上等高的 padding-top，让两端顶部同基准。"""
    with sync_playwright() as pw:
        br = None
        for kw in ({"channel": "msedge"},
                   {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"}):
            try:
                br = pw.chromium.launch(**kw)
                break
            except Exception:      # noqa: BLE001
                pass
        if br is None:
            raise SystemExit("无可用浏览器内核")
        pg = br.new_page(viewport={"width": vw, "height": VH}, device_scale_factor=2)
        pg.goto("file:///" + INDEX.replace("\\", "/"))
        pg.wait_for_timeout(900)
        pg.evaluate("try{localStorage.clear()}catch(e){}")
        pg.reload()
        pg.wait_for_timeout(1400)
        pg.evaluate("switchTab('trade')")
        pg.wait_for_timeout(1000)
        # 模拟真机安全区（与小程序 statusBarHeight 同值）
        pg.evaluate("(v) => { document.querySelector('.app').style.paddingTop = v + 'px'; }", sbh)
        pg.evaluate("document.querySelector('#screen').scrollTop = 0")
        pg.wait_for_timeout(400)
        res = pg.evaluate("""(list) => list.map((s) => {
            const el = document.querySelector('#page-trade ' + s) || document.querySelector(s);
            if (!el) return [s, null, null, null, null];
            const b = el.getBoundingClientRect();
            return [s, +b.left.toFixed(1), +b.top.toFixed(1), +b.width.toFixed(1), +b.height.toFixed(1)];
        })""", SEL)
        meta = pg.evaluate("""() => {
            const sc = document.querySelector('#screen');
            const tb = document.querySelector('.tabbar');
            const app = document.querySelector('.app');
            return {scrollHeight: sc.scrollHeight, clientHeight: sc.clientHeight,
                    tabTop: +tb.getBoundingClientRect().top.toFixed(1),
                    tabH: +tb.getBoundingClientRect().height.toFixed(1),
                    appH: +app.getBoundingClientRect().height.toFixed(1),
                    screenTop: +sc.getBoundingClientRect().top.toFixed(1),
                    appPadTop: parseFloat(getComputedStyle(app).paddingTop) || 0};
        }""")
        br.close()
        return res, meta


p("=" * 88)
p("交易页元素级对拍（视口 430 CSS px，两端同一分量纲，可直接相减）")
p("=" * 88)

mp_res, mp_vp, mp_sys = node_side()
sbh = int(mp_sys.get("sbh") or 0)
# 让 PWA 侧视口宽 == 小程序模拟器真实宽（scrollWidth），否则响应式布局会被量成「错位」
try:
    vw = int((json.loads(mp_vp) or {}).get("scrollWidth") or VW)
except Exception:
    vw = VW
p("对齐宽度：PWA 视口宽 = %d（取自小程序 scrollWidth，确保两端同宽才可比）" % vw)
pwa_res, pwa_meta = pwa_side(sbh, vw)

p("小程序视口: " + mp_vp)
p("小程序系统信息: " + json.dumps(mp_sys, ensure_ascii=False))
p("状态栏高度: %d px（已同步注入 PWA 的 .app padding-top，两端顶部同基准）" % sbh)
p("PWA 元信息: " + json.dumps(pwa_meta))
p()

mps = {r[0]: r for r in mp_res}
pwas = {r[0]: r for r in pwa_res}

p("%-24s %-24s %-24s %s" % ("选择器", "小程序 (l,t,w,h)", "PWA (l,t,w,h)", "差 (dl,dt,dw,dh)"))
p("-" * 88)
bad = []
miss = []
for s in SEL:
    a, b = mps.get(s), pwas.get(s)
    if a is None or b is None:
        miss.append(s)
        p("%-24s %s" % (s, "缺失"))
        continue
    if a[1] is None and b[1] is None:
        miss.append(s)
        p("%-24s %-24s %-24s %s" % (s, "两侧都不存在", "两侧都不存在", "-"))
        continue
    if a[1] is None:
        miss.append(s)
        p("%-24s %-24s %-24s %s" % (s, "小程序缺失", "有", "!"))
        continue
    if b[1] is None:
        miss.append(s)
        p("%-24s %-24s %-24s %s" % (s, "有", "PWA 缺失", "!"))
        continue
    d = [round(a[i] - b[i], 1) for i in range(1, 5)]
    flag = ""
    if abs(d[1]) >= 2 or abs(d[2]) >= 4 or abs(d[3]) >= 2:
        flag = "   <<< 关注"
        bad.append((s, d))
    p("%-24s %-24s %-24s %s%s" % (
        s,
        "(%s,%s,%s,%s)" % tuple(a[1:]),
        "(%s,%s,%s,%s)" % tuple(b[1:]),
        "(%s,%s,%s,%s)" % tuple(d), flag))

p()
p("差异超阈值的项：%d 个 %s" % (len(bad), "" if bad else "✅ 全部在阈值内"))
for s, d in bad:
    p("   %-24s dl=%s dt=%s dw=%s dh=%s" % (s, d[0], d[1], d[2], d[3]))
if miss:
    p("未测到的项：%s" % ", ".join(miss))

p()
p("-" * 88)
p("底部留白自检：滚到底时最后一行距底栏多远")
p("  （口径：scrollHeight − 内容底在『滚动内容坐标系』里的位置。")
p("    ⚠️ 不能直接用视口坐标 —— PWA 侧被注入了 .app padding-top 模拟安全区，")
p("       那一段不属于滚动内容，不减掉会凭空少算 sbh px。）")
try:
    mp_sc = json.loads(mp_vp)["scrollHeight"]
    mp_cb = max(r[2] + r[4] for r in mp_res if r[1] is not None)
    mp_off = 0
    pwa_cb = max(r[2] + r[4] for r in pwa_res if r[1] is not None)
    pwa_off = pwa_meta.get("appPadTop", 0)
    pwa_sc = pwa_meta["scrollHeight"]
    mp_blank = mp_sc - (mp_cb - mp_off)
    pwa_blank = pwa_sc - (pwa_cb - pwa_off)
    p("  小程序：内容底视口 y=%.1f（滚动内容内 y=%.1f），scrollHeight=%s ⇒ 底部留白 %.1f px"
      % (mp_cb, mp_cb - mp_off, mp_sc, mp_blank))
    p("  PWA   ：内容底视口 y=%.1f（滚动内容内 y=%.1f），scrollHeight=%s ⇒ 底部留白 %.1f px"
      % (pwa_cb, pwa_cb - pwa_off, pwa_sc, pwa_blank))
    d = mp_blank - pwa_blank
    p("  ⇒ 两端留白差 %.1f px  %s" % (d, "✅ 一致（均为 PWA .page 的 padding-bottom:80px）"
                                  if abs(d) < 2 else "❌ 不一致"))
except Exception as e:      # noqa: BLE001
    p("  自检失败：%s" % e)

io.open(os.path.join(HERE, "_rect_trade_cmp.txt"), "w", encoding="utf-8").write("\n".join(OUT))
p()
p("写出 promo/_rect_trade_cmp.txt")
p("RESULT=OK")
