# -*- coding: utf-8 -*-
"""
mp_rect_body.py —— 身体成分详情页 / 身体成分录入弹层 / 全屏涨停仪式 的元素级对拍（⑥c）。

与 mp_rect_trade_modals.py 同一套机制，三个新面孔各有一条**专属坑**：

  1) **身体成分详情页是独立页面**（PWA 里是 switchTab 的一个 .page，小程序里必须 navigateTo）。
     ⇒ 小程序侧要先 navigateTo；PWA 侧走 openBodyDetail(idx)（源码里就是 switchTab + renderBodyDetail）。
     ⚠️ 页面根节点（.page ↔ #page-body-detail）**故意不量**：两端把顶栏安全区放在不同层级
        （PWA 在 .app 的 padding-top、小程序在 .page 的 padding-top）⇒ 根节点 rect 天生差一个 sbh。
        那是**已知的结构性差异**，不是布局错；要比的是里面那些内容块，它们的 y 是对齐的。

  2) **涨停仪式是自定义组件**（components/celeb）。组件内部节点**不对页面 selectorQuery 暴露**
     ⇒ 探针里必须 `wx.createSelectorQuery().in(comp)`，否则全部静默变成「未测到」。
     开门方式：小程序走 app.onCelebrate(info)（与真机 settleDay → celebrate 钩子同一条通路）；
     PWA 走 settleDay 里那两行原样（填 #celeb-net + classList.add('show')）——两边都不是
     「setData 翻开关」式的假开门。

  3) **弹层与浮层的视口**：PWA 的 .sheet-mask / #celeb 都是 fixed/absolute-inset:0，
     只认浏览器视口 ⇒ 必须拿小程序实测的 windowHeight 去设 PWA 的视口高（不是设 #screen）。

  另：`.celeb .heading .em` 的**渐变裁切被有意降级**成纯琥珀色（小程序 webview 不保证支持
  background-clip:text，一旦不生效三个字会直接消失）。rect 不受颜色影响，故仍在测点里。

输出：promo/_rect_body_cmp.txt
用法：
  <venv>/python.exe promo/mp_rect_body.py             # 全量（脚本自己 arm 9420）
  <venv>/python.exe promo/mp_rect_body.py --pwa-only  # 只量 PWA（不需 IDE）
  <venv>/python.exe promo/mp_rect_body.py --mp-only   # 只量小程序（调试探针用）
"""
import argparse
import io
import json
import os
import subprocess
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mp_ws                                                     # noqa: E402

from playwright.sync_api import sync_playwright                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
INDEX = os.path.join(ROOT, "index.html")
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NM = r"C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules"
MOCK = os.path.join(HERE, "_body_mock.json")

VW = 390                 # 两端同宽（小程序实测 .sheet-mask 宽 = 390）
VH_FALLBACK = 930        # --pwa-only 时的视口高
CELEB_NET = -767         # 打给两端同一个缺口数，浮层上的大数才可比

# 阈值：沿用 ⑥c 原口径（l/t/w/h）
TH = {"l": 4.0, "t": 2.0, "w": 4.0, "h": 2.0}


def make_mock():
    """两端灌**同一份**存档：4 个身体成分点（体脂率有 4 个点 ⇒ 趋势折线真连线）
    + 3 个不在 bodyLog 里的体重日期（⇒ BMI 走推算点，覆盖那条分支）。
    lastDate = 今天 ⇒ 不触发跨天补结算（免得真弹一次涨停仪式干扰弹层量测）。"""
    t = date.today()

    def d(n):
        return (t - timedelta(days=n)).isoformat()

    st = {
        "user": {"gender": "male", "age": 32, "height": 175, "weight": 72.8, "target": -500,
                 "startWeight": 80, "targetWeight": None, "avatar": None, "userId": "FT_RECT",
                 "bodyFat": None, "restingHr": None, "activity": "sedentary"},
        "body": {"bmi": 23.8, "bodyFat": 16.2, "muscleRate": 43.8, "waterRate": 56.7,
                 "bodyAge": 28, "visceralFat": 7, "source": "manual", "syncedAt": "09:30",
                 "_prev": {"bmi": 24.0, "bodyFat": 16.9, "muscleRate": 43.4, "waterRate": 56.4,
                           "bodyAge": 29, "visceralFat": 7}},
        "bodyLog": [
            {"date": d(21), "bmi": 24.6, "bodyFat": 18.2, "muscleRate": 42.5,
             "waterRate": 55.8, "bodyAge": 30, "visceralFat": 8},
            {"date": d(14), "bmi": 24.2, "bodyFat": 17.4, "muscleRate": 43.0,
             "waterRate": 56.1, "bodyAge": 29, "visceralFat": 8},
            {"date": d(7), "bmi": 24.0, "bodyFat": 16.9, "muscleRate": 43.4,
             "waterRate": 56.4, "bodyAge": 29, "visceralFat": 7},
            {"date": d(1), "bmi": 23.8, "bodyFat": 16.2, "muscleRate": 43.8,
             "waterRate": 56.7, "bodyAge": 28, "visceralFat": 7},
        ],
        "weightLog": [{"date": d(20), "weight": 75.2},
                      {"date": d(10), "weight": 74.0},
                      {"date": d(3), "weight": 73.1}],
        "diet": [], "exercise": [],
        "lastDate": t.isoformat(),
        "celebFired": False, "settledDate": None,
        "coins": 1200, "exp": 320, "limitUpCount": 3, "limitUpStreak": 2,
        "lastLimitUpDate": d(2), "coinsEarnedTotal": 2400,
        "cards": {}, "totalDraws": 0, "collectRewards": {}, "ach": {},
        "usuals": [], "foodFreq": {}, "usualsHidden": [],
        "exerciseCustom": [], "maxOverage": 0, "streakDays": 6, "maxStreak": 9,
    }
    return st


# ── 三组测点：pwa / mp 两个列表**顺序一一对应** ─────────────────────────────
GROUPS = [
    {"key": "bodySheet（身体成分录入弹层）",
     "pwa_expr": "openBodyEdit();",
     "pwa_close": "closeBodyEdit();",
     "mp_open": {"kind": "pageMethod", "name": "onBodyManual", "arg": None},
     "mp_close": {"kind": "pageMethod", "name": "closeBodySheet"},
     "settle": 1100,
     # ⚠️ 刻意**不量** `.field label` / `.field input`：小程序侧这两个的 rect 查不到
     #    （select() 返回 null ⇒ 闸里算「未测到」）。label/input 是内置/原生组件，
     #    iOS 模拟器下不参与 selectorQuery 的 rect 返回。历史同族脚本（交易页 6 弹层）
     #    同样只量到 `.field` 这一层，保持口径一致。
     #    输入框高度并不是漏测：`.field` 的总高（本例 68.2）本身就是 label + input 的和，
     #    适配层那条 `.field input{height:43px}` 一旦失效，`.field` 会当场变矮而被抓到。
     "pwa": ["#body-sheet", "#body-sheet .sheet", "#body-sheet h3", "#body-sheet .close",
             "#body-sheet .sheet > div:nth-child(3)", "#body-sheet .body-grid",
             "#body-sheet .field", "#body-sheet .confirm.sell"],
     # h3 → .sheet-h、行内 style 的 div → .bs-sub、button → .confirm.sell(view)
     "mp": [".sheet-mask", ".sheet-mask .sheet", ".sheet-mask .sheet-h", ".sheet-mask .close",
            ".bs-sub", ".sheet-mask .body-grid",
            ".sheet-mask .field", ".sheet-mask .confirm.sell"]},

    {"key": "bodyDetail（身体成分详情页 · idx=0 BMI）",
     "pwa_expr": "openBodyDetail(0);",
     "pwa_close": "backToMarket();",
     "navigate": "/pages/body-detail/body-detail?idx=0",
     "mp_close": {"kind": "back"},
     "settle": 2200,                     # 子页首次渲染 + canvas 挂载
     "pwa": ["#bd-tabs", "#bd-tabs .bd-tab.on", "#bd-card", "#bd-card .top",
             "#bd-card .top .val", "#bd-card .tag", "#bd-card .score", "#bd-card .score-note",
             "#bd-card .track", "#bd-card .track-labels", "#bd-card .track-bar",
             "#bd-card .dot", "#bd-card .track-names", "#bd-ai",
             "#bd-ai p", "#bd-trend", "#bd-trend svg"],
     # <b> → .b、<span> → .tk/.nm、<p> → .p、内联 svg → canvas（.bf-canvas）
     "mp": [".bd-tabs", ".bd-tabs .bd-tab.on", "#bd-card", "#bd-card .top",
            "#bd-card .top .val", "#bd-card .tag", "#bd-card .score", "#bd-card .score-note",
            "#bd-card .track", "#bd-card .track-labels", "#bd-card .track-bar",
            "#bd-card .dot", "#bd-card .track-names", "#bd-ai",
            "#bd-ai .p", "#bd-trend", ".bf-canvas"]},

    {"key": "celeb（全屏涨停仪式 · 自定义组件）",
     # 🔴 这一组的 PWA 视口要**额外加一个底栏高**，原因见 pwa_side 里的长注释：
     #    PWA 的 #celeb 是 .screen 的孩子（.screen 才是 position:relative），
     #    所以它的高 = 视口 − 底栏；而小程序的 .celeb 是 fixed ⇒ 高 = webview 高。
     "pwa_viewport_extra_tabbar": True,
     # PWA：settleDay 里那两行原样（index.html L5656-5657）
     "pwa_expr": "(function(){var net=%d;var ce=document.getElementById('celeb-net');"
                 "if(ce)ce.innerHTML=net+'<small>kcal</small>';"
                 "var cb=document.getElementById('celeb');if(cb)cb.classList.add('show');})()" % CELEB_NET,
     "pwa_close": "closeCeleb();",
     "mp_open": {"kind": "celebrate", "arg": {"date": "2026-09-22", "net": CELEB_NET, "streak": 3}},
     "mp_close": {"kind": "compMethod", "name": "onClose"},
     "comp": "#celeb",                   # ⚠️ 组件内节点必须 .in(comp) 才查得到
     "settle": 900,
     "pwa": ["#celeb", "#celeb .trophy", "#celeb .trophy svg", "#celeb .big",
             "#celeb .big small", "#celeb > div:nth-child(3)", "#celeb .heading",
             "#celeb .heading .em", "#celeb .stats", "#celeb .stats > div:nth-child(1)",
             "#celeb .stats .n", "#celeb .btn"],
     # 内联 svg → 烘焙 PNG（.trophy-ic）、行内 style 的 div → .celeb-sub、> div → > .c
     "mp": [".celeb", ".celeb .trophy", ".celeb .trophy-ic", ".celeb .big",
            ".celeb .big .small", ".celeb-sub", ".celeb .heading",
            ".celeb .heading .em", ".celeb .stats", ".celeb .stats .c",
            ".celeb .stats .n", ".celeb .btn"]},
]

OUT = []


def p(s=""):
    OUT.append(s)
    print(s)


# ---------------------------------------------------------------- 小程序侧
def node_side(groups):
    if not mp_ws.ensure_port(quiet=True):
        raise SystemExit("自动化端口 9420 未就绪（先跑 promo/_fix_step2_restart_ide.py 排查）")
    spec = {
        "startUrl": "/pages/market/market",
        "settle": 2800,
        "groups": [{"key": g["key"], "subs": g["mp"], "comp": g.get("comp"),
                    "open": g.get("mp_open"), "close": g.get("mp_close"),
                    "navigate": g.get("navigate"), "settle": g.get("settle", 900)}
                   for g in groups],
    }
    env = dict(os.environ)
    env["NODE_PATH"] = NM
    env["PATH"] = os.path.dirname(NODE) + ";" + env.get("PATH", "")
    pr = subprocess.run([NODE, os.path.join(HERE, "_rect_mp_body.js"), json.dumps(spec)],
                        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", env=env, timeout=600)
    lines = (pr.stdout or "").splitlines()
    hit = [l for l in lines if l.startswith("BODY_RECTS_JSON=")]
    if not hit:
        raise SystemExit("小程序侧测量失败：\n" + (pr.stdout or "")[-1500:]
                         + "\n" + (pr.stderr or "")[-1500:])
    data = json.loads(hit[0][len("BODY_RECTS_JSON="):])
    rects = {g["key"]: g["rects"] for g in (data.get("groups") or [])}
    traces = {g["key"]: (g.get("trace") or "") for g in (data.get("groups") or [])}
    return data.get("sys") or {}, rects, traces


def seed_mp_set():
    r = mp_ws._node("_seed_mp.js", ["set", MOCK])
    if r.returncode != 0:
        raise SystemExit("灌存档失败：\n" + (r.stdout or "") + (r.stderr or ""))
    return (r.stdout or "").strip().replace("\n", " / ")


def seed_mp_restore():
    r = mp_ws._node("_seed_mp.js", ["restore"])
    return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()


# ---------------------------------------------------------------- PWA 侧
def pwa_side(groups, vh_base, sab=0, sbh=0):
    seed_json = io.open(MOCK, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = None
        for kw in ({"channel": "msedge"},
                   {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX"
                                       r"\Chrome\Application\360ChromeX.exe"}):
            try:
                br = pw.chromium.launch(**kw)
                break
            except Exception:                                    # noqa: BLE001
                pass
        if br is None:
            raise SystemExit("无可用浏览器内核")
        pg = br.new_page(viewport={"width": VW, "height": vh_base}, device_scale_factor=2)
        pg.goto("file:///" + INDEX.replace("\\", "/"))
        pg.wait_for_timeout(900)
        pg.evaluate("(s) => { localStorage.setItem('jianpan_v2', s); }", seed_json)
        pg.reload()
        pg.wait_for_timeout(1700)
        if sab:
            # .sheet 的 padding-bottom = calc(28px + env(safe-area-inset-bottom))：
            # 浏览器里 env()=0、模拟器里有值 ⇒ 补成同一个值，否则 .confirm.* 恒差 sab px（假差）
            pg.add_style_tag(content=".sheet-mask .sheet{padding-bottom:%dpx !important;}" % (28 + sab))
        if sbh:
            # 顶栏安全区两端放在不同层级：PWA 在 .app 的 padding-top（浏览器里 env()=0），
            # 小程序在 .page 的 padding-top ⇒ 不补这一刀，详情页所有测点 dt 恒差一个 sbh（假差）。
            # ⚠️ 注在目标页 `#page-body-detail` 上（滚动内容**内**），⛔ 别注 .app
            #    —— 注 .app 会让 .screen 高度跟着变，反而引入新的偏移。
            pg.add_style_tag(content="#page-body-detail{padding-top:%dpx;}" % sbh)
        pg.evaluate("switchTab('market')")
        pg.wait_for_timeout(900)

        # 🔴 「视口高」对这两类元素的意义不同，必须分开算：
        #    · .sheet-mask 是 position:fixed ⇒ 高 = 浏览器视口高 ⇒ 视口设成小程序 wh 就对上了
        #    · #celeb 是 **.screen 的孩子**（.screen 是 position:relative 的滚动容器，源码 L672 打开、
        #      .tabbar 从 L1275 才开始 ⇒ #celeb 在 .screen 之内）⇒ 它的高 = 视口 − 底栏高，
        #      而小程序侧 .celeb 是 fixed ⇒ 高 = webview 高（= 小程序 wh，本来就不含 tabBar）。
        #      ⇒ celeb 组的视口要设成 wh + 底栏高，两边的高才会相等。
        #    ⚠️ 别用「小程序 screenHeight」直接当视口：两端底栏+安全区的构成不同（PWA 的
        #      .tabbar 是 CSS 撑的、浏览器里 env(safe-area-inset-bottom)=0；小程序 tabBar 是原生的），
        #      拿 screenHeight 凑纯属碰运气 —— 这里改成**实测 PWA 自己的底栏高**。
        tab_h = pg.evaluate("() => { const t = document.querySelector('.tabbar');"
                            " return t ? +t.getBoundingClientRect().height.toFixed(1) : 0; }")
        res = {}
        for g in groups:
            vh = vh_base + (tab_h if g.get("pwa_viewport_extra_tabbar") else 0)
            pg.set_viewport_size({"width": VW, "height": int(round(vh))})
            pg.wait_for_timeout(320)                  # 等重排
            pg.evaluate("(function(){%s})()" % g["pwa_expr"])
            pg.wait_for_timeout(g.get("settle", 900))
            rects = pg.evaluate("""(list) => list.map((s) => {
                const el = document.querySelector(s);
                if (!el) return [s, null, null, null, null];
                const b = el.getBoundingClientRect();
                return [s, +b.left.toFixed(1), +b.top.toFixed(1), +b.width.toFixed(1), +b.height.toFixed(1)];
            })""", g["pwa"])
            res[g["key"]] = rects
            pg.evaluate("(function(){%s})()" % g["pwa_close"])
            pg.wait_for_timeout(320)
        br.close()
        p("PWA 底栏实测高 = %.1fpx（celeb 组的视口按 wh+底栏 处理）" % tab_h)
        return res


# ---------------------------------------------------------------- 比对
def cmp_group(g, ap, bp):
    p("  ── %s ──" % g["key"])
    p("  %-34s %-26s %-26s %s" % ("选择器(PWA↔MP 对齐)", "PWA (l,t,w,h)", "小程序 (l,t,w,h)",
                                 "差 (dl,dt,dw,dh)"))
    bad, miss = [], []
    for i in range(len(g["pwa"])):
        a = ap[i] if ap and i < len(ap) else None
        b = bp[i] if bp and i < len(bp) else None
        sa, sb = g["pwa"][i], g["mp"][i]
        if not a or not b or a[1] is None or b[1] is None:
            miss.append("%s ↔ %s" % (sa, sb))
            p("  %-34s %s" % (sa + " ↔ " + sb, "缺失/未测"))
            continue
        d = [round(a[k] - b[k], 1) for k in range(1, 5)]
        flag = ""
        if (abs(d[0]) >= TH["l"] or abs(d[1]) >= TH["t"]
                or abs(d[2]) >= TH["w"] or abs(d[3]) >= TH["h"]):
            flag = "   <<< 关注"
            bad.append((sa, d))
        p("  %-34s %-26s %-26s %s%s" % (
            sa + " ↔ " + sb,
            "(%s,%s,%s,%s)" % tuple(a[1:]),
            "(%s,%s,%s,%s)" % tuple(b[1:]),
            "(%s,%s,%s,%s)" % tuple(d), flag))
    p("  超阈值：%d 个 %s" % (len(bad), "" if bad else "✅ 全部在阈值内"))
    for sa, d in bad:
        p("     %-32s dl=%s dt=%s dw=%s dh=%s" % (sa, d[0], d[1], d[2], d[3]))
    if miss:
        p("  未测到：%s" % ", ".join(miss))
    # ⚠️ 未测到必须算失败：选择器一旦失效（改类名/删元素），测点会静默变「未测到」，
    #    只数 bad 的话闸会报 0 超阈值 = **假通过**。
    return len(bad), len(miss)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwa-only", action="store_true", help="只量 PWA 侧（不需 IDE）")
    ap.add_argument("--mp-only", action="store_true", help="只量小程序侧（调试探针）")
    args = ap.parse_args()

    if not os.path.exists(MOCK):
        io.open(MOCK, "w", encoding="utf-8").write(
            json.dumps(make_mock(), ensure_ascii=False, indent=1))
        p("已生成 mock：%s" % MOCK)

    p("=" * 100)
    p("身体成分详情页 / 录入弹层 / 全屏涨停仪式 —— 元素级对拍（⑥c）")
    p("=" * 100)

    if args.pwa_only:
        pwa = pwa_side(GROUPS, VH_FALLBACK)
        p("PWA 侧：%d 组已量（视口 %dx%d，未对齐小程序 wh）" % (len(pwa), VW, VH_FALLBACK))
        for g in GROUPS:
            p("")
            p("  %s：" % g["key"])
            for r in pwa.get(g["key"], []):
                p("    %-34s (%s,%s,%s,%s)" % (r[0], r[1], r[2], r[3], r[4]))
        io.open(os.path.join(HERE, "_rect_body_cmp.txt"), "w", encoding="utf-8").write(
            "\n".join(OUT) + "\n")
        return 0

    if args.mp_only:
        sysinfo, mp, traces = node_side(GROUPS)
        p("小程序系统信息：%s" % json.dumps(sysinfo, ensure_ascii=False))
        for g in GROUPS:
            p("")
            p("  %s：%s" % (g["key"], traces.get(g["key"]) or "（打开/关闭全部 OK）"))
            for r in mp.get(g["key"], []):
                p("    %-34s (%s,%s,%s,%s)" % (r[0], r[1], r[2], r[3], r[4]))
        io.open(os.path.join(HERE, "_rect_body_cmp.txt"), "w", encoding="utf-8").write(
            "\n".join(OUT) + "\n")
        return 0

    # ---- 全量：先 arm（_seed_mp.js 直接连 9420，必须先 arm），再灌存档（自动备份），测完 finally 还原 ----
    if not mp_ws.ensure_port(quiet=True):
        raise SystemExit("自动化端口 9420 未就绪（先跑 promo/_fix_step2_restart_ide.py 排查）")
    p("灌存档：%s" % seed_mp_set())
    try:
        sysinfo, mp, traces = node_side(GROUPS)
        wh = int(sysinfo.get("wh") or VH_FALLBACK)
        sab = int(sysinfo.get("sab") or 0)
        sbh = int(sysinfo.get("sbh") or 0)
        p("小程序系统信息：%s" % json.dumps(sysinfo, ensure_ascii=False))
        for g in GROUPS:
            # ⚠️ 只有含 ERR 才算「打开/关闭有问题」；trace 里正常路径也会留痕（如 'nav'）
            if "ERR" in (traces.get(g["key"]) or ""):
                p("⚠️ 小程序侧 %s 的打开/关闭有问题：%s" % (g["key"], traces[g["key"]]))
        p("⇒ PWA 侧视口设为 %dx%d、注入 safe-area-bottom=%dpx / padding-top=%dpx（两端安全区对齐）"
          % (VW, wh, sab, sbh))
        pwa = pwa_side(GROUPS, wh, sab, sbh)
    finally:
        ok, msg = seed_mp_restore()
        p("存档还原：%s %s" % ("✅" if ok else "❌", msg.replace("\n", " / ")))

    total_bad = total_miss = total_pts = 0
    for g in GROUPS:
        p("")
        bad, miss = cmp_group(g, pwa.get(g["key"]), mp.get(g["key"]))
        total_bad += bad
        total_miss += miss
        total_pts += len(g["pwa"])

    p("")
    p("=" * 100)
    p("测点合计 %d 个：超阈值 %d 个 / 未测到 %d 个" % (total_pts, total_bad, total_miss))
    verdict = "OK" if (total_bad == 0 and total_miss == 0) else "FAIL"
    p("RESULT=%s" % verdict)
    io.open(os.path.join(HERE, "_rect_body_cmp.txt"), "w", encoding="utf-8").write(
        "\n".join(OUT) + "\n")
    p("报告：%s" % os.path.join(HERE, "_rect_body_cmp.txt"))
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
