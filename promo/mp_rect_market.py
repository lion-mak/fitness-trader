# -*- coding: utf-8 -*-
"""
mp_rect_market.py —— 行情页元素级对拍：同一组选择器在两端量 rect，逐项比位置与尺寸。

与 mp_rect_compare.py（持仓页）同源，差别只有三处：
  ① 选择器集合换成行情页（5 块全量：K线 / 运动网格 / 大盘云图 / 身体成分 / 历史成交）
  ② 页面路由 /pages/market/market，PWA 侧前缀 #page-market
  ③ **先把真实存档灌进两端再量**（空存档下量不到色阶、多块云图、历史成交柱 ——
     而那正是行情页最该验的东西）。灌入用 promo/_seed_mp.js，用完全部还原。

用法：python promo/mp_rect_market.py          （需 cli auto 拉起 9420）
      python promo/mp_rect_market.py --empty  （不灌存档，按空态量，用于对照）
输出：promo/_rect_market_cmp.txt
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
MOCK = os.path.join(HERE, "mock.json")
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NM = r"C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules"

VW, VH = 430, 930
ROUTE = "/pages/market/market"
PWA_PAGE = "#page-market"

# 两端同源选择器（wxml 照搬了 PWA 的 class / id）。
# ⚠️ 只挑**两端都存在**的：小程序侧 .history-empty / .body-source / .metric-grid / .card-title .m
#    用的是 class 而非 id（PWA 侧是 id），所以统一用 class 选，避免一侧量不到。
# ⚠️ 刻意**不含** .ex-heat-inner：PWA 的月份标签 + 星期轴都在滚动容器里，
#    内容宽 = 22 + trackW；小程序把星期轴移出滚动容器（无可靠 sticky），内容宽 = trackW。
#    差这 22px 是**设计如此**，写进表里只会淹没真正的错位。
SEL = [
    ".pheader", ".logo", ".avatar-sm", ".lt", ".lt .id",
    ".card", ".card-title",
    ".kline-title-right", ".kline-tabs", ".kline-tab",
    ".kchart-wrap", ".ma-legend", ".ma7", ".ma14", ".ma30", ".kw-mini",
    "#ex-heat-card", ".ex-heat", ".ex-heat-board", ".ex-heat-axis", ".ex-heat-days",
    ".ex-heat-scroll", ".ex-heat-months", ".ex-heat-grid", ".ex-heat-cell",
    ".ex-heat-foot", ".ex-heat-legend",
    ".mm-frame", ".mm-inner", ".mm-legend",
    ".body-source", ".metric-grid", ".metric", ".metric .head", ".metric .v",
    ".metric .track-wrap", ".body-actions", ".body-action",
    ".history-card", ".history-header", ".history-tabs", ".history-tab",
    "#history-chart", ".history-legend",
]

# 🔴 小程序专属项（PWA 侧没有对应元素）—— 只量、不对比，但**量不到要算失败**。
#    2026-09-24 补齐：这四项原来躺在 SEL 里，于是每跑必报「缺失（小程序 有 / PWA 无）」，
#    这道闸**从写下那天起就不可能绿**，多跑几轮之后人就学会了忽略它的 FAIL。
#    （本文件头部写着「只挑两端都存在的」，这四项是违反那条规则混进来的。）
#      · .ma14        —— 小程序新增 MA14 均线（Mak 2026-09-24 要求；PWA 只有 MA7/MA30）
#      · .kchart-wrap —— 小程序包 canvas 的定位壳（PWA 的 K 线就是一个 <svg id="kchart">）
#      · .ex-heat-board / .ex-heat-axis —— 小程序把星期轴移出滚动容器后的两层壳（无 sticky）
#      · .lt .id      —— PWA 用 <span id="hdr-id">（id），class 选不到；小程序用 class
MP_ONLY = [".ma14", ".kchart-wrap", ".ex-heat-board", ".ex-heat-axis", ".lt .id"]

# MA14 插进图例后，它**右边**的项必然整体右移（设计如此，不是错位）。
# 这些选择器的 dl 要扣掉「MA14 宽 + 间距」再判，期望值全部从本次实测现算（不写死）。
SHIFTED_BY_MP_ONLY = [".ma30"]

EMPTY_MODE = "--empty" in sys.argv
VP_MISMATCH = False
OUT = []


def p(s=""):
    OUT.append(s)
    print(s)


def run_node(script, args, timeout=300):
    env = dict(os.environ)
    env["NODE_PATH"] = NM
    env["PATH"] = os.path.dirname(NODE) + ";" + env.get("PATH", "")
    return subprocess.run([NODE, os.path.join(HERE, script)] + args,
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=timeout)


def mp_side():
    pr = run_node("_rect_mp.js", [json.dumps(SEL), ROUTE])
    lines = (pr.stdout or "").splitlines()
    line = [l for l in lines if l.startswith("RECT_JSON=")]
    vp = [l for l in lines if l.startswith("VIEWPORT=")]
    sy = [l for l in lines if l.startswith("SYS=")]
    if not line:
        raise SystemExit("小程序侧测量失败：\n" + (pr.stdout or "")[-1500:] + "\n" + (pr.stderr or "")[-1500:])
    return (json.loads(line[0][len("RECT_JSON="):]),
            (vp[0][len("VIEWPORT="):] if vp else "{}"),
            json.loads(sy[0][len("SYS="):]) if sy else {})


def mp_probe():
    pr = run_node("_probe_market.js", [], timeout=300)
    for l in (pr.stdout or "").splitlines():
        if l.startswith("PROBE="):
            return json.loads(l[len("PROBE="):])
    return {}


LAUNCH = [{"channel": "msedge"},
          {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"}]


def pwa_side(sbh, seed_json):
    """seed_json: 与小程序同一份存档的 JSON 串；None = 空存档（清 localStorage）。"""
    with sync_playwright() as pw:
        br = None
        for kw in LAUNCH:
            try:
                br = pw.chromium.launch(**kw)
                break
            except Exception:      # noqa: BLE001
                pass
        if br is None:
            raise SystemExit("无可用浏览器内核")
        pg = br.new_page(viewport={"width": VW, "height": VH}, device_scale_factor=2)
        pg.goto("file:///" + INDEX.replace("\\", "/"))
        pg.wait_for_timeout(900)
        if seed_json is None:
            pg.evaluate("try{localStorage.clear()}catch(e){}")
        else:
            pg.evaluate("(s) => { localStorage.setItem('jianpan_v2', s); }", seed_json)
        pg.reload()
        pg.wait_for_timeout(1600)
        pg.evaluate("switchTab('market')")
        pg.wait_for_timeout(1100)
        # 模拟真机安全区：留白注入 #page-market（**滚动内容之内**），
        # 与小程序把 padding-top 写在 .page 上同侧。注到 .app 会造成假偏移。
        pg.evaluate("(v) => { document.querySelector('#page-market').style.paddingTop = v + 'px'; }", sbh)
        pg.evaluate("(h) => { const s = document.querySelector('#screen');"
                    " s.style.flex = 'none'; s.style.height = h + 'px'; }", 850)
        pg.evaluate("document.querySelector('#screen').scrollTop = 0")
        pg.wait_for_timeout(600)
        res = pg.evaluate("""(list) => list.map((s) => {
            const el = document.querySelector('#page-market ' + s) || document.querySelector(s);
            if (!el) return [s, null, null, null, null];
            const b = el.getBoundingClientRect();
            return [s, +b.left.toFixed(1), +b.top.toFixed(1), +b.width.toFixed(1), +b.height.toFixed(1)];
        })""", SEL)
        snap = pg.evaluate("""() => {
            const g = (s) => { const e = document.querySelector(s); return e ? e.innerText.replace(/\\n/g, ' | ') : '(缺)'; };
            return {
                weight: g('#kline-weight'), exSub: g('#ex-heat-sub'), mmSub: g('#mm-sub'),
                legend: g('.history-legend'), bodySrc: g('.body-source'),
                scrollHeight: document.querySelector('#screen').scrollHeight,
            };
        }""")
        br.close()
        return res, snap


p("=" * 92)
p("行情页元素级对拍（视口 430 CSS px，两端同一分量纲，可直接相减）")
p("模式：" + ("空存档对照" if EMPTY_MODE else "真实存档（96 天，两端同一份）"))
p("=" * 92)

seeded = False
try:
    if not EMPTY_MODE:
        r = run_node("_seed_mp.js", ["set", MOCK])
        if r.returncode != 0:
            raise SystemExit("灌存档失败：\n" + (r.stdout or "") + (r.stderr or ""))
        p("小程序侧：" + (r.stdout or "").strip().replace("\n", " / "))
        seeded = True

    mp_res, mp_vp, mp_sys = mp_side()
    sbh = int(mp_sys.get("sbh") or 0)
    mp_snap = mp_probe()

    seed_json = None
    if not EMPTY_MODE:
        seed_json = json.dumps(json.load(io.open(MOCK, encoding="utf-8"))["state"], ensure_ascii=False)
    pwa_res, pwa_snap = pwa_side(sbh, seed_json)

    p("小程序视口: " + mp_vp)
    p("小程序系统: " + json.dumps(mp_sys, ensure_ascii=False))
    p("状态栏高度: %d px（两端同侧注入，顶部同基准）" % sbh)
    p()

    # 🔴 视口必须先对表，再谈 rect 差。
    #    这一行是 2026-09-24 补的：当时开发者工具的模拟器停在 iPhone 12（宽 390），
    #    而本闸与 PWA 侧都按 430 布（VW=430）⇒ 30 项差异**全部**由视口造成，
    #    报告却长得像「布局全错」，需要人去逐行反推才有结论。
    #    视口不对时下面的 rect 差没有任何意义（格宽会随容器宽重算）。
    #    ⚠️ 只置标志、不在这里 raise：出口只有最下面那一个（写报告 + 非零退出码），
    #       在中间直接 SystemExit(0) 会让「视口不对」变成一道假绿。
    mvw = int(json.loads(mp_vp).get("scrollWidth") or 0)
    if mvw != VW:
        VP_MISMATCH = True
        p("🔴 小程序视口宽 %d ≠ 本闸基准 %d —— 开发者工具的模拟器机型不对。" % (mvw, VW))
        p("   rect 差会随容器宽整体漂移（格宽/云图列宽都会重算），下面的数值不可解读。")
        p("   动作：开发者工具 → 模拟器机型切到 iPhone 15 Pro Max（逻辑像素 430×932）后重跑。")
        p()
    p("-" * 92)
    p("数据一致性自检（两端必须看到同一组数字，否则 rect 差里会混进「内容不同」）")
    for k, lab in (("weight", "体重"), ("exSub", "运动网格副标题"), ("mmSub", "云图副标题"),
                   ("legend", "历史成交图例"), ("bodySrc", "身体成分来源")):
        a = (mp_snap.get("data") or {}).get({"weight": "weightText", "exSub": "exSub",
                                            "mmSub": "mmSub", "legend": "histLegend",
                                            "bodySrc": "bodySrcText"}[k])
        if k == "legend":
            a = mp_snap.get("data", {}).get("histLegend")
            a = "摄入 %s / 运动 %s · 日均 %s / %s" % (a.get("in"), a.get("ex"), a.get("avgIn"), a.get("avgEx")) if a else "(缺)"
        b = pwa_snap.get(k)
        same = "✅" if str(a) == str(b) or (k == "legend" and str(a).replace(" ", "") == str(b).replace(" ", "")) else "⚠️"
        p("  %s %-14s 小程序 %-40s PWA %s" % (same, lab, str(a)[:40], str(b)[:44]))
    p("  scrollHeight：小程序 %s / PWA %s" % (json.loads(mp_vp).get("scrollHeight"), pwa_snap.get("scrollHeight")))
    p()

    mps = {r[0]: r for r in mp_res}
    pwas = {r[0]: r for r in pwa_res}

    p("%-22s %-26s %-26s %s" % ("选择器", "小程序 (l,t,w,h)", "PWA (l,t,w,h)", "差 (dl,dt,dw,dh)"))
    p("-" * 92)
    bad, miss = [], []
    if VP_MISMATCH:
        bad.append(("__viewport__", [mvw - VW, 0, 0, 0]))
        p("（视口宽不符，逐项对比已跳过 —— 视口不对时 rect 差不可解读）")
    for s in ([] if VP_MISMATCH else SEL):
        a, b = mps.get(s), pwas.get(s)
        # 小程序专属项（PWA 里没有对应元素）：不算「未测到」，但**必须真的量到**
        # ——量不到说明这条新元素根本没渲染出来（那才是真问题）。
        if s in MP_ONLY:
            if a is None or a[1] is None:
                miss.append(s)
                p("%-22s %s" % (s, "缺失（小程序也要有，本闸要求它必须渲染出来）"))
            else:
                p("%-22s %-26s %-26s %s" % (s, "(%s,%s,%s,%s)" % tuple(a[1:]),
                                            "—（PWA 无此项）", "—"))
            continue
        if a is None or b is None or a[1] is None or b[1] is None:
            miss.append(s)
            p("%-22s %s" % (s, "缺失（小程序 %s / PWA %s）" % ("有" if a and a[1] is not None else "无",
                                                          "有" if b and b[1] is not None else "无")))
            continue
        d = [round(a[i] - b[i], 1) for i in range(1, 5)]
        # MA14 造成的**设计性右移**：小程序在图例里多插了一条均线（Mak 2026-09-24 要求），
        # 它后面的 .ma30 必然右移。期望位移 = .ma14 的宽 + 它两侧的间距，
        # 全部从**本次实测**的小程序几何现算（不写死数字）——
        # 这样「图例换行/溢出/间距被改坏」仍然会被这条抓住。
        note = ""
        if s in SHIFTED_BY_MP_ONLY and not VP_MISMATCH:
            m14, m7 = mps.get(".ma14"), mps.get(".ma7")
            if m14 and m7 and m14[1] is not None and m7[1] is not None:
                gap = m14[1] - (m7[1] + m7[3])
                exp_dl = round(m14[3] + gap, 1)
                note = "  （含 MA14 设计性位移 %.1f）" % exp_dl
                d[0] = round(d[0] - exp_dl, 1)
        flag = ""
        if abs(d[1]) >= 2 or abs(d[2]) >= 4 or abs(d[3]) >= 2 or abs(d[0]) >= 4:
            flag = "   <<< 关注"
            bad.append((s, d))
        p("%-22s %-26s %-26s %s%s%s" % (
            s, "(%s,%s,%s,%s)" % tuple(a[1:]), "(%s,%s,%s,%s)" % tuple(b[1:]),
            "(%s,%s,%s,%s)" % tuple(d), note, flag))

    p()
    p("差异超阈值的项：%d 个 %s" % (len(bad), "" if bad else "✅ 全部在阈值内"))
    for s, d in bad:
        p("   %-22s dl=%s dt=%s dw=%s dh=%s" % (s, d[0], d[1], d[2], d[3]))
    if miss:
        p("未测到的项（%d）：%s" % (len(miss), ", ".join(miss)))
    p()
    p("RESULT=" + ("OK" if (not bad and not miss) else
                   ("FAIL → 视口不符（小程序 %d / 基准 %d）：模拟器机型不对，切到 iPhone 15 Pro Max 后重跑"
                    % (mvw, VW)) if VP_MISMATCH else
                   "FAIL → 超阈值 %d 个 / 未测到 %d 个" % (len(bad), len(miss))))
finally:
    if seeded:
        r = run_node("_seed_mp.js", ["restore"])
        p()
        p("还原小程序存储：" + (r.stdout or "").strip().replace("\n", " / "))

io.open(os.path.join(HERE, "_rect_market_cmp.txt"), "w", encoding="utf-8").write("\n".join(OUT))
print("写出 promo/_rect_market_cmp.txt")
# ⚠️ 原来这里没有退出码（且上面那行打印的是非标准 "CHECK"）⇒ mp_gates.py 判退出码 ⇒ 这道闸永远 ✅。
#    2026-09-23 审计发现整族 rect 闸都缺退出码，统一补上。（bad/miss 是模块级变量，此处仍在作用域内）
sys.exit(0 if (not bad and not miss) else 1)
