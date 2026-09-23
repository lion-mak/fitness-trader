# -*- coding: utf-8 -*-
"""
mp_rect_trade_modals.py —— 交易页 6 个录入弹层元素级对拍。

与 mp_rect_trade.py（交易页主体）同机制，但弹层只在打开时存在，所以两端都要先「打开」再量。
三条硬要求（都是踩过坑之后定下的）：

  1) **两端都走真实开门方法**（PWA: openFoodSearch()/… ；小程序: getCurrentPages()[0].openFoodSearch()/…）
     ⛔ 不能用 setData 只翻布尔开关 —— 那样小程序侧列表区是空的，而 PWA 是满的，
        量出来的差全是假差（实测 .sheet 高度差 384px / 514px）。

  2) **两端同可视区高**：先量小程序拿到 sys.wh（windowHeight），再用它设 PWA 浏览器视口高。
     ⚠️ 不能只设 PWA 的 #screen 高度 —— .sheet-mask 是 position:fixed，只认浏览器视口高；
        而小程序侧 fixed 元素恒等于 windowHeight。不统一就会每块差 (930-wh) px。

  3) **两端灌同一份存档**（promo/_modal_mock.json）：含今日一条饮食 + 一条运动，
     这样 openRecordEdit / onEditRec 两端都能打开同一条记录（id=mf1）。
     灌存档走 _seed_mp.js（自动备份 → 测完 finally 还原，绝不留下痕迹）。

输出：promo/_rect_trade_modals_cmp.txt
用法：
  <venv>/python.exe promo/mp_rect_trade_modals.py             # 全量（脚本自己 arm 9420）
  <venv>/python.exe promo/mp_rect_trade_modals.py --pwa-only  # 只量 PWA 侧（不需 IDE）
"""
import argparse
import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mp_ws                                                     # noqa: E402

from playwright.sync_api import sync_playwright                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
INDEX = os.path.join(ROOT, "index.html")
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NM = r"C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules"
MOCK = os.path.join(HERE, "_modal_mock.json")
VW = 390            # 两端同为 390（小程序实测 .sheet-mask 宽 = 390）
VH_FALLBACK = 930   # --pwa-only 时的视口高（没问小程序，只能取一个参考值）
MOCK_DIET_ID = "mf1"

# 阈值（沿用原 ⑥c 口径）
TH = {"l": 4.0, "t": 2.0, "w": 4.0, "h": 2.0}

# 六个录入弹层：pwa_expr = PWA 侧真实开门表达式；mp_open = (方法名, 参数)；settle = 打开后等待
MODALS = [
    {"key": "foodSearch",
     "pwa_expr": "openFoodSearch();",
     "pwa_close": "document.getElementById('food-search-sheet').classList.remove('show');",
     "mp_open": ("openFoodSearch", None), "mp_close": "closeFoodSearch",
     "settle": 1400,                      # 内部有 FoodStore.ready() 异步
     "pwa": ["#food-search-sheet", "#food-search-sheet .sheet", "#food-search-sheet h3",
             "#food-search-sheet .close", "#food-search-sheet .searchbox",
             "#food-search-sheet .food-cats", "#food-search-sheet .results",
             "#food-search-sheet .ghost-btn"],
     "mp":  [".sheet-mask", ".sheet-mask .sheet", ".sheet-mask .sheet-h",
             ".sheet-mask .close", ".sheet-mask .searchbox",
             ".sheet-mask .food-cats", ".sheet-mask .results",
             ".sheet-mask .ghost-btn"]},

    {"key": "foodSheet",
     "pwa_expr": "openFoodSheet(encodeURIComponent('米饭'));",
     "pwa_close": "document.getElementById('food-sheet').classList.remove('show');",
     "mp_open": ("openFoodSheet", "米饭"), "mp_close": "closeFoodSheet",
     "settle": 900,
     # ⚠️ `#fs-usual` 在 PWA 里是**容器 div**（`<div style="margin-top:9px;" id="fs-usual">`，
     #    innerHTML 才是按钮）⇒ 必须取 `.usual-toggle` 才与小程序同语义，
     #    否则拿 350 宽的容器比 126 宽的按钮，dw=223.7 是**假差**（踩过）。
     "pwa": ["#food-sheet", "#food-sheet .sheet", "#food-sheet h3", "#food-sheet .close",
             "#fs-per", "#fs-usual .usual-toggle", ".fs-mode", "#fs-unit-hint",
             "#fs-macros .mkv", "#fs-macros", "#food-sheet .confirm.buy"],
     "mp":  [".sheet-mask", ".sheet-mask .sheet", ".sheet-mask .sheet-h", ".sheet-mask .close",
             ".fs-per", ".usual-toggle", ".fs-mode", ".sheet-mask .form-hint",
             ".sheet-mask .mkv", ".sheet-mask .fs-macros", ".sheet-mask .confirm.buy"]},

    {"key": "exList",
     "pwa_expr": "openExList();",
     "pwa_close": "document.getElementById('ex-list-sheet').classList.remove('show');",
     "mp_open": ("openExList", None), "mp_close": "closeExList",
     "settle": 900,
     "pwa": ["#ex-list-sheet", "#ex-list-sheet .sheet", "#ex-list-sheet h3",
             "#ex-list-sheet .close", "#ex-list", "#ex-list .result-item",
             "#ex-list-sheet .ghost-btn"],
     "mp":  [".sheet-mask", ".sheet-mask .sheet", ".sheet-mask .sheet-h",
             ".sheet-mask .close", ".sheet-mask .results", ".sheet-mask .result-item",
             ".sheet-mask .ghost-btn"]},

    {"key": "customEx",
     "pwa_expr": "openCustomEx();",
     "pwa_close": "document.getElementById('custom-ex-sheet').classList.remove('show');",
     "mp_open": ("openCustomEx", None), "mp_close": "closeCustomEx",
     "settle": 900,
     "pwa": ["#custom-ex-sheet", "#custom-ex-sheet .sheet", "#custom-ex-sheet h3",
             "#custom-ex-sheet .close", "#custom-ex-sheet .field",
             "#custom-ex-sheet .ghost-btn", "#custom-ex-sheet .confirm.sell"],
     "mp":  [".sheet-mask", ".sheet-mask .sheet", ".sheet-mask .sheet-h",
             ".sheet-mask .close", ".sheet-mask .field",
             ".sheet-mask .ghost-btn", ".sheet-mask .confirm.sell"]},

    {"key": "exSheet",
     "pwa_expr": "openExSheet('跑步');",
     "pwa_close": "document.getElementById('ex-sheet').classList.remove('show');",
     "mp_open": ("openExSheet", "跑步"), "mp_close": "closeExSheet",
     "settle": 900,
     "pwa": ["#ex-sheet", "#ex-sheet .sheet", "#ex-sheet h3", "#ex-sheet .close",
             "#es-met", "#ex-sheet .field", "#ex-sheet .intensity-row", "#es-formula",
             "#ex-sheet .confirm.sell"],
     "mp":  [".sheet-mask", ".sheet-mask .sheet", ".sheet-mask .sheet-h", ".sheet-mask .close",
             ".fs-per", ".sheet-mask .field", ".sheet-mask .intensity-row", ".ex-formula",
             ".sheet-mask .confirm.sell"]},

    {"key": "recEdit",
     "pwa_expr": "openRecordEdit('%s', 'food');" % MOCK_DIET_ID,
     "pwa_close": "document.getElementById('rec-edit-sheet').classList.remove('show');",
     "mp_open": ("onEditRec", {"currentTarget": {"dataset": {"id": MOCK_DIET_ID, "type": "food"}}}),
     "mp_close": "closeRecEdit",
     "settle": 900,
     "pwa": ["#rec-edit-sheet", "#rec-edit-sheet .sheet", "#rec-edit-sheet h3",
             "#rec-edit-sheet .close", "#re-sub", "#rec-edit-sheet .field",
             "#rec-edit-sheet .confirm.buy"],
     "mp":  [".sheet-mask", ".sheet-mask .sheet", ".sheet-mask .sheet-h",
             ".sheet-mask .close", ".fs-per", ".sheet-mask .field",
             ".sheet-mask .confirm.buy"]},
]

OUT = []


def p(s=""):
    OUT.append(s)
    print(s)


# ---------------------------------------------------------------- 小程序侧
def node_side(modals):
    """返回 (sysinfo, {key: rects})。会先 arm 端口、再调探针。"""
    if not mp_ws.ensure_port(quiet=True):
        raise SystemExit("自动化端口 9420 未就绪（先跑 promo/_fix_step2_restart_ide.py 排查）")
    spec = [{"key": m["key"], "subs": m["mp"],
             "openMethod": m["mp_open"][0], "openArg": m["mp_open"][1],
             "closeMethod": m["mp_close"], "settle": m.get("settle", 800)}
            for m in modals]
    env = dict(os.environ)
    env["NODE_PATH"] = NM
    env["PATH"] = os.path.dirname(NODE) + ";" + env.get("PATH", "")
    pr = subprocess.run(
        [NODE, os.path.join(HERE, "_rect_mp_trade_modals.js"), json.dumps(spec)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env, timeout=420)
    lines = (pr.stdout or "").splitlines()
    hit = [l for l in lines if l.startswith("MODAL_RECTS_JSON=")]
    if not hit:
        raise SystemExit("小程序侧测量失败：\n" + (pr.stdout or "")[-1200:] + "\n" + (pr.stderr or "")[-1200:])
    data = json.loads(hit[0][len("MODAL_RECTS_JSON="):])
    return data.get("sys") or {}, {d["key"]: d["rects"] for d in data.get("modals") or []}


def seed_mp_set():
    r = mp_ws._node("_seed_mp.js", ["set", MOCK])
    if r.returncode != 0:
        raise SystemExit("灌存档失败：\n" + (r.stdout or "") + (r.stderr or ""))
    return (r.stdout or "").strip().replace("\n", " / ")


def seed_mp_restore():
    r = mp_ws._node("_seed_mp.js", ["restore"])
    return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()


# ---------------------------------------------------------------- PWA 侧
def pwa_side(modals, vw, vh, sab=0):
    seed_json = io.open(MOCK, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = None
        for kw in ({"channel": "msedge"},
                   {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"}):
            try:
                br = pw.chromium.launch(**kw)
                break
            except Exception:                                    # noqa: BLE001
                pass
        if br is None:
            raise SystemExit("无可用浏览器内核")
        pg = br.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=2)
        pg.goto("file:///" + INDEX.replace("\\", "/"))
        pg.wait_for_timeout(900)
        pg.evaluate("(s) => { localStorage.setItem('jianpan_v2', s); }", seed_json)
        pg.reload()
        pg.wait_for_timeout(1600)
        if sab:
            # PWA 的 .sheet 是 padding:20px 20px calc(28px + env(safe-area-inset-bottom))；
            # 浏览器里 env(safe-area-inset-bottom)=0，模拟器（iPhone 12）里=34
            # ⇒ 把两端补成同一个底部内边距，否则 .confirm.* 恒差 sab px（假差）
            pg.add_style_tag(content=".sheet-mask .sheet{padding-bottom:%dpx !important;}" % (28 + sab))
        pg.evaluate("switchTab('trade')")
        pg.wait_for_timeout(1100)
        res = {}
        for m in modals:
            pg.evaluate("(function(){%s})()" % m["pwa_expr"])
            pg.wait_for_timeout(m.get("settle", 800))
            rects = pg.evaluate("""(list) => list.map((s) => {
                const el = document.querySelector(s);
                if (!el) return [s, null, null, null, null];
                const b = el.getBoundingClientRect();
                return [s, +b.left.toFixed(1), +b.top.toFixed(1), +b.width.toFixed(1), +b.height.toFixed(1)];
            })""", m["pwa"])
            res[m["key"]] = rects
            pg.evaluate("(function(){%s})()" % m["pwa_close"])
            pg.wait_for_timeout(220)
        br.close()
        return res


# ---------------------------------------------------------------- 比对
def cmp_modal(m, ap, bp):
    p("  ── 弹层：%s ──" % m["key"])
    p("  %-30s %-26s %-26s %s" % ("选择器(PWA↔MP 对齐)", "PWA (l,t,w,h)", "小程序 (l,t,w,h)", "差 (dl,dt,dw,dh)"))
    bad = []
    miss = []
    for i in range(len(m["pwa"])):
        a = ap[i] if ap and i < len(ap) else None
        b = bp[i] if bp and i < len(bp) else None
        sa = m["pwa"][i]
        sb = m["mp"][i]
        if not a or not b or a[1] is None or b[1] is None:
            miss.append(sa)
            p("  %-30s %s" % (sa + " ↔ " + sb, "缺失/未测"))
            continue
        d = [round(a[k] - b[k], 1) for k in range(1, 5)]
        flag = ""
        if abs(d[0]) >= TH["l"] or abs(d[1]) >= TH["t"] or abs(d[2]) >= TH["w"] or abs(d[3]) >= TH["h"]:
            flag = "   <<< 关注"
            bad.append((sa, d))
        p("  %-30s %-26s %-26s %s%s" % (
            sa + " ↔ " + sb,
            "(%s,%s,%s,%s)" % tuple(a[1:]),
            "(%s,%s,%s,%s)" % tuple(b[1:]),
            "(%s,%s,%s,%s)" % tuple(d), flag))
    p("  超阈值：%d 个 %s" % (len(bad), "" if bad else "✅ 全部在阈值内"))
    for sa, d in bad:
        p("     %-28s dl=%s dt=%s dw=%s dh=%s" % (sa, d[0], d[1], d[2], d[3]))
    if miss:
        p("  未测到：%s" % ", ".join(miss))
    # ⚠️ 返回值带 miss：选择器一旦失效（页面改类名/删元素），测点会静默变成「未测到」，
    #    只数 bad 的话闸会报 0 超阈值 = **假通过**。未测到必须是失败。
    return len(bad), len(miss)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwa-only", action="store_true", help="只量 PWA 侧（不需 IDE）")
    args = ap.parse_args()

    p("=" * 96)
    p("交易页 6 弹层元素级对拍（两端同可视区高，可直接相减）")
    p("=" * 96)

    if args.pwa_only:
        pwa = pwa_side(MODALS, VW, VH_FALLBACK)
        p("PWA 侧：%d 个弹层已量（视口 %dx%d，未对齐小程序 wh）" % (len(pwa), VW, VH_FALLBACK))
        p()
        p("── PWA oracle（小程序侧未量，--pwa-only）──")
        for m in MODALS:
            p("  %s:" % m["key"])
            for r in pwa.get(m["key"], []):
                p("    %-30s (%s,%s,%s,%s)" % (r[0], r[1], r[2], r[3], r[4]))
        io.open(os.path.join(HERE, "_rect_trade_modals_cmp.txt"), "w", encoding="utf-8", newline="").write("\n".join(OUT))
        p()
        p("写出 promo/_rect_trade_modals_cmp.txt（仅 PWA oracle）")
        p("RESULT=OK")
        return

    # 1) 灌同一份存档（含今日记录，供 recEdit 两端打开同一条）
    p("灌存档 → 小程序（_modal_mock.json）：" + seed_mp_set())
    p()
    restored = False
    try:
        # 2) 小程序侧先量（顺便取 windowHeight）
        sysinfo, mp = node_side(MODALS)
        wh = int(sysinfo.get("wh") or 0)
        if not wh:
            raise SystemExit("小程序侧没回 windowHeight，无法对齐 PWA 视口：%r" % sysinfo)
        p("小程序 windowHeight = %d px ⇒ PWA 浏览器视口高用同值（.sheet-mask 是 fixed，只认视口高）" % wh)
        p("小程序侧自证：%s" % json.dumps(sysinfo, ensure_ascii=False))
        sab = int(sysinfo.get("sab") or 0)
        p("小程序底部安全区 = %d px ⇒ PWA 的 .sheet padding-bottom 补到 %d px（28+%d）" % (sab, 28 + sab, sab))
        p("小程序侧：%d 个弹层已量" % len(mp))
        p()

        # 3) PWA 侧（同一份存档、同一可视区高、同一底部安全区）
        pwa = pwa_side(MODALS, VW, wh, sab)
        p("PWA 侧：%d 个弹层已量（视口 %dx%d）" % (len(pwa), VW, wh))
        p()
    finally:
        ok, msg = seed_mp_restore()
        restored = ok
        p("还原小程序存档：" + ("✅ " if ok else "❌ ") + msg.replace("\n", " / "))
        p()

    total_bad = 0
    total_miss = 0
    for m in MODALS:
        nb, nm = cmp_modal(m, pwa.get(m["key"]), mp.get(m["key"]))
        total_bad += nb
        total_miss += nm
        p()
    p("=" * 96)
    p("合计超阈值：%d 个 / 未测到：%d 个（6 弹层 / 每个 %d 个测点）"
      % (total_bad, total_miss, len(MODALS[0]["pwa"])))
    p("存档还原：%s" % ("✅" if restored else "❌ 需手工 restore"))
    ok = (total_bad == 0 and total_miss == 0 and restored)
    p("RESULT=" + ("OK 全过" if ok else
                   "FAIL → 超阈值 %d 个 / 未测到 %d 个 / 还原%s"
                   % (total_bad, total_miss, "OK" if restored else "失败")))
    io.open(os.path.join(HERE, "_rect_trade_modals_cmp.txt"), "w", encoding="utf-8", newline="").write("\n".join(OUT))
    # ⚠️ 必须有非零退出码：mp_gates.py 判的是退出码，光打印 RESULT=FAIL 的话闸永远报 ✅（假保证）。
    #    2026-09-23 发现同族的 mp_rect_{trade,me,market,board,ach_gacha,compare}.py **全都没退出码**。
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
