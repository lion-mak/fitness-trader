# -*- coding: utf-8 -*-
"""
mp_rect_me.py —— 「我的」簇元素级对拍（⑥c）：我的 hub / 健康币 / 操盘手段位 三屏一次跑完。

与 mp_rect_board.py 同机制，差别有六：
  1. 三屏各自一条 route + 一组选择器，浏览器只拉起一次（切屏用 PWA 自己的 showCoins/showLevel）；
  2. **两端先灌同一份存档**（promo/mock.json，经 _seed_mp.js，跑完 restore 还原）——
     空存档下我的页只有 0 和默认头像，量不出「勋章数 / 收集度 / 高段位」这些真正要看的东西；
     ⚠️ 不灌存档时两端状态不同，量出来的差值里混的是「内容不同」而不是「样式不同」；
  3. 选择器一律加 **#page-xxx 作用域**（.backrow/.pagetitle/.card 在 PWA 里被 5 个屏共用，
     裸 querySelector 会取到别的隐藏屏 ⇒ rect 全 0，看着像「PWA 缺失」）；
  4. 支持**两端选择器不同名**的配对（PWA 的 HTML 标签在小程序不存在：
     input↔.inp / select↔.pick / label↔.lab / `.profile-stat > div`↔.ps-cell）；
  5. 每个选择器除 rect 外还取**文本**（两端逐字比对，证明看的是同一份数据）；
     ⚠️ 计算样式探针**这条路封死**：本版工具 `fields({computedStyle})` 会抛
     `An object could not be cloned` 且把会话弄死 ⇒ 定位靠「更细的选择器 rect + 文本」；
  6. 底部留白判据对**三屏都生效**，口径 = 「`.page` 内最后一块**块级内容**的底边 ↔ 页底的空隙」
     （两端都该是 `.page` 的 padding-bottom:80px = 纯呼吸留白）。
     ⛔ 旧口径「max(被测选择器底边)」已废弃：它等于「`.confirm.sell` 之下有多少空」，
        而两端在那之后的**内容本来就不同**（PWA 数据备份卡 / 小程序 数据迁移卡+版本卡）
        ⇒ 报的是内容差异，不是留白差异（2026-09-23 实测：误报 154.2px，且改内容高矮它都不动）。
        ⛔ 也不能直接比 scrollHeight：hub 两端内容不同（小程序多两张卡），必然不等。
     ⚠️ 小程序侧取不到 computedStyle ⇒ 用 `selectAll(块选择器).max(bottom)` 与 `.page` rect
        反推 padding-bottom；`.page 高` 与 `scrollHeight` 相等是这条推断成立的前提（脚本会核）。

排除项（无同源选择器，另由 mp_me_test.js 的运行时断言盯住内容）：
  · `.av-img` / `.av-ph` / `.ic-img`（PWA 是 <img>/<svg>，无 class）；
  · `.coin-card .arr`：PWA 那个 › 是**无 class 的 inline style div**（实测「PWA 缺失」），
    与菜单里的 .arr 不是一回事 ⇒ 不进选择器表；
  · 数据迁移卡（MP 独有功能集：从聊天文件导入 / 导出为文件）与版本卡 —— PWA 侧是「数据备份」卡，
    按钮用 .confirm + inline flex，无同源 class。

用法：<venv>/python.exe promo/mp_rect_me.py   （脚本自己 arm 9420，不用先手工 cli auto）
输出：promo/_rect_me_cmp.txt
"""
import io
import json
import os
import subprocess
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mp_ws                                                     # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
INDEX = os.path.join(ROOT, "index.html")
MOCK = os.path.join(HERE, "mock.json")
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NM = r"C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules"
LAUNCH = ({"channel": "msedge"},
          {"executable_path": r"C:\Users\Administrator\AppData\Local\360ChromeX\Chrome\Application\360ChromeX.exe"})

VW = 430          # 会被小程序实测 scrollWidth 覆盖（两端必须同宽才可比）

# 选择器表：字符串 = 两端同名；dict = 两端不同名（PWA 标签 / 小程序 class 的等价物）
GROUPS = [
    {
        "key": "profile", "title": "我的 hub",
        "route": "/pages/me/me", "tab": True,
        "switch": "switchTab('profile')",
        "sel": [
            ".profile-head", ".av-lg", ".name", ".name .lvl", ".info",
            {"mp": ".uid", "pwa": "#p-id"},
            ".profile-stat", {"mp": ".ps-cell", "pwa": ".profile-stat > div"},
            ".profile-stat .v", ".profile-stat .l",
            ".coin-card", ".coin-card .coin", ".coin-card .n", ".coin-card .l",
            ".card-title", ".card-title .t",
            ".menu-item", ".menu-item .ic", ".menu-item .n", ".menu-item .v",
            ".body-viz", ".body-viz .body-fig", ".viz-stats",
            ".viz-stats .vstat", ".vstat-v", ".vstat-l",
            ".edit-fields", ".ef-title",
            ".field", {"mp": ".field .lab", "pwa": ".field label"},
            {"mp": ".field .inp", "pwa": ".field input"},
            {"mp": ".field .pick", "pwa": ".field select"},
            ".bmr-box", ".bmr-row", ".bmr-cell", ".bmr-v", ".bmr-l", ".bmr-f", ".bmr-tip",
            ".confirm.sell",
        ],
        "probe": [".name .lvl", ".info", ".menu-item .v", ".bmr-tip",
                  {"mp": ".uid", "pwa": "#p-id"}],
        # hub 的 `#page-profile` 最后一个直接子节点是「数据备份」卡 ⇒ 小程序侧用 `.card`
        # 的 selectAll 取最靠下的一张（`.card` 在本页共 4 张，最后一整张 = 版本与更新卡）。
        "tailMp": ".card",
    },
    {
        "key": "coins", "title": "健康币",
        "route": "/pages/coins/coins", "tab": False,
        "switch": "showCoins()",
        "sel": [
            ".backrow", ".backrow .arrow", ".backrow .tt",
            ".pagetitle", ".pagetitle .k", ".pagetitle .t",
            ".coin-hero", ".coin-hero .big", ".coin-hero .sub", ".coin-hero .today",
            ".card", ".card-title", ".card-title .t", ".card-title .m",
            ".rule-list", ".rule", ".rule .n", ".rule .v", ".rule .d",
            ".confirm.buy", ".gap-note",
        ],
        "probe": [".backrow .tt", ".pagetitle .t", ".coin-hero .big", ".coin-hero .today",
                  ".rule .v", ".confirm.buy"],
        # ⚠️ 必须是**顶层块**（.card），不是它内部的最后一个元素（.gap-note）：
        #    `.gap-note` 之后还有卡的 padding-bottom 15px，量它会把那 15px 算成「留白」⇒
        #    假报 95 vs 80（2026-09-23 实测）。PWA 侧取的是 #page-xxx 的直接子节点，
        #    两端口径都是「顶层块的底边 ↔ 页底」，才可比。
        "tailMp": ".card",
    },
    {
        "key": "level", "title": "操盘手段位",
        "route": "/pages/level/level", "tab": False,
        "switch": "showLevel()",
        "sel": [
            ".backrow", ".backrow .arrow", ".backrow .tt",
            ".pagetitle", ".pagetitle .k", ".pagetitle .t",
            ".rank-hero", ".rank-hero .r-name", ".rank-hero .r-lv", ".rank-hero .r-desc",
            ".card", ".card-title", ".card-title .t", ".card-title .m",
            ".xp-bar", ".xp-bar .fill", ".xp-tip",
            ".rank-row", ".rank-row .dot", ".rank-row .rn", ".rank-row .rl", ".rank-row .rd",
            ".gap-note",
        ],
        "probe": [".backrow .tt", ".pagetitle .t", ".rank-hero .r-name", ".rank-hero .r-lv",
                  ".xp-tip", ".card-title .m", ".rank-row .rn", ".rank-row .rl"],
        # 同 coins：必须取顶层块 .card（末尾 `.gap-note` 之后还有卡自身 15px padding-bottom）
        "tailMp": ".card",
    },
]

OUT = []


def p(s=""):
    OUT.append(s)
    print(s)


def pairs_of(g, field):
    """把选择器表规范化成 [(显示名, 小程序选择器, PWA 选择器), ...]"""
    out = []
    for e in g[field]:
        if isinstance(e, str):
            out.append((e, e, e))
        else:
            out.append(("%s ←→ %s" % (e["mp"], e["pwa"]), e["mp"], e["pwa"]))
    return out


def run_node(script, args, timeout=600):
    env = dict(os.environ)
    env["NODE_PATH"] = NM
    env["PATH"] = os.path.dirname(NODE) + ";" + env.get("PATH", "")
    return subprocess.run([NODE, os.path.join(HERE, script)] + args,
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=timeout)


def node_groups(spec):
    pr = run_node("_rect_mp_groups.js", [json.dumps(spec)])
    got, sysinfo = {}, {}
    for l in (pr.stdout or "").splitlines():
        if l.startswith("GROUP="):
            o = json.loads(l[len("GROUP="):])
            got[o["key"]] = o
        elif l.startswith("SYS="):
            sysinfo = json.loads(l[len("SYS="):])
    if len(got) != len(spec):
        return None, None, (pr.stdout or "")[-1200:] + "\n" + (pr.stderr or "")[-1200:]
    return got, sysinfo, None


PWA_PROBE_JS = """([list, scope]) => {
    const pick = (s) => {
        let el = null;
        if (scope) { try { el = document.querySelector(scope + s); } catch (e) { el = null; } }
        if (!el) { try { el = document.querySelector(s); } catch (e) { el = null; } }
        return el;
    };
    const rects = {}, texts = {};
    list.forEach((s) => {
        const el = pick(s);
        if (!el) { rects[s] = null; texts[s] = null; return; }
        const b = el.getBoundingClientRect();
        rects[s] = [+b.left.toFixed(1), +b.top.toFixed(1), +b.width.toFixed(1), +b.height.toFixed(1)];
        texts[s] = (el.innerText !== undefined ? el.innerText : el.textContent)
                     .replace(/\\s+/g, ' ').trim().slice(0, 80);
    });
    return {rects: rects, texts: texts};
}"""

PWA_META_JS = """([scope, padSel]) => {
    const sc = document.querySelector('#screen');
    const tb = document.querySelector('.tabbar');
    const pd = document.querySelector(padSel);
    /* 「.page 内最后一块内容的底边」—— 直接取 #page-xxx 的**最后一个子节点**的底边。
       为什么不用「max(被测选择器底边)」：那量的是「.confirm.sell 之下有多少空」，
       而两端在 .confirm.sell 之后的**内容本来就不同**
       （PWA 是数据备份卡；小程序是数据迁移卡 + 版本与更新卡）
       ⇒ 那个口径量到的是「内容差异」，不是「底部留白差异」。 */
    const kids = pd ? [...pd.children] : [];
    let lastKidBottom = null;
    kids.forEach((el) => {
      const b = el.getBoundingClientRect().bottom;
      if (lastKidBottom === null || b > lastKidBottom) lastKidBottom = b;
    });
    const pr = pd ? pd.getBoundingClientRect() : null;
    return {scrollHeight: sc.scrollHeight, clientHeight: sc.clientHeight,
            tabH: +tb.getBoundingClientRect().height.toFixed(1),
            pagePadTop: pd ? (parseFloat(getComputedStyle(pd).paddingTop) || 0) : 0,
            pagePadBottom: pd ? (parseFloat(getComputedStyle(pd).paddingBottom) || 0) : 0,
            pageHeight: pr ? +pr.height.toFixed(1) : null,
            pageBottom: pr ? +pr.bottom.toFixed(1) : null,
            lastKidBottom: lastKidBottom === null ? null : +lastKidBottom.toFixed(1),
            kidN: kids.length};
}"""


def main():
    p("=" * 104)
    p("「我的」簇元素级对拍（我的 hub / 健康币 / 操盘手段位）—— 两端同为 CSS px，可直接相减")
    p("=" * 104)

    if not mp_ws.ensure_port():
        raise SystemExit("自动化端口 9420 未就绪（先看 promo/_fix_step2_restart_ide.py 的结论）")

    # 1) 两端灌同一份存档
    seeded = False
    r = run_node("_seed_mp.js", ["set", MOCK])
    if r.returncode != 0:
        raise SystemExit("灌存档失败：\n" + (r.stdout or "") + (r.stderr or ""))
    p("小程序侧灌存档：" + (r.stdout or "").strip().replace("\n", " / "))
    seeded = True
    seed_json = json.dumps(json.load(io.open(MOCK, encoding="utf-8"))["state"], ensure_ascii=False)

    any_bad = 0
    try:
        # 2) 小程序侧三屏（必须同一会话量完：9420 会在每次会话结束时被 IDE 关掉）
        spec = []
        for g in GROUPS:
            mp_sels = []
            for _, a, _b in pairs_of(g, "sel"):
                if a not in mp_sels:
                    mp_sels.append(a)
            mp_probe = []
            for _, a, _b in pairs_of(g, "probe"):
                if a not in mp_probe:
                    mp_probe.append(a)
            spec.append({"key": g["key"], "route": g["route"], "tab": g["tab"],
                         "sel": mp_sels, "probe": mp_probe,
                         "tailMp": g.get("tailMp")})

        got, sysinfo, err = node_groups(spec)
        if got is None:
            p("⚠️ 第一轮测量失败，重新 arm 端口后重试：\n" + err[:500])
            if not mp_ws.ensure_port():
                raise SystemExit("重试前 arm 失败")
            got, sysinfo, err = node_groups(spec)
        if got is None:
            raise SystemExit("小程序侧测量失败：\n" + err)

        sbh = int(sysinfo.get("sbh") or 0)
        wh = int(sysinfo.get("wh") or 0)
        vw = VW
        for g in GROUPS:
            try:
                vw = int(got[g["key"]]["vp"].get("scrollWidth") or vw)
            except Exception:      # noqa: BLE001
                pass
        p("对齐宽度：PWA 视口宽 = %d（取自小程序 scrollWidth）" % vw)
        p("状态栏 %d px（注到两端同一侧：小程序写在 .page 上 ⇒ PWA 也注 #page-xxx）" % sbh)
        p("小程序 windowHeight = %d px ⇒ PWA 的 #screen 高度同值，两端可视区一致" % wh)
        p()

        # 3) PWA 侧
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
            pg = br.new_page(viewport={"width": vw, "height": 930}, device_scale_factor=2)
            pg.goto("file:///" + INDEX.replace("\\", "/"))
            pg.wait_for_timeout(900)
            pg.evaluate("(s) => { localStorage.setItem('jianpan_v2', s); }", seed_json)
            pg.reload()
            pg.wait_for_timeout(1600)
            pg.evaluate("(h) => { const s = document.querySelector('#screen');"
                        " s.style.flex = 'none'; s.style.height = h + 'px'; }", wh)
            pg.wait_for_timeout(300)

            for g in GROUPS:
                scope = "#page-%s " % g["key"]
                pad_sel = "#page-%s" % g["key"]
                pg.evaluate("() => { " + g["switch"] + "; }")
                pg.wait_for_timeout(700)
                # 安全区注在 #page-xxx（滚动内容之内），与小程序把 padding-top 写在 .page 上同侧。
                # ⚠️ 注到 .app 会连 tabBar/screen 一起推下去，造成假偏移（行情页对拍已定论）。
                pg.evaluate("(v) => { const e = document.querySelector('%s');"
                            " if (e) e.style.paddingTop = v + 'px'; }" % pad_sel, sbh)
                pg.evaluate("() => { const s = document.querySelector('#screen'); if (s) s.scrollTop = 0; }")
                pg.wait_for_timeout(350)

                pwa_sels, _ = [], None
                for _, _a, b in pairs_of(g, "sel"):
                    if b not in pwa_sels:
                        pwa_sels.append(b)
                pwa_probe = []
                for _, _a, b in pairs_of(g, "probe"):
                    if b not in pwa_probe:
                        pwa_probe.append(b)
                res = pg.evaluate(PWA_PROBE_JS, [pwa_sels + [x for x in pwa_probe if x not in pwa_sels], scope])
                pmeta = pg.evaluate(PWA_META_JS, [scope, pad_sel])

                mp = got[g["key"]]
                p("-" * 104)
                p("【%s】%s  ←→ %s" % (g["title"], g["route"], g["switch"]))

                # 同源核对：两端文本必须逐字相同，否则 rect 差里混的是「内容不同」
                diff_txt = []
                for lab, a_s, b_s in pairs_of(g, "probe"):
                    a = (mp["text"] or {}).get(a_s)
                    b = (res["texts"] or {}).get(b_s)
                    if a != b:
                        diff_txt.append((lab, a, b))
                if diff_txt:
                    p("  ⚠️ 两端文本不一致（差值里有「内容不同」的成分，先看这里再看 rect）：")
                    for lab, a, b in diff_txt:
                        p("     %-26s 小程序=%-40s PWA=%s" % (lab, str(a)[:40], str(b)[:44]))
                else:
                    p("  ✅ 两端同源：%d 个探针的文本逐字相同" % len(g["probe"]))
                p("  小程序 scrollHeight=%s | PWA #screen scrollHeight=%s / clientHeight=%s / tabBar=%s"
                  % (mp["vp"].get("scrollHeight"), pmeta["scrollHeight"],
                     pmeta["clientHeight"], pmeta["tabH"]))
                p()

                p("%-28s %-24s %-24s %s" % ("选择器", "小程序 (l,t,w,h)", "PWA (l,t,w,h)", "差 (dl,dt,dw,dh)"))
                p("-" * 104)
                bad, miss = [], []
                for lab, a_s, b_s in pairs_of(g, "sel"):
                    a, b = (mp["rect"] or {}).get(a_s), (res["rects"] or {}).get(b_s)
                    if (a is None) and (b is None):
                        miss.append(lab)
                        p("%-28s %s" % (lab, "两侧都不存在"))
                        continue
                    if a is None:
                        miss.append(lab)
                        p("%-28s %-24s %s" % (lab, "小程序缺失", "PWA 有"))
                        continue
                    if b is None:
                        miss.append(lab)
                        p("%-28s %-24s %s" % (lab, "有", "PWA 缺失"))
                        continue
                    dd = [round(a[i] - b[i], 1) for i in range(4)]
                    flag = ""
                    if abs(dd[1]) >= 2 or abs(dd[2]) >= 4 or abs(dd[3]) >= 2:
                        flag = "   <<< 关注"
                        bad.append((lab, dd))
                    p("%-28s %-24s %-24s %s%s" % (
                        lab, "(%s,%s,%s,%s)" % tuple(a), "(%s,%s,%s,%s)" % tuple(b),
                        "(%s,%s,%s,%s)" % tuple(dd), flag))

                p()
                p("  差异超阈值：%d 个 %s" % (len(bad), "" if not bad else "❌"))
                for lab, dd in bad:
                    p("     %-28s dl=%s dt=%s dw=%s dh=%s" % (lab, dd[0], dd[1], dd[2], dd[3]))
                if miss:
                    p("  未测到：%s" % ", ".join(miss))
                any_bad += len(bad)

                # 底部留白：`.page` 内最后一块**块级内容**的底边 ↔ 页底之间有多少空。
                # 两端都该等于 `.page` 的 padding-bottom（80px，纯呼吸留白）。
                # ⛔ 旧口径（max(被测元素底边)）已废弃，理由见 _rect_mp_groups.js 的注释：
                #    它量的是「.confirm.sell 之下有多少空」，而两端在那之后的**内容不同**
                #    （PWA 数据备份卡 / 小程序 数据迁移卡+版本卡）⇒ 报的是内容差异不是留白差异。
                # ⛔ 也不要用 scrollHeight 直接比：hub 两端内容本来就不同（小程序多两张卡）。
                p()
                tl = mp.get("tail") or {}
                if tl.get("pageBottom") is None or pmeta.get("lastKidBottom") is None:
                    p("  底部留白自检：N/A —— 缺测量数据（小程序 .page rect=%s / PWA 末子节点=%s）"
                      % (tl.get("pageBottom"), pmeta.get("lastKidBottom")))
                else:
                    mp_tail = tl["pageBottom"] - tl["maxBottom"]
                    pwa_tail = pmeta["pageBottom"] - pmeta["lastKidBottom"]
                    d = mp_tail - pwa_tail
                    p("  底部留白（.page 最后一块块级内容底边 ↔ 页底）：小程序 %.1f px / PWA %.1f px"
                      " ⇒ 差 %.1f px %s" % (mp_tail, pwa_tail, d,
                                            "✅" if abs(d) < 2 else "❌"))
                    p("     · PWA 真值：padding-bottom=%s px；#page-%s 的 %d 个直接子节点里"
                      " 最后一个的底边=%s（页高 %.1f）"
                      % (pmeta["pagePadBottom"], g["key"], pmeta["kidN"],
                         pmeta["lastKidBottom"], pmeta["pageHeight"]))
                    p("     · 小程序侧：selectAll('%s') 命中 %d 块，最靠下底边=%s；"
                      ".page 高 %.1f / scrollHeight %s（两者应相等）%s"
                      % (tl["sel"], tl["n"], tl["maxBottom"], tl["pageHeight"],
                         tl["scrollHeight"],
                         "" if abs((tl["pageHeight"] or 0) - (tl["scrollHeight"] or 0)) < 2
                         else "  ⚠️ 不等，.page 未必铺满视口"))
                    if abs(d) >= 2:
                        any_bad += 1
                p()

            br.close()

    finally:
        if seeded:
            r = run_node("_seed_mp.js", ["restore"], timeout=180)
            p("小程序侧还原存档：" + (r.stdout or "").strip().replace("\n", " / "))

    p("=" * 104)
    p("三屏合计差异超阈值：%d 个 %s" % (any_bad, "✅ 全部通过" if any_bad == 0 else "❌ 见上"))
    io.open(os.path.join(HERE, "_rect_me_cmp.txt"), "w", encoding="utf-8").write("\n".join(OUT))
    p("写出 promo/_rect_me_cmp.txt")
    p("RESULT=%s" % ("OK" if any_bad == 0 else "FAIL"))
    # ⚠️ 原来 main() 返回 None ⇒ 退出码恒为 0 ⇒ mp_gates.py 判退出码 ⇒ 这道闸永远 ✅（假保证）。
    #    2026-09-23 审计整族 rect 闸时统一补上（trade/board/compare 是硬编码 OK、market 打 "CHECK"）。
    return 0 if any_bad == 0 else 1


sys.exit(main())
